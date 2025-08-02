# KTV Multilayer Processing API

API untuk processing GeoJSON dengan 3 dataset (GFW, JRC, SBTN) dan generate statistik forest loss.

## Features

- Process GeoJSON files dengan multiple forest loss datasets
- Generate statistik loss area dan persentase
- Determine risk level berdasarkan loss area
- Find year dengan loss terbanyak
- Support untuk polygon analysis

## Endpoints

- `GET /` - Root endpoint dengan informasi API
- `GET /health` - Health check
- `POST /api/v1/multilayer_processing_ktv` - Main processing endpoint

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