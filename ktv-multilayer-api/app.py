import os
import tempfile
from dotenv import load_dotenv
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

# Load environment variables
if os.getenv("APP_ENV") != "production":
    load_dotenv()

app = FastAPI(
    title="KTV Multilayer Processing API",
    version="1.0.0",
    description="API for KTV Multilayer Processing with GFW, JRC, and SBTN datasets"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "message": "KTV Multilayer Processing API",
        "version": "1.0.0",
        "endpoints": [
            "/health",
            "/api/v1/multilayer_processing_ktv"
        ]
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "KTV Multilayer API"}

@app.post("/api/v1/multilayer_processing_ktv", tags=["EUDR Multilayer Processing"])
async def multilayer_processing_ktv(file: UploadFile = File(...)):
    """
    Process GeoJSON dengan 3 dataset (GFW, JRC, SBTN) dan generate statistik loss
    Output: GeoJSON dengan attribut loss untuk setiap dataset
    """
    logger.info("KTV Multilayer Processing: Starting...")
    
    try:
        # Import di dalam fungsi untuk menghindari import error saat startup
        from services.data.ktv_multilayer_service import process_ktv_multilayer
        from services.whisp_main.process_geojson import authenticate_ee_with_service_account
        
        # Save uploaded file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".geojson") as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name
        
        logger.info(f"KTV Multilayer Processing: File saved to {tmp_path}")
        
        # Authenticate Earth Engine
        service_account_path = os.getenv("EE_SERVICE_ACCOUNT_PATH")
        if not service_account_path:
            raise ValueError("EE_SERVICE_ACCOUNT_PATH not set in environment")
        
        authenticate_ee_with_service_account(service_account_path)
        logger.info("KTV Multilayer Processing: EE Authentication successful")
        
        # Process dengan 3 dataset
        result_geojson = process_ktv_multilayer(tmp_path)
        
        # Cleanup
        os.unlink(tmp_path)
        
        logger.success("KTV Multilayer Processing: Completed successfully")
        return {
            "status": "success",
            "message": "KTV multilayer processing completed",
            "data": result_geojson
        }
        
    except Exception as e:
        logger.error(f"KTV Multilayer Processing error: {str(e)}")
        if 'tmp_path' in locals():
            try:
                os.unlink(tmp_path)
            except:
                pass
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0" if os.getenv("APP_ENV") == "production" else "127.0.0.1"
    
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=False if os.getenv("APP_ENV") == "production" else True
    )