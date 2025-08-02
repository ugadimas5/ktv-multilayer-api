"""
General API Router
Handles health check and general information endpoints
"""
from fastapi import APIRouter
from datetime import datetime

# Router instance
router = APIRouter(
    tags=["General"],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
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
            "geojson_file_upload": "/api/v1/upload-geojson",
            "health_check": "/health"
        },
        "documentation": "/docs",
        "contact": "support@multilayer-api.com",
        "core_datasets": [
            "GFW Loss (2021-2024)",
            "JRC Loss (2021-2024)", 
            "SBTN Loss (2021-2024)"
        ],
        "risk_classification": "Binary (High/Low)",
        "features": [
            "File upload via Swagger UI",
            "Parallel processing with 16 service accounts",
            "Round-robin account distribution",
            "Thread-safe operations",
            "Binary risk classification"
        ]
    }

@router.get("/health")
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
            "compliance_processor": "operational",
            "parallel_processing": "enabled",
            "file_upload": "enabled"
        },
        "performance": {
            "service_accounts_available": 16,
            "max_parallel_workers": 8,
            "max_file_size_mb": 50,
            "max_features_per_request": 1000
        }
    }
