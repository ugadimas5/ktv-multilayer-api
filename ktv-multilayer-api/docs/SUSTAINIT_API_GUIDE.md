# Sustainit API Documentation

Complete guide for using Sustainit environmental compliance endpoints.

## Base URL

- **Production**: `https://api.sustainit.id`
- **Development**: `http://localhost:8000`

## Authentication

Currently, all endpoints are open access. No API key required.

---

## 📍 Endpoints Overview

Every endpoint returns `data` as a FeatureCollection with exactly one feature per input
feature, in input order, keeping the input properties (e.g. `plot_id`, `name`) and adding
the analysis fields. Errors are returned as non-2xx statuses (see Error Handling).

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
- **file**: GeoJSON FeatureCollection (max 100MB, 1000 features)
- Supported geometry: Polygon, MultiPolygon

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
        "plot_id": "plot-0",
        "wdpa_status": "compliant",
        "wdpa_categories": []
      },
      "geometry": {...}
    }]
  }
}
```

### WDPA Status Classification

- **compliant**: No protected area intersection
- **indicative**: Intersection with sustainable use zones (V, VI) or areas with unclear status (Not Assigned, Not Reported, Not Applicable)
- **non_compliant**: Intersection with strict protection zones (Ia, Ib, II, III, IV)

### IUCN Categories

| Category | Description | Status |
|----------|-------------|--------|
| Ia, Ib | Strict Nature Reserve, Wilderness Area | non_compliant |
| II | National Park | non_compliant |
| III | Natural Monument | non_compliant |
| IV | Habitat/Species Management Area | non_compliant |
| V | Protected Landscape/Seascape | indicative |
| VI | Managed Resource Protected Area | indicative |

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
- **file**: GeoJSON FeatureCollection (max 100MB, 1000 features)
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
        "plot_id": "plot-0",
        "total_area_hectares": 48.1,
        "overall_compliance": {
          "overall_risk": "high",
          "compliance_status": "NON_COMPLIANT",
          "high_risk_datasets": ["GFW Forest Loss", "JRC Forest Loss", "SBTN Natural Lands Loss"],
          "total_high_risk_indicators": 3
        },
        "gfw_loss": {"gfw_loss_stat": "high", "gfw_loss_area": 2.5, "gfw_loss_percent": 5.2, "gfw_loss_year_compilation": 2023},
        "jrc_loss": {"jrc_loss_stat": "high", "jrc_loss_area": 1.8, "jrc_loss_percent": 3.7, "jrc_loss_year_compilation": 2022},
        "sbtn_loss": {"sbtn_loss_stat": "high", "sbtn_loss_area": 2.1, "sbtn_loss_percent": 4.3, "sbtn_loss_year_compilation": 2023}
      },
      "geometry": {...}
    }]
  }
}
```

### Risk Classification

Loss areas are in hectares (pixel-area weighted), percentages are 0-100 of the plot area.

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
- **file**: GeoJSON FeatureCollection (max 100MB, 1000 features)
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
        "plot_id": "plot-0",
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
| **zero_area** | Polygon with no/minimal area (< 1 m²) | High |
| **not_ring** | Unclosed ring, fewer than 4 positions, or malformed/out-of-range coordinates | Critical |

`area_sqm` is the geodesic (WGS84) area in m². The input geometry is returned unchanged.

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
- **file**: GeoJSON FeatureCollection (max 100MB, 1000 features)
- Supported geometry: Polygon, MultiPolygon

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
    "average_rainfall_mm": 2450.3,
    "processing_time_seconds": 180.3
  },
  "data": {
    "type": "FeatureCollection",
    "features": [{
      "type": "Feature",
      "properties": {
        "plot_id": "plot-0",
        "rainfall_mean_mm": 2450.3,
        "rainfall_min_mm": 2300.1,
        "rainfall_max_mm": 2600.8,
        "rainfall_std_mm": 45.2,
        "area_hectares": 25.5,
        "analysis_period": {
          "start_date": "2025-01-01",
          "end_date": "2025-12-31"
        },
        "data_source": "CHIRPS Pentad (annual total, bilinear-resampled)"
      },
      "geometry": {...}
    }]
  }
}
```

### Data Source

- **Dataset**: CHIRPS Pentad (UCSB-CHG/CHIRPS/PENTAD)
- **Original Resolution**: ~5.5km (0.05 degrees), bilinear-resampled and reduced at 30 m
- **Statistic**: Annual rainfall total (mm); mean/min/max/std over the plot
- **Period**: Latest complete calendar year (the previous year from March onwards)
- **Coverage**: 50°S-50°N; values are `null` outside it

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
- **file**: GeoJSON FeatureCollection (max 100MB, 1000 features)
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
    "total_net_emission_tco2e": 12450.75,
    "processing_time_seconds": 40.8
  },
  "data": {
    "type": "FeatureCollection",
    "features": [{
      "type": "Feature",
      "properties": {
        "plot_id": "plot-0",
        "gfw_ghg_emission": {
          "area_hectares": 2.5,
          "forest_type": "Secondary Forest",
          "gross_co2_tco2e": 700.0,
          "gross_n2o_tco2e": 0.0013,
          "gross_ch4_tco2e": 0.0001,
          "total_gross_emission_tco2e": 700.0014,
          "soc_emission_tco2e": 65.0,
          "gross_emission_with_soc_tco2e": 765.0014,
          "post_carbon_stock_tc": 142.5,
          "net_emission_tco2e": 622.5014,
          "emission_intensity_tco2e_per_ha": 249.0006
        },
        "jrc_ghg_emission": {...},
        "sbtn_ghg_emission": {...},
        "total_net_emission_tco2e": 622.5014,
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
3. **Step 3**: `total_net_emission_tco2e` per feature is the largest of the three datasets (they overlap, so they are not summed)

---

## Common Parameters

### File Upload Requirements

| Parameter | Specification |
|-----------|--------------|
| **Max File Size** | 100 MB (max 1000 features) |
| **Formats** | .geojson, .json |
| **Encoding** | UTF-8 |
| **Geometry Types** | Polygon, MultiPolygon |
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
| 413 | Payload Too Large | File exceeds 100MB or 1000 features |
| 422 | Validation Error | A feature has a missing or malformed polygon (analysis endpoints) |
| 500 | Internal Server Error | Processing failed |
| 502 | Bad Gateway | Earth Engine returned an error |
| 503 | Service Unavailable | Earth Engine could not be initialized |

### Error Response Example

```json
{
  "detail": "File too large: 105.2MB. Max: 100MB"
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
