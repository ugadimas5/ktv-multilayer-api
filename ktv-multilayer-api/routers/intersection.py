from fastapi import APIRouter, HTTPException, Query, Path
from fastapi.responses import RedirectResponse
from typing import Optional, Dict, Any
from services.gee_intersection_service import gee_intersection_service

router = APIRouter(
    prefix="/api/v1/gee/intersection",
    tags=["GEE Intersection Analysis"]
)

@router.get("/tiles/{type}/{commodity}/{z}/{x}/{y}")
async def get_intersection_tile(
    type: str = Path(..., description="Intersection type: commodity_flood, commodity_landslide, commodity_flood_landslide"),
    commodity: str = Path(..., description="Commodity: rubber, palm, cocoa, coffee"),
    z: int = Path(..., description="Zoom level"),
    x: int = Path(..., description="X coordinate"),
    y: int = Path(..., description="Y coordinate"),
    country: Optional[str] = Query(None, description="Country name"),
    province: Optional[str] = Query(None, description="Province name"),
    district: Optional[str] = Query(None, description="District name")
):
    """
    Get visualization tile for intersection analysis.
    
    Types:
    - **commodity_flood**: Intersection of Commodity and Flood Hazard (>0.5)
    - **commodity_landslide**: Intersection of Commodity and Landslide (Nov-Dec 2025)
    - **commodity_flood_landslide**: Intersection of all three
    """
    return gee_intersection_service.get_tile(
        type=type,
        commodity=commodity,
        z=z, x=x, y=y,
        country=country,
        province=province,
        district=district
    )

@router.get("/stats")
async def get_intersection_stats(
    type: str = Query(..., description="Intersection type: commodity_flood, commodity_landslide, commodity_flood_landslide"),
    commodity: str = Query(..., description="Commodity: rubber, palm, cocoa, coffee"),
    country: Optional[str] = Query(None, description="Country name"),
    province: Optional[str] = Query(None, description="Province name"),
    district: Optional[str] = Query(None, description="District name")
):
    """
    Calculate area of intersection.
    """
    return gee_intersection_service.calculate_area(
        type=type,
        commodity=commodity,
        country=country,
        province=province,
        district=district
    )
