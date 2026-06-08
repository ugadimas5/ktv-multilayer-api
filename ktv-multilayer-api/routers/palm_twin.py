"""
palm-twin router.

Fire-hotspot (FIRMS VIIRS) proximity analysis + radius visualization around
palm plots (polygons) and mills (points).
"""
import json
import asyncio
from fastapi import APIRouter, UploadFile, File, Query, HTTPException
from loguru import logger

from services.firms_service import (
    polygon_radius_hotspot,
    point_radius_hotspot,
    radius_vis_polygon,
    radius_vis_point,
    DEFAULT_YEAR,
    AVAILABLE_YEARS,
    VIS_POINT_DEFAULT_LIMIT,
)

router = APIRouter(prefix="/api/v1", tags=["palm-twin"])

_YEAR_DESC = f"FIRMS VIIRS year. Available: {AVAILABLE_YEARS} (default {DEFAULT_YEAR})."


async def _read_json(file: UploadFile) -> dict:
    contents = await file.read()
    try:
        return json.loads(contents.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")


async def _read_text(file: UploadFile) -> str:
    contents = await file.read()
    try:
        return contents.decode("utf-8-sig")  # tolerate BOM
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Cannot decode file as UTF-8: {e}")


async def _run(fn, *args):
    """Run a blocking EE call off the event loop."""
    return await asyncio.get_event_loop().run_in_executor(None, fn, *args)


@router.post("/polygon_radius_hotspot", tags=["palm-twin"],
             summary="Polygon centroid radius (1km, 5km) overlap with fire hotspots")
async def polygon_radius_hotspot_endpoint(
    file: UploadFile = File(...),
    year: int = Query(DEFAULT_YEAR, description=_YEAR_DESC),
):
    """
    Upload a polygon GeoJSON (e.g. data/plot_kebun_sawit_sample100.geojson). For each
    polygon, a 1km and 5km radius is built from its centroid and intersected with FIRMS
    fire hotspots. Returns, per polygon, hotspot counts and a hit flag for each radius,
    plus the list of plot_ids that hit hotspots per radius.
    """
    logger.info("palm-twin polygon_radius_hotspot: starting...")
    geojson = await _read_json(file)
    try:
        return await _run(polygon_radius_hotspot, geojson, year)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"polygon_radius_hotspot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/point_radius_hotspot", tags=["palm-twin"],
             summary="Point radius (10/20/30/50km) overlap with fire hotspots")
async def point_radius_hotspot_endpoint(
    file: UploadFile = File(...),
    year: int = Query(DEFAULT_YEAR, description=_YEAR_DESC),
    limit: int = Query(0, description="Max points to process (0 = all). mill.csv has ~4100; all may take minutes."),
    offset: int = Query(0, description="Skip the first N points (for paging)."),
):
    """
    Upload a points CSV with Latitude/Longitude columns (e.g. data/mill.csv). For each
    point, radii of 10, 20, 30 and 50km are built and intersected with FIRMS fire
    hotspots. Returns, per point, hotspot counts and a hit flag for each radius, plus
    the list of mill_ids that hit hotspots per radius. Use limit/offset to scope large files.
    """
    logger.info("palm-twin point_radius_hotspot: starting...")
    text = await _read_text(file)
    try:
        return await _run(point_radius_hotspot, text, year, limit, offset)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"point_radius_hotspot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/radius_vis_polygon", tags=["palm-twin"],
             summary="GeoJSON of 1km & 5km rings around each polygon centroid")
async def radius_vis_polygon_endpoint(file: UploadFile = File(...)):
    """
    Upload a polygon GeoJSON (e.g. data/plot_kebun_sawit_sample100.geojson). Returns a
    GeoJSON FeatureCollection with 1km and 5km circle rings around each polygon centroid
    (for map visualization). Each ring carries plot_id and radius_km.
    """
    logger.info("palm-twin radius_vis_polygon: starting...")
    geojson = await _read_json(file)
    try:
        return await _run(radius_vis_polygon, geojson)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"radius_vis_polygon error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/radius_vis_point", tags=["palm-twin"],
             summary="GeoJSON of 10/20/30/50km rings around each point")
async def radius_vis_point_endpoint(
    file: UploadFile = File(...),
    limit: int = Query(VIS_POINT_DEFAULT_LIMIT, description=f"Max points to draw rings for (0 = all; default {VIS_POINT_DEFAULT_LIMIT}). Large values produce very large GeoJSON."),
    offset: int = Query(0, description="Skip the first N points (for paging)."),
):
    """
    Upload a points CSV with Latitude/Longitude columns (e.g. data/mill.csv). Returns a
    GeoJSON FeatureCollection with 10, 20, 30 and 50km circle rings around each point
    (for map visualization). Each ring carries mill_id and radius_km. Capped by limit
    (default {VIS_POINT_DEFAULT_LIMIT}) since mill.csv has ~4100 points.
    """
    logger.info("palm-twin radius_vis_point: starting...")
    text = await _read_text(file)
    try:
        return await _run(radius_vis_point, text, limit, offset)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"radius_vis_point error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
