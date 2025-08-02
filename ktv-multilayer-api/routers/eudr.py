"""
EUDR Compliance Router
Handles EUDR compliance analysis endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from loguru import logger

# Router instance
router = APIRouter(
    prefix="/api/v1",
    tags=["EUDR Compliance"],
    responses={404: {"description": "Not found"}},
)

# Pydantic models
class CoordinatesModel(BaseModel):
    latitude: float
    longitude: float

class EUDRComplianceRequest(BaseModel):
    coordinates: CoordinatesModel
    buffer_km: Optional[float] = 5.0

@router.post("/eudr-compliance")
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
