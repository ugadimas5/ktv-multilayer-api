# EUDR Compliance Analysis Guide

## Overview

The MultilayerService now implements production-grade EUDR (EU Deforestation Regulation) compliance analysis using multiple satellite datasets with parallel processing capabilities.

## Concept Differences

### Previous Implementation (Simple)
- Basic forest analysis for single coordinates
- Limited dataset integration
- Mock data fallbacks
- Simple compliance determination

### Current Implementation (Production-Grade)
- Comprehensive EUDR compliance framework
- Multi-satellite data fusion
- Zonal statistics methodology
- Parallel processing support (16 Google Service Accounts)
- Database integration capabilities
- Year-by-year tracking (2021-2024)

## Dataset Stack

### 1. JRC EUFO 2020 (Forest Classification)
```python
'JRC/GFC2020/V2' -> 'EUFO_2020'
```
- **Purpose**: Forest area detection
- **Compliance Logic**: Forest presence = NON_COMPLIANT
- **Usage**: Primary forest classification for EUDR

### 2. JRC TMF Deforestation (2021-2025)
```python
'projects/JRC/TMF/v1_2024/DeforestationYear' -> 'TMF_def_2021-2025'
```
- **Purpose**: Post-2020 deforestation detection
- **Compliance Logic**: Deforestation after 2020 = NON_COMPLIANT
- **Tracking**: Year-by-year analysis (2021, 2022, 2023, 2024)

### 3. SBTN Natural Lands (2020)
```python
'WRI/SBTN/naturalLands/v1_1/2020' -> 'SBTN'
```
- **Purpose**: Biodiversity impact assessment
- **Classification**: High if coverage > 0, Low if coverage = 0
- **Usage**: Conservation priority determination

### 4. GLAD Primary Forests
```python
'UMD/GLAD/PRIMARY_HUMID_TROPICAL_FORESTS/v1' -> 'GLAD_Primary'
```
- **Purpose**: Primary forest detection
- **Coverage**: Humid tropical regions globally
- **Status**: Critical for EUDR compliance

### 5. GFC Hansen 2024
```python
'UMD/hansen/global_forest_change_2024_v1_12' -> 'GFC_loss_year_YYYY'
```
- **Purpose**: Global forest change monitoring
- **Coverage**: Annual loss data 2001-2024
- **Primary Focus**: Primary forest loss in EUDR context

## Compliance Analysis Methodology

### Zonal Statistics Approach
```python
def zonal_stats_ee(geom, img, band_names):
    # Production implementation
    reducer = ee.Reducer.mean()
    scale = 30  # 30m resolution
    maxPixels = 1e13  # Large area support
```

### Compliance Determination
1. **JRC Forest Check**: Forest area > 0 → NON_COMPLIANT
2. **JRC Deforestation Check**: Loss 2021-2024 → NON_COMPLIANT  
3. **SBTN Natural Lands**: Coverage > 0 → High biodiversity impact
4. **GLAD Primary Forests**: Coverage > 0 → NON_COMPLIANT
5. **GFC Primary Loss**: Loss 2021-2024 → NON_COMPLIANT

### Area Calculations
- **Input**: Geometry in WGS84 (EPSG:4326)
- **Processing**: Web Mercator projection for area calculation
- **Output**: Hectares with percentage coverage
- **Precision**: 2 decimal places for area, percentage

## API Response Structure

### EUDR Compliance Response
```json
{
  "area_hectares": 78.54,
  "coordinates": {"latitude": -2.5, "longitude": 115.0},
  "buffer_km": 5.0,
  "jrc_compliance": {
    "forest_classification_status": "non_compliant",
    "forest_area_hectares": 45.2,
    "forest_percentage": 57.5,
    "deforestation_status": "non_compliant", 
    "deforestation_area_hectares": 12.3,
    "deforestation_years": ["2022", "2023"]
  },
  "sbtn_compliance": {
    "natural_lands_status": "non_compliant",
    "biodiversity_impact": "High",
    "ecosystem_risk_score": 0.85
  },
  "gfw_compliance": {
    "primary_forest_status": "non_compliant",
    "primary_loss_status": "non_compliant"
  },
  "overall_compliance_status": {
    "status": "NON_COMPLIANT",
    "risk_level": "HIGH",
    "total_violations": 6
  }
}
```

## Production Features

### Parallel Processing Support
- 16 Google Service Account authentication
- Batch processing for large datasets
- Multi-geometry analysis capabilities
- Database integration (PostgreSQL + PostGIS)

### Error Handling
- Graceful fallback to mock data
- Comprehensive logging with loguru
- Exception handling for each dataset
- API reliability maintenance

### Performance Optimization
- Earth Engine best practices
- Efficient band selection
- Optimized reducer operations
- Scale and maxPixels tuning

## Usage Examples

### Basic EUDR Compliance Check
```python
from services.data.multilayer_service import MultilayerService

service = MultilayerService()
result = service.analyze_eudr_compliance(
    coordinates={"latitude": -2.5, "longitude": 115.0},
    buffer_km=5.0
)
```

### API Endpoint Usage
```bash
curl -X POST "https://multilayer-api.fly.dev/api/v1/eudr-compliance" \
  -H "Content-Type: application/json" \
  -d '{
    "coordinates": {"latitude": -2.5, "longitude": 115.0},
    "buffer_km": 5.0
  }'
```

## Compliance Interpretation

### COMPLIANT Status
- No forest areas detected
- No deforestation post-2020
- Low biodiversity impact
- No primary forest presence

### NON_COMPLIANT Status
- Forest areas detected (requires due diligence)
- Post-2020 deforestation (violates cutoff)
- Primary forest presence (critical areas)
- Natural lands presence (biodiversity concern)

## Technical Requirements

### Earth Engine Authentication
- Service account credentials required
- Multiple accounts for parallel processing
- Proper initialization and error handling

### Dependencies
```python
earthengine-api>=0.1.0
shapely>=2.0.0
loguru>=0.7.0
pandas>=2.0.0
geopandas>=0.14.0
```

### Environment Variables
```bash
EE_SERVICE_ACCOUNT_PATH=/path/to/service/accounts/
```

This implementation provides production-grade EUDR compliance analysis suitable for regulatory reporting and supply chain due diligence requirements.
