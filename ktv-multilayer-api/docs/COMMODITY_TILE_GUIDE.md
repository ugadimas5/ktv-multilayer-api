# GEE Commodity Tile Service Guide

## Overview

Service untuk visualisasi commodity mapping menggunakan Google Earth Engine dan dataset dari Forest Data Partnership (FDP). Service ini menyediakan tile endpoint yang langsung dapat digunakan untuk visualisasi web mapping, mirip dengan flood tile service.

## Available Commodities

| Commodity | Color | Asset ID |
|-----------|-------|----------|
| **Rubber** | #8B4513 (Brown) | `forestdatapartnership/assets/rubber/model_2025a` |
| **Palm Oil** | #228B22 (Green) | `forestdatapartnership/assets/palm/model_2025a` |
| **Cocoa** | #654321 (Dark Brown) | `forestdatapartnership/assets/cocoa/model_2025a` |
| **Coffee** | #6F4E37 (Coffee Brown) | `forestdatapartnership/assets/coffee/model_2025a` |

## API Endpoints

### 1. Get Available Datasets

```http
GET /api/v1/gee/commodity/datasets
```

**Response:**
```json
{
  "status": "success",
  "total_datasets": 4,
  "datasets": {
    "rubber": {
      "name": "Rubber Plantations",
      "description": "Rubber plantation probability map from Forest Data Partnership",
      "asset_id": "projects/forestdatapartnership/assets/rubber/model_2025a",
      "band": "probability",
      "threshold": 0.5,
      "style": "rubber"
    }
  },
  "visualization_styles": {
    "rubber": {
      "min": 1,
      "max": 1,
      "palette": ["8B4513"]
    }
  },
  "data_source": "Forest Data Partnership",
  "model_version": "2025a",
  "active_bounds": "Custom bbox",
  "cache_info": {
    "enabled": true,
    "duration_seconds": 3600,
    "cached_datasets": ["rubber", "palm"]
  }
}
```

### 2. Get Dataset Info

```http
GET /api/v1/gee/commodity/tiles/{commodity}
```

**Parameters:**
- `commodity`: rubber | palm | cocoa | coffee

**Example:**
```bash
curl http://localhost:8000/api/v1/gee/commodity/tiles/rubber
```

**Response:**
```json
{
  "status": "success",
  "commodity": "rubber",
  "info": {...},
  "visualization": {...},
  "cached": true,
  "tile_urls": {
    "template": "http://localhost:8000/api/v1/gee/commodity/tiles/rubber/{z}/{x}/{y}",
    "leaflet": "L.tileLayer('...').addTo(map);",
    "openlayers": "new ol.layer.Tile(...)",
    "mapbox": "map.addLayer(...)"
  }
}
```

### 3. Get Map Tiles

```http
GET /api/v1/gee/commodity/tiles/{commodity}/{z}/{x}/{y}
```

**Parameters:**
- `commodity`: rubber | palm | cocoa | coffee
- `z`: Zoom level (0-20)
- `x`: Tile X coordinate
- `y`: Tile Y coordinate

**Response:** 307 Redirect to Google Earth Engine tile URL

**Performance:**
- First request: 5-10 seconds (GEE computation)
- Cached requests: <1 second (map ID cached for 1 hour)

### 4. Clear Cache

```http
POST /api/v1/gee/commodity/cache/clear?commodity=rubber
```

**Query Parameters:**
- `commodity` (optional): Specific commodity to clear cache. Omit to clear all.

**Response:**
```json
{
  "status": "success",
  "message": "Cleared cache for rubber",
  "affected_commodities": ["rubber"]
}
```

## Web Integration

### Leaflet.js

```javascript
// Add single commodity layer
const rubberLayer = L.tileLayer(
  'http://localhost:8000/api/v1/gee/commodity/tiles/rubber/{z}/{x}/{y}',
  {
    attribution: 'Rubber (FDP)',
    maxZoom: 18,
    opacity: 0.7
  }
).addTo(map);

// Add all commodities
const commodities = ['rubber', 'palm', 'cocoa', 'coffee'];
const layers = {};

commodities.forEach(commodity => {
  layers[commodity] = L.tileLayer(
    `http://localhost:8000/api/v1/gee/commodity/tiles/${commodity}/{z}/{x}/{y}`,
    { opacity: 0.7, maxZoom: 18 }
  );
});

// Toggle layer
function toggleCommodity(commodity, show) {
  if (show) {
    layers[commodity].addTo(map);
  } else {
    map.removeLayer(layers[commodity]);
  }
}
```

### OpenLayers

```javascript
import TileLayer from 'ol/layer/Tile';
import XYZ from 'ol/source/XYZ';

const rubberLayer = new TileLayer({
  source: new XYZ({
    url: 'http://localhost:8000/api/v1/gee/commodity/tiles/rubber/{z}/{x}/{y}'
  }),
  opacity: 0.7
});

map.addLayer(rubberLayer);
```

## Bounding Box

Service ini menggunakan bounding box yang sama dengan flood service:

1. **Default:** Indonesia bounds (95°E - 141°E, 11°S - 6°N)
2. **Custom:** Auto-load dari `data/temp/flood_test.geojson`

### Current Bbox (Riau/Jambi)
```
West: 98.80°E
East: 99.36°E
South: 1.46°N
North: 2.01°N
Area: ~3,200 km²
```

## Data Specifications

### Source
- **Provider:** Forest Data Partnership (FDP)
- **Model:** model_2025a
- **Resolution:** 10 meters
- **Format:** Probability raster (0-1)

### Processing
1. **Threshold:** 0.5 probability
2. **Output:** Binary (0 = no commodity, 1 = commodity detected)
3. **Transparency:** 0 values masked (selfMask)
4. **Clipping:** Automatically clipped to active bbox

### Visualization
- **Method:** Single-color overlay
- **Colors:** Commodity-specific (see table above)
- **Blending:** Additive (can see multiple commodities)

## Cache Behavior

### Map ID Caching
- **Duration:** 1 hour (3600 seconds)
- **Key:** Commodity name
- **Effect:** Instant tile loading after first request

### When to Clear Cache
1. Updated `flood_test.geojson` bbox
2. Changed visualization parameters
3. Testing new datasets
4. Tiles appear outdated

```bash
# Clear specific commodity
curl -X POST http://localhost:8000/api/v1/gee/commodity/cache/clear?commodity=rubber

# Clear all commodities
curl -X POST http://localhost:8000/api/v1/gee/commodity/cache/clear
```

## Error Handling

### Common Errors

**503 Service Unavailable**
```json
{
  "detail": "Service initializing. Please try again in a few seconds."
}
```
- **Cause:** Earth Engine not initialized yet
- **Solution:** Wait 2-3 seconds and retry

**404 Not Found**
```json
{
  "detail": "Commodity 'banana' not found"
}
```
- **Cause:** Invalid commodity name
- **Solution:** Use: rubber, palm, cocoa, or coffee

**500 GEE Computation Error**
```json
{
  "detail": "GEE computation error: ..."
}
```
- **Cause:** Earth Engine processing error
- **Solution:** Check logs, verify bbox, clear cache

## Performance Tips

1. **First Load:** Be patient (5-10s for first tile generation)
2. **Caching:** Map ID cached for 1 hour - instant subsequent loads
3. **Bbox:** Use custom bbox to reduce area and improve speed
4. **Parallel Loading:** Load multiple commodities simultaneously
5. **Zoom Levels:** Higher zoom = more tiles = slower initial load

## Complete Example

```html
<!DOCTYPE html>
<html>
<head>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    #map { height: 600px; }
  </style>
</head>
<body>
  <div id="map"></div>
  <div>
    <label><input type="checkbox" id="rubber"> Rubber</label>
    <label><input type="checkbox" id="palm"> Palm</label>
    <label><input type="checkbox" id="cocoa"> Cocoa</label>
    <label><input type="checkbox" id="coffee"> Coffee</label>
  </div>

  <script>
    const map = L.map('map').setView([1.74, 99.08], 10);
    
    // Basemap
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
    
    // Commodity layers
    const layers = {
      rubber: L.tileLayer('http://localhost:8000/api/v1/gee/commodity/tiles/rubber/{z}/{x}/{y}', {opacity: 0.7}),
      palm: L.tileLayer('http://localhost:8000/api/v1/gee/commodity/tiles/palm/{z}/{x}/{y}', {opacity: 0.7}),
      cocoa: L.tileLayer('http://localhost:8000/api/v1/gee/commodity/tiles/cocoa/{z}/{x}/{y}', {opacity: 0.7}),
      coffee: L.tileLayer('http://localhost:8000/api/v1/gee/commodity/tiles/coffee/{z}/{x}/{y}', {opacity: 0.7})
    };
    
    // Toggle handlers
    ['rubber', 'palm', 'cocoa', 'coffee'].forEach(commodity => {
      document.getElementById(commodity).addEventListener('change', function() {
        if (this.checked) {
          layers[commodity].addTo(map);
        } else {
          map.removeLayer(layers[commodity]);
        }
      });
    });
  </script>
</body>
</html>
```

## Comparison: Old vs New Approach

### Old Approach (commodity_analysis endpoint)
```javascript
// ❌ Complex: Upload GeoJSON every time
const formData = new FormData();
formData.append('file', geojsonBlob);
const response = await fetch('/commodity_analysis?commodity=rubber', {
  method: 'POST',
  body: formData
});
const data = await response.json();
L.tileLayer(data.tile_url).addTo(map);
```

### New Approach (tile endpoint)
```javascript
// ✅ Simple: Direct tile URL
L.tileLayer('/api/v1/gee/commodity/tiles/rubber/{z}/{x}/{y}')
  .addTo(map);
```

**Benefits:**
- No file upload needed
- Cleaner code
- Better caching
- Consistent with flood tiles
- Easier debugging

## Testing

```bash
# 1. Test datasets list
curl http://localhost:8000/api/v1/gee/commodity/datasets

# 2. Test tile info
curl http://localhost:8000/api/v1/gee/commodity/tiles/rubber

# 3. Test tile generation (browser)
http://localhost:8000/api/v1/gee/commodity/tiles/rubber/10/512/384

# 4. Clear cache
curl -X POST http://localhost:8000/api/v1/gee/commodity/cache/clear

# 5. Full UI test
# Open test.html in browser, toggle commodity checkboxes
```

## Troubleshooting

### Tiles not loading
1. Check console for errors
2. Verify Earth Engine initialized: Check API logs
3. Clear browser cache
4. Clear server cache: POST to `/cache/clear`

### Slow performance
1. Reduce bbox area (edit `flood_test.geojson`)
2. Wait for cache (first load always slower)
3. Check network tab for 307 redirects

### Wrong colors
1. Check visualization styles in `/datasets` response
2. Verify commodity name spelling
3. Clear cache and regenerate

## Related Documentation

- [FLOOD_ANALYSIS_GUIDE.md](./FLOOD_ANALYSIS_GUIDE.md) - Flood tile service
- [README_BBOX.md](../data/temp/README_BBOX.md) - Bbox configuration
- [API_EXAMPLES.md](../API_EXAMPLES.md) - General API usage
