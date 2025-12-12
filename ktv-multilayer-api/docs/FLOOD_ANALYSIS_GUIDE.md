# Flood Analysis API Guide

## Overview

The Flood Analysis API provides satellite-based flood detection and monitoring using Sentinel-1 radar imagery. The API analyzes historical flood patterns (2016-2023) and generates flood hazard maps, permanent water detection, and statistical analysis.

## Key Features

- **Multi-year flood analysis** (2016-2023)
- **Flood hazard mapping** with index values (0-1)
- **Permanent water body detection**
- **Seasonal comparison** (wet vs dry season)
- **Map tile generation** for web visualization
- **Statistical analysis** with area calculations

## Data Source

- **Satellite**: Sentinel-1 GRD (Ground Range Detected)
- **Polarization**: VV (Vertical-Vertical)
- **Processing**: 10th percentile composite with 50m speckle filtering
- **Water Threshold**: -15 dB

## Methodology

### Flood Detection Algorithm

1. **Seasonal Water Masking**
   - Wet Season: December (12-01 to 12-31)
   - Dry Season: August (08-01 to 08-31)
   - Extract VV band from Sentinel-1
   - Apply 10th percentile reducer
   - Speckle filter with 50m focal mean
   - Threshold at -15 dB for water detection

2. **Flood Classification**
   - Flood = Water present in wet season AND absent in dry season
   - This identifies temporary flooding events

3. **Flood Hazard Index**
   - Sum of flood occurrences across years
   - Divided by total years analyzed
   - Result: 0 (never flooded) to 1 (floods every year)

4. **Permanent Water**
   - Areas with water in all seasons/years
   - Excludes flood-prone areas

## Available Endpoints

### 1. Get Available Datasets

```http
GET /api/v1/gee/flood/datasets
```

Returns list of available flood datasets with metadata.

**Response:**
```json
{
  "status": "success",
  "total_datasets": 5,
  "datasets": {
    "flood_hazard": {
      "name": "Flood Hazard Index",
      "description": "Composite flood hazard index (0-1) showing flood frequency across analysis years",
      "type": "continuous",
      "years": [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023]
    },
    "permanent_water": {
      "name": "Permanent Water Bodies",
      "description": "Areas identified as permanent water across all analysis periods",
      "type": "binary"
    },
    "flood_2023": {
      "name": "Flood 2023",
      "description": "Flood areas detected in 2023",
      "type": "binary"
    }
  },
  "supported_years": [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023],
  "season_config": {
    "wet_season": "December (12-01 to 12-31)",
    "dry_season": "August (08-01 to 08-31)"
  }
}
```

### 2. Get Map Tiles

```http
GET /api/v1/gee/flood/tiles/{dataset}/{z}/{x}/{y}
```

**Parameters:**
- `dataset`: Dataset name (flood_hazard, permanent_water, flood_2023, etc.)
- `z`: Zoom level (0-18)
- `x`: Tile X coordinate
- `y`: Tile Y coordinate

**Example - Leaflet Integration:**
```javascript
// Add flood hazard layer
const floodHazardLayer = L.tileLayer(
  'https://your-api.com/api/v1/gee/flood/tiles/flood_hazard/{z}/{x}/{y}',
  {
    attribution: 'Sentinel-1 GRD | Copernicus',
    maxZoom: 18,
    opacity: 0.7
  }
).addTo(map);

// Add permanent water layer
const waterLayer = L.tileLayer(
  'https://your-api.com/api/v1/gee/flood/tiles/permanent_water/{z}/{x}/{y}',
  {
    attribution: 'Sentinel-1 GRD | Copernicus',
    maxZoom: 18
  }
).addTo(map);

// Add 2023 flood layer
const flood2023 = L.tileLayer(
  'https://your-api.com/api/v1/gee/flood/tiles/flood_2023/{z}/{x}/{y}',
  {
    attribution: 'Sentinel-1 GRD | Copernicus',
    maxZoom: 18
  }
);

// Layer control
const overlays = {
  "Flood Hazard": floodHazardLayer,
  "Permanent Water": waterLayer,
  "Flood 2023": flood2023
};
L.control.layers(null, overlays).addTo(map);
```

**Example - OpenLayers Integration:**
```javascript
// Flood hazard layer
const floodHazardSource = new ol.source.XYZ({
  url: 'https://your-api.com/api/v1/gee/flood/tiles/flood_hazard/{z}/{x}/{y}',
  crossOrigin: 'anonymous'
});

const floodHazardLayer = new ol.layer.Tile({
  source: floodHazardSource,
  opacity: 0.7
});

map.addLayer(floodHazardLayer);
```

### 3. Get Dataset Information

```http
GET /api/v1/gee/flood/tiles/{dataset}
```

Returns detailed information about a specific dataset including tile URL templates.

**Example:**
```bash
curl https://your-api.com/api/v1/gee/flood/tiles/flood_hazard
```

**Response:**
```json
{
  "status": "success",
  "dataset": "flood_hazard",
  "info": {
    "name": "Flood Hazard Index",
    "description": "Composite flood hazard index (0-1) showing flood frequency across analysis years",
    "type": "continuous"
  },
  "visualization": {
    "min": 0,
    "max": 1,
    "palette": ["white", "pink", "red"]
  },
  "tile_urls": {
    "template": "https://your-api.com/api/v1/gee/flood/tiles/flood_hazard/{z}/{x}/{y}",
    "leaflet": "L.tileLayer('...').addTo(map);",
    "openlayers": "new ol.layer.Tile({...});",
    "mapbox": "map.addLayer({...});"
  }
}
```

### 4. Analyze Flood Statistics

```http
POST /api/v1/gee/flood/analyze
```

Analyze flood statistics for a specific area using GeoJSON geometry.

**Request Body:**
```json
{
  "geojson": {
    "type": "Polygon",
    "coordinates": [
      [
        [106.8, -6.2],
        [106.9, -6.2],
        [106.9, -6.1],
        [106.8, -6.1],
        [106.8, -6.2]
      ]
    ]
  },
  "years": [2020, 2021, 2022, 2023]
}
```

**Parameters:**
- `geojson`: GeoJSON geometry (Polygon, MultiPolygon, or FeatureCollection)
- `years`: Optional list of years to analyze (default: 2016-2023)

**Response:**
```json
{
  "status": "success",
  "analysis_period": "2020-2023",
  "total_area_hectares": 1234.56,
  "flood_hazard_index": 0.45,
  "yearly_statistics": [
    {
      "year": 2020,
      "flood_area_hectares": 123.45
    },
    {
      "year": 2021,
      "flood_area_hectares": 234.56
    },
    {
      "year": 2022,
      "flood_area_hectares": 156.78
    },
    {
      "year": 2023,
      "flood_area_hectares": 189.12
    }
  ],
  "summary": {
    "total_years_analyzed": 4,
    "avg_flood_area_hectares": 175.98,
    "max_flood_year": 2021,
    "min_flood_year": 2020
  },
  "metadata": {
    "data_source": "Sentinel-1 GRD",
    "analysis_timestamp": "2025-12-12T10:30:00Z",
    "wet_season": "December",
    "dry_season": "August"
  }
}
```

**Example - Python:**
```python
import requests
import json

# Define area of interest
aoi = {
    "type": "Polygon",
    "coordinates": [
        [
            [106.8, -6.2],
            [106.9, -6.2],
            [106.9, -6.1],
            [106.8, -6.1],
            [106.8, -6.2]
        ]
    ]
}

# Analyze flood
response = requests.post(
    'https://your-api.com/api/v1/gee/flood/analyze',
    json={
        'geojson': aoi,
        'years': [2020, 2021, 2022, 2023]
    }
)

data = response.json()
print(f"Flood Hazard Index: {data['flood_hazard_index']}")
print(f"Average Flood Area: {data['summary']['avg_flood_area_hectares']} ha")
```

**Example - JavaScript:**
```javascript
// Define area of interest
const aoi = {
  type: 'Polygon',
  coordinates: [[
    [106.8, -6.2],
    [106.9, -6.2],
    [106.9, -6.1],
    [106.8, -6.1],
    [106.8, -6.2]
  ]]
};

// Analyze flood
fetch('https://your-api.com/api/v1/gee/flood/analyze', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    geojson: aoi,
    years: [2020, 2021, 2022, 2023]
  })
})
.then(response => response.json())
.then(data => {
  console.log('Flood Hazard Index:', data.flood_hazard_index);
  console.log('Average Flood Area:', data.summary.avg_flood_area_hectares, 'ha');
  
  // Display yearly statistics
  data.yearly_statistics.forEach(stat => {
    console.log(`${stat.year}: ${stat.flood_area_hectares} ha`);
  });
});
```

## Complete Web Map Example

```html
<!DOCTYPE html>
<html>
<head>
  <title>Flood Hazard Map</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    #map { height: 600px; }
    .info { padding: 10px; background: white; border-radius: 5px; }
  </style>
</head>
<body>
  <div id="map"></div>
  <script>
    // Initialize map
    const map = L.map('map').setView([-6.2, 106.8], 10);
    
    // Base layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors'
    }).addTo(map);
    
    // Flood hazard layer
    const floodHazard = L.tileLayer(
      'https://your-api.com/api/v1/gee/flood/tiles/flood_hazard/{z}/{x}/{y}',
      {
        attribution: 'Sentinel-1 | Copernicus',
        opacity: 0.6
      }
    ).addTo(map);
    
    // Permanent water layer
    const permanentWater = L.tileLayer(
      'https://your-api.com/api/v1/gee/flood/tiles/permanent_water/{z}/{x}/{y}',
      {
        attribution: 'Sentinel-1 | Copernicus'
      }
    );
    
    // Flood 2023
    const flood2023 = L.tileLayer(
      'https://your-api.com/api/v1/gee/flood/tiles/flood_2023/{z}/{x}/{y}',
      {
        attribution: 'Sentinel-1 | Copernicus'
      }
    );
    
    // Layer control
    const overlays = {
      "Flood Hazard Index": floodHazard,
      "Permanent Water": permanentWater,
      "Flood 2023": flood2023
    };
    L.control.layers(null, overlays).addTo(map);
    
    // Legend
    const legend = L.control({ position: 'bottomright' });
    legend.onAdd = function() {
      const div = L.DomUtil.create('div', 'info');
      div.innerHTML = `
        <h4>Flood Hazard Index</h4>
        <div style="background: linear-gradient(to right, white, pink, red); 
                    width: 200px; height: 20px; border: 1px solid black;"></div>
        <div style="display: flex; justify-content: space-between; width: 200px;">
          <span>0 (Never)</span>
          <span>1 (Always)</span>
        </div>
      `;
      return div;
    };
    legend.addTo(map);
    
    // Click to analyze
    map.on('click', async function(e) {
      const bounds = map.getBounds();
      const polygon = {
        type: 'Polygon',
        coordinates: [[
          [bounds.getWest(), bounds.getSouth()],
          [bounds.getEast(), bounds.getSouth()],
          [bounds.getEast(), bounds.getNorth()],
          [bounds.getWest(), bounds.getNorth()],
          [bounds.getWest(), bounds.getSouth()]
        ]]
      };
      
      const response = await fetch('https://your-api.com/api/v1/gee/flood/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          geojson: polygon,
          years: [2020, 2021, 2022, 2023]
        })
      });
      
      const data = await response.json();
      alert(`Flood Hazard Index: ${data.flood_hazard_index}\n` +
            `Avg Flood Area: ${data.summary.avg_flood_area_hectares} ha`);
    });
  </script>
</body>
</html>
```

## Customization

### Adjust Season Dates

The service uses hardcoded season dates optimized for tropical regions. To customize for your region, modify [gee_flood_service.py](../services/gee_flood_service.py):

```python
# In _analyze_flood_year method
wet_season = {'name': 'wet', 'start': '-12-01', 'end': '-12-31'}  # Change dates
dry_season = {'name': 'dry', 'start': '-08-01', 'end': '-08-31'}  # Change dates
```

### Adjust Water Threshold

Current threshold: -15 dB. To adjust sensitivity:

```python
# In _process_seasonal_water method
water = image_min.lt(-15).toByte()  # Change -15 to your threshold
```

Lower values (e.g., -18 dB) = more sensitive (detects more water)
Higher values (e.g., -12 dB) = less sensitive (detects less water)

## Performance Notes

- **Tile Generation**: Generated on-the-fly, ~500ms per tile
- **Statistical Analysis**: 10-30 seconds depending on area size
- **Recommended Area**: < 10,000 km² for optimal performance
- **Caching**: Consider implementing tile caching for production

## Use Cases

1. **Flood Risk Assessment**
   - Identify high-risk areas using flood hazard index
   - Plan infrastructure placement
   - Insurance risk modeling

2. **Emergency Response**
   - Monitor current flood extent
   - Compare with historical patterns
   - Plan evacuation routes

3. **Urban Planning**
   - Avoid flood-prone areas for development
   - Design drainage systems
   - Green space allocation

4. **Agriculture**
   - Identify flood-prone croplands
   - Plan irrigation systems
   - Crop insurance assessments

5. **Environmental Monitoring**
   - Track wetland changes
   - Monitor river dynamics
   - Climate change impact assessment

## Limitations

- **Temporal**: Limited to 2016-2023 data
- **Season**: Fixed wet/dry season dates (customizable)
- **Resolution**: ~10m Sentinel-1 resolution
- **Cloud Coverage**: Radar-based, not affected by clouds
- **Urban Areas**: May have false positives due to building reflections
- **Vegetation**: Dense canopy may mask flooding

## Support

For questions or issues:
- Check API documentation at `/docs`
- Review example code in this guide
- Contact: your-support@email.com
