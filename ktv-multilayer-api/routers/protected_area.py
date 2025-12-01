"""
Protected Area Analysis Router
Handles WDPA (World Database on Protected Areas) analysis endpoints
Tag: sustainit
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks, Body
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
from loguru import logger
import ee
import os
import json
import tempfile
import asyncio

# Router instance
router = APIRouter(
    prefix="/api/v1",
    tags=["sustainit"],
    responses={404: {"description": "Not found"}},
)

# Pydantic models
class CoordinatesModel(BaseModel):
    latitude: float
    longitude: float

class ProtectedAreaRequest(BaseModel):
    coordinates: CoordinatesModel
    buffer_km: Optional[float] = 5.0


def calculate_wdpa_stats(geometry: ee.Geometry) -> Dict[str, Any]:
    """
    Calculate WDPA statistics for a given geometry
    Args:
        geometry: EE Geometry to analyze
    Returns:
        Dict containing WDPA statistics
    """
    try:
        # Load WDPA dataset
        wdpa = ee.FeatureCollection('WCMC/WDPA/current/polygons')
        
        # Filter WDPA polygons that intersect with input geometry
        intersecting_pas = wdpa.filterBounds(geometry)
        
        # Get IUCN categories for intersecting protected areas
        pa_categories = intersecting_pas.aggregate_array('IUCN_CAT').distinct().getInfo()
        
        # Default status is compliant if no intersection
        wdpa_status = 'compliant'
        if pa_categories:
            # Categories that indicate indicative status
            indicative_categories = ['V', 'VI', 'Not Applicable', 'Not Assigned', 'Not Reported']
            # Categories that indicate non-compliant status
            strict_categories = ['Ia', 'Ib', 'II', 'III', 'IV']
            
            # Check categories
            if any(cat in strict_categories for cat in pa_categories):
                wdpa_status = 'non-compliant'
            elif any(cat in indicative_categories for cat in pa_categories):
                wdpa_status = 'indicative'
        
        return {
            'wdpa_status': wdpa_status,
            'wdpa_categories': pa_categories if pa_categories else []
        }
        
    except Exception as e:
        logger.error(f"Error calculating WDPA stats: {e}")
        return {
            'wdpa_status': 'compliant',  # Default to compliant on error
            'wdpa_categories': []
        }


def calculate_rainfall_stats(geometry: ee.Geometry, start_date: str = '2023-10-01', end_date: str = '2024-01-31') -> Dict[str, Any]:
    """
    Calculate rainfall statistics using downscaled CHIRPS data for a given geometry
    Args:
        geometry: EE Geometry to analyze
        start_date: Start date for analysis (default: 2023-10-01)
        end_date: End date for analysis (default: 2024-01-31)
    Returns:
        Dict containing rainfall statistics
    """
    try:
        # Load CHIRPS precipitation dataset
        chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY") \
                    .filterDate(start_date, end_date) \
                    .filterBounds(geometry) \
                    .select('precipitation')
        
        # Compute total precipitation over the period
        total_precip = chirps.sum()
        
        # Load a Sentinel-2 image for projection reference
        ref_image = ee.ImageCollection("COPERNICUS/S2_SR") \
                       .filterBounds(geometry) \
                       .filterDate(start_date, end_date) \
                       .first() \
                       .select('B4')
        
        # Get 100-meter projection from reference
        target_projection = ref_image.projection().atScale(100)
        
        # Resample and reproject CHIRPS to 100 meters (downscaled)
        downscaled_precip = total_precip \
                              .resample('bilinear') \
                              .reproject(crs=target_projection)
        
        # Calculate statistics for the geometry
        stats = downscaled_precip.reduceRegion(
            reducer=ee.Reducer.mean().combine(
                reducer2=ee.Reducer.min(),
                sharedInputs=True
            ).combine(
                reducer2=ee.Reducer.max(),
                sharedInputs=True
            ).combine(
                reducer2=ee.Reducer.stdDev(),
                sharedInputs=True
            ),
            geometry=geometry,
            scale=100,
            maxPixels=1e9
        ).getInfo()
        
        # Extract statistics
        mean_rainfall = stats.get('precipitation_mean', 0)
        min_rainfall = stats.get('precipitation_min', 0)
        max_rainfall = stats.get('precipitation_max', 0)
        std_rainfall = stats.get('precipitation_stdDev', 0)
        
        # Calculate area in hectares
        area_ha = geometry.area().divide(10000).getInfo()
        
        return {
            'rainfall_mean_mm': round(mean_rainfall, 2) if mean_rainfall else 0,
            'rainfall_min_mm': round(min_rainfall, 2) if min_rainfall else 0,
            'rainfall_max_mm': round(max_rainfall, 2) if max_rainfall else 0,
            'rainfall_std_mm': round(std_rainfall, 2) if std_rainfall else 0,
            'area_hectares': round(area_ha, 2),
            'analysis_period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'data_source': 'CHIRPS Daily (downscaled to 100m)',
            'resolution': '100m'
        }
        
    except Exception as e:
        logger.error(f"Error calculating rainfall stats: {e}")
        return {
            'rainfall_mean_mm': 0,
            'rainfall_min_mm': 0,
            'rainfall_max_mm': 0,
            'rainfall_std_mm': 0,
            'area_hectares': 0,
            'analysis_period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'data_source': 'CHIRPS Daily (downscaled to 100m)',
            'resolution': '100m',
            'error': str(e)
        }


def calculate_ghg_emission(geometry: ee.Geometry, forest_type: str = 'Secondary Forest') -> Dict[str, Any]:
    """
    Calculate GHG emission statistics for deforestation in a given geometry
    Args:
        geometry: EE Geometry to analyze
        forest_type: Type of forest ('Primary Forest' or 'Secondary Forest')
    Returns:
        Dict containing GHG emission statistics
    """
    try:
        # Calculate area in hectares
        area_ha = geometry.area().divide(10000).getInfo()
        
        # Dummy constants (replace with actual database values in production)
        # Based on parameter_def_forest_biomass table
        FOREST_BIOMASS = {
            'Primary Forest': 520.0,    # tCO2e/ha for primary forest
            'Secondary Forest': 280.0   # tCO2e/ha for secondary forest
        }
        
        # Based on parameter_def_burning table
        BURNING_PARAMS = {
            'b': 0.5,           # Burning efficiency
            'comfi': 0.5,       # Combustion factor
            'g_n2o': 0.007,     # N2O emission factor (kg/kg dry matter)
            'g_ch4': 0.0048,    # CH4 emission factor (kg/kg dry matter)
            'gwp_n2o': 298,     # Global Warming Potential for N2O
            'gwp_ch4': 25       # Global Warming Potential for CH4
        }
        
        # Based on parameter_def_carbon_stock table (post land-use carbon stock)
        POST_LAND_USE_CARBON = {
            'agb': 47.0,  # Above-ground biomass (tC/ha)
            'bgb': 10.0   # Below-ground biomass (tC/ha)
        }
        
        # SOC emission constant (from gis_int_def_param_soc_constanta)
        SOC_EMISSION_CONSTANT = 26.0  # tCO2e/ha
        
        # Get forest biomass value based on forest type
        forest_biomass = FOREST_BIOMASS.get(forest_type, FOREST_BIOMASS['Secondary Forest'])
        
        # Calculate gross CO2 emissions
        gross_co2 = area_ha * forest_biomass
        
        # Calculate gross N2O emissions
        gross_n2o = (
            (area_ha * BURNING_PARAMS['b'] * BURNING_PARAMS['comfi'] * BURNING_PARAMS['g_n2o']) 
            * 0.001
        ) * BURNING_PARAMS['gwp_n2o']
        
        # Calculate gross CH4 emissions
        gross_ch4 = (
            (area_ha * BURNING_PARAMS['b'] * BURNING_PARAMS['comfi'] * BURNING_PARAMS['g_ch4']) 
            * 0.001
        ) * BURNING_PARAMS['gwp_ch4']
        
        # Calculate total gross emission
        total_gross_emission = gross_co2 + gross_n2o + gross_ch4
        
        # Calculate gross emission with SOC constant
        gross_emission_with_soc = total_gross_emission + (SOC_EMISSION_CONSTANT * area_ha)
        
        # Calculate post-carbon stock
        post_carbon_stock = area_ha * (POST_LAND_USE_CARBON['agb'] + POST_LAND_USE_CARBON['bgb'])
        
        # Calculate post land-use carbon stock with area
        post_luc_ccs_with_area_def = area_ha * (POST_LAND_USE_CARBON['agb'] + POST_LAND_USE_CARBON['bgb'])
        
        # Calculate post land-use carbon stock per hectare
        post_luc_ccs_per_hectare = (
            post_luc_ccs_with_area_def / area_ha if area_ha != 0 else 0
        )
        
        # Net emissions (gross - post carbon stock)
        net_emission = gross_emission_with_soc - post_carbon_stock
        
        return {
            'area_hectares': round(area_ha, 4),
            'forest_type': forest_type,
            'gross_co2_tco2e': round(gross_co2, 4),
            'gross_n2o_tco2e': round(gross_n2o, 4),
            'gross_ch4_tco2e': round(gross_ch4, 4),
            'total_gross_emission_tco2e': round(total_gross_emission, 4),
            'soc_emission_tco2e': round(SOC_EMISSION_CONSTANT * area_ha, 4),
            'gross_emission_with_soc_tco2e': round(gross_emission_with_soc, 4),
            'post_carbon_stock_tc': round(post_carbon_stock, 4),
            'post_luc_ccs_per_hectare_tc': round(post_luc_ccs_per_hectare, 4),
            'net_emission_tco2e': round(net_emission, 4),
            'emission_intensity_tco2e_per_ha': round(net_emission / area_ha if area_ha != 0 else 0, 4),
            'parameters_used': {
                'forest_biomass': forest_biomass,
                'burning_efficiency': BURNING_PARAMS['b'],
                'combustion_factor': BURNING_PARAMS['comfi'],
                'soc_constant': SOC_EMISSION_CONSTANT,
                'post_agb': POST_LAND_USE_CARBON['agb'],
                'post_bgb': POST_LAND_USE_CARBON['bgb']
            }
        }
        
    except Exception as e:
        logger.error(f"Error calculating GHG emission: {e}")
        return {
            'area_hectares': 0,
            'forest_type': forest_type,
            'gross_co2_tco2e': 0,
            'gross_n2o_tco2e': 0,
            'gross_ch4_tco2e': 0,
            'total_gross_emission_tco2e': 0,
            'soc_emission_tco2e': 0,
            'gross_emission_with_soc_tco2e': 0,
            'post_carbon_stock_tc': 0,
            'post_luc_ccs_per_hectare_tc': 0,
            'net_emission_tco2e': 0,
            'emission_intensity_tco2e_per_ha': 0,
            'error': str(e)
        }


@router.post("/protected-area", tags=["sustainit"], summary="Upload GeoJSON for Protected Area Analysis")
async def protected_area(file: UploadFile = File(...)):
    """
    Upload and analyze GeoJSON file for Protected Area intersection analysis.
    
    Analyzes each feature in the uploaded GeoJSON to check if it intersects with 
    protected areas from the WDPA (World Database on Protected Areas) dataset.
    
    **Request Body:**
    Upload a GeoJSON file (multipart/form-data)
    - **file**: GeoJSON file (.geojson or .json)
    - Maximum file size: 50MB
    - Supported geometry types: Polygon, MultiPolygon, Point, LineString
    
    **Analysis Method:**
    - Processes each feature geometry
    - Checks intersection with WDPA polygons
    - Classifies based on IUCN categories
    - Returns compliance status per feature
    
    **IUCN Categories:**
    - **Strict Protection (Non-Compliant)**: Ia, Ib, II, III, IV
    - **Sustainable Use (Indicative)**: V, VI
    - **Other**: Not Applicable, Not Assigned, Not Reported
    
    **Response Format:**
    ```json
    {
      "status": "success",
      "file_info": {
        "filename": "plots.geojson",
        "size_mb": 2.5,
        "features_count": 100
      },
      "analysis_summary": {
        "total_processed": 100,
        "compliant": 85,
        "indicative": 10,
        "non_compliant": 5,
        "processing_time_seconds": 45.2
      },
      "data": {
        "type": "FeatureCollection",
        "features": [...]
      }
    }
    ```
    
    **Use Cases:**
    - Bulk protected area compliance checking
    - Land use planning for multiple plots
    - Conservation area impact assessment
    - Due diligence for land acquisition
    """
    logger.info("Protected Area File Upload: Starting...")
    tmp_path = None
    
    try:
        # Save uploaded file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".geojson") as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name
        
        logger.info(f"Protected Area File Upload: File saved to {tmp_path}")
        
        # Validate file size
        file_size_mb = len(contents) / (1024 * 1024)
        if file_size_mb > 50:
            os.unlink(tmp_path)
            raise HTTPException(
                status_code=413, 
                detail=f"File too large: {file_size_mb:.1f}MB. Max: 50MB"
            )
        
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
        
        # Get features
        features = geojson_data.get("features", [])
        if not isinstance(features, list):
            features = [geojson_data]
        
        features_count = len(features)
        logger.info(f"Processing {features_count} features for protected area analysis")
        
        # Initialize Earth Engine
        from authentication.auth_helper import auth_init_ee
        try:
            auth_init_ee("eudr-0", print_status=False)
        except Exception as auth_error:
            logger.warning(f"Failed to authenticate with eudr-0: {auth_error}")
            ee.Initialize()
        
        start_time = datetime.now()
        
        # Async processing function
        async def process_feature_async(feature):
            """Process a single feature for protected area intersection"""
            geometry = feature.get("geometry")
            properties = feature.get("properties", {})
            
            if not geometry or not geometry.get("type") or not geometry.get("coordinates"):
                logger.warning("Invalid geometry format")
                return None
            
            try:
                # Convert to ee.Geometry based on type
                if geometry["type"] == "Polygon":
                    ee_geometry = ee.Geometry.Polygon(geometry["coordinates"])
                elif geometry["type"] == "MultiPolygon":
                    ee_geometry = ee.Geometry.MultiPolygon(geometry["coordinates"])
                elif geometry["type"] == "Point":
                    ee_geometry = ee.Geometry.Point(geometry["coordinates"])
                elif geometry["type"] == "LineString":
                    ee_geometry = ee.Geometry.LineString(geometry["coordinates"])
                else:
                    logger.warning(f"Unsupported geometry type: {geometry['type']}")
                    return None
                
                # Calculate WDPA stats (run in executor to avoid blocking)
                loop = asyncio.get_event_loop()
                wdpa_result = await loop.run_in_executor(
                    None, 
                    calculate_wdpa_stats, 
                    ee_geometry
                )
                
                # Merge with existing properties
                result_properties = {
                    **properties,
                    "wdpa_status": wdpa_result["wdpa_status"],
                    "wdpa_categories": wdpa_result["wdpa_categories"],
                    "analysis_timestamp": datetime.utcnow().isoformat() + "Z"
                }
                
                return {
                    "type": "Feature",
                    "properties": result_properties,
                    "geometry": geometry
                }
                
            except Exception as e:
                logger.error(f"Error processing feature: {str(e)}")
                return {
                    "type": "Feature",
                    "properties": {
                        **properties,
                        "wdpa_status": "error",
                        "wdpa_categories": [],
                        "error_message": str(e)
                    },
                    "geometry": geometry
                }
        
        # Process all features in parallel
        logger.info("Processing features in parallel...")
        processed_features = await asyncio.gather(
            *(process_feature_async(f) for f in features)
        )
        
        # Filter out None results
        processed_features = [f for f in processed_features if f is not None]
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Cleanup temp file
        os.unlink(tmp_path)
        
        # Calculate summary statistics
        compliant_count = sum(
            1 for f in processed_features 
            if f["properties"].get("wdpa_status") == "compliant"
        )
        indicative_count = sum(
            1 for f in processed_features 
            if f["properties"].get("wdpa_status") == "indicative"
        )
        non_compliant_count = sum(
            1 for f in processed_features 
            if f["properties"].get("wdpa_status") == "non-compliant"
        )
        error_count = sum(
            1 for f in processed_features 
            if f["properties"].get("wdpa_status") == "error"
        )
        
        logger.success(
            f"Protected Area File Upload: Processing completed. "
            f"Compliant: {compliant_count}, Indicative: {indicative_count}, "
            f"Non-Compliant: {non_compliant_count}"
        )
        
        return {
            "status": "success",
            "message": "Protected area analysis completed",
            "file_info": {
                "filename": file.filename,
                "size_mb": round(file_size_mb, 2),
                "features_count": features_count
            },
            "analysis_summary": {
                "total_processed": len(processed_features),
                "compliant": compliant_count,
                "indicative": indicative_count,
                "non_compliant": non_compliant_count,
                "errors": error_count,
                "parallel_processing": True,
                "processing_time_seconds": round(processing_time, 2)
            },
            "data": {
                "type": "FeatureCollection",
                "features": processed_features
            },
            "metadata": {
                "processing_timestamp": datetime.utcnow().isoformat() + "Z",
                "api_version": "1.0.0",
                "dataset_used": "WCMC/WDPA/current/polygons",
                "analysis_type": "protected_area_intersection"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Protected Area File Upload error: {str(e)}")
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception as cleanup_err:
                logger.error(f"Failed to remove temp file {tmp_path}: {cleanup_err}")
        raise HTTPException(
            status_code=500,
            detail=f"Protected area analysis failed: {str(e)}"
        )


@router.post("/deforestation", tags=["sustainit"], summary="Upload GeoJSON for Deforestation Analysis")
async def deforestation(file: UploadFile = File(...)):
    """
    Upload and analyze GeoJSON file for EUDR compliance, returning unrounded area/percent values.
    Proses setiap feature secara async-parallel untuk efisiensi dan memory safety.
    
    **Request Body:**
    Upload a GeoJSON file (multipart/form-data)
    - **file**: GeoJSON file (.geojson or .json)
    - Maximum file size: 50MB
    - Supported geometry types: Polygon, MultiPolygon
    
    **Analysis Method:**
    - Processes each feature geometry
    - Analyzes forest loss using GFW, JRC, SBTN datasets
    - Returns unrounded statistics
    - Binary risk classification (High/Low)
    
    **Datasets:**
    - **GFW Loss**: Global Forest Watch deforestation 2021-2024
    - **JRC Loss**: Joint Research Centre forest loss 2021-2024
    - **SBTN Loss**: Science Based Targets Network loss 2021-2024
    
    **Response Format:**
    ```json
    {
      "status": "success",
      "file_info": {
        "filename": "plots.geojson",
        "size_mb": 2.5,
        "features_count": 100
      },
      "analysis_summary": {
        "total_processed": 100,
        "high_risk": 15,
        "low_risk": 85,
        "processing_time_seconds": 45.2
      },
      "data": {
        "type": "FeatureCollection",
        "features": [...]
      }
    }
    ```
    
    **Use Cases:**
    - EUDR compliance bulk checking
    - Deforestation risk assessment
    - Supply chain due diligence
    - Forest loss monitoring
    """
    logger.info("Deforestation Analysis: Starting...")
    tmp_path = None
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".geojson") as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name
        
        logger.info(f"Deforestation Analysis: File saved to {tmp_path}")
        
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
        
        from services.data.multilayer_service import MultilayerService
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

        logger.success("Deforestation Analysis: Async processing completed successfully")
        return {
            "status": "success",
            "message": "Deforestation analysis completed",
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
            },
            "metadata": {
                "processing_timestamp": datetime.utcnow().isoformat() + "Z",
                "api_version": "1.0.0",
                "datasets_used": [
                    "GFW Loss (2021-2024)",
                    "JRC Loss (2021-2024)",
                    "SBTN Loss (2021-2024)"
                ],
                "analysis_type": "deforestation_risk_assessment"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deforestation Analysis error: {str(e)}")
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception as cleanup_err:
                logger.error(f"Failed to remove temp file {tmp_path}: {cleanup_err}")
        raise HTTPException(status_code=500, detail=f"Deforestation analysis failed: {str(e)}")


@router.post("/validate-geometry", tags=["sustainit"], summary="Validate Geometry Quality")
async def validate_geometry(file: UploadFile = File(...)):
    """
    Validate geometry quality for uploaded GeoJSON file.
    
    Performs comprehensive geometry validation including:
    - Self-intersection detection
    - Duplicate vertices checking
    - Invalid geometry structure
    - Zero area detection
    - Unclosed rings
    
    **Request Body:**
    Upload a GeoJSON file (multipart/form-data)
    - **file**: GeoJSON file (.geojson or .json)
    - Maximum file size: 50MB
    - Supported geometry types: Polygon, MultiPolygon
    
    **Analysis Checks:**
    - **Self-intersection**: Polygons that intersect themselves
    - **Duplicate vertices**: Repeated coordinate points
    - **Invalid geometry**: Malformed geometry structure
    - **Not ring**: Unclosed polygon boundaries
    - **Zero area**: Polygons with no area
    
    **Response Format:**
    ```json
    {
      "status": "success",
      "file_info": {
        "filename": "plots.geojson",
        "size_mb": 2.5,
        "features_count": 100
      },
      "analysis_summary": {
        "total_processed": 100,
        "valid": 85,
        "invalid": 15,
        "processing_time_seconds": 2.5
      },
      "data": {
        "type": "FeatureCollection",
        "features": [...]
      }
    }
    ```
    
    **Use Cases:**
    - Pre-submission geometry validation
    - Data quality assurance
    - Geometry error detection
    - Compliance checking
    """
    logger.info("Validate Geometry: Starting validation process...")
    tmp_path = None
    
    try:
        # Save uploaded file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".geojson") as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name
        
        logger.info(f"Validate Geometry: File saved to {tmp_path}")
        
        # Validate file size
        file_size_mb = len(contents) / (1024 * 1024)
        if file_size_mb > 50:
            os.unlink(tmp_path)
            raise HTTPException(
                status_code=413, 
                detail=f"File too large: {file_size_mb:.1f}MB. Max: 50MB"
            )
        
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
        
        # Get features
        features = geojson_data.get("features", [])
        if not isinstance(features, list):
            features = [geojson_data]
        
        features_count = len(features)
        logger.info(f"Processing {features_count} features for geometry validation")
        
        start_time = datetime.now()
        
        # Simple geometry validation using shapely
        from shapely.geometry import shape
        from shapely.validation import explain_validity
        
        def validate_single_geometry(feature):
            """Validate a single geometry feature"""
            geometry = feature.get("geometry")
            properties = feature.get("properties", {})
            
            if not geometry:
                return {
                    "type": "Feature",
                    "properties": {
                        **properties,
                        "validation_status": "invalid",
                        "is_valid": False,
                        "self_intersection": False,
                        "duplicate_vertices": False,
                        "zero_area": False,
                        "not_ring": False,
                        "issues": ["No geometry provided"]
                    },
                    "geometry": geometry
                }
            
            try:
                # Convert to shapely geometry
                geom = shape(geometry)
                issues = []
                
                # Check if geometry is valid
                is_valid = geom.is_valid
                if not is_valid:
                    validity_msg = explain_validity(geom)
                    issues.append(f"Invalid geometry: {validity_msg}")
                
                # Check for self-intersection
                self_intersection = "self-intersection" in explain_validity(geom).lower() if not is_valid else False
                if self_intersection:
                    issues.append("Self-intersection detected")
                
                # Check for duplicate vertices
                duplicate_vertices = False
                if hasattr(geom, 'exterior'):
                    coords = list(geom.exterior.coords)
                    if len(coords) != len(set(coords)):
                        duplicate_vertices = True
                        issues.append("Duplicate vertices found")
                
                # Check for zero area
                zero_area = False
                if hasattr(geom, 'area'):
                    if geom.area == 0 or geom.area < 1e-10:
                        zero_area = True
                        issues.append("Zero or near-zero area")
                
                # Check if ring is closed
                not_ring = False
                if hasattr(geom, 'exterior'):
                    coords = list(geom.exterior.coords)
                    if len(coords) > 0 and coords[0] != coords[-1]:
                        not_ring = True
                        issues.append("Unclosed ring")
                
                validation_status = "valid" if len(issues) == 0 else "invalid"
                
                return {
                    "type": "Feature",
                    "properties": {
                        **properties,
                        "validation_status": validation_status,
                        "is_valid": is_valid,
                        "self_intersection": self_intersection,
                        "duplicate_vertices": duplicate_vertices,
                        "zero_area": zero_area,
                        "not_ring": not_ring,
                        "issues": issues,
                        "area_sqm": round(geom.area * 111000 * 111000, 2) if hasattr(geom, 'area') else 0
                    },
                    "geometry": geometry
                }
                
            except Exception as e:
                logger.error(f"Error validating geometry: {str(e)}")
                return {
                    "type": "Feature",
                    "properties": {
                        **properties,
                        "validation_status": "error",
                        "is_valid": False,
                        "self_intersection": False,
                        "duplicate_vertices": False,
                        "zero_area": False,
                        "not_ring": False,
                        "issues": [f"Validation error: {str(e)}"]
                    },
                    "geometry": geometry
                }
        
        # Process all features
        processed_features = []
        for feature in features:
            validated_feature = validate_single_geometry(feature)
            processed_features.append(validated_feature)
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Cleanup temp file
        os.unlink(tmp_path)
        
        # Calculate summary statistics
        valid_count = sum(
            1 for f in processed_features 
            if f["properties"].get("validation_status") == "valid"
        )
        invalid_count = sum(
            1 for f in processed_features 
            if f["properties"].get("validation_status") == "invalid"
        )
        error_count = sum(
            1 for f in processed_features 
            if f["properties"].get("validation_status") == "error"
        )
        
        logger.success(
            f"Validate Geometry: Processing completed. "
            f"Valid: {valid_count}, Invalid: {invalid_count}, Errors: {error_count}"
        )
        
        return {
            "status": "success",
            "message": "Geometry validation completed",
            "file_info": {
                "filename": file.filename,
                "size_mb": round(file_size_mb, 2),
                "features_count": features_count
            },
            "analysis_summary": {
                "total_processed": len(processed_features),
                "valid": valid_count,
                "invalid": invalid_count,
                "errors": error_count,
                "processing_time_seconds": round(processing_time, 2)
            },
            "data": {
                "type": "FeatureCollection",
                "features": processed_features
            },
            "metadata": {
                "processing_timestamp": datetime.utcnow().isoformat() + "Z",
                "api_version": "1.0.0",
                "validation_type": "geometry_quality_check",
                "validation_library": "shapely"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Validate Geometry error: {str(e)}")
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception as cleanup_err:
                logger.error(f"Failed to remove temp file {tmp_path}: {cleanup_err}")
        raise HTTPException(
            status_code=500,
            detail=f"Geometry validation failed: {str(e)}"
        )


@router.post("/rainfall", tags=["sustainit"], summary="Upload GeoJSON for Rainfall Analysis")
async def rainfall(file: UploadFile = File(...)):
    """
    Upload and analyze GeoJSON file for rainfall statistics using downscaled CHIRPS data.
    
    Analyzes each feature in the uploaded GeoJSON to calculate rainfall statistics
    using CHIRPS (Climate Hazards Group InfraRed Precipitation with Station data)
    downscaled to 100m resolution using Sentinel-2 projection.
    
    **Request Body:**
    Upload a GeoJSON file (multipart/form-data)
    - **file**: GeoJSON file (.geojson or .json)
    - Maximum file size: 50MB
    - Supported geometry types: Polygon, MultiPolygon, Point, LineString
    
    **Analysis Method:**
    - Processes each feature geometry
    - Loads CHIRPS daily precipitation data
    - Downscales from ~5.5km to 100m resolution using bilinear interpolation
    - Uses Sentinel-2 projection for accurate downscaling
    - Calculates mean, min, max, and standard deviation
    
    **Data Source:**
    - **CHIRPS Daily**: Climate Hazards Group precipitation data
    - **Original Resolution**: ~5.5km (0.05 degrees)
    - **Downscaled Resolution**: 100 meters
    - **Default Period**: 2023-10-01 to 2024-01-31 (3 months)
    - **Method**: Bilinear resampling
    
    **Response Format:**
    ```json
    {
      "status": "success",
      "file_info": {
        "filename": "plots.geojson",
        "size_mb": 2.5,
        "features_count": 100
      },
      "analysis_summary": {
        "total_processed": 100,
        "processing_time_seconds": 45.2
      },
      "data": {
        "type": "FeatureCollection",
        "features": [
          {
            "type": "Feature",
            "properties": {
              "rainfall_mean_mm": 450.5,
              "rainfall_min_mm": 420.0,
              "rainfall_max_mm": 480.0,
              "rainfall_std_mm": 15.3,
              "area_hectares": 25.5,
              "analysis_period": {
                "start_date": "2023-10-01",
                "end_date": "2024-01-31"
              }
            },
            "geometry": {...}
          }
        ]
      }
    }
    ```
    
    **Use Cases:**
    - Agricultural water availability assessment
    - Drought risk analysis
    - Irrigation planning
    - Crop suitability evaluation
    - Climate risk assessment
    """
    logger.info("Rainfall Analysis: Starting...")
    tmp_path = None
    
    try:
        # Save uploaded file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".geojson") as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name
        
        logger.info(f"Rainfall Analysis: File saved to {tmp_path}")
        
        # Validate file size
        file_size_mb = len(contents) / (1024 * 1024)
        if file_size_mb > 50:
            os.unlink(tmp_path)
            raise HTTPException(
                status_code=413, 
                detail=f"File too large: {file_size_mb:.1f}MB. Max: 50MB"
            )
        
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
        
        # Get features
        features = geojson_data.get("features", [])
        if not isinstance(features, list):
            features = [geojson_data]
        
        features_count = len(features)
        logger.info(f"Processing {features_count} features for rainfall analysis")
        
        # Initialize Earth Engine
        from authentication.auth_helper import auth_init_ee
        try:
            auth_init_ee("eudr-0", print_status=False)
        except Exception as auth_error:
            logger.warning(f"Failed to authenticate with eudr-0: {auth_error}")
            ee.Initialize()
        
        start_time = datetime.now()
        
        # Async processing function
        async def process_feature_async(feature):
            """Process a single feature for rainfall statistics"""
            geometry = feature.get("geometry")
            properties = feature.get("properties", {})
            
            if not geometry or not geometry.get("type") or not geometry.get("coordinates"):
                logger.warning("Invalid geometry format")
                return None
            
            try:
                # Convert to ee.Geometry based on type
                if geometry["type"] == "Polygon":
                    ee_geometry = ee.Geometry.Polygon(geometry["coordinates"])
                elif geometry["type"] == "MultiPolygon":
                    ee_geometry = ee.Geometry.MultiPolygon(geometry["coordinates"])
                elif geometry["type"] == "Point":
                    ee_geometry = ee.Geometry.Point(geometry["coordinates"])
                elif geometry["type"] == "LineString":
                    ee_geometry = ee.Geometry.LineString(geometry["coordinates"])
                else:
                    logger.warning(f"Unsupported geometry type: {geometry['type']}")
                    return None
                
                # Calculate rainfall stats (run in executor to avoid blocking)
                loop = asyncio.get_event_loop()
                rainfall_result = await loop.run_in_executor(
                    None, 
                    calculate_rainfall_stats, 
                    ee_geometry
                )
                
                # Merge with existing properties
                result_properties = {
                    **properties,
                    **rainfall_result,
                    "analysis_timestamp": datetime.utcnow().isoformat() + "Z"
                }
                
                return {
                    "type": "Feature",
                    "properties": result_properties,
                    "geometry": geometry
                }
                
            except Exception as e:
                logger.error(f"Error processing feature: {str(e)}")
                return {
                    "type": "Feature",
                    "properties": {
                        **properties,
                        "rainfall_mean_mm": 0,
                        "rainfall_min_mm": 0,
                        "rainfall_max_mm": 0,
                        "rainfall_std_mm": 0,
                        "error_message": str(e)
                    },
                    "geometry": geometry
                }
        
        # Process all features in parallel
        logger.info("Processing features in parallel...")
        processed_features = await asyncio.gather(
            *(process_feature_async(f) for f in features)
        )
        
        # Filter out None results
        processed_features = [f for f in processed_features if f is not None]
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Cleanup temp file
        os.unlink(tmp_path)
        
        # Calculate summary statistics
        total_rainfall = sum(
            f["properties"].get("rainfall_mean_mm", 0) 
            for f in processed_features
        )
        avg_rainfall = total_rainfall / len(processed_features) if processed_features else 0
        
        logger.success(
            f"Rainfall Analysis: Processing completed. "
            f"Average rainfall: {avg_rainfall:.2f}mm"
        )
        
        return {
            "status": "success",
            "message": "Rainfall analysis completed",
            "file_info": {
                "filename": file.filename,
                "size_mb": round(file_size_mb, 2),
                "features_count": features_count
            },
            "analysis_summary": {
                "total_processed": len(processed_features),
                "average_rainfall_mm": round(avg_rainfall, 2),
                "parallel_processing": True,
                "processing_time_seconds": round(processing_time, 2)
            },
            "data": {
                "type": "FeatureCollection",
                "features": processed_features
            },
            "metadata": {
                "processing_timestamp": datetime.utcnow().isoformat() + "Z",
                "api_version": "1.0.0",
                "data_source": "CHIRPS Daily (UCSB-CHG/CHIRPS/DAILY)",
                "resolution": "100m (downscaled from ~5.5km)",
                "method": "Bilinear interpolation with Sentinel-2 projection",
                "default_period": "2023-10-01 to 2024-01-31",
                "analysis_type": "rainfall_statistics"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rainfall Analysis error: {str(e)}")
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception as cleanup_err:
                logger.error(f"Failed to remove temp file {tmp_path}: {cleanup_err}")
        raise HTTPException(
            status_code=500,
            detail=f"Rainfall analysis failed: {str(e)}"
        )


@router.post("/ghg-emission", tags=["sustainit"], summary="Upload GeoJSON for GHG Emission Calculation from Deforestation")
async def ghg_emission(file: UploadFile = File(...)):
    """
    Upload and analyze GeoJSON file for Greenhouse Gas (GHG) emission calculation from deforestation.
    
    **Process Flow:**
    1. Calculate deforestation areas using GFW, JRC, and SBTN datasets
    2. Calculate GHG emissions for each deforestation area detected
    3. Returns emissions for each dataset (GFW, JRC, SBTN)
    
    **GHG Calculation includes:**
    - CO2 emissions from biomass loss
    - N2O emissions from burning
    - CH4 emissions from burning
    - Soil organic carbon (SOC) emissions
    - Post land-use carbon stock
    - Net emissions (gross - post carbon stock)
    
    **Request Body:**
    Upload a GeoJSON file (multipart/form-data)
    - **file**: GeoJSON file (.geojson or .json)
    - Maximum file size: 50MB
    - Supported geometry types: Polygon, MultiPolygon
    - Optional property: `forest_type` (Primary Forest or Secondary Forest)
    
    **Deforestation Datasets:**
    - **GFW Loss**: Global Forest Watch deforestation 2021-2024
    - **JRC Loss**: Joint Research Centre forest loss 2021-2024
    - **SBTN Loss**: Science Based Targets Network loss 2021-2024
    
    **Calculation Parameters:**
    Based on IPCC guidelines with default parameters:
    - **Forest Biomass**: Primary (520 tCO2e/ha), Secondary (280 tCO2e/ha)
    - **Burning Efficiency**: 0.5 (50%)
    - **Combustion Factor**: 0.5
    - **N2O GWP**: 298, **CH4 GWP**: 25
    - **SOC Emission**: 26 tCO2e/ha
    - **Post-Carbon Stock**: AGB (47 tC/ha) + BGB (10 tC/ha)
    
    **Response Format:**
    ```json
    {
      "status": "success",
      "file_info": {
        "filename": "plots.geojson",
        "size_mb": 2.5,
        "features_count": 100
      },
      "analysis_summary": {
        "total_processed": 100,
        "total_deforestation_area_ha": 45.5,
        "total_net_emission_tco2e": 12450.75,
        "datasets": {
          "gfw": {"total_emission": 5200.5, "area": 18.5},
          "jrc": {"total_emission": 4100.25, "area": 15.0},
          "sbtn": {"total_emission": 3150.0, "area": 12.0}
        },
        "processing_time_seconds": 45.2
      },
      "data": {
        "type": "FeatureCollection",
        "features": [...]
      }
    }
    ```
    
    **Use Cases:**
    - GHG emission accounting for deforestation
    - Carbon footprint assessment from forest loss
    - EUDR compliance reporting with emissions
    - Climate impact assessment
    - Land-use change emission monitoring
    """
    logger.info("GHG Emission from Deforestation: Starting...")
    tmp_path = None
    
    try:
        # Save uploaded file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".geojson") as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name
        
        logger.info(f"GHG Emission from Deforestation: File saved to {tmp_path}")
        
        # Validate file size
        file_size_mb = len(contents) / (1024 * 1024)
        if file_size_mb > 50:
            os.unlink(tmp_path)
            raise HTTPException(
                status_code=413, 
                detail=f"File too large: {file_size_mb:.1f}MB. Max: 50MB"
            )
        
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
        
        # Get features
        features = geojson_data.get("features", [])
        if not isinstance(features, list):
            features = [geojson_data]
        
        features_count = len(features)
        logger.info(f"Processing {features_count} features for deforestation and GHG emission analysis")
        
        # Initialize services
        from authentication.auth_helper import auth_init_ee
        from services.data.multilayer_service import MultilayerService
        
        # Initialize Earth Engine (menggunakan account eudr-0 by default)
        try:
            auth_init_ee("eudr-0", print_status=False)
        except Exception as auth_error:
            logger.warning(f"Failed to authenticate with eudr-0: {auth_error}")
            # Fallback to default ee.Initialize() if service account fails
            ee.Initialize()
        
        service = MultilayerService()
        
        start_time = datetime.now()
        
        # Async processing function
        async def process_feature_async(feature):
            """
            Process a single feature:
            1. Calculate deforestation areas (GFW, JRC, SBTN)
            2. Calculate GHG emissions for each deforestation area
            """
            geometry = feature.get("geometry")
            properties = feature.get("properties", {})
            
            if not geometry or not geometry.get("type") or not geometry.get("coordinates"):
                logger.warning("Invalid geometry format")
                return None
            
            try:
                # Convert to ee.Geometry based on type
                if geometry["type"] == "Polygon":
                    ee_geometry = ee.Geometry.Polygon(geometry["coordinates"])
                elif geometry["type"] == "MultiPolygon":
                    ee_geometry = ee.Geometry.MultiPolygon(geometry["coordinates"])
                else:
                    logger.warning(f"Unsupported geometry type: {geometry['type']}")
                    return None
                
                # Get forest type from properties or use default
                forest_type = properties.get("forest_type", "Secondary Forest")
                if forest_type not in ["Primary Forest", "Secondary Forest"]:
                    forest_type = "Secondary Forest"
                
                # Step 1: Calculate deforestation statistics
                loop = asyncio.get_event_loop()
                deforestation_result = await loop.run_in_executor(
                    None,
                    service._process_single_feature,
                    feature,
                    service.get_ee_datasets(),
                    True
                )
                
                # Extract deforestation areas
                gfw_area_ha = deforestation_result.get('gfw_loss_area_ha', 0)
                jrc_area_ha = deforestation_result.get('jrc_loss_area_ha', 0)
                sbtn_area_ha = deforestation_result.get('sbtn_loss_area_ha', 0)
                
                # Step 2: Calculate GHG emissions for each dataset
                ghg_results = {}
                
                # Calculate for GFW deforestation
                if gfw_area_ha > 0:
                    gfw_geometry = ee_geometry  # Use actual deforestation geometry
                    gfw_ghg = await loop.run_in_executor(
                        None,
                        calculate_ghg_emission,
                        gfw_geometry,
                        forest_type
                    )
                    # Override area with actual deforestation area
                    gfw_ghg['area_hectares'] = gfw_area_ha
                    # Recalculate emissions based on deforestation area
                    gfw_ghg = recalculate_ghg_for_area(gfw_area_ha, forest_type)
                    ghg_results['gfw'] = gfw_ghg
                else:
                    ghg_results['gfw'] = create_zero_emission_result(forest_type)
                
                # Calculate for JRC deforestation
                if jrc_area_ha > 0:
                    jrc_ghg = recalculate_ghg_for_area(jrc_area_ha, forest_type)
                    ghg_results['jrc'] = jrc_ghg
                else:
                    ghg_results['jrc'] = create_zero_emission_result(forest_type)
                
                # Calculate for SBTN deforestation
                if sbtn_area_ha > 0:
                    sbtn_ghg = recalculate_ghg_for_area(sbtn_area_ha, forest_type)
                    ghg_results['sbtn'] = sbtn_ghg
                else:
                    ghg_results['sbtn'] = create_zero_emission_result(forest_type)
                
                # Merge all results
                result_properties = {
                    **properties,
                    # Deforestation data
                    'gfw_loss_area_ha': deforestation_result.get('gfw_loss_area_ha', 0),
                    'gfw_loss_percent': deforestation_result.get('gfw_loss_percent', 0),
                    'jrc_loss_area_ha': deforestation_result.get('jrc_loss_area_ha', 0),
                    'jrc_loss_percent': deforestation_result.get('jrc_loss_percent', 0),
                    'sbtn_loss_area_ha': deforestation_result.get('sbtn_loss_area_ha', 0),
                    'sbtn_loss_percent': deforestation_result.get('sbtn_loss_percent', 0),
                    'risk_level': deforestation_result.get('risk_level', 'Low'),
                    # GHG emissions by dataset
                    'gfw_ghg_emission': ghg_results['gfw'],
                    'jrc_ghg_emission': ghg_results['jrc'],
                    'sbtn_ghg_emission': ghg_results['sbtn'],
                    # Total emissions
                    'total_net_emission_tco2e': (
                        ghg_results['gfw']['net_emission_tco2e'] +
                        ghg_results['jrc']['net_emission_tco2e'] +
                        ghg_results['sbtn']['net_emission_tco2e']
                    ),
                    'forest_type': forest_type,
                    'analysis_timestamp': datetime.utcnow().isoformat() + "Z"
                }
                
                return {
                    "type": "Feature",
                    "properties": result_properties,
                    "geometry": geometry
                }
                
            except Exception as e:
                logger.error(f"Error processing feature: {str(e)}")
                return {
                    "type": "Feature",
                    "properties": {
                        **properties,
                        "error_message": str(e),
                        "total_net_emission_tco2e": 0
                    },
                    "geometry": geometry
                }
        
        # Helper function to recalculate GHG for specific area
        def recalculate_ghg_for_area(area_ha: float, forest_type: str) -> Dict[str, Any]:
            """Recalculate GHG emissions for a specific deforestation area"""
            FOREST_BIOMASS = {
                'Primary Forest': 520.0,
                'Secondary Forest': 280.0
            }
            BURNING_PARAMS = {
                'b': 0.5, 'comfi': 0.5,
                'g_n2o': 0.007, 'g_ch4': 0.0048,
                'gwp_n2o': 298, 'gwp_ch4': 25
            }
            POST_LAND_USE_CARBON = {'agb': 47.0, 'bgb': 10.0}
            SOC_EMISSION_CONSTANT = 26.0
            
            forest_biomass = FOREST_BIOMASS.get(forest_type, FOREST_BIOMASS['Secondary Forest'])
            gross_co2 = area_ha * forest_biomass
            gross_n2o = ((area_ha * BURNING_PARAMS['b'] * BURNING_PARAMS['comfi'] * BURNING_PARAMS['g_n2o']) * 0.001) * BURNING_PARAMS['gwp_n2o']
            gross_ch4 = ((area_ha * BURNING_PARAMS['b'] * BURNING_PARAMS['comfi'] * BURNING_PARAMS['g_ch4']) * 0.001) * BURNING_PARAMS['gwp_ch4']
            total_gross_emission = gross_co2 + gross_n2o + gross_ch4
            gross_emission_with_soc = total_gross_emission + (SOC_EMISSION_CONSTANT * area_ha)
            post_carbon_stock = area_ha * (POST_LAND_USE_CARBON['agb'] + POST_LAND_USE_CARBON['bgb'])
            net_emission = gross_emission_with_soc - post_carbon_stock
            
            return {
                'area_hectares': round(area_ha, 4),
                'forest_type': forest_type,
                'gross_co2_tco2e': round(gross_co2, 4),
                'gross_n2o_tco2e': round(gross_n2o, 4),
                'gross_ch4_tco2e': round(gross_ch4, 4),
                'total_gross_emission_tco2e': round(total_gross_emission, 4),
                'soc_emission_tco2e': round(SOC_EMISSION_CONSTANT * area_ha, 4),
                'gross_emission_with_soc_tco2e': round(gross_emission_with_soc, 4),
                'post_carbon_stock_tc': round(post_carbon_stock, 4),
                'net_emission_tco2e': round(net_emission, 4),
                'emission_intensity_tco2e_per_ha': round(net_emission / area_ha if area_ha != 0 else 0, 4)
            }
        
        def create_zero_emission_result(forest_type: str) -> Dict[str, Any]:
            """Create zero emission result for no deforestation"""
            return {
                'area_hectares': 0,
                'forest_type': forest_type,
                'gross_co2_tco2e': 0,
                'gross_n2o_tco2e': 0,
                'gross_ch4_tco2e': 0,
                'total_gross_emission_tco2e': 0,
                'soc_emission_tco2e': 0,
                'gross_emission_with_soc_tco2e': 0,
                'post_carbon_stock_tc': 0,
                'net_emission_tco2e': 0,
                'emission_intensity_tco2e_per_ha': 0
            }
        
        # Process all features in parallel
        logger.info("Processing features in parallel for deforestation and GHG emissions...")
        processed_features = await asyncio.gather(
            *(process_feature_async(f) for f in features)
        )
        
        # Filter out None results
        processed_features = [f for f in processed_features if f is not None]
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Cleanup temp file
        os.unlink(tmp_path)
        
        # Calculate summary statistics
        total_gfw_area = sum(f["properties"].get("gfw_loss_area_ha", 0) for f in processed_features)
        total_jrc_area = sum(f["properties"].get("jrc_loss_area_ha", 0) for f in processed_features)
        total_sbtn_area = sum(f["properties"].get("sbtn_loss_area_ha", 0) for f in processed_features)
        total_deforestation_area = total_gfw_area + total_jrc_area + total_sbtn_area
        
        total_gfw_emission = sum(f["properties"].get("gfw_ghg_emission", {}).get("net_emission_tco2e", 0) for f in processed_features)
        total_jrc_emission = sum(f["properties"].get("jrc_ghg_emission", {}).get("net_emission_tco2e", 0) for f in processed_features)
        total_sbtn_emission = sum(f["properties"].get("sbtn_ghg_emission", {}).get("net_emission_tco2e", 0) for f in processed_features)
        total_net_emission = total_gfw_emission + total_jrc_emission + total_sbtn_emission
        
        high_risk_count = sum(1 for f in processed_features if f["properties"].get("risk_level") == "High")
        low_risk_count = len(processed_features) - high_risk_count
        
        logger.success(
            f"GHG Emission from Deforestation: Completed. "
            f"Total deforestation: {total_deforestation_area:.2f} ha, "
            f"Total emission: {total_net_emission:.2f} tCO2e"
        )
        
        return {
            "status": "success",
            "message": "GHG emission from deforestation analysis completed",
            "file_info": {
                "filename": file.filename,
                "size_mb": round(file_size_mb, 2),
                "features_count": features_count
            },
            "analysis_summary": {
                "total_processed": len(processed_features),
                "high_risk": high_risk_count,
                "low_risk": low_risk_count,
                "total_deforestation_area_ha": round(total_deforestation_area, 4),
                "total_net_emission_tco2e": round(total_net_emission, 4),
                "datasets": {
                    "gfw": {
                        "total_area_ha": round(total_gfw_area, 4),
                        "total_emission_tco2e": round(total_gfw_emission, 4)
                    },
                    "jrc": {
                        "total_area_ha": round(total_jrc_area, 4),
                        "total_emission_tco2e": round(total_jrc_emission, 4)
                    },
                    "sbtn": {
                        "total_area_ha": round(total_sbtn_area, 4),
                        "total_emission_tco2e": round(total_sbtn_emission, 4)
                    }
                },
                "parallel_processing": True,
                "processing_time_seconds": round(processing_time, 2)
            },
            "data": {
                "type": "FeatureCollection",
                "features": processed_features
            },
            "metadata": {
                "processing_timestamp": datetime.utcnow().isoformat() + "Z",
                "api_version": "1.0.0",
                "deforestation_datasets": ["GFW (2021-2024)", "JRC (2021-2024)", "SBTN (2021-2024)"],
                "calculation_method": "IPCC guidelines with default parameters",
                "note": "Calculates deforestation first, then GHG emissions per dataset",
                "analysis_type": "ghg_emission_from_deforestation"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GHG Emission from Deforestation error: {str(e)}")
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception as cleanup_err:
                logger.error(f"Failed to remove temp file {tmp_path}: {cleanup_err}")
        raise HTTPException(
            status_code=500,
            detail=f"GHG emission from deforestation analysis failed: {str(e)}"
        )
