"""
Simplified EUDR Forest Compliance API - Refactored with Proper Router Structure
Version 2.1.0 - Modular FastAPI Application

This version separates concerns using FastAPI routers for better maintainability:
- routers/general.py: Health checks and general information
- routers/eudr.py: EUDR compliance analysis
- routers/geojson.py: GeoJSON file upload and processing
"""

import os
from dotenv import load_dotenv
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables
if os.getenv("APP_ENV") != "production":
    load_dotenv()

# Import routers
from routers.general import router as general_router
from routers.eudr import router as eudr_router
from routers.geojson import router as geojson_router

# Create FastAPI application
app = FastAPI(
    title="Simplified EUDR Forest Compliance API",
    version="2.1.0",
    description="""
    Simplified EUDR compliance monitoring using 3 core satellite datasets with binary risk classification.
    
    **🌟 NEW FEATURES:**
    - **File Upload via Swagger UI**: Upload GeoJSON files directly through the web interface
    - **Parallel Processing**: 16 service accounts with round-robin distribution  
    - **Thread-Safe Operations**: Concurrent processing without conflicts
    - **Modular Architecture**: Clean router-based structure
    
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
    
    **🚀 Quick Start:**
    1. **Single Point Analysis**: Use `/api/v1/eudr-compliance`
    2. **File Upload**: Use `/api/v1/upload-geojson` (supports drag & drop in Swagger)
    3. **JSON Processing**: Use `/api/v1/process-geojson` for direct JSON requests
    
    **📁 File Upload Support:**
    - Maximum file size: 50MB
    - Supported formats: .geojson, .json
    - Maximum features: 1000 per file
    - Automatic validation and error handling
    
    **⚡ Performance:**
    - Parallel processing with 16 Google Earth Engine service accounts
    - Round-robin account distribution for optimal performance
    - Thread-safe concurrent operations
    - Processing time: ~2-5 seconds per feature
    
    **Use Cases:**
    - Quick EUDR compliance screening
    - Supply chain risk assessment
    - Deforestation hotspot identification
    - Regulatory due diligence
    - Bulk analysis of farm plots
    """,
    contact={
        "name": "Simplified EUDR API Support",
        "email": "support@forestapi.com"
    },
    license_info={
        "name": "Commercial License",
        "url": "https://forestapi.com/license"
    },
    servers=[
        {
            "url": "http://localhost:8000",
            "description": "Development server"
        },
        {
            "url": "https://api.forestapi.com",
            "description": "Production server"
        }
    ]
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(general_router)
app.include_router(eudr_router)
app.include_router(geojson_router)

# Legacy endpoints for backward compatibility
from routers.legacy import router as legacy_router
app.include_router(legacy_router)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0" if os.getenv("APP_ENV") == "production" else "127.0.0.1"
    
    print("🌍 Starting EUDR Forest Compliance API...")
    print(f"📡 Server: {host}:{port}")
    print(f"📚 Documentation: http://{host}:{port}/docs")
    print(f"🔧 Environment: {'Production' if os.getenv('APP_ENV') == 'production' else 'Development'}")
    print("✨ Features: File Upload + Parallel Processing")
    
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=False if os.getenv("APP_ENV") == "production" else True
    )
