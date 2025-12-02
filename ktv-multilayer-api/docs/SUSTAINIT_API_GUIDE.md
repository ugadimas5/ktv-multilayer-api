# Sustainit API Documentation

Complete guide for using Sustainit environmental compliance endpoints.

## Base URL

- **Production**: `https://api.sustainit.id`
- **Development**: `http://localhost:8000`

## Authentication

Currently, all endpoints are open access. No API key required.

---

## 📍 Endpoints Overview

All Sustainit endpoints are tagged with `sustainit` and follow the pattern `/api/v1/{endpoint-name}`.

| Endpoint | Method | Description | Use Case |
|----------|--------|-------------|----------|
| `/protected-area` | POST | Protected area intersection analysis | WDPA compliance checking |
| `/deforestation` | POST | Deforestation risk assessment | EUDR forest loss analysis |
| `/validate-geometry` | POST | Geometry quality validation | Data quality assurance |
| `/rainfall` | POST | Rainfall statistics analysis | Agricultural planning |
| `/ghg-emission` | POST | GHG emission calculation | Carbon accounting |

---

## 1. Protected Area Analysis

**Endpoint**: `POST /api/v1/protected-area`

Analyzes GeoJSON features for intersection with World Database on Protected Areas (WDPA).

### Request

```bash
curl -X POST "https://api.sustainit.id/api/v1/protected-area" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your_plots.geojson"
```

### Request Body
- **file**: GeoJSON file (max 50MB)
- Supported geometry: Polygon, MultiPolygon, Point, LineString

### Response

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
    "features": [{
      "type": "Feature",
      "properties": {
        "wdpa_status": "compliant",
        "wdpa_categories": [],
        "analysis_timestamp": "2025-12-02T08:00:00Z"
      },
      "geometry": {...}
    }]
  }
}
```

### WDPA Status Classification

- **compliant**: No protected area intersection or only sustainable use zones (V, VI)
- **indicative**: Protected area with unclear status (Not Assigned, Not Reported)
- **non-compliant**: Intersection with strict protection zones (Ia, Ib, II, III, IV)

### IUCN Categories

| Category | Description | Status |
|----------|-------------|--------|
| Ia, Ib | Strict Nature Reserve, Wilderness Area | Non-compliant |
| II | National Park | Non-compliant |
| III | Natural Monument | Non-compliant |
| IV | Habitat/Species Management Area | Non-compliant |
| V | Protected Landscape/Seascape | Indicative |
| VI | Managed Resource Protected Area | Indicative |

---

## 2. Deforestation Analysis

**Endpoint**: `POST /api/v1/deforestation`

Analyzes forest loss using GFW, JRC, and SBTN satellite datasets (2021-2024).

### Request

```bash
curl -X POST "https://api.sustainit.id/api/v1/deforestation" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your_plots.geojson"
```

### Request Body
- **file**: GeoJSON file (max 50MB)
- Supported geometry: Polygon, MultiPolygon

### Response

```json
{
  "status": "success",
  "file_info": {
    "filename": "plots.geojson",
    "size_mb": 3.2,
    "features_count": 50
  },
  "analysis_summary": {
    "total_processed": 50,
    "high_risk": 8,
    "low_risk": 42,
    "processing_time_seconds": 120.5
  },
  "data": {
    "type": "FeatureCollection",
    "features": [{
      "type": "Feature",
      "properties": {
        "gfw_loss_area_ha": 2.5,
        "gfw_loss_percent": 5.2,
        "jrc_loss_area_ha": 1.8,
        "jrc_loss_percent": 3.7,
        "sbtn_loss_area_ha": 2.1,
        "sbtn_loss_percent": 4.3,
        "risk_level": "High",
        "analysis_timestamp": "2025-12-02T08:00:00Z"
      },
      "geometry": {...}
    }]
  }
}
```

### Risk Classification

- **High Risk**: Any loss detected > 0 hectares (non-EUDR compliant)
- **Low Risk**: No loss detected (EUDR compliant)

### Datasets Used

| Dataset | Period | Resolution | Description |
|---------|--------|------------|-------------|
| **GFW Loss** | 2021-2024 | 30m | Global Forest Watch |
| **JRC Loss** | 2021-2024 | 10m | Joint Research Centre |
| **SBTN Loss** | 2021-2024 | 10m | Science Based Targets |

---

## 3. Geometry Validation

**Endpoint**: `POST /api/v1/validate-geometry`

Validates geometry quality for uploaded GeoJSON features.

### Request

```bash
curl -X POST "https://api.sustainit.id/api/v1/validate-geometry" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your_plots.geojson"
```

### Request Body
- **file**: GeoJSON file (max 50MB)
- Supported geometry: Polygon, MultiPolygon

### Response

```json
{
  "status": "success",
  "file_info": {
    "filename": "plots.geojson",
    "size_mb": 1.8,
    "features_count": 75
  },
  "analysis_summary": {
    "total_processed": 75,
    "valid": 68,
    "invalid": 7,
    "processing_time_seconds": 3.2
  },
  "data": {
    "type": "FeatureCollection",
    "features": [{
      "type": "Feature",
      "properties": {
        "validation_status": "valid",
        "is_valid": true,
        "self_intersection": false,
        "duplicate_vertices": false,
        "zero_area": false,
        "not_ring": false,
        "issues": [],
        "area_sqm": 25000.5
      },
      "geometry": {...}
    }]
  }
}
```

### Validation Checks

| Check | Description | Impact |
|-------|-------------|--------|
| **is_valid** | Overall geometry validity | Critical |
| **self_intersection** | Polygon intersects itself | High |
| **duplicate_vertices** | Repeated coordinate points | Medium |
| **zero_area** | Polygon with no/minimal area | High |
| **not_ring** | Unclosed polygon boundary | Critical |

---

## 4. Rainfall Analysis

**Endpoint**: `POST /api/v1/rainfall`

Calculates rainfall statistics using CHIRPS daily data downscaled to 100m resolution.

### Request

```bash
curl -X POST "https://api.sustainit.id/api/v1/rainfall" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your_plots.geojson"
```

### Request Body
- **file**: GeoJSON file (max 50MB)
- Supported geometry: Polygon, MultiPolygon, Point, LineString

### Response

```json
{
  "status": "success",
  "file_info": {
    "filename": "plots.geojson",
    "size_mb": 2.1,
    "features_count": 60
  },
  "analysis_summary": {
    "total_processed": 60,
    "average_rainfall_mm": 450.5,
    "processing_time_seconds": 180.3
  },
  "data": {
    "type": "FeatureCollection",
    "features": [{
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
        },
        "data_source": "CHIRPS Daily (downscaled to 100m)",
        "resolution": "100m"
      },
      "geometry": {...}
    }]
  }
}
```

### Data Source

- **Dataset**: CHIRPS Daily (UCSB-CHG/CHIRPS/DAILY)
- **Original Resolution**: ~5.5km (0.05 degrees)
- **Downscaled Resolution**: 100 meters
- **Method**: Bilinear interpolation with Sentinel-2 projection
- **Default Period**: 2023-10-01 to 2024-01-31 (3 months)

### Use Cases

- Agricultural water availability assessment
- Drought risk analysis
- Irrigation planning
- Crop suitability evaluation

---

## 5. GHG Emission Calculation

**Endpoint**: `POST /api/v1/ghg-emission`

Calculates greenhouse gas emissions from deforestation using IPCC guidelines.

### Request

```bash
curl -X POST "https://api.sustainit.id/api/v1/ghg-emission" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your_plots.geojson"
```

### Request Body
- **file**: GeoJSON file (max 50MB)
- Supported geometry: Polygon, MultiPolygon
- Optional property in GeoJSON: `forest_type` ("Primary Forest" or "Secondary Forest")

### Response

```json
{
  "status": "success",
  "file_info": {
    "filename": "plots.geojson",
    "size_mb": 2.8,
    "features_count": 40
  },
  "analysis_summary": {
    "total_processed": 40,
    "high_risk": 12,
    "low_risk": 28,
    "total_deforestation_area_ha": 45.5,
    "total_net_emission_tco2e": 12450.75,
    "datasets": {
      "gfw": {
        "total_area_ha": 18.5,
        "total_emission_tco2e": 5200.5
      },
      "jrc": {
        "total_area_ha": 15.0,
        "total_emission_tco2e": 4100.25
      },
      "sbtn": {
        "total_area_ha": 12.0,
        "total_emission_tco2e": 3150.0
      }
    },
    "processing_time_seconds": 240.8
  },
  "data": {
    "type": "FeatureCollection",
    "features": [{
      "type": "Feature",
      "properties": {
        "gfw_loss_area_ha": 2.5,
        "gfw_ghg_emission": {
          "area_hectares": 2.5,
          "forest_type": "Secondary Forest",
          "gross_co2_tco2e": 700.0,
          "gross_n2o_tco2e": 0.52,
          "gross_ch4_tco2e": 0.08,
          "total_gross_emission_tco2e": 700.6,
          "soc_emission_tco2e": 65.0,
          "gross_emission_with_soc_tco2e": 765.6,
          "post_carbon_stock_tc": 142.5,
          "net_emission_tco2e": 623.1,
          "emission_intensity_tco2e_per_ha": 249.24
        },
        "jrc_ghg_emission": {...},
        "sbtn_ghg_emission": {...},
        "total_net_emission_tco2e": 1540.25,
        "forest_type": "Secondary Forest"
      },
      "geometry": {...}
    }]
  }
}
```

### Emission Components

| Component | Description | Unit |
|-----------|-------------|------|
| **Gross CO2** | CO2 from biomass loss | tCO2e |
| **Gross N2O** | N2O from biomass burning | tCO2e |
| **Gross CH4** | CH4 from biomass burning | tCO2e |
| **SOC Emission** | Soil organic carbon loss | tCO2e |
| **Post Carbon Stock** | Carbon in post land-use | tC |
| **Net Emission** | Total - Post carbon stock | tCO2e |

### Calculation Parameters

Based on IPCC guidelines with default parameters:

| Parameter | Primary Forest | Secondary Forest |
|-----------|----------------|------------------|
| **Forest Biomass** | 520 tCO2e/ha | 280 tCO2e/ha |
| **Burning Efficiency** | 0.5 (50%) | 0.5 (50%) |
| **Combustion Factor** | 0.5 | 0.5 |
| **SOC Constant** | 26 tCO2e/ha | 26 tCO2e/ha |
| **Post AGB** | 47 tC/ha | 47 tC/ha |
| **Post BGB** | 10 tC/ha | 10 tC/ha |

### Process Flow

1. **Step 1**: Calculate deforestation areas (GFW, JRC, SBTN)
2. **Step 2**: Calculate GHG emissions for each detected deforestation area
3. **Step 3**: Aggregate total emissions per feature and dataset

---

## Common Parameters

### File Upload Requirements

| Parameter | Specification |
|-----------|--------------|
| **Max File Size** | 50 MB |
| **Formats** | .geojson, .json |
| **Encoding** | UTF-8 |
| **Geometry Types** | Polygon, MultiPolygon (Point, LineString for some endpoints) |
| **Coordinate System** | WGS84 (EPSG:4326) |

### Response Format

All endpoints return standardized response structure:

```json
{
  "status": "success" | "error",
  "message": "Description",
  "file_info": {...},
  "analysis_summary": {...},
  "data": {...},
  "metadata": {...}
}
```

---

## Error Handling

### Common Error Codes

| HTTP Code | Error | Description |
|-----------|-------|-------------|
| 400 | Bad Request | Invalid JSON or GeoJSON format |
| 413 | Payload Too Large | File exceeds 50MB limit |
| 422 | Validation Error | Invalid geometry or parameters |
| 500 | Internal Server Error | Processing failed |

### Error Response Example

```json
{
  "detail": "File too large: 55.2MB. Max: 50MB"
}
```

---

## Rate Limits

Currently no rate limits enforced. Fair use policy applies.

---

## Example Usage with Python

```python
import requests

# Upload GeoJSON for deforestation analysis
url = "https://api.sustainit.id/api/v1/deforestation"
files = {"file": open("plots.geojson", "rb")}

response = requests.post(url, files=files)
result = response.json()

print(f"Total processed: {result['analysis_summary']['total_processed']}")
print(f"High risk: {result['analysis_summary']['high_risk']}")
```

## Example Usage with cURL

```bash
# Protected Area Analysis
curl -X POST "https://api.sustainit.id/api/v1/protected-area" \
  -F "file=@plots.geojson" \
  -o protected_area_result.json

# Deforestation Analysis
curl -X POST "https://api.sustainit.id/api/v1/deforestation" \
  -F "file=@plots.geojson" \
  -o deforestation_result.json

# Geometry Validation
curl -X POST "https://api.sustainit.id/api/v1/validate-geometry" \
  -F "file=@plots.geojson" \
  -o validation_result.json

# Rainfall Analysis
curl -X POST "https://api.sustainit.id/api/v1/rainfall" \
  -F "file=@plots.geojson" \
  -o rainfall_result.json

# GHG Emission Calculation
curl -X POST "https://api.sustainit.id/api/v1/ghg-emission" \
  -F "file=@plots.geojson" \
  -o ghg_emission_result.json
```

---

## Support & Contact

- **API Documentation**: https://api.sustainit.id/docs
- **Interactive Testing**: https://api.sustainit.id/docs (Swagger UI)
- **Alternative Docs**: https://api.sustainit.id/redoc

---

## Version History

- **v2.1.0** (2025-12-02): Initial Sustainit endpoints release
  - Protected Area Analysis
  - Deforestation Analysis
  - Geometry Validation
  - Rainfall Analysis
  - GHG Emission Calculation

---

## License

Commercial License - © 2025 Sustainit
