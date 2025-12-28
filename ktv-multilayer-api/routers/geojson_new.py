
from fastapi import Request as FastAPIRequest
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from typing import Dict, Any
from loguru import logger
# Add session middleware (reminder: add to main app if not present)
# from fastapi import FastAPI
# app = FastAPI()
# app.add_middleware(SessionMiddleware, secret_key="your-secret-key")

class SetFloodBBoxRequest(BaseModel):
    geometry: Dict[str, Any]

from fastapi import APIRouter, Body, File, HTTPException, Query, Request, UploadFile

# Router instance
router = APIRouter(
    prefix="/api/v1",
    tags=["GeoJSON Upload & Processing"],
    responses={404: {"description": "Not found"}},
)

@router.post("/gee/flood/bbox/set", tags=["Disaster"])
async def set_flood_bbox(
    req: SetFloodBBoxRequest,
    request: FastAPIRequest
):
    """
    Set active flood bounding box (bbox) for the current session/user.
    All subsequent tile requests in this session will use this bbox.

    **Body:**
    {
      "geometry": { ...GeoJSON Polygon/MultiPolygon... }
    }

    **Returns:**
    - Status and bbox info
    """
    try:
        coords = req.geometry.get("coordinates")
        if req.geometry["type"] == "Polygon":
            flat = coords[0]
        elif req.geometry["type"] == "MultiPolygon":
            flat = [pt for poly in coords for pt in poly[0]]
        else:
            raise HTTPException(status_code=400, detail="Only Polygon or MultiPolygon supported")
        lons = [c[0] for c in flat]
        lats = [c[1] for c in flat]
        bbox = [min(lons), min(lats), max(lons), max(lats)]
        request.session["flood_bbox"] = bbox
        return {
            "status": "success",
            "bbox": bbox,
            "message": "Active flood bbox set for this session. All tile requests will use this boundary."
        }
    except Exception as e:
        logger.error(f"Error setting session bbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))
# Route khusus tile Indonesia (masking ADM0_CODE=116)
from services.gee_dataset_service import gee_dataset_service


"""
GeoJSON File Upload Router
Handles file upload and GeoJSON processing endpoints
"""
import os
import json
import tempfile
from fastapi import APIRouter, Body, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from datetime import datetime
import ee
import asyncio
from services.data.multilayer_service import MultilayerService

# Pydantic models
class GeoJSONRequest(BaseModel):
    geojson: Dict[str, Any]
    analysis_params: Optional[Dict[str, Any]] = {}


class FloodAnalysisRequest(BaseModel):
    """Request model for flood analysis"""
    geojson: Dict[str, Any]
    years: Optional[List[int]] = None


@router.post("/upload-geojson-notrounded", tags=["EUDR File Upload"], summary="Upload GeoJSON and get unrounded results")
async def upload_geojson_notrounded(file: UploadFile = File(...)):
    """
    Upload and analyze GeoJSON file for EUDR compliance, returning unrounded area/percent values.
    Proses setiap feature secara async-parallel untuk efisiensi dan memory safety.
    """
    logger.info("EUDR File Upload (notrounded): Starting...")
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".geojson") as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name
        logger.info(f"EUDR File Upload (notrounded): File saved to {tmp_path}")
        file_size_mb = len(contents) / (1024 * 1024)
        if file_size_mb > 50:
            os.unlink(tmp_path)
            raise HTTPException(status_code=413, detail=f"File too large: {file_size_mb:.1f}MB. Max: 50MB")
        try:
            geojson_data = json.loads(contents.decode('utf-8'))
        except json.JSONDecodeError as e:
            os.unlink(tmp_path)
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
        if "type" not in geojson_data or geojson_data["type"] not in ["FeatureCollection", "Feature"]:
            os.unlink(tmp_path)
            raise HTTPException(status_code=400, detail="Invalid GeoJSON structure")

        features = geojson_data.get("features", [])
        if not isinstance(features, list):
            features = [geojson_data]
        features_count = len(features)
        service = MultilayerService()
        start_time = datetime.now()

        async def process_feature_async(feature):
            geometry = feature.get("geometry")
            if not geometry or not geometry.get("type") or not geometry.get("coordinates"):
                logger.warning("Invalid geometry format")
                return None
            try:
                # Konversi ke ee.Geometry sesuai tipe
                if geometry["type"] == "Polygon":
                    ee_geometry = ee.Geometry.Polygon(geometry["coordinates"])
                elif geometry["type"] == "MultiPolygon":
                    ee_geometry = ee.Geometry.MultiPolygon(geometry["coordinates"])
                else:
                    logger.warning(f"Unsupported geometry type: {geometry['type']}")
                    return None
                # Proses statistik (sync, bisa di-offload ke thread jika perlu)
                # Gunakan executor agar tidak blocking event loop
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, service._process_single_feature, feature, service.get_ee_datasets(), True)
                return {
                    "type": "Feature",
                    "properties": {k: v for k, v in result.items() if k != 'geometry'},
                    "geometry": geometry
                }
            except Exception as e:
                logger.error(f"Error processing feature: {str(e)}")
                return None

        # Proses semua feature secara paralel
        processed_features = await asyncio.gather(*(process_feature_async(f) for f in features))
        processed_features = [f for f in processed_features if f]

        processing_time = (datetime.now() - start_time).total_seconds()
        os.unlink(tmp_path)

        # Hitung ringkasan risiko jika ada risk_level di properties
        high_risk_count = sum(1 for f in processed_features if f and f["properties"].get('risk_level') == 'High')
        low_risk_count = features_count - high_risk_count

        logger.success("EUDR File Upload (notrounded): Async processing completed successfully")
        return {
            "status": "success",
            "message": "EUDR file processing (notrounded) completed (async)",
            "file_info": {
                "filename": file.filename,
                "size_mb": round(file_size_mb, 2),
                "features_count": features_count
            },
            "analysis_summary": {
                "total_processed": len(processed_features),
                "high_risk": high_risk_count,
                "low_risk": low_risk_count,
                "parallel_processing": True,
                "processing_time_seconds": round(processing_time, 2)
            },
            "data": {
                "type": "FeatureCollection",
                "features": processed_features
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"EUDR File Upload error (notrounded): {str(e)}")
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception as cleanup_err:
                logger.error(f"Failed to remove temp file {tmp_path}: {cleanup_err}")
        raise HTTPException(status_code=500, detail=f"Processing failed (notrounded): {str(e)}")


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

@router.get("/gee/tiles/indonesia/{dataset}/{z}/{x}/{y}", tags=["GEE Tile Services"])
async def get_gee_tile_indonesia(
    dataset: str,
    z: int,
    x: int,
    y: int,
    style: Optional[str] = Query("default", description="Visualization style (default, red, orange, light_green, dark_green, blue, purple)")
):
    """
    Get map tile for specific Google Earth Engine dataset, masked to Indonesia only (ADM0_CODE=116).
    """
    return gee_dataset_service.get_tile_indonesia(dataset, z, x, y, style)

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


# =================Route for GEE Flood Analysis Services=========================

def _get_flood_service():
    """Get GEE Flood service with lazy loading"""
    try:
        from services.gee_flood_service import gee_flood_service
        return gee_flood_service
    except ImportError as e:
        logger.error(f"Failed to import GEE Flood service: {e}")
        raise HTTPException(
            status_code=503,
            detail="GEE Flood Service not available. Please install Earth Engine dependencies."
        )

# =================Route for GEE Landslide Analysis Services=========================
def _get_landslide_service():
    """Get GEE Landslide service with lazy loading"""
    try:
        from services.gee_landslide_service import gee_landslide_service
        return gee_landslide_service
    except ImportError as e:
        logger.error(f"Failed to import GEE Landslide service: {e}")
        raise HTTPException(
            status_code=503,
            detail="GEE Landslide Service not available. Please install Earth Engine dependencies."
        )


# List available landslide datasets
@router.get("/gee/landslide/datasets", tags=["Disaster"])
async def get_landslide_datasets():
    """
    Get list of available landslide analysis datasets (Sentinel-1 SAR, Nov-Dec 2025).
    """
    try:
        landslide_service = _get_landslide_service()
        return landslide_service.get_available_datasets()
    except Exception as e:
        logger.error(f"Error getting landslide datasets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Landslide tile endpoint (GET/POST, geometry override)
from typing import Union
class LandslideTileRequest(BaseModel):
    geometry: Optional[Dict[str, Any]] = None

@router.api_route("/gee/landslide/tiles/{dataset}/{z}/{x}/{y}", methods=["GET", "POST"], tags=["Disaster"])
async def get_landslide_tile(
    dataset: str,
    z: int,
    x: int,
    y: int,
    request: FastAPIRequest,
    body: Union[LandslideTileRequest, None] = Body(default=None),
    country: Optional[str] = Query(None, description="Filter by country name"),
    province: Optional[str] = Query(None, description="Filter by province name"),
    district: Optional[str] = Query(None, description="Filter by district name")
):
    """
    Get map tile for landslide analysis dataset.
    If session bbox is set, tile will be clipped to that boundary. If POST body geometry is provided, it overrides session bbox for that request.
    Optional filters: country, province, district (using GAUL 2024).
    """
    try:
        landslide_service = _get_landslide_service()
        bounds = None
        # Priority: POST body geometry > session bbox > default
        if body and body.geometry:
            import ee
            bounds = ee.Geometry(body.geometry)
        else:
            bbox = request.session.get("flood_bbox")
            if bbox:
                import ee
                bounds = ee.Geometry.Rectangle(bbox)
        return landslide_service.get_tile(dataset, z, x, y, bounds=bounds, country=country, province=province, district=district)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting landslide tile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Landslide dataset info endpoint
@router.get("/gee/landslide/tiles/{dataset}", tags=["Disaster"])
async def get_landslide_dataset_info(
    dataset: str,
    request: Request
):
    """
    Get detailed information and tile URL template for landslide dataset.
    """
    try:
        landslide_service = _get_landslide_service()
        base_url = f"{request.url.scheme}://{request.url.netloc}"
        return landslide_service.get_dataset_info(dataset, base_url)
    except Exception as e:
        logger.error(f"Error getting landslide dataset info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gee/flood/datasets", tags=["Disaster"])
async def get_flood_datasets():
    """
    Get list of available flood analysis datasets.
    
    **Available Datasets:**
    - **flood_hazard**: Composite flood hazard index (0-1) across 2016-2023
    - **permanent_water**: Permanent water bodies detection
    - **flood_2023**: Flood areas detected in 2023
    - **flood_2022**: Flood areas detected in 2022
    - **flood_2021**: Flood areas detected in 2021
    
    **Data Source:** Sentinel-1 GRD radar imagery
    
    **Methodology:**
    - VV polarization band analysis
    - Minimum composite (10th percentile)
    - Speckle filtering (50m focal mean)
    - Water threshold: -15 dB
    - Flood = water in wet season AND dry in dry season
    
    **Season Configuration:**
    - Wet Season: December (12-01 to 12-31)
    - Dry Season: August (08-01 to 08-31)
    - *Note: Adjust dates based on your region's climate*
    """
    try:
        flood_service = _get_flood_service()
        return flood_service.get_available_datasets()
    except Exception as e:
        logger.error(f"Error getting flood datasets: {e}")
        raise HTTPException(status_code=500, detail=str(e))



from typing import Union

class FloodTileRequest(BaseModel):
    geometry: Optional[Dict[str, Any]] = None


@router.api_route("/gee/flood/tiles/{dataset}/{z}/{x}/{y}", methods=["GET", "POST"], tags=["Disaster"])
async def get_flood_tile(
    dataset: str,
    z: int,
    x: int,
    y: int,
    request: FastAPIRequest,
    body: Union[FloodTileRequest, None] = Body(default=None),
    country: Optional[str] = Query(None, description="Filter by country name"),
    province: Optional[str] = Query(None, description="Filter by province name"),
    district: Optional[str] = Query(None, description="Filter by district name")
):
    """
    Get map tile for flood analysis dataset.
    If session bbox is set, tile will be clipped to that boundary. If POST body geometry is provided, it overrides session bbox for that request.
    Optional filters: country, province, district (using GAUL 2024).
    """
    try:
        flood_service = _get_flood_service()
        bounds = None
        # Priority: POST body geometry > session bbox > default
        if body and body.geometry:
            import ee
            bounds = ee.Geometry(body.geometry)
        else:
            bbox = request.session.get("flood_bbox")
            if bbox:
                import ee
                bounds = ee.Geometry.Rectangle(bbox)
        return flood_service.get_tile(dataset, z, x, y, bounds=bounds, country=country, province=province, district=district)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting flood tile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gee/flood/tiles/{dataset}", tags=["Disaster"])
async def get_flood_dataset_info(
    dataset: str,
    request: Request
):
    """
    Get detailed information and tile URL template for flood dataset.
    
    **Parameters:**
    - **dataset**: Dataset name (flood_hazard, permanent_water, flood_YYYY)
    
    **Returns:**
    - Dataset metadata and description
    - Tile URL templates for Leaflet, OpenLayers, MapBox
    - Visualization parameters
    - Code examples for web mapping
    
    **Perfect for:** Setting up flood monitoring dashboards and risk assessment maps
    """
    try:
        flood_service = _get_flood_service()
        base_url = f"{request.url.scheme}://{request.url.netloc}"
        return flood_service.get_dataset_info(dataset, base_url)
    except Exception as e:
        logger.error(f"Error getting flood dataset info: {e}")
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/gee/flood/analyze", tags=["Disaster"])
async def analyze_flood_area(request: FloodAnalysisRequest):
    """
    Analyze flood statistics for a specific area (GeoJSON).
    
    **Request Body:**
    ```json
    {
      "geojson": {
        "type": "Polygon",
        "coordinates": [[[106.8, -6.2], [106.9, -6.2], [106.9, -6.1], [106.8, -6.1], [106.8, -6.2]]]
      },
      "years": [2020, 2021, 2022, 2023]
    }
    ```
    
    **Returns:**
    - Flood hazard index for the area
    - Yearly flood area statistics (hectares)
    - Summary with max/min flood years
    - Total area and average flood area
    
    **Analysis Details:**
    - Processes Sentinel-1 radar data
    - Compares wet (December) vs dry (August) seasons
    - Calculates flood frequency across years
    - Returns area in hectares
    
    **Processing Time:** 10-30 seconds depending on area size
    """
    try:
        flood_service = _get_flood_service()
        
        # Validate years
        if request.years:
            valid_years = [y for y in request.years if 2021 <= y <= 2025]
            if not valid_years:
                raise HTTPException(
                    status_code=400,
                    detail="Years must be between 2021 and 2025"
                )
            years = valid_years
        else:
            years = None
        
        # Run analysis
        result = flood_service.analyze_flood_stats(request.geojson, years)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing flood area: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gee/flood/bbox/info", tags=["Disaster"])
async def get_flood_bbox_info():
    """
    Get information about current active bounding box for flood analysis.
    
    **Returns:**
    - Current active bounds (custom or default)
    - Bounds source (flood_test.geojson or default Indonesia)
    - Bounds coordinates [west, south, east, north]
    
    **Use Case:** Check which area is being used for tile generation
    """
    try:
        flood_service = _get_flood_service()
        
        is_custom = flood_service._custom_bounds_coords is not None
        
        # Get bbox coords
        if is_custom:
            bbox = flood_service._custom_bounds_coords
        else:
            bbox = flood_service._default_bounds_coords
        
        return {
            "status": "success",
            "bounds_type": "custom" if is_custom else "default",
            "bounds_source": "flood_test.geojson" if is_custom else "Indonesia default",
            "bbox": bbox,
            "bbox_description": f"West: {bbox[0]:.2f}°, South: {bbox[1]:.2f}°, East: {bbox[2]:.2f}°, North: {bbox[3]:.2f}°",
            "area_info": {
                "location": "Aceh region" if is_custom else "Indonesia",
                "approximate_size_km2": round(
                    (bbox[2] - bbox[0]) * 111 * (bbox[3] - bbox[1]) * 111, 2
                )
            }
        }
    except Exception as e:
        logger.error(f"Error getting bbox info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gee/flood/bbox/reset", tags=["Disaster"])
async def reset_flood_bbox():
    """
    Reset bounding box to default Indonesia bounds.
    
    **Effect:** 
    - Clears custom bbox from flood_test.geojson
    - Reverts to full Indonesia coverage
    - Clears all cached tiles (forces regeneration)
    
    **Use when:** You want to switch from local area back to Indonesia-wide view
    """
    try:
        flood_service = _get_flood_service()
        flood_service._custom_bounds_coords = None
        flood_service.clear_cache()
        
        logger.info("Reset to default Indonesia bounds")
        
        return {
            "status": "success",
            "message": "Bounding box reset to default Indonesia",
            "bounds": "95°E to 141°E, 11°S to 6°N",
            "cache_cleared": True
        }
    except Exception as e:
        logger.error(f"Error resetting bbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# GEE COMMODITY SERVICES
# =============================================================================

def _get_commodity_service():
    """Get GEE Commodity service with lazy loading"""
    try:
        from services.gee_commodity_service import gee_commodity_service
        return gee_commodity_service
    except ImportError as e:
        logger.error(f"Failed to import GEE Commodity service: {e}")
        raise HTTPException(
            status_code=503,
            detail="GEE Commodity Service not available. Please install Earth Engine dependencies."
        )


@router.get("/gee/commodity/datasets", tags=["Disaster"])
async def get_commodity_datasets():
    """
    Get list of available commodity datasets from Forest Data Partnership.
    
    **Available Commodities:**
    - **rubber**: Rubber plantation probability map
    - **palm**: Palm oil plantation probability map
    - **cocoa**: Cocoa plantation probability map
    - **coffee**: Coffee plantation probability map
    
    **Data Source:** Forest Data Partnership (FDP)
    
    **Model:** model_2025a
    
    **Threshold:** 0.5 probability (binary output)
    
    **Usage Example:**
    ```javascript
    // Leaflet
    L.tileLayer('http://localhost:8000/api/v1/gee/commodity/tiles/rubber/{z}/{x}/{y}')
        .addTo(map);
    ```
    
    **Response includes:**
    - Dataset metadata (name, description, asset ID)
    - Visualization styles (colors)
    - Cache information
    - Active bounding box
    """
    try:
        commodity_service = _get_commodity_service()
        datasets = commodity_service.get_available_datasets()
        return datasets
    except Exception as e:
        logger.error(f"Error getting commodity datasets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gee/commodity/tiles/{commodity}", tags=["Disaster"])
async def get_commodity_tile_info(commodity: str, request: Request):
    """
    Get detailed information for a specific commodity dataset.
    
    **Path Parameters:**
    - **commodity**: Commodity name (rubber, palm, cocoa, coffee)
    
    **Returns:**
    - Dataset details and metadata
    - Tile URL templates for different mapping libraries
    - Visualization parameters
    - Cache status
    
    **Example:** `/gee/commodity/tiles/rubber`
    """
    try:
        commodity_service = _get_commodity_service()
        base_url = str(request.base_url).rstrip('/')
        info = commodity_service.get_dataset_info(commodity, base_url)
        return info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting commodity tile info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gee/commodity/tiles/{commodity}/{z}/{x}/{y}", tags=["Disaster"])
async def get_commodity_tile(
    commodity: str, 
    z: int, 
    x: int, 
    y: int,
    country: Optional[str] = Query(None, description="Filter by Country Name (e.g., 'Indonesia')"),
    province: Optional[str] = Query(None, description="Filter by Province Name (e.g., 'Aceh')"),
    district: Optional[str] = Query(None, description="Filter by District Name (e.g., 'West Aceh')")
):
    """
    Get map tile for commodity visualization.
    
    **Path Parameters:**
    - **commodity**: Commodity name (rubber, palm, cocoa, coffee)
    - **z**: Zoom level (0-20)
    - **x**: Tile X coordinate
    - **y**: Tile Y coordinate
    
    **Query Parameters:**
    - **country**: Filter by Country Name (e.g., 'Indonesia')
    - **province**: Filter by Province Name (e.g., 'Aceh')
    - **district**: Filter by District Name (e.g., 'West Aceh')
    
    **Returns:** Redirect to Google Earth Engine tile URL
    
    **Note:** 
    - First request may take 5-10 seconds while GEE generates map ID
    - Subsequent requests use cached map ID (1 hour cache)
    - Tiles automatically clipped to custom bbox if flood_test.geojson exists
    
    **Visualization:**
    - Binary presence/absence (threshold: 0.5 probability)
    - Transparent background (0 values masked)
    - Color-coded by commodity type
    
    **Example:** `/gee/commodity/tiles/rubber/10/512/384?country=Indonesia&province=Aceh`
    """
    try:
        commodity_service = _get_commodity_service()
        
        # Ensure EE is initialized (retry if needed)
        if not commodity_service.is_initialized:
            logger.info("Earth Engine not initialized, attempting to initialize now...")
            commodity_service._authenticate_ee()
            
            if not commodity_service.is_initialized:
                raise HTTPException(
                    status_code=503,
                    detail="Earth Engine initialization failed. Check service account credentials."
                )
        
        # Get tile (uses cached map ID if available)
        return commodity_service.get_tile(commodity, z, x, y, country=country, province=province, district=district)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting commodity tile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gee/commodity/cache/clear", tags=["Disaster"])
async def clear_commodity_cache(commodity: Optional[str] = None):
    """
    Clear map ID cache for commodity datasets.
    
    **Query Parameters:**
    - **commodity** (optional): Specific commodity to clear. If omitted, clears all.
    
    **Use when:**
    - Visualization looks outdated
    - Bounding box changed
    - Force tile regeneration
    
    **Effect:**
    - Next tile request will regenerate map ID from GEE
    - May take 5-10 seconds for first tile after clear
    """
    try:
        commodity_service = _get_commodity_service()
        commodity_service.clear_cache(commodity)
        return {"status": "success", "message": f"Cache cleared for {commodity if commodity else 'all commodities'}"}
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gee/flood/stats", tags=["Disaster"])
async def get_flood_stats(
    dataset: str = Query(..., description="Dataset name (e.g., flood_hazard, permanent_water)"),
    country: Optional[str] = Query(None, description="Filter by Country Name"),
    province: Optional[str] = Query(None, description="Filter by Province Name"),
    district: Optional[str] = Query(None, description="Filter by District Name")
):
    """
    Get area statistics for flood datasets within a boundary.
    Returns area in square meters and hectares.
    """
    try:
        flood_service = _get_flood_service()
        return flood_service.calculate_area(dataset, country, province, district)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting flood stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gee/landslide/stats", tags=["Disaster"])
async def get_landslide_stats(
    dataset: str = Query(..., description="Dataset name (e.g., landslide_nov_dec_2025)"),
    country: Optional[str] = Query(None, description="Filter by Country Name"),
    province: Optional[str] = Query(None, description="Filter by Province Name"),
    district: Optional[str] = Query(None, description="Filter by District Name")
):
    """
    Get area statistics for landslide datasets within a boundary.
    Returns area in square meters and hectares.
    """
    try:
        landslide_service = _get_landslide_service()
        return landslide_service.calculate_area(dataset, country, province, district)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting landslide stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gee/commodity/stats", tags=["Disaster"])
async def get_commodity_stats(
    commodity: str = Query(..., description="Commodity name (e.g., rubber, palm)"),
    country: Optional[str] = Query(None, description="Filter by Country Name"),
    province: Optional[str] = Query(None, description="Filter by Province Name"),
    district: Optional[str] = Query(None, description="Filter by District Name")
):
    """
    Get area statistics for commodity datasets within a boundary.
    Returns area in square meters and hectares.
    """
    try:
        commodity_service = _get_commodity_service()
        return commodity_service.calculate_area(commodity, country, province, district)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting commodity stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
        msg = f"Cleared cache for {commodity}" if commodity else "Cleared all commodity cache"
        logger.info(msg)
        
        return {
            "status": "success",
            "message": msg,
            "affected_commodities": [commodity] if commodity else list(commodity_service.datasets.keys())
        }
    except Exception as e:
        logger.error(f"Error clearing commodity cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))
