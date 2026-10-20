"""
Analysis service for the plot analysis API (docs/ANALYSIS-API-SPEC.md):
validate-geometry, deforestation, protected-area, rainfall and ghg-emission.

Every public function takes the input GeoJSON features and returns one
properties dict per feature, in input order. Earth Engine work is batched with
reduceRegions over chunks of plots (instead of one getInfo() per plot) so a
batch of 1000 plots fits in the frontend's 110 s budget. Earth Engine errors
are raised, never replaced with zeros, so the API can answer non-2xx.
"""

import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from functools import partial
from typing import Any, Callable, Dict, List, Optional

import ee
from loguru import logger
from pyproj import Geod
from shapely.geometry import Polygon, shape
from shapely.validation import explain_validity

from services.data.multilayer_service import MultilayerService
from services.ee_auth import initialize_ee

EE_KEY_FILE = os.path.join("authentication", "eudr-0.json")

# Chunk limits keep each Earth Engine request well below its payload limit.
MAX_CHUNK_FEATURES = 100
MAX_CHUNK_VERTICES = 50_000
ZERO_AREA_SQM = 1.0

LOSS_PREFIXES = ("gfw_loss", "jrc_loss", "sbtn_loss")
LOSS_YEARS = (2021, 2022, 2023, 2024)
LOSS_DATASET_NAMES = {
    "gfw_loss": "GFW Forest Loss",
    "jrc_loss": "JRC Forest Loss",
    "sbtn_loss": "SBTN Natural Lands Loss",
}

WDPA_ASSET = "WCMC/WDPA/current/polygons"
STRICT_IUCN_CATEGORIES = {"Ia", "Ib", "II", "III", "IV"}

CHIRPS_ASSET = "UCSB-CHG/CHIRPS/PENTAD"
RAINFALL_STATS = ("mean", "min", "max", "stdDev")

# GHG parameters (moved unchanged from the previous ghg-emission endpoint)
FOREST_BIOMASS = {"Primary Forest": 520.0, "Secondary Forest": 280.0}  # tCO2e/ha
BURNING_PARAMS = {"b": 0.5, "comfi": 0.5, "g_n2o": 0.007, "g_ch4": 0.0048, "gwp_n2o": 298, "gwp_ch4": 25}
POST_LAND_USE_CARBON = {"agb": 47.0, "bgb": 10.0}  # tC/ha
SOC_EMISSION_CONSTANT = 26.0  # tCO2e/ha

_GEOD = Geod(ellps="WGS84")
_EE_POOL = ThreadPoolExecutor(
    max_workers=int(os.getenv("ANALYSIS_EE_WORKERS", "8")), thread_name_prefix="analysis-ee"
)
_ee_lock = threading.Lock()
_ee_ready = False


class EarthEngineUnavailable(RuntimeError):
    """Earth Engine could not be initialized with any credentials."""


def ensure_ee() -> None:
    """
    Initialize Earth Engine once per process with the authentication/eudr-0.json
    service account (else default credentials), under GOOGLE_CLOUD_PROJECT_ID or,
    when unset, the key's own project. Earth Engine needs a registered Cloud project.
    """
    global _ee_ready
    if _ee_ready:
        return
    with _ee_lock:
        if _ee_ready:
            return
        try:
            credentials = ee.ServiceAccountCredentials(None, EE_KEY_FILE)
            initialize_ee(credentials, project=credentials.project_id)
        except Exception as auth_error:
            logger.warning(f"Failed to authenticate with {EE_KEY_FILE}: {auth_error}; trying default credentials")
            try:
                ee.Initialize(project=os.getenv("GOOGLE_CLOUD_PROJECT_ID") or None)
            except Exception as e:
                raise EarthEngineUnavailable(str(e)) from e
        _ee_ready = True


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _polygons(geometry: Dict[str, Any]) -> List[list]:
    """Rings of each polygon in a Polygon/MultiPolygon geometry."""
    coordinates = geometry["coordinates"]
    return [coordinates] if geometry["type"] == "Polygon" else coordinates


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _ring_problem(ring: Any) -> Optional[str]:
    if not isinstance(ring, list) or len(ring) < 4:
        return "Ring has fewer than 4 positions"
    for position in ring:
        if not isinstance(position, (list, tuple)) or len(position) < 2 \
                or not (_is_number(position[0]) and _is_number(position[1])):
            return "Ring contains a malformed position"
        if not (-180 <= position[0] <= 180 and -90 <= position[1] <= 90):
            return "Ring has coordinates outside the longitude/latitude range"
    if list(ring[0][:2]) != list(ring[-1][:2]):
        return "Ring is not closed"
    return None


def geometry_problem(geometry: Any) -> Optional[str]:
    """Why `geometry` is not a well-formed Polygon/MultiPolygon, or None if it is."""
    if not isinstance(geometry, dict) or geometry.get("type") not in ("Polygon", "MultiPolygon"):
        return "Geometry is missing or not a Polygon/MultiPolygon"
    if not isinstance(geometry.get("coordinates"), list) or not geometry["coordinates"]:
        return "Geometry has no coordinates"
    for rings in _polygons(geometry):
        if not isinstance(rings, list) or not rings:
            return "Polygon has no rings"
        for ring in rings:
            problem = _ring_problem(ring)
            if problem:
                return problem
    return None


def geodesic_area_m2(geometry: Dict[str, Any]) -> float:
    """Geodesic (WGS84) area in m² of a well-formed Polygon/MultiPolygon, holes subtracted."""
    total = 0.0
    for rings in _polygons(geometry):
        for i, ring in enumerate(rings):
            area, _ = _GEOD.polygon_area_perimeter([p[0] for p in ring], [p[1] for p in ring])
            total += abs(area) if i == 0 else -abs(area)
    return max(total, 0.0)


def _vertex_count(geometry: Dict[str, Any]) -> int:
    return sum(len(ring) for rings in _polygons(geometry) for ring in rings)


def _has_duplicate_vertices(ring: list) -> bool:
    points = [tuple(p[:2]) for p in ring[:-1]]  # ring is closed; skip the closing point
    return len(points) != len(set(points))


# ---------------------------------------------------------------------------
# validate-geometry (local, no Earth Engine)
# ---------------------------------------------------------------------------

def validate_geometry(feature: Dict[str, Any]) -> Dict[str, Any]:
    """
    Quality flags for one feature. Never raises: broken input is reported through
    the flags. `not_ring` also covers rings that are structurally unusable
    (malformed or out-of-range positions), since those can't be analyzed either.
    """
    issues: List[str] = []
    zero_area = self_intersection = duplicate_vertices = False
    area_sqm = 0.0

    problem = geometry_problem(feature.get("geometry"))
    if problem:
        issues.append(problem)
    else:
        geometry = feature["geometry"]
        try:
            for rings in _polygons(geometry):
                duplicate_vertices = duplicate_vertices or any(_has_duplicate_vertices(r) for r in rings)
                polygon = Polygon(rings[0], rings[1:])
                # Degenerate in GeoJSON's planar lon/lat sense (geodesic edges can still enclose area)
                zero_area = zero_area or polygon.area == 0
                validity = explain_validity(polygon)
                if "self-intersection" in validity.lower():
                    self_intersection = True
                elif validity != "Valid Geometry":
                    issues.append(f"Invalid geometry: {validity}")
            area_sqm = geodesic_area_m2(geometry)
            zero_area = zero_area or area_sqm < ZERO_AREA_SQM
        except Exception as e:
            logger.warning(f"Geometry validation error: {e}")
            problem = f"Validation error: {e}"
            issues.append(problem)

        if self_intersection:
            issues.append("Self-intersection detected")
        if duplicate_vertices:
            issues.append("Duplicate vertices found")
        if zero_area:
            issues.append("Zero or near-zero area")

    return {
        "area_sqm": round(area_sqm, 2),
        "zero_area": zero_area,
        "self_intersection": self_intersection,
        "not_ring": problem is not None,
        "duplicate_vertices": duplicate_vertices,
        "is_valid": not issues,
        "validation_status": "valid" if not issues else "invalid",
        "issues": issues,
    }


def validate_geometries(features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [validate_geometry(feature) for feature in features]


# ---------------------------------------------------------------------------
# Earth Engine batching
# ---------------------------------------------------------------------------

def _chunks(features: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    chunks: List[List[Dict[str, Any]]] = [[]]
    vertices = 0
    for feature in features:
        count = _vertex_count(feature["geometry"])
        if chunks[-1] and (len(chunks[-1]) >= MAX_CHUNK_FEATURES or vertices + count > MAX_CHUNK_VERTICES):
            chunks.append([])
            vertices = 0
        chunks[-1].append(feature)
        vertices += count
    return chunks


def _run_batched(features: List[Dict[str, Any]],
                 reduce_chunk: Callable[[List[Dict[str, Any]]], List[Any]]) -> List[Any]:
    """Run `reduce_chunk` over chunks of features in parallel; results come back in input order."""
    ensure_ee()
    results: List[Any] = []
    for chunk_results in _EE_POOL.map(reduce_chunk, _chunks(features)):
        results.extend(chunk_results)
    return results


def _ee_geometry(geometry: Dict[str, Any]) -> ee.Geometry:
    """ee.Geometry from GeoJSON, dropping altitude (Earth Engine only accepts 2D positions)."""
    polygons = [[[[p[0], p[1]] for p in ring] for ring in rings] for rings in _polygons(geometry)]
    coordinates = polygons[0] if geometry["type"] == "Polygon" else polygons
    return ee.Geometry({"type": geometry["type"], "coordinates": coordinates})


def _to_ee_collection(features: List[Dict[str, Any]]) -> ee.FeatureCollection:
    return ee.FeatureCollection([
        ee.Feature(_ee_geometry(feature["geometry"]), {"idx": i}) for i, feature in enumerate(features)
    ])


def _rows_by_index(collection_info: Dict[str, Any], count: int) -> List[Dict[str, Any]]:
    """Properties of an Earth Engine result collection, ordered by the `idx` set in _to_ee_collection."""
    rows: List[Optional[Dict[str, Any]]] = [None] * count
    for feature in collection_info["features"]:
        rows[int(feature["properties"]["idx"])] = feature["properties"]
    if any(row is None for row in rows):
        raise ee.EEException("Earth Engine returned fewer features than were sent")
    return rows


def _bounds(features: List[Dict[str, Any]], margin: float = 0.01) -> ee.Geometry:
    lons = [p[0] for f in features for rings in _polygons(f["geometry"]) for ring in rings for p in ring]
    lats = [p[1] for f in features for rings in _polygons(f["geometry"]) for ring in rings for p in ring]
    return ee.Geometry.Rectangle([min(lons) - margin, min(lats) - margin,
                                  max(lons) + margin, max(lats) + margin])


# ---------------------------------------------------------------------------
# deforestation
# ---------------------------------------------------------------------------

def _loss_bands() -> List[str]:
    return [f"{p}_combined" for p in LOSS_PREFIXES] + [f"{p}_{y}" for p in LOSS_PREFIXES for y in LOSS_YEARS]


def _loss_area_chunk(features: List[Dict[str, Any]]) -> List[Dict[str, float]]:
    """Loss area in hectares per band (combined and per year) for each feature."""
    bands = _loss_bands()
    # Loss masks (0/1) from MultilayerService, weighted by true pixel area -> m² when summed
    loss_area = MultilayerService.get_ee_datasets().select(bands).unmask(0).multiply(ee.Image.pixelArea())
    info = loss_area.reduceRegions(
        collection=_to_ee_collection(features), reducer=ee.Reducer.sum(), scale=30
    ).select([".*"], None, False).getInfo()
    return [{band: (row.get(band) or 0.0) / 10_000 for band in bands}
            for row in _rows_by_index(info, len(features))]


def _loss_stats(prefix: str, loss_ha: Dict[str, float], plot_ha: float) -> Dict[str, Any]:
    area = loss_ha[f"{prefix}_combined"]
    by_year = {year: loss_ha[f"{prefix}_{year}"] for year in LOSS_YEARS}
    worst_year = max(by_year, key=by_year.get)
    return {
        f"{prefix}_stat": "high" if area > 0 else "low",
        f"{prefix}_area": area,
        f"{prefix}_percent": min(area / plot_ha * 100, 100.0) if plot_ha > 0 else 0.0,
        f"{prefix}_year_compilation": worst_year if area > 0 and by_year[worst_year] > 0 else None,
        "dataset": f"{prefix.upper()} Loss Detection (2021-2024)",
    }


def deforestation(features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """GFW/JRC/SBTN forest loss (2021-2024, after the EUDR cutoff) per plot; any loss -> high risk."""
    results = []
    for feature, loss_ha in zip(features, _run_batched(features, _loss_area_chunk)):
        plot_ha = geodesic_area_m2(feature["geometry"]) / 10_000
        result: Dict[str, Any] = {"total_area_hectares": plot_ha}
        for prefix in LOSS_PREFIXES:
            result[prefix] = _loss_stats(prefix, loss_ha, plot_ha)
        high_risk = [LOSS_DATASET_NAMES[p] for p in LOSS_PREFIXES if result[p][f"{p}_stat"] == "high"]
        result["overall_compliance"] = {
            "overall_risk": "high" if high_risk else "low",
            "compliance_status": "NON_COMPLIANT" if high_risk else "COMPLIANT",
            "high_risk_datasets": high_risk,
            "total_high_risk_indicators": len(high_risk),
        }
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# protected-area (WDPA)
# ---------------------------------------------------------------------------

def _wdpa_chunk(features: List[Dict[str, Any]]) -> List[List[str]]:
    """Distinct IUCN categories of the WDPA areas intersecting each feature."""
    wdpa = ee.FeatureCollection(WDPA_ASSET).filterBounds(_bounds(features))
    info = _to_ee_collection(features).map(lambda plot: ee.Feature(None, {
        "idx": plot.get("idx"),
        "categories": wdpa.filterBounds(plot.geometry()).aggregate_array("IUCN_CAT").distinct(),
    })).getInfo()
    return [row.get("categories") or [] for row in _rows_by_index(info, len(features))]


def _wdpa_status(categories: List[str]) -> str:
    if not categories:
        return "compliant"
    if any(category in STRICT_IUCN_CATEGORIES for category in categories):
        return "non_compliant"
    return "indicative"


def protected_area(features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """WDPA overlap per plot: strict IUCN (Ia-IV) -> non_compliant, other overlap -> indicative."""
    return [{"wdpa_status": _wdpa_status(categories), "wdpa_categories": categories}
            for categories in _run_batched(features, _wdpa_chunk)]


# ---------------------------------------------------------------------------
# rainfall (CHIRPS)
# ---------------------------------------------------------------------------

def rainfall_year(today: Optional[date] = None) -> int:
    """Latest calendar year with complete CHIRPS data, allowing ~2 months of publication lag."""
    today = today or date.today()
    return today.year - 1 if today.month >= 3 else today.year - 2


def _rainfall_stat(row: Dict[str, Any], name: str) -> Optional[float]:
    # Single-band reduceRegions names outputs "mean"/...; accept band-prefixed names too
    value = row.get(name, row.get(f"precipitation_{name}"))
    return None if value is None else float(value)


def _rainfall_chunk(features: List[Dict[str, Any]], year: int) -> List[Dict[str, Optional[float]]]:
    """Annual rainfall statistics (mm) for each feature."""
    annual = (ee.ImageCollection(CHIRPS_ASSET)
              .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
              .select("precipitation")
              .map(lambda image: image.resample("bilinear"))
              .sum())
    reducer = (ee.Reducer.mean()
               .combine(reducer2=ee.Reducer.minMax(), sharedInputs=True)
               .combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True))

    def reduce(collection: ee.FeatureCollection) -> Dict[str, Any]:
        return annual.reduceRegions(collection=collection, reducer=reducer, scale=30) \
            .select([".*"], None, False).getInfo()

    rows = _rows_by_index(reduce(_to_ee_collection(features)), len(features))

    # Plots smaller than a pixel can come back empty; sample a point inside them instead
    missing = [i for i, row in enumerate(rows) if _rainfall_stat(row, "mean") is None]
    if missing:
        inside = {i: shape(features[i]["geometry"]).representative_point() for i in missing}
        points = ee.FeatureCollection([
            ee.Feature(ee.Geometry.Point([point.x, point.y]), {"idx": i}) for i, point in inside.items()
        ])
        for feature in reduce(points)["features"]:
            rows[int(feature["properties"]["idx"])] = feature["properties"]

    return [{name: _rainfall_stat(row, name) for name in RAINFALL_STATS} for row in rows]


def rainfall(features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Annual CHIRPS rainfall per plot for the latest complete year (null outside CHIRPS' 50°S-50°N)."""
    year = rainfall_year()

    def mm(value: Optional[float]) -> Optional[float]:
        return None if value is None else round(value, 2)

    results = []
    for feature, stats in zip(features, _run_batched(features, partial(_rainfall_chunk, year=year))):
        results.append({
            "rainfall_mean_mm": mm(stats["mean"]),
            "rainfall_min_mm": mm(stats["min"]),
            "rainfall_max_mm": mm(stats["max"]),
            "rainfall_std_mm": mm(stats["stdDev"]),
            "area_hectares": round(geodesic_area_m2(feature["geometry"]) / 10_000, 4),
            "analysis_period": {"start_date": f"{year}-01-01", "end_date": f"{year}-12-31"},
            "data_source": "CHIRPS Pentad (annual total, bilinear-resampled)",
        })
    return results


# ---------------------------------------------------------------------------
# ghg-emission
# ---------------------------------------------------------------------------

def ghg_for_area(area_ha: float, forest_type: str) -> Dict[str, Any]:
    """GHG emission (tCO2e) for a deforested area; formula unchanged from the previous endpoint."""
    forest_biomass = FOREST_BIOMASS.get(forest_type, FOREST_BIOMASS["Secondary Forest"])
    burned = area_ha * BURNING_PARAMS["b"] * BURNING_PARAMS["comfi"]
    gross_co2 = area_ha * forest_biomass
    gross_n2o = burned * BURNING_PARAMS["g_n2o"] * 0.001 * BURNING_PARAMS["gwp_n2o"]
    gross_ch4 = burned * BURNING_PARAMS["g_ch4"] * 0.001 * BURNING_PARAMS["gwp_ch4"]
    total_gross_emission = gross_co2 + gross_n2o + gross_ch4
    soc_emission = SOC_EMISSION_CONSTANT * area_ha
    gross_emission_with_soc = total_gross_emission + soc_emission
    post_carbon_stock = area_ha * (POST_LAND_USE_CARBON["agb"] + POST_LAND_USE_CARBON["bgb"])
    net_emission = gross_emission_with_soc - post_carbon_stock
    return {
        "area_hectares": round(area_ha, 4),
        "forest_type": forest_type,
        "gross_co2_tco2e": round(gross_co2, 4),
        "gross_n2o_tco2e": round(gross_n2o, 4),
        "gross_ch4_tco2e": round(gross_ch4, 4),
        "total_gross_emission_tco2e": round(total_gross_emission, 4),
        "soc_emission_tco2e": round(soc_emission, 4),
        "gross_emission_with_soc_tco2e": round(gross_emission_with_soc, 4),
        "post_carbon_stock_tc": round(post_carbon_stock, 4),
        "net_emission_tco2e": round(net_emission, 4),
        "emission_intensity_tco2e_per_ha": round(net_emission / area_ha, 4) if area_ha else 0,
    }


def ghg_emission(features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    GHG emission of each dataset's forest loss. The datasets overlap, so the total
    is the largest of the three (as the frontend assumes), not their sum.
    """
    results = []
    for feature, loss in zip(features, deforestation(features)):
        forest_type = (feature.get("properties") or {}).get("forest_type")
        if forest_type not in FOREST_BIOMASS:
            forest_type = "Secondary Forest"
        emissions = {
            f"{prefix.split('_')[0]}_ghg_emission": ghg_for_area(loss[prefix][f"{prefix}_area"], forest_type)
            for prefix in LOSS_PREFIXES
        }
        results.append({
            **emissions,
            "total_net_emission_tco2e": max(e["net_emission_tco2e"] for e in emissions.values()),
            "forest_type": forest_type,
        })
    return results
