"""
GAUL CSV Export Router
Endpoint to extract all province, adm0_code, adm1_code, adm2_code for Indonesia as CSV.
"""
import ee
from fastapi import APIRouter, Response, HTTPException
from typing import Optional
from authentication.auth_helper import auth_init_ee
import os
import csv
import io

router = APIRouter()

@router.get("/gaul_level2_csv", tags=["GAUL Boundaries"], summary="Export GAUL Level2 Indonesia as CSV")
async def gaul_level2_csv():
    """
    Export all province (ADM1_NAME), adm0_code, adm1_code, adm2_code for Indonesia (ADM0_NAME == 'Indonesia') as CSV.
    """
    # Earth Engine auth (reuse service account logic)
    service_account_path = os.getenv("EE_SINGLE_SERVICE_ACCOUNT_PATH")
    if not service_account_path:
        raise HTTPException(status_code=500, detail="EE_SINGLE_SERVICE_ACCOUNT_PATH not set in environment")
    auth_init_ee("eudr-1", auth_path=os.path.dirname(service_account_path), print_status=False)

    try:
        fc = ee.FeatureCollection("FAO/GAUL/2015/level2")
        indo = fc.filter(ee.Filter.eq("ADM0_NAME", "Indonesia"))
        features = indo.getInfo()["features"]
        # Prepare CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ADM0_CODE", "ADM0_NAME", "ADM1_CODE", "ADM1_NAME", "ADM2_CODE", "ADM2_NAME"])
        for feat in features:
            p = feat["properties"]
            writer.writerow([
                p.get("ADM0_CODE", ""),
                p.get("ADM0_NAME", ""),
                p.get("ADM1_CODE", ""),
                p.get("ADM1_NAME", ""),
                p.get("ADM2_CODE", ""),
                p.get("ADM2_NAME", "")
            ])
        csv_content = output.getvalue()
        output.close()
        return Response(content=csv_content, media_type="text/csv")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export GAUL Level2 CSV: {str(e)}")
