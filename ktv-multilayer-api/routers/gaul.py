"""
GAUL Level2 Boundary GeoJSON Export Router
Endpoint to generate GeoJSON from ee.FeatureCollection('FAO/GAUL/2015/level2')
with schema matching the provided table and commodity_analysis upload format.
"""
import ee
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, List
from authentication.auth_helper import auth_init_ee
import os

router = APIRouter()

# Field mapping based on provided schema
GAUL_FIELDS = [
    "ADM0_CODE", "ADM0_NAME", "DISP_AREA", "STATUS", "Shape_Area", "Shape_Leng",
    "ADM1_CODE", "ADM1_NAME", "ADM2_CODE", "ADM2_NAME", "EXP2_YEAR", "STR2_YEAR"
]

@router.get("/gaul_level2_geojson", tags=["GAUL Boundaries"], summary="Generate GeoJSON from GAUL Level2 boundaries")
async def gaul_level2_geojson(
    adm0_code: Optional[int] = Query(None, description="Filter by country GAUL code (ADM0_CODE)"),
    adm1_code: Optional[int] = Query(None, description="Filter by ADM1_CODE (first admin level)"),
    adm2_code: Optional[int] = Query(None, description="Filter by ADM2_CODE (second admin level)")
):
    """
    Generate GeoJSON FeatureCollection from FAO/GAUL/2015/level2 with schema matching commodity_analysis upload.
    Optional filters: adm0_code, adm1_code, adm2_code.
    """
    # Earth Engine auth (reuse service account logic)
    service_account_path = os.getenv("EE_SINGLE_SERVICE_ACCOUNT_PATH")
    if not service_account_path:
        raise HTTPException(status_code=500, detail="EE_SINGLE_SERVICE_ACCOUNT_PATH not set in environment")
    auth_init_ee("eudr-1", auth_path=os.path.dirname(service_account_path), print_status=False)

    try:
        fc = ee.FeatureCollection("FAO/GAUL/2015/level2")
        # Apply filters if provided
        if adm0_code is not None:
            fc = fc.filter(ee.Filter.eq("ADM0_CODE", adm0_code))
        if adm1_code is not None:
            fc = fc.filter(ee.Filter.eq("ADM1_CODE", adm1_code))
        if adm2_code is not None:
            fc = fc.filter(ee.Filter.eq("ADM2_CODE", adm2_code))
        # Select only required fields
        fc = fc.select(GAUL_FIELDS)
        # Get GeoJSON (client-side)
        geojson = fc.getInfo()
        # Format as FeatureCollection for output
        return JSONResponse(content=geojson)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate GAUL Level2 GeoJSON: {str(e)}")
