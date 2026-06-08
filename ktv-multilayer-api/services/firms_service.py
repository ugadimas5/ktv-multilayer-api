"""
FIRMS fire-hotspot analysis service (tag: palm-twin).

Uses the FIRMS VIIRS vector FeatureCollections from the GEE community catalog:
    projects/sat-io/open-datasets/VIIRS/VNP14IMGTDL_NRT_{year}
Available years in that asset: 2018-2021 (default 2021). Fields incl.
acq_date, acq_time, confidence (l/n/h), frp, bright_ti4/5, daynight, satellite.

Functions:
  - polygon_radius_hotspot: per polygon centroid, buffer 1km & 5km, count hotspots.
  - point_radius_hotspot:   per point, buffer 10/20/30/50km, count hotspots.
  - radius_vis_polygon:     GeoJSON of 1km & 5km rings per polygon centroid.
  - radius_vis_point:       GeoJSON of 10/20/30/50km rings per point.

Inputs can be large (mill.csv ~4k points), so processing is chunked and the
point endpoints expose limit/offset.
"""
import os
import csv
import io
import ee
from typing import Dict, Any, List
from loguru import logger

VIIRS_BASE = "projects/sat-io/open-datasets/VIIRS/VNP14IMGTDL_NRT_"
AVAILABLE_YEARS = [2018, 2019, 2020, 2021]
DEFAULT_YEAR = 2021

POLYGON_RADII_M = [1000, 5000]                 # 1 km, 5 km
POINT_RADII_M = [10000, 20000, 30000, 50000]   # 10, 20, 30, 50 km

CHUNK_SIZE = 250          # features per Earth Engine round-trip
VIS_POINT_DEFAULT_LIMIT = 200   # cap rings returned for point visualization

_ee_ready = False


def _ensure_ee() -> None:
    """Make sure Earth Engine is initialized (reuse global state if already done)."""
    global _ee_ready
    if _ee_ready:
        return
    try:
        ee.Number(1).getInfo()
        _ee_ready = True
        return
    except Exception:
        pass
    from authentication.auth_helper import auth_init_ee
    path = os.getenv("EE_SERVICE_ACCOUNT_PATH", "services/whisp_main/src/")
    auth_init_ee("eudr-0", path, print_status=False)
    _ee_ready = True


def validate_year(year: int) -> int:
    year = int(year)
    if year not in AVAILABLE_YEARS:
        raise ValueError(f"FIRMS year {year} not available. Available: {AVAILABLE_YEARS}")
    return year


def firms_collection(year: int) -> ee.FeatureCollection:
    return ee.FeatureCollection(f"{VIIRS_BASE}{int(year)}")


def _km(m: int) -> str:
    return f"{m // 1000}km"


def _buffer_err(m: int) -> float:
    """maxError for buffering: ~1% of radius (bounds vertex count), min 10 m."""
    return max(10.0, m * 0.01)


def _chunk(lst: List[Any], size: int):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def _select(items: List[Any], limit: int, offset: int) -> List[Any]:
    offset = max(0, int(offset or 0))
    if limit and int(limit) > 0:
        return items[offset:offset + int(limit)]
    return items[offset:]


# ----------------------------- input parsing -----------------------------
def _polygon_features(geojson: Dict[str, Any]) -> List[Dict[str, Any]]:
    feats = geojson.get("features")
    if not isinstance(feats, list):
        feats = [geojson]
    out = []
    for ft in feats:
        geom = (ft or {}).get("geometry") or {}
        if geom.get("type") in ("Polygon", "MultiPolygon") and geom.get("coordinates"):
            out.append(ft)
    return out


def _polygon_identity(props: Dict[str, Any]) -> Dict[str, Any]:
    props = props or {}
    return {
        "plot_id": props.get("plot_id") or props.get("plot") or "unknown",
        "country": props.get("country_name") or props.get("country") or "unknown",
    }


def _points_from_csv(text: str) -> List[Dict[str, Any]]:
    # newline='' so the csv module handles \r\n itself (avoids "new-line in unquoted field")
    reader = csv.DictReader(io.StringIO(text, newline=''))
    pts = []
    for row in reader:
        lat_raw = row.get("Latitude") or row.get("latitude") or row.get("lat")
        lon_raw = row.get("Longitude") or row.get("longitude") or row.get("lon")
        try:
            lat = float(lat_raw)
            lon = float(lon_raw)
        except (TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        pts.append({
            "mill_id": (row.get("UML_ID") or row.get("Mill_Name") or "unknown"),
            "mill_name": (row.get("Mill_Name") or "unknown"),
            "country": (row.get("Country") or "unknown"),
            "lat": lat,
            "lon": lon,
        })
    return pts


# ----------------------------- hotspot analysis -----------------------------
def _hotspot_counter(firms: ee.FeatureCollection, radii_m: List[int], from_centroid: bool):
    """Return an EE map() fn that sets hotspot count + hit flag per radius on each feature."""
    def fn(feature: ee.Feature) -> ee.Feature:
        base = feature.geometry().centroid(maxError=1) if from_centroid else feature.geometry()
        props = {}
        for m in radii_m:
            n = firms.filterBounds(base.buffer(m, _buffer_err(m))).size()
            props[f"hotspot_{_km(m)}"] = n
            props[f"hit_{_km(m)}"] = n.gt(0)
        return feature.set(props)
    return fn


def _summarize_hits(features: List[Dict[str, Any]], radii_m: List[int], id_field: str) -> Dict[str, Any]:
    hits = {_km(m): [] for m in radii_m}
    summary = {"total": len(features)}
    for m in radii_m:
        summary[f"hit_{_km(m)}"] = 0
    for feat in features:
        p = feat.get("properties", {})
        for m in radii_m:
            k = _km(m)
            if p.get(f"hit_{k}"):
                summary[f"hit_{k}"] += 1
                hits[k].append(p.get(id_field))
    return {"summary": summary, "hits": hits}


def _run_hotspot(ee_features: List[ee.Feature], firms, radii_m, from_centroid: bool) -> List[Dict[str, Any]]:
    out = []
    counter = _hotspot_counter(firms, radii_m, from_centroid)
    for batch in _chunk(ee_features, CHUNK_SIZE):
        info = ee.FeatureCollection(batch).map(counter).getInfo()
        out.extend(info.get("features", []))
    return out


def polygon_radius_hotspot(geojson: Dict[str, Any], year: int = DEFAULT_YEAR) -> Dict[str, Any]:
    _ensure_ee()
    year = validate_year(year)
    firms = firms_collection(year)

    feats = _polygon_features(geojson)
    if not feats:
        raise ValueError("No valid Polygon/MultiPolygon features found in upload.")
    ee_feats = [ee.Feature(ee.Geometry(ft["geometry"]), _polygon_identity(ft.get("properties", {})))
                for ft in feats]

    features = _run_hotspot(ee_feats, firms, POLYGON_RADII_M, from_centroid=True)
    agg = _summarize_hits(features, POLYGON_RADII_M, "plot_id")
    return {
        "status": "success",
        "analysis": "polygon_radius_hotspot",
        "firms_source": f"{VIIRS_BASE}{year}",
        "firms_year": year,
        "radii_km": [m // 1000 for m in POLYGON_RADII_M],
        "summary": agg["summary"],
        "hits": agg["hits"],
        "data": {"type": "FeatureCollection", "features": features},
    }


def point_radius_hotspot(csv_text: str, year: int = DEFAULT_YEAR,
                         limit: int = 0, offset: int = 0) -> Dict[str, Any]:
    _ensure_ee()
    year = validate_year(year)
    firms = firms_collection(year)

    all_pts = _points_from_csv(csv_text)
    if not all_pts:
        raise ValueError("No valid points (with Latitude/Longitude) found in CSV.")
    pts = _select(all_pts, limit, offset)
    ee_feats = [ee.Feature(ee.Geometry.Point([p["lon"], p["lat"]]),
                           {"mill_id": p["mill_id"], "mill_name": p["mill_name"], "country": p["country"]})
                for p in pts]

    features = _run_hotspot(ee_feats, firms, POINT_RADII_M, from_centroid=False)
    agg = _summarize_hits(features, POINT_RADII_M, "mill_id")
    return {
        "status": "success",
        "analysis": "point_radius_hotspot",
        "firms_source": f"{VIIRS_BASE}{year}",
        "firms_year": year,
        "radii_km": [m // 1000 for m in POINT_RADII_M],
        "total_points": len(all_pts),
        "processed_points": len(features),
        "summary": agg["summary"],
        "hits": agg["hits"],
        "data": {"type": "FeatureCollection", "features": features},
    }


# ----------------------------- radius visualization -----------------------------
def _ring_features(ee_features: List[ee.Feature], radii_m: List[int], id_key: str,
                   from_centroid: bool) -> List[Dict[str, Any]]:
    out = []
    for batch in _chunk(ee_features, CHUNK_SIZE):
        fc = ee.FeatureCollection(batch)
        parts = []
        for m in radii_m:
            def make(feature, m=m):
                g = feature.geometry().centroid(maxError=1) if from_centroid else feature.geometry()
                return ee.Feature(g.buffer(m, _buffer_err(m)), {id_key: feature.get(id_key), "radius_km": m // 1000})
            parts.append(fc.map(make))
        merged = parts[0]
        for p in parts[1:]:
            merged = merged.merge(p)
        out.extend(merged.getInfo().get("features", []))
    return out


def radius_vis_polygon(geojson: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_ee()
    feats = _polygon_features(geojson)
    if not feats:
        raise ValueError("No valid Polygon/MultiPolygon features found in upload.")
    ee_feats = [ee.Feature(ee.Geometry(ft["geometry"]), _polygon_identity(ft.get("properties", {})))
                for ft in feats]
    features = _ring_features(ee_feats, POLYGON_RADII_M, "plot_id", from_centroid=True)
    return {"type": "FeatureCollection", "features": features,
            "radii_km": [m // 1000 for m in POLYGON_RADII_M]}


def radius_vis_point(csv_text: str, limit: int = VIS_POINT_DEFAULT_LIMIT, offset: int = 0) -> Dict[str, Any]:
    _ensure_ee()
    all_pts = _points_from_csv(csv_text)
    if not all_pts:
        raise ValueError("No valid points (with Latitude/Longitude) found in CSV.")
    pts = _select(all_pts, limit, offset)
    ee_feats = [ee.Feature(ee.Geometry.Point([p["lon"], p["lat"]]), {"mill_id": p["mill_id"]})
                for p in pts]
    features = _ring_features(ee_feats, POINT_RADII_M, "mill_id", from_centroid=False)
    return {"type": "FeatureCollection", "features": features,
            "radii_km": [m // 1000 for m in POINT_RADII_M],
            "total_points": len(all_pts), "processed_points": len(pts)}
