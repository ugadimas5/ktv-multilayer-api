"""
GeoJSON File Upload Router
Handles file upload and GeoJSON processing endpoints
"""
import os
import json
import tempfile
from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger

# Router instance
router = APIRouter(
    prefix="/api/v1",
    tags=["GeoJSON Upload & Processing"],
    responses={404: {"description": "Not found"}},
)

# Pydantic models
class GeoJSONRequest(BaseModel):
    geojson: Dict[str, Any]
    analysis_params: Optional[Dict[str, Any]] = {}

@router.post("/upload-geojson", tags=["EUDR File Upload"])
async def upload_geojson_file(file: UploadFile = File(...)):
    """
    Upload and analyze GeoJSON file for EUDR compliance using satellite datasets.
    
    Processes each feature in the uploaded GeoJSON file against three key datasets:
    - GFW (Global Forest Watch) tree cover loss
    - JRC (Joint Research Centre) annual forest cover change  
    - SBTN (Science Based Targets Network) forest loss data
    
    Returns risk assessment with binary classification (compliant/non-compliant) for each feature.
    """
    logger.info("EUDR File Upload: Starting...")
    
    try:
        # Save uploaded file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".geojson") as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name
        
        logger.info(f"EUDR File Upload: File saved to {tmp_path}")
        
        # Validate file size
        file_size_mb = len(contents) / (1024 * 1024)
        if file_size_mb > 50:
            os.unlink(tmp_path)
            raise HTTPException(status_code=413, detail=f"File too large: {file_size_mb:.1f}MB. Max: 50MB")
        
        # Parse and validate GeoJSON
        try:
            geojson_data = json.loads(contents.decode('utf-8'))
        except json.JSONDecodeError as e:
            os.unlink(tmp_path)
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
        
        # Validate GeoJSON structure
        if "type" not in geojson_data or geojson_data["type"] not in ["FeatureCollection", "Feature"]:
            os.unlink(tmp_path)
            raise HTTPException(status_code=400, detail="Invalid GeoJSON structure")
        
        # Process with multilayer service
        from services.data.multilayer_service import MultilayerService
        
        service = MultilayerService()
        start_time = datetime.now()
        result = service.process_geojson(geojson_data)
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Cleanup
        os.unlink(tmp_path)
        
        # Calculate summary
        features_count = len(geojson_data.get("features", [geojson_data]))
        high_risk_count = sum(1 for r in result.get('results', []) if r.get('risk_level') == 'High')
        low_risk_count = features_count - high_risk_count
        
        logger.success("EUDR File Upload: Processing completed successfully")
        
        return {
            "status": "success",
            "message": "EUDR file processing completed",
            "file_info": {
                "filename": file.filename,
                "size_mb": round(file_size_mb, 2),
                "features_count": features_count
            },
            "analysis_summary": {
                "total_processed": len(result.get('results', [])),
                "high_risk": high_risk_count,
                "low_risk": low_risk_count,
                "parallel_processing": result.get('parallel_processing_enabled', False),
                "processing_time_seconds": round(processing_time, 2)
            },
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"EUDR File Upload error: {str(e)}")
        if 'tmp_path' in locals():
            try:
                os.unlink(tmp_path)
            except:
                pass
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@router.post("/multilayer_processing_ktv", tags=["EUDR Multilayer Processing"])
async def multilayer_processing_ktv(file: UploadFile = File(...)):
    """
    Process GeoJSON with 3 forest datasets (GFW, JRC, SBTN) and generate loss statistics.
    
    Analyzes uploaded GeoJSON features against multiple satellite datasets to calculate
    forest loss metrics and generate comprehensive loss statistics for each dataset.
    
    Returns: Enhanced GeoJSON with loss attributes for each dataset.
    """
    logger.info("KTV Multilayer Processing: Starting...")
    
    try:
        # Import inside function to avoid import errors at startup
        from services.data.multilayer_service import MultilayerService
        
        # Save uploaded file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".geojson") as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name
        
        logger.info(f"KTV Multilayer Processing: File saved to {tmp_path}")
        
        # Authenticate Earth Engine - load from .env
        from dotenv import load_dotenv
        load_dotenv()
        service_account_path = os.getenv("EE_SERVICE_ACCOUNT_PATH")
        if not service_account_path:
            raise ValueError("EE_SERVICE_ACCOUNT_PATH not set in .env file")
        
        # Parse GeoJSON from file
        try:
            geojson_data = json.loads(contents.decode('utf-8'))
        except json.JSONDecodeError as e:
            os.unlink(tmp_path)
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
        
        # Process with multilayer service
        service = MultilayerService()
        start_time = datetime.now()
        result_geojson = service.process_geojson(geojson_data)
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Cleanup
        os.unlink(tmp_path)
        
        logger.success("KTV Multilayer Processing: Completed successfully")
        return {
            "status": "success",
            "message": "KTV multilayer processing completed",
            "processing_time_seconds": round(processing_time, 2),
            "data": result_geojson
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"KTV Multilayer Processing error: {str(e)}")
        if 'tmp_path' in locals():
            try:
                os.unlink(tmp_path)
            except:
                pass
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@router.post("/process-geojson")
async def process_geojson(request: GeoJSONRequest):
    """
    **Process GeoJSON Data (JSON Request)**
    
    Process GeoJSON data sent as JSON payload for EUDR compliance analysis with parallel processing.
    
    **Features:**
    - Parallel processing with 16 service accounts
    - Round-robin account distribution
    - Thread-safe processing
    - Binary risk classification
    - Comprehensive analysis results
    
    **Request Format:**
    ```json
    {
      "geojson": {
        "type": "FeatureCollection",
        "features": [
          {
            "type": "Feature",
            "properties": {
              "plot_id": "PLOT_001",
              "country_name": "Indonesia",
              "farm_name": "Palm Oil Plantation"
            },
            "geometry": {
              "type": "Polygon",
              "coordinates": [[...]]
            }
          }
        ]
      },
      "analysis_params": {
        "risk_threshold": 0.7
      }
    }
    ```
    
    **Analysis Output:**
    - Individual feature risk assessment
    - Forest loss statistics per dataset
    - Binary risk classification (High/Low)
    - Processing metadata
    
    **Processing Time:** 
    - Single feature: 2-5 seconds
    - 20 features (parallel): 15-30 seconds
    - 100 features (parallel): 60-120 seconds
    """
    try:
        logger.info("Processing GeoJSON data via JSON request")
        
        # Validate GeoJSON structure
        if "type" not in request.geojson:
            raise HTTPException(status_code=400, detail="Invalid GeoJSON: missing 'type' field")
        
        if request.geojson["type"] not in ["FeatureCollection", "Feature"]:
            raise HTTPException(status_code=400, detail="GeoJSON must be FeatureCollection or Feature")
        
        # Import and use the service
        from services.data.multilayer_service import MultilayerService
        
        # Create service instance
        service = MultilayerService()
        
        # Process the GeoJSON
        start_time = datetime.now()
        result = service.process_geojson(request.geojson)
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Count features
        if request.geojson["type"] == "FeatureCollection":
            features_count = len(request.geojson.get("features", []))
        else:
            features_count = 1
        
        logger.success("GeoJSON JSON processing completed successfully")
        
        return {
            "status": "success",
            "message": "Bulk GeoJSON processing completed successfully",
            "total_features": features_count,
            "parallel_processing_enabled": result.get('parallel_processing_enabled', False),
            "accounts_used": result.get('accounts_used', 'N/A'),
            "processing_time_seconds": round(processing_time, 2),
            "results": result.get('results', []),
            "metadata": {
                "processing_timestamp": datetime.utcnow().isoformat() + "Z",
                "api_version": "2.1.0",
                "analysis_type": "geojson_json_processing",
                "datasets_used": [
                    "GFW Loss (2021-2024)",
                    "JRC Loss (2021-2024)",
                    "SBTN Loss (2021-2024)"
                ]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GeoJSON JSON processing error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "GeoJSON processing failed",
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        )

# =================Route for GEE Tile Services=========================

# Import GEE service (lazy loading to avoid startup errors)
def _get_gee_service():
    """Get GEE service with lazy loading"""
    try:
        from services.gee_dataset_service import gee_dataset_service
        return gee_dataset_service
    except ImportError as e:
        logger.error(f"Failed to import GEE service: {e}")
        raise HTTPException(
            status_code=503, 
            detail="GEE Tile Service not available. Please install Earth Engine dependencies."
        )

@router.get("/gee/datasets", tags=["GEE Tile Services"])
async def get_gee_datasets():
    """
    Get list of available Google Earth Engine datasets for EUDR compliance.
    
    Returns 6 core datasets:
    - **gfw**: Global Forest Watch forest cover
    - **gfw_loss**: GFW deforestation 2021-2024
    - **jrc**: Joint Research Centre forest cover 2020
    - **jrc_loss**: JRC deforestation 2021-2024  
    - **sbtn**: Science Based Targets Network natural lands
    - **sbtn_loss**: SBTN deforestation 2021-2024
    
    Each dataset includes visualization parameters and usage examples.
    """
    try:
        gee_service = _get_gee_service()
        return gee_service.get_available_datasets()
    except Exception as e:
        logger.error(f"Error getting GEE datasets: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/gee/tiles/{dataset}/{z}/{x}/{y}", tags=["GEE Tile Services"])
async def get_gee_tile(
    dataset: str,
    z: int,
    x: int, 
    y: int,
    style: Optional[str] = Query("default", description="Visualization style (default, red, orange, light_green, dark_green, blue, purple)")
):
    """
    Get map tile for specific Google Earth Engine dataset.
    
    **Parameters:**
    - **dataset**: Dataset name (gfw, gfw_loss, jrc, jrc_loss, sbtn, sbtn_loss)
    - **z**: Zoom level (0-18)
    - **x**: Tile X coordinate
    - **y**: Tile Y coordinate
    - **style**: Visualization style for colors
    
    **Returns:** Redirects to Earth Engine tile URL
    
    **Usage Examples:**
    ```javascript
    // Leaflet
    L.tileLayer('https://your-api.com/api/v1/gee/tiles/gfw_loss/{z}/{x}/{y}').addTo(map);
    
    // OpenLayers  
    new ol.layer.Tile({
        source: new ol.source.XYZ({
            url: 'https://your-api.com/api/v1/gee/tiles/jrc/{z}/{x}/{y}'
        })
    });
    ```
    """
    try:
        gee_service = _get_gee_service()
        return gee_service.get_tile(dataset, z, x, y, style)
    except Exception as e:
        logger.error(f"Error getting GEE tile: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/gee/tiles/{dataset}", tags=["GEE Tile Services"])
async def get_gee_dataset_info(
    dataset: str,
    request: Request
):
    """
    Get dataset information and tile URL template for web mapping libraries.
    
    **Parameters:**
    - **dataset**: Dataset name (gfw, gfw_loss, jrc, jrc_loss, sbtn, sbtn_loss)
    
    **Returns:**
    - Dataset metadata and description
    - Tile URL templates for different mapping libraries
    - Available visualization styles
    - Code examples for Leaflet, OpenLayers, and MapBox
    
    **Perfect for:** Setting up web maps with EUDR compliance layers
    """
    try:
        gee_service = _get_gee_service()
        base_url = f"{request.url.scheme}://{request.url.netloc}"
        return gee_service.get_dataset_info(dataset, base_url)
    except Exception as e:
        logger.error(f"Error getting GEE dataset info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/gee/refresh", tags=["GEE Tile Services"])
async def refresh_gee_datasets():
    """
    Refresh Google Earth Engine datasets and reinitialize tile service.
    
    **Use this endpoint when:**
    - Earth Engine service needs to be restarted
    - Dataset cache needs to be cleared
    - After updating service account credentials
    
    **Returns:** Success message with timestamp and dataset count
    """
    try:
        gee_service = _get_gee_service()
        return gee_service.refresh_datasets()
    except Exception as e:
        logger.error(f"Error refreshing GEE datasets: {e}")
        raise HTTPException(status_code=500, detail=str(e))
