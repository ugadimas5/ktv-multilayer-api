"""
Legacy Router
Handles backward compatibility endpoints
"""
import os
import tempfile
from fastapi import APIRouter, HTTPException, UploadFile, File
from datetime import datetime
from loguru import logger

# Router instance
router = APIRouter(
    prefix="/api/v1",
    tags=["Legacy"],
    responses={404: {"description": "Not found"}},
)

@router.post("/multilayer_processing_ktv", deprecated=True)
async def legacy_multilayer_processing(file: UploadFile = File(...)):
    """
    **[DEPRECATED]** Legacy KTV endpoint. Please use /api/v1/upload-geojson instead.
    
    This endpoint is maintained for backward compatibility only.
    New implementations should use the modern file upload endpoint.
    """
    logger.warning("Legacy endpoint called - redirecting to new file upload processing")
    
    try:
        # Read uploaded file
        contents = await file.read()
        import json
        geojson_data = json.loads(contents)
        
        # Import the new processing function
        from routers.geojson import process_geojson
        from routers.geojson import GeoJSONRequest
        
        # Call new endpoint
        request = GeoJSONRequest(geojson=geojson_data)
        result = await process_geojson(request)
        
        # Return result with legacy wrapper
        return {
            "status": "success",
            "message": "Legacy processing completed (redirected to new endpoint)",
            "legacy_warning": "This endpoint is deprecated. Please use /api/v1/upload-geojson",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Legacy processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Legacy processing failed: {str(e)}")

@router.post("/forest-analysis", deprecated=True)
async def legacy_forest_analysis(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
    buffer_km: float = 5.0
):
    """
    **[DEPRECATED]** Legacy forest analysis endpoint.
    
    Please use /api/v1/eudr-compliance for new implementations.
    """
    logger.warning("Legacy forest analysis endpoint called")
    
    try:
        # Import the new compliance function
        from routers.eudr import eudr_compliance_analysis
        from routers.eudr import EUDRComplianceRequest, CoordinatesModel
        
        # Create request object
        request = EUDRComplianceRequest(
            coordinates=CoordinatesModel(latitude=latitude, longitude=longitude),
            buffer_km=buffer_km
        )
        
        # Call new endpoint
        result = await eudr_compliance_analysis(request)
        
        # Return result with legacy wrapper
        return {
            "status": "success",
            "message": "Legacy forest analysis completed (redirected to EUDR compliance)",
            "legacy_warning": "This endpoint is deprecated. Please use /api/v1/eudr-compliance",
            "data": result,
            "analysis_summary": {
                "location": f"Lat: {latitude:.3f}, Lng: {longitude:.3f}",
                "time_period": f"{start_date} to {end_date}",
                "buffer_area_km2": round(3.14159 * (buffer_km ** 2), 2),
                "datasets_analyzed": 3
            }
        }
        
    except Exception as e:
        logger.error(f"Legacy forest analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Legacy analysis failed: {str(e)}")
