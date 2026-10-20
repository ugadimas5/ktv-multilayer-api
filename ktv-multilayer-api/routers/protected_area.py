"""
Plot Analysis Router
Tag: sustainit

Implements the contract in docs/ANALYSIS-API-SPEC.md:
POST /api/v1/{validate-geometry, deforestation, protected-area, rainfall, ghg-emission}
with a multipart `file` field holding a GeoJSON FeatureCollection of plots.

Every endpoint answers {"data": FeatureCollection} with exactly one feature per
input feature, in input order, carrying the input properties (plot_id, name)
plus the analysis fields. Any failure is a non-2xx status, never default values.
"""
import json
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Tuple

import ee
from fastapi import APIRouter, File, HTTPException, UploadFile
from loguru import logger
from starlette.concurrency import run_in_threadpool

from services import analysis_service as analysis

router = APIRouter(
    prefix="/api/v1",
    tags=["sustainit"],
    responses={404: {"description": "Not found"}},
)

MAX_UPLOAD_MB = 100
MAX_FEATURES = 1000


async def _read_features(file: UploadFile, require_polygons: bool) -> Tuple[List[Dict[str, Any]], float]:
    """Parse the uploaded GeoJSON into its features; 400/413/422 on bad input."""
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        raise HTTPException(status_code=413, detail=f"File too large: {size_mb:.1f}MB. Max: {MAX_UPLOAD_MB}MB")

    try:
        geojson_data = json.loads(contents.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    if not isinstance(geojson_data, dict) or geojson_data.get("type") not in ("FeatureCollection", "Feature"):
        raise HTTPException(status_code=400, detail="Invalid GeoJSON: expected a FeatureCollection or Feature")
    features = geojson_data.get("features") if geojson_data["type"] == "FeatureCollection" else [geojson_data]
    if not isinstance(features, list) or not all(isinstance(f, dict) for f in features):
        raise HTTPException(status_code=400, detail="Invalid GeoJSON: features must be a list of Feature objects")
    if not features:
        raise HTTPException(status_code=400, detail="GeoJSON contains no features")
    if len(features) > MAX_FEATURES:
        raise HTTPException(status_code=413, detail=f"Too many features: {len(features)}. Max: {MAX_FEATURES}")

    if require_polygons:
        for i, feature in enumerate(features):
            problem = analysis.geometry_problem(feature.get("geometry"))
            if problem:
                plot_id = (feature.get("properties") or {}).get("plot_id", f"#{i}")
                raise HTTPException(status_code=422, detail=f"Feature {plot_id}: {problem}")
    return features, size_mb


async def _analyze(name: str, analyze: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
                   features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Run a blocking batch analysis off the event loop, mapping failures to non-2xx."""
    try:
        return await run_in_threadpool(analyze, features)
    except analysis.EarthEngineUnavailable as e:
        logger.error(f"{name}: Earth Engine not available: {e}")
        raise HTTPException(status_code=503, detail=f"Earth Engine not available: {e}")
    except ee.EEException as e:
        logger.error(f"{name}: Earth Engine error: {e}")
        raise HTTPException(status_code=502, detail=f"Earth Engine error: {e}")
    except Exception as e:
        logger.exception(f"{name} failed")
        raise HTTPException(status_code=500, detail=f"{name} failed: {e}")


def _response(file: UploadFile, size_mb: float, features: List[Dict[str, Any]],
              results: List[Dict[str, Any]], started: float, message: str,
              summary: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
    output_features = [
        {
            "type": "Feature",
            "geometry": feature.get("geometry"),
            "properties": {**(feature.get("properties") or {}), **result},
        }
        for feature, result in zip(features, results)
    ]
    return {
        "status": "success",
        "message": message,
        "file_info": {
            "filename": file.filename,
            "size_mb": round(size_mb, 2),
            "features_count": len(features),
        },
        "analysis_summary": {
            "total_processed": len(output_features),
            **summary,
            "processing_time_seconds": round(time.monotonic() - started, 2),
        },
        "data": {"type": "FeatureCollection", "features": output_features},
        "metadata": {
            "processing_timestamp": datetime.utcnow().isoformat() + "Z",
            "api_version": "2.0.0",
            **metadata,
        },
    }


@router.post("/validate-geometry", summary="Validate Geometry Quality")
async def validate_geometry(file: UploadFile = File(...)):
    """
    Check the quality of each plot polygon. Runs locally (no Earth Engine) and
    never fails on broken polygons: they are reported through the flags.

    **Request:** multipart/form-data, field **file** = GeoJSON FeatureCollection
    (max 1000 features).

    **Output properties** (input properties are kept, e.g. `plot_id`, `name`):
    - `area_sqm`: geodesic area in m²
    - `zero_area`: area below 1 m²
    - `self_intersection`: the boundary crosses itself
    - `not_ring`: ring not closed, fewer than 4 positions, or malformed/out-of-range coordinates
    - `duplicate_vertices`: a vertex is repeated
    - `is_valid`, `validation_status`, `issues`: overall verdict and reasons

    `geometry` is returned unchanged.
    """
    started = time.monotonic()
    features, size_mb = await _read_features(file, require_polygons=False)
    results = await _analyze("Geometry validation", analysis.validate_geometries, features)
    valid = sum(1 for r in results if r["is_valid"])
    return _response(
        file, size_mb, features, results, started,
        message="Geometry validation completed",
        summary={"valid": valid, "invalid": len(results) - valid},
        metadata={"validation_type": "geometry_quality_check", "validation_library": "shapely + pyproj"},
    )


@router.post("/deforestation", summary="Upload GeoJSON for Deforestation Analysis")
async def deforestation(file: UploadFile = File(...)):
    """
    Forest loss inside each plot after the EUDR cutoff (2021-2024) from three
    datasets: **GFW** (loss in primary forest), **JRC** (TMF deforestation in
    EU forest 2020) and **SBTN** (loss in natural lands). Any loss is high risk.

    **Request:** multipart/form-data, field **file** = GeoJSON FeatureCollection
    of Polygon/MultiPolygon plots (max 1000 features).

    **Output properties** (input properties are kept):
    - `overall_compliance.overall_risk`: `"high"` if any dataset shows loss, else `"low"`
    - `gfw_loss.gfw_loss_area` (ha), `gfw_loss.gfw_loss_percent` (0-100)
    - `jrc_loss.jrc_loss_area` (ha), `jrc_loss.jrc_loss_percent` (0-100)
    - `sbtn_loss.sbtn_loss_area` (ha), `sbtn_loss.sbtn_loss_percent` (0-100)
    - `total_area_hectares`, `*_stat`, `*_year_compilation` (year with most loss)
    """
    started = time.monotonic()
    features, size_mb = await _read_features(file, require_polygons=True)
    results = await _analyze("Deforestation analysis", analysis.deforestation, features)
    high_risk = sum(1 for r in results if r["overall_compliance"]["overall_risk"] == "high")
    return _response(
        file, size_mb, features, results, started,
        message="Deforestation analysis completed",
        summary={"high_risk": high_risk, "low_risk": len(results) - high_risk},
        metadata={
            "datasets_used": ["GFW Loss (2021-2024)", "JRC Loss (2021-2024)", "SBTN Loss (2021-2024)"],
            "analysis_type": "deforestation_risk_assessment",
        },
    )


@router.post("/protected-area", summary="Upload GeoJSON for Protected Area Analysis")
async def protected_area(file: UploadFile = File(...)):
    """
    Overlap of each plot with protected areas in the **WDPA** (World Database on
    Protected Areas, `WCMC/WDPA/current/polygons`).

    **Request:** multipart/form-data, field **file** = GeoJSON FeatureCollection
    of Polygon/MultiPolygon plots (max 1000 features).

    **Output properties** (input properties are kept):
    - `wdpa_status`:
      - `"non_compliant"`: overlaps a strict protected area (IUCN Ia, Ib, II, III, IV)
      - `"indicative"`: overlaps another protected area (IUCN V, VI, Not Reported/Assigned/Applicable)
      - `"compliant"`: no overlap
    - `wdpa_categories`: IUCN categories of the overlapping areas (`[]` if none)
    """
    started = time.monotonic()
    features, size_mb = await _read_features(file, require_polygons=True)
    results = await _analyze("Protected area analysis", analysis.protected_area, features)
    counts = {status: sum(1 for r in results if r["wdpa_status"] == status)
              for status in ("compliant", "indicative", "non_compliant")}
    return _response(
        file, size_mb, features, results, started,
        message="Protected area analysis completed",
        summary=counts,
        metadata={"dataset_used": analysis.WDPA_ASSET, "analysis_type": "protected_area_intersection"},
    )


@router.post("/rainfall", summary="Upload GeoJSON for Rainfall Analysis")
async def rainfall(file: UploadFile = File(...)):
    """
    Annual rainfall over each plot from **CHIRPS** (`UCSB-CHG/CHIRPS/PENTAD`),
    for the latest complete calendar year, bilinear-resampled from ~5.5 km.
    CHIRPS covers 50°S-50°N; values are `null` for plots outside it.

    **Request:** multipart/form-data, field **file** = GeoJSON FeatureCollection
    of Polygon/MultiPolygon plots (max 1000 features).

    **Output properties** (input properties are kept):
    - `rainfall_mean_mm`, `rainfall_min_mm`, `rainfall_max_mm`, `rainfall_std_mm`: annual total (mm) over the plot
    - `area_hectares`: plot area
    - `analysis_period.start_date`, `analysis_period.end_date`: `YYYY-MM-DD`
    """
    started = time.monotonic()
    features, size_mb = await _read_features(file, require_polygons=True)
    results = await _analyze("Rainfall analysis", analysis.rainfall, features)
    means = [r["rainfall_mean_mm"] for r in results if r["rainfall_mean_mm"] is not None]
    return _response(
        file, size_mb, features, results, started,
        message="Rainfall analysis completed",
        summary={"average_rainfall_mm": round(sum(means) / len(means), 2) if means else None},
        metadata={"data_source": f"CHIRPS ({analysis.CHIRPS_ASSET})", "analysis_type": "rainfall_statistics"},
    )


@router.post("/ghg-emission", summary="Upload GeoJSON for GHG Emission Calculation from Deforestation")
async def ghg_emission(file: UploadFile = File(...)):
    """
    GHG emission from the forest loss found by `/deforestation`, per dataset
    (GFW, JRC, SBTN). Uses forest biomass for the plot's optional `forest_type`
    property (`"Primary Forest"` or `"Secondary Forest"`, the default), burning
    N2O/CH4, soil organic carbon, and post land-use carbon stock.

    **Request:** multipart/form-data, field **file** = GeoJSON FeatureCollection
    of Polygon/MultiPolygon plots (max 1000 features).

    **Output properties** (input properties are kept):
    - `gfw_ghg_emission`, `jrc_ghg_emission`, `sbtn_ghg_emission`: each with
      `area_hectares` (loss, ha), `net_emission_tco2e` and the emission breakdown
    - `total_net_emission_tco2e`: the largest of the three (datasets overlap, so they are not summed)
    """
    started = time.monotonic()
    features, size_mb = await _read_features(file, require_polygons=True)
    results = await _analyze("GHG emission analysis", analysis.ghg_emission, features)
    return _response(
        file, size_mb, features, results, started,
        message="GHG emission from deforestation analysis completed",
        summary={"total_net_emission_tco2e": round(sum(r["total_net_emission_tco2e"] for r in results), 4)},
        metadata={
            "deforestation_datasets": ["GFW (2021-2024)", "JRC (2021-2024)", "SBTN (2021-2024)"],
            "calculation_method": "IPCC guidelines with default parameters",
            "analysis_type": "ghg_emission_from_deforestation",
        },
    )
