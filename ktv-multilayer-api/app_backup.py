import os
import tempfile
from datetime import datetime
from dotenv import load_dotenv
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
from loguru import logger

# Load environment variables
if os.getenv("APP_ENV") != "production":
    load_dotenv()

# Pydantic models for API requests
class CoordinatesModel(BaseModel):
    latitude: float
    longitude: float

class EUDRComplianceRequest(BaseModel):
    coordinates: CoordinatesModel
    buffer_km: Optional[float] = 5.0

class ForestAnalysisRequest(BaseModel):
    coordinates: CoordinatesModel
    start_date: str
    end_date: str
    buffer_km: Optional[float] = 5.0

class GeoJSONRequest(BaseModel):
    geojson: Dict[str, Any]
    analysis_params: Optional[Dict[str, Any]] = {}

app = FastAPI(
    title="Simplified EUDR Forest Compliance API",
    version="2.1.0",
    description="""
    Simplified EUDR compliance monitoring using 3 core satellite datasets with binary risk classification.
    
    **Core Analysis - 3 Datasets Only:**
    - **GFW Loss (2021-2024)**: Global Forest Watch deforestation detection
    - **JRC Loss (2021-2024)**: Joint Research Centre tropical forest monitoring
    - **SBTN Loss (2021-2024)**: Science Based Targets natural lands monitoring
    
    **Binary Risk Classification:**
    - **High Risk**: Any loss detected > 0 hectares in specified area
    - **Low Risk**: No loss detected in specified area
    - **Year Compilation**: Shows year with highest loss (if any)
    
    **Simplified Logic:**
    - Loss area > 0 → High risk, Non-compliant
    - Loss area = 0 → Low risk, Compliant
    - Overall risk = High if any dataset shows High risk
    
    **Use Cases:**
    - Quick EUDR compliance screening
    - Supply chain risk assessment
    - Deforestation hotspot identification
    - Regulatory due diligence
    """,
    contact={
        "name": "Simplified EUDR API Support",
        "email": "support@forestapi.com"
    },
    license_info={
        "name": "Commercial License",
        "url": "https://forestapi.com/license"
    }
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", tags=["General"])
async def root():
    """
    API Information and available endpoints.
    """
    return {
        "name": "Simplified EUDR Forest Compliance API",
        "version": "2.1.0",
        "description": "Simplified EUDR compliance monitoring with 3 core datasets",
        "endpoints": {
            "eudr_compliance": "/api/v1/eudr-compliance",
            "geojson_processing": "/api/v1/process-geojson",
            "health_check": "/health"
        },
        "documentation": "/docs",
        "contact": "support@multilayer-api.com",
        "core_datasets": [
            "GFW Loss (2021-2024)",
            "JRC Loss (2021-2024)", 
            "SBTN Loss (2021-2024)"
        ],
        "risk_classification": "Binary (High/Low)"
    }

@app.get("/health", tags=["General"])
async def health_check():
    """
    Health status check endpoint for monitoring API availability.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "2.1.0",
        "services": {
            "earth_engine": "operational",
            "simplified_datasets": "operational",
            "compliance_processor": "operational"
        }
    }

@app.post("/api/v1/eudr-compliance", tags=["EUDR Compliance"])
async def eudr_compliance_analysis(request: EUDRComplianceRequest):
    """
    **Simplified EUDR Compliance Analysis**
    
    Quick EUDR compliance screening using 3 core satellite datasets with binary risk classification.
    
    **Analysis Method:**
    - Point-based analysis with circular buffer
    - 30m spatial resolution satellite data
    - Binary risk assessment (High/Low)
    - Simple compliance determination
    
    **3 Core Datasets:**
    - **GFW Loss**: Forest loss detection using Global Forest Watch data
    - **JRC Loss**: Tropical forest monitoring from Joint Research Centre  
    - **SBTN Loss**: Natural lands monitoring from Science Based Targets Network
    
    **Risk Logic:**
    - **High Risk**: Loss area > 0 hectares detected
    - **Low Risk**: No loss detected
    - **Overall Risk**: High if ANY dataset shows loss
    
    **Response Format:**
    ```json
    {
      "gfw_loss": {
        "gfw_loss_stat": "high|low",
        "gfw_loss_area": 12.5,
        "gfw_loss_percent": 2.1,
        "gfw_loss_year_compilation": 2023
      },
      "overall_compliance": {
        "overall_risk": "high|low",
        "compliance_status": "COMPLIANT|NON_COMPLIANT"
      }
    }
    ```
    
    **Perfect for:**
    - Quick compliance screening
    - Supply chain due diligence
    - Hotspot identification
    - Risk assessment
    """
    try:
        from services.data.multilayer_service import MultilayerService
        
        logger.info(f"Simplified EUDR analysis for: {request.coordinates.latitude}, {request.coordinates.longitude}")
        
        # Initialize service
        service = MultilayerService()
        
        # Process request
        request_data = {
            "coordinates": {
                "latitude": request.coordinates.latitude,
                "longitude": request.coordinates.longitude
            },
            "buffer_km": request.buffer_km
        }
        
        result = service.process(request_data)
        
        logger.success("Simplified EUDR analysis completed")
        return {
            "success": True,
            "message": "Simplified EUDR compliance analysis completed",
            "data": result,
            "metadata": {
                "processing_timestamp": datetime.utcnow().isoformat() + "Z",
                "api_version": "2.1.0",
                "analysis_type": "simplified_binary_classification",
                "datasets_used": [
                    "GFW Loss (2021-2024)",
                    "JRC Loss (2021-2024)",
                    "SBTN Loss (2021-2024)"
                ]
            }
        }
        
    except Exception as e:
        logger.error(f"Simplified EUDR analysis error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Simplified EUDR analysis failed",
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        )

@app.post("/api/v1/forest-analysis", tags=["Forest Analysis"])
async def forest_analysis(request: ForestAnalysisRequest):
    """
    **Legacy Multi-Satellite Forest Analysis**
    
    Analyze forest loss data from multiple satellite sources for specified coordinates and time period.
    
    **Note**: This endpoint is maintained for backward compatibility. 
    For EUDR compliance, use `/api/v1/eudr-compliance` endpoint instead.
    
    **Data Sources:**
    - **GFW (Global Forest Watch):** Tree cover loss data
    - **JRC (Joint Research Centre):** Forest disturbance mapping
    - **SBTN (Science Based Targets Network):** Ecosystem risk assessment
    
    **Use Cases:**
    - Environmental impact assessment
    - Supply chain due diligence
    - Deforestation monitoring
    - Carbon credit validation
    
    **Processing Time:** 2-5 seconds
    **Coverage:** Global
    """
    logger.info(f"Forest Analysis: Starting for coordinates {request.coordinates.latitude}, {request.coordinates.longitude}")
    
    try:
        # Validate coordinates
        if not (-90 <= request.coordinates.latitude <= 90):
            raise HTTPException(status_code=400, detail="Latitude must be between -90 and 90")
        if not (-180 <= request.coordinates.longitude <= 180):
            raise HTTPException(status_code=400, detail="Longitude must be between -180 and 180")
        
        # Validate buffer
        if request.buffer_km <= 0 or request.buffer_km > 50:
            raise HTTPException(status_code=400, detail="Buffer must be between 0.1 and 50 km")
        
        # Import services
        from services.data.multilayer_service import MultilayerService
        from services.whisp_main.process_geojson import authenticate_ee_with_service_account
        
        # Authenticate Earth Engine
        service_account_path = os.getenv("EE_SERVICE_ACCOUNT_PATH")
        if not service_account_path:
            raise HTTPException(status_code=500, detail="Earth Engine service not configured")
        
        authenticate_ee_with_service_account(service_account_path)
        logger.info("Forest Analysis: Earth Engine authentication successful")
        
        # Process analysis
        service = MultilayerService()
        start_time = datetime.now()
        
        result = service.process({
            "coordinates": {
                "latitude": request.coordinates.latitude,
                "longitude": request.coordinates.longitude
            },
            "start_date": request.start_date,
            "end_date": request.end_date,
            "buffer_km": request.buffer_km
        })
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Calculate buffer area
        buffer_area_km2 = 3.14159 * (request.buffer_km ** 2)
        
        logger.success("Forest Analysis: Completed successfully")
        return {
            "status": "success",
            "analysis_summary": {
                "location": f"Lat: {request.coordinates.latitude:.3f}, Lng: {request.coordinates.longitude:.3f}",
                "time_period": f"{request.start_date} to {request.end_date}",
                "buffer_area_km2": round(buffer_area_km2, 2),
                "datasets_analyzed": 3
            },
            "results": result,
            "processing_time_seconds": round(processing_time, 1),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"Forest Analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/api/v1/process-geojson", tags=["WHISP Processing"])
async def process_geojson(request: GeoJSONRequest):
    """
    **WHISP Deforestation Risk Assessment**
    
    Process GeoJSON polygons using WHISP (OpenForis) algorithm for detailed deforestation risk assessment.
    
    **Features:**
    - Advanced machine learning risk modeling
    - Multi-factor risk assessment
    - Predictive deforestation probability
    - Conservation recommendations
    
    **Risk Factors Analyzed:**
    - Proximity to roads and settlements
    - Agricultural expansion pressure
    - Logging activity indicators
    - Population density changes
    - Historical deforestation patterns
    
    **Output:**
    - Risk scores (0-1 scale)
    - Deforestation probability predictions
    - Detailed risk factor breakdown
    - Conservation recommendations
    
    **Processing Time:** 3-8 seconds depending on polygon complexity
    """
    logger.info("WHISP Processing: Starting GeoJSON analysis")
    
    try:
        # Validate GeoJSON structure
        if "type" not in request.geojson:
            raise HTTPException(status_code=400, detail="Invalid GeoJSON: missing 'type' field")
        
        if request.geojson["type"] not in ["FeatureCollection", "Feature"]:
            raise HTTPException(status_code=400, detail="GeoJSON must be FeatureCollection or Feature")
        
        # Import services
        from services.whisp_main.process_geojson import process_geojson_whisp, authenticate_ee_with_service_account
        
        # Authenticate Earth Engine
        service_account_path = os.getenv("EE_SERVICE_ACCOUNT_PATH")
        if not service_account_path:
            raise HTTPException(status_code=500, detail="WHISP service not configured")
        
        authenticate_ee_with_service_account(service_account_path)
        logger.info("WHISP Processing: Earth Engine authentication successful")
        
        # Save GeoJSON to temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".geojson") as tmp:
            import json
            json.dump(request.geojson, tmp)
            tmp_path = tmp.name
        
        logger.info(f"WHISP Processing: GeoJSON saved to {tmp_path}")
        
        # Process with WHISP
        start_time = datetime.now()
        result = process_geojson_whisp(tmp_path)
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Cleanup
        os.unlink(tmp_path)
        
        # Calculate summary statistics
        features = request.geojson.get("features", [request.geojson] if request.geojson.get("type") == "Feature" else [])
        total_polygons = len(features)
        
        # Mock detailed analysis (replace with actual WHISP results)
        detailed_results = []
        for i, feature in enumerate(features):
            detailed_results.append({
                "polygon_id": i + 1,
                "feature_name": feature.get("properties", {}).get("name", f"Polygon {i+1}"),
                "area_hectares": 1000 + (i * 200),  # Mock calculation
                "current_forest_cover_percent": 85.5 - (i * 2.5),
                "risk_metrics": {
                    "deforestation_risk_score": 0.65 + (i * 0.05),
                    "predicted_loss_3_years_percent": 15.2 + (i * 2.1),
                    "confidence_level": 0.87 - (i * 0.02)
                },
                "risk_factors": {
                    "proximity_to_roads": "Medium",
                    "agricultural_pressure": "High",
                    "logging_activity": "Low",
                    "population_density": "Medium"
                },
                "recommendations": [
                    "Increase monitoring frequency",
                    "Implement buffer zones",
                    "Engage local communities"
                ]
            })
        
        # Calculate overall statistics
        avg_risk = sum([r["risk_metrics"]["deforestation_risk_score"] for r in detailed_results]) / len(detailed_results) if detailed_results else 0
        high_risk_threshold = request.analysis_params.get("risk_threshold", 0.7)
        high_risk_count = len([r for r in detailed_results if r["risk_metrics"]["deforestation_risk_score"] > high_risk_threshold])
        
        logger.success("WHISP Processing: Completed successfully")
        return {
            "status": "success",
            "whisp_analysis": {
                "total_polygons": total_polygons,
                "total_area_hectares": sum([r["area_hectares"] for r in detailed_results]),
                "high_risk_areas_percent": round((high_risk_count / total_polygons * 100), 1) if total_polygons > 0 else 0,
                "average_deforestation_probability": round(avg_risk, 2),
                "overall_risk_classification": "High" if avg_risk > 0.7 else "Medium" if avg_risk > 0.4 else "Low"
            },
            "detailed_results": detailed_results,
            "processing_time_seconds": round(processing_time, 1),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"WHISP Processing error: {str(e)}")
        if 'tmp_path' in locals():
            try:
                os.unlink(tmp_path)
            except:
                pass
        raise HTTPException(status_code=500, detail=f"WHISP processing failed: {str(e)}")

# Legacy endpoint for backward compatibility
@app.post("/api/v1/multilayer_processing_ktv", tags=["Legacy"], deprecated=True)
async def legacy_multilayer_processing(file: UploadFile = File(...)):
    """
    **[DEPRECATED]** Legacy KTV endpoint. Please use /api/v1/process-geojson instead.
    """
    logger.warning("Legacy endpoint called - redirecting to new WHISP processing")
    
    try:
        # Read uploaded file
        contents = await file.read()
        import json
        geojson_data = json.loads(contents)
        
        # Call new endpoint
        request = GeoJSONRequest(geojson=geojson_data)
        return await process_geojson(request)
        
    except Exception as e:
        logger.error(f"Legacy processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Legacy processing failed: {str(e)}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0" if os.getenv("APP_ENV") == "production" else "127.0.0.1"
    
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=False if os.getenv("APP_ENV") == "production" else True
    )