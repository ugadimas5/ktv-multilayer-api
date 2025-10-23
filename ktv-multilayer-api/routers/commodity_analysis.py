import os
import json
import tempfile
from datetime import datetime
from typing import Optional, List, Dict, Any

import ee
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse
from loguru import logger

from authentication.auth_helper import auth_init_ee

router = APIRouter()

# === Konstanta & Konfigurasi ===
DATA_ASSET_MAP: Dict[str, str] = {
    "rubber": "projects/forestdatapartnership/assets/rubber/model_2025a",
    "cocoa":  "projects/forestdatapartnership/assets/cocoa/model_2025a",
    "coffee": "projects/forestdatapartnership/assets/coffee/model_2025a",
    "palm":   "projects/forestdatapartnership/assets/palm/model_2025a",
}
MAX_UPLOAD_MB = 50
BAND_NAME = "probability"
THRESHOLD = 0.5
SCALE_M = 10


@router.post("/commodity_analysis", tags=["Commodity Analysis"])
async def commodity_analysis(
    file: UploadFile = File(...),
    commodity: str = Query(..., description="Commodity type: rubber, cocoa, coffee, palm"),
):
    """
    Upload dan analisis GeoJSON menggunakan dataset komoditas terpilih.
    Menghitung jumlah piksel (10m) yang melebihi ambang probabilitas, dan
    mengembalikan tile URL untuk visualisasi (mask transparan untuk nilai 0).
    """
    if commodity not in DATA_ASSET_MAP:
        raise HTTPException(status_code=400, detail=f"Invalid commodity: {commodity}")

    logger.info(f"[{datetime.utcnow().isoformat()}] Start analysis: commodity='{commodity}' filename='{file.filename}'")

    tmp_path: Optional[str] = None
    features: List[Dict[str, Any]] = []
    file_size_mb: float = 0.0
    asset_id = DATA_ASSET_MAP[commodity]

    try:
        # --- Earth Engine auth via service account ---
        service_account_path = os.getenv("EE_SINGLE_SERVICE_ACCOUNT_PATH")
        if not service_account_path:
            raise HTTPException(status_code=500, detail="EE_SINGLE_SERVICE_ACCOUNT_PATH not set in environment")

        # Gunakan profil yang sama dengan endpoint lain (mis. 'eudr-1')
        auth_init_ee("eudr-1", auth_path=os.path.dirname(service_account_path), print_status=False)
        logger.info("Earth Engine authenticated for /commodity_analysis")

        # --- Baca file upload ke memori & cek ukuran ---
        contents = await file.read()
        file_size_mb = len(contents) / (1024 * 1024)
        if file_size_mb > MAX_UPLOAD_MB:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: {file_size_mb:.1f}MB. Max: {MAX_UPLOAD_MB}MB"
            )

        # Simpan ke file sementara (memudahkan debugging & cleanup)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".geojson") as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        logger.info(f"Saved upload to {tmp_path} ({file_size_mb:.2f} MB)")

        # --- Parse & validasi GeoJSON ---
        try:
            geojson_data = json.loads(contents.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

        gtype = geojson_data.get("type")
        if gtype not in {"FeatureCollection", "Feature"}:
            raise HTTPException(status_code=400, detail="Invalid GeoJSON: must be Feature or FeatureCollection")

        if gtype == "FeatureCollection":
            feats = geojson_data.get("features")
            if not isinstance(feats, list) or len(feats) == 0:
                raise HTTPException(status_code=400, detail="FeatureCollection has no features")
            features = feats
        else:
            features = [geojson_data]  # Single Feature

        # --- Build commodity image ---
        # Coba sebagai ImageCollection (mosaic), fallback ke Image tunggal
        try:
            img = ee.ImageCollection(asset_id).mosaic().select(BAND_NAME)
        except Exception:
            img = ee.Image(asset_id).select(BAND_NAME)

        binary_image = img.gt(THRESHOLD)

        # --- Generate tile layer URL for visualization ---
        # Gunakan selfMask() agar piksel 0 transparan; hanya 1 yang berwarna.
        try:
            viz_image = binary_image.selfMask()
            map_id_dict = viz_image.getMapId({
                "min": 1,
                "max": 1,
                "palette": ["FF0000"],  # merah untuk piksel bernilai 1
            })
            tile_url = map_id_dict["tile_fetcher"].url_format
        except Exception as e:
            logger.warning(f"Failed to generate tile URL: {e}")
            tile_url = None

        # --- Zonal stats per feature ---
        results: List[Dict[str, Any]] = []
        for idx, feature in enumerate(features):
            fid = feature.get("id", f"feature_{idx}")
            geom = feature.get("geometry")

            if not geom or "type" not in geom or "coordinates" not in geom:
                logger.error(f"Feature {fid} missing/invalid geometry")
                results.append({
                    "feature_id": fid,
                    "commodity_pixel_count": 0,
                    "reduce_region_error": "Invalid or missing geometry"
                })
                continue

            # Normalisasi Polygon -> MultiPolygon untuk robust
            if geom["type"] == "Polygon":
                geom = {"type": "MultiPolygon", "coordinates": [geom["coordinates"]]}

            # Jika geometri bukan (Multi)Polygon, fallback ke bounds()
            if geom["type"] not in {"MultiPolygon", "Polygon"}:
                try:
                    aoi = ee.Geometry(geom).bounds()
                    used_bounds = True
                except Exception as e:
                    logger.error(f"Feature {fid} geometry error: {e}")
                    results.append({
                        "feature_id": fid,
                        "commodity_pixel_count": 0,
                        "reduce_region_error": f"Geometry error: {str(e)}"
                    })
                    continue
            else:
                aoi = ee.Geometry(geom)
                used_bounds = False

            stat = None
            error_msg = None
            try:
                stat = binary_image.reduceRegion(
                    reducer=ee.Reducer.sum(),
                    geometry=aoi,
                    scale=SCALE_M,
                    maxPixels=1e13,
                    bestEffort=True,
                ).getInfo()
            except Exception as e:
                error_msg = f"reduceRegion failed on geometry: {str(e)}"
                logger.warning(error_msg)
                # Fallback: gunakan bounds
                try:
                    stat = binary_image.reduceRegion(
                        reducer=ee.Reducer.sum(),
                        geometry=aoi.bounds(),
                        scale=SCALE_M,
                        maxPixels=1e13,
                        bestEffort=True,
                    ).getInfo()
                except Exception as e2:
                    error_msg = f"reduceRegion failed on bounds: {str(e2)}"
                    logger.error(error_msg)

            # Ambil nilai band (jumlah piksel 1); coercion aman ke int
            value = 0
            if stat and isinstance(stat, dict):
                v = stat.get(BAND_NAME, 0)
                try:
                    value = int(v) if v is not None else 0
                except Exception:
                    value = int(float(v)) if v is not None else 0
            else:
                logger.error(f"reduceRegion returned empty/None for feature {fid}")

            results.append({
                "feature_id": fid,
                "commodity_pixel_count": value,
                "reduce_region_error": error_msg if (error_msg or value == 0) else None,
                "used_bounds": used_bounds,
            })

        logger.success("Commodity analysis completed")

        response_data = {
            "status": "success",
            "message": f"Commodity file processing completed for '{commodity}'",
            "file_info": {
                "filename": file.filename,
                "size_mb": round(file_size_mb, 2),
                "features_count": len(features),
                "processed_at_utc": datetime.utcnow().isoformat(),
            },
            "commodity": commodity,
            "asset_id": asset_id,
            "threshold": THRESHOLD,
            "scale_m": SCALE_M,
            "tile_url": tile_url,  # ditambahkan untuk visualisasi
            "results": results,
        }
        logger.info(f"Response summary: features={len(features)}")
        return JSONResponse(content=response_data)

    except HTTPException:
        # Error terstruktur, propagate apa adanya
        raise
    except Exception as e:
        logger.exception(f"Commodity analysis error: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    finally:
        # Pastikan file temp dibersihkan
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
                logger.debug(f"Temp file removed: {tmp_path}")
            except Exception as e:
                logger.warning(f"Failed to remove temp file {tmp_path}: {e}")
