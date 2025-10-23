# KTV Multilayer Processing API

API untuk processing GeoJSON dengan 3 dataset (GFW, JRC, SBTN) dan generate statistik forest loss.

## Features

- Process GeoJSON files dengan multiple forest loss datasets
- Generate statistik loss area dan persentase
- Determine risk level berdasarkan loss area
- Find year dengan loss terbanyak
- Support untuk polygon analysis



## Endpoints

- `GET /` - Root endpoint dengan informasi API dan daftar endpoint
- `GET /health` - Health check (status API dan dependency)
- `POST /api/v1/upload-geojson` - Upload dan analisis GeoJSON untuk EUDR compliance (rounded)
- `POST /api/v1/upload-geojson-notrounded` - Upload dan analisis GeoJSON untuk EUDR compliance (nilai area/percent tidak dibulatkan)
- `POST /api/v1/multilayer_processing_ktv` - Analisis multilayer KTV (forest loss GFW, JRC, SBTN)
- `POST /api/v1/commodity_analysis?commodity=<rubber|cocoa|coffee|palm>` - Analisis binary zonal statistics untuk dataset komoditas (unggah GeoJSON, dapatkan pixel count, area hektar, tile URL)

- `POST /api/v1/process-geojson` - Analisis GeoJSON dengan parameter custom (advanced)
- `POST /api/v1/eudr-compliance` - Analisis compliance EUDR berbasis titik (buffer & risk assessment)
- `GET /api/v1/gee/datasets` - Daftar dataset GEE yang tersedia untuk tile service
- `GET /api/v1/gee/tiles/{dataset}/{z}/{x}/{y}` - Tile XYZ untuk visualisasi dataset GEE
- `GET /api/v1/gee/tiles/{dataset}` - Info tile dan template URL untuk dataset GEE
- `POST /api/v1/gee/refresh` - Refresh cache dataset GEE
- `GET /api/v1/gaul_level2_geojson` - Generate GeoJSON boundary dari ee.FeatureCollection("FAO/GAUL/2015/level2") (dengan filter ADM0/ADM1/ADM2)
### GAUL Level2 Boundary Endpoint

**GET /api/v1/gaul_level2_geojson?adm0_code=&adm1_code=&adm2_code=**

- Generate GeoJSON FeatureCollection dari boundary administratif FAO/GAUL/2015/level2.
- Mendukung filter: `adm0_code` (kode negara), `adm1_code`, `adm2_code` (opsional).
- Output: GeoJSON dengan field sesuai skema tabel GAUL (lihat tabel di bawah).

**Contoh request:**

```bash
curl -X GET 'https://ktv-multilayer-api.fly.dev/api/v1/gaul_level2_geojson?adm0_code=102&adm1_code=2001'
```

**Contoh response (schema):**
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { ... },
      "properties": {
        "ADM0_CODE": 102,
        "ADM0_NAME": "Indonesia",
        "DISP_AREA": "Tidak",
        "STATUS": "Negara",
        "Shape_Area": 123456.78,
        "Shape_Leng": 9876.54,
        "ADM1_CODE": 2001,
        "ADM1_NAME": "Jawa Barat",
        "ADM2_CODE": 30012,
        "ADM2_NAME": "Bandung",
        "EXP2_YEAR": 2025,
        "STR2_YEAR": 2001
      }
    }
  ]
}
```

**Field Schema:**

| Nama         | Jenis   | Deskripsi                                              |
|--------------|---------|--------------------------------------------------------|
| ADM0_CODE    | INT     | Kode negara GAUL                                       |
| ADM0_NAME    | STRING  | Nama negara PBB                                        |
| DISP_AREA    | STRING  | Wilayah yang belum stabil: 'Ya' atau 'Tidak'           |
| STATUS       | STRING  | Status negara                                          |
| Shape_Area   | DOUBLE  | Area bentuk                                            |
| Shape_Leng   | DOUBLE  | Panjang bentuk                                         |
| ADM1_CODE    | INT     | Kode GAUL unit administratif di tingkat pertama        |
| ADM1_NAME    | STRING  | Nama unit administratif di tingkat pertama             |
| ADM2_CODE    | INT     | Kode GAUL unit administratif di tingkat kedua          |
| ADM2_NAME    | STRING  | Nama unit administratif di tingkat kedua               |
| EXP2_YEAR    | INT     | Tahun masa habis berlaku unit administratif           |
| STR2_YEAR    | INT     | Tahun pembuatan unit administratif                    |


### Commodity Analysis Endpoint

**POST /api/v1/commodity_analysis?commodity=<rubber|cocoa|coffee|palm>**

- Upload GeoJSON (FeatureCollection/Feature) dan pilih komoditas.
- Mendukung: rubber, cocoa, coffee, palm.
- Output: jumlah piksel (10m) dengan probabilitas > 0.5, area hektar, error info, dan tile URL untuk visualisasi.

**Contoh request:**

```bash
curl -X POST \
  'https://ktv-multilayer-api.fly.dev/api/v1/commodity_analysis?commodity=rubber' \
  -F "file=@your-geojson-file.geojson"
```

**Contoh response:**
```json
{
  "status": "success",
  "message": "Commodity file processing completed for 'rubber'",
  "file_info": {
    "filename": "your-geojson-file.geojson",
    "size_mb": 0.12,
    "features_count": 1,
    "processed_at_utc": "2024-06-01T12:34:56.789Z"
  },
  "commodity": "rubber",
  "asset_id": "projects/forestdatapartnership/assets/rubber/model_2025a",
  "threshold": 0.5,
  "scale_m": 10,
  "tile_url": "https://earthengine.googleapis.com/v1alpha/projects/earthengine-legacy/maps/xyz...",
  "results": [
    {
      "feature_id": "feature_0",
      "commodity_pixel_count": 1234,
      "reduce_region_error": null,
      "used_bounds": false
    }
  ]
}
```

---

### Endpoint Lainnya

- **/api/v1/upload-geojson**: Upload GeoJSON, analisis compliance EUDR (rounded)
- **/api/v1/upload-geojson-notrounded**: Upload GeoJSON, analisis compliance EUDR (nilai tidak dibulatkan)
- **/api/v1/multilayer_processing_ktv**: Analisis multilayer forest loss (GFW, JRC, SBTN)
- **/api/v1/process-geojson**: Analisis GeoJSON dengan parameter custom
- **/api/v1/eudr-compliance**: Analisis compliance berbasis titik (buffer)
- **/api/v1/gee/datasets**: Daftar dataset GEE untuk tile
- **/api/v1/gee/tiles/{dataset}/{z}/{x}/{y}**: Tile XYZ GEE
- **/api/v1/gee/tiles/{dataset}**: Info tile dataset
- **/api/v1/gee/refresh**: Refresh cache dataset

## Deployment

### Local Development

```bash
pip install -r requirements.txt
python app.py
```

### Fly.io Deployment

```bash
# Login
flyctl auth login

# Launch
flyctl launch

# Set secrets
flyctl secrets set EE_SERVICE_ACCOUNT_PATH="/app/data/ee-service-account.json"

# Create volume
flyctl volumes create ktv_data --size 1

# Upload service account
flyctl ssh console
# Copy your EE service account JSON to /app/data/

# Deploy
flyctl deploy
```

## Usage

```bash
curl -X POST \
  https://ktv-multilayer-api.fly.dev/api/v1/multilayer_processing_ktv \
  -F "file=@your-geojson-file.geojson"
```

## Response Format

```json
{
  "status": "success",
  "message": "KTV multilayer processing completed",
  "data": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "properties": {
          "plot_id": "PLOT_001",
          "gfw_loss_stat": "high",
          "gfw_loss_percent": 5.67,
          "gfw_loss_area": 12.34,
          "gfw_loss_year_compilation": 2022,
          "jrc_loss_stat": "low",
          "jrc_loss_percent": 0.23,
          "jrc_loss_area": 0.45,
          "jrc_loss_year_compilation": 2021,
          "sbtn_loss_stat": "high",
          "sbtn_loss_percent": 3.45,
          "sbtn_loss_area": 7.89,
          "sbtn_loss_year_compilation": 2023
        },
        "geometry": {...}
      }
    ]
  }
}
```