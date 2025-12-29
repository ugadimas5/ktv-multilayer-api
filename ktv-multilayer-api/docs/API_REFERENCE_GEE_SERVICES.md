# GEE Services API Reference

This document provides detailed documentation for the Google Earth Engine (GEE) based analysis services: **Flood Analysis**, **Landslide Analysis**, and **Commodity Analysis**.

## Common Parameters

All services support spatial filtering using administrative boundaries based on **FAO GAUL 2024** definitions.

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `country` | `string` | Country Name (ADM0) | `Indonesia` |
| `province` | `string` | Province Name (ADM1) | `Aceh` |
| `district` | `string` | District/Regency Name (ADM2) | `Aceh Barat` |

> **Note:** These parameters are optional. If provided, the analysis and visualization will be clipped to the specified boundary.

---

## 1. Flood Analysis Service

Provides flood hazard mapping and historical flood detection using Sentinel-1 SAR imagery.

### 1.1 Get Flood Map Tile
Retrieves a visualization tile (XYZ format) for flood datasets.

**Endpoint:**
`GET /api/v1/gee/flood/tiles/{dataset}/{z}/{x}/{y}`

**Path Parameters:**
- `dataset`: The dataset identifier (see below).
- `z`, `x`, `y`: Zoom level and tile coordinates.

**Query Parameters:**
- `country`, `province`, `district`: (Optional) Filter by location.

**Available Datasets:**
- `flood_hazard`: Composite flood hazard index (0-1).
- `permanent_water`: Detected permanent water bodies.
- `flood_nov_dec_2025`: Flood detection for Nov-Dec 2025 (vs Baseline Aug-Oct 2025).
- `flood_2024`: Flood extent for year 2024.
- `flood_2023`: Flood extent for year 2023.

**Response:**
- **307 Temporary Redirect**: Redirects to the Google Earth Engine tile URL.

**Example Request:**
```http
GET /api/v1/gee/flood/tiles/flood_hazard/10/512/384?country=Indonesia&province=Aceh
```

### 1.2 Get Flood Area Statistics
Calculates the total area of flood hazard or water bodies within a specified boundary.

**Endpoint:**
`GET /api/v1/gee/flood/stats`

**Query Parameters:**
- `dataset`: (Required) Dataset name (e.g., `flood_hazard`).
- `country`, `province`, `district`: (Optional) Filter by location.

**Response (JSON):**
```json
{
  "dataset": "flood_hazard",
  "location": {
    "country": "Indonesia",
    "province": "Aceh",
    "district": "Aceh Barat"
  },
  "scale_used": 10,
  "area_sqm": 154200.50,
  "area_ha": 15.42
}
```
- `scale_used`: The resolution in meters used for calculation (10m for district, 30m for province, 100m for country).
- `area_sqm`: Area in square meters.
- `area_ha`: Area in hectares.

---

## 2. Landslide Analysis Service

Provides landslide detection using Sentinel-1 SAR (Backscatter change) and Sentinel-2 Optical (NDVI difference).

### 2.1 Get Landslide Map Tile
Retrieves a visualization tile for landslide detection layers.

**Endpoint:**
`GET /api/v1/gee/landslide/tiles/{dataset}/{z}/{x}/{y}`

**Path Parameters:**
- `dataset`: The dataset identifier.
- `z`, `x`, `y`: Zoom level and tile coordinates.

**Query Parameters:**
- `country`, `province`, `district`: (Optional) Filter by location.

**Available Datasets:**
- `landslide_nov_dec_2025`: SAR-based detection (Nov-Dec 2025).
- `landslide_ndvi_nov_dec_2025`: NDVI-based detection (Nov-Dec 2025).

**Visualization:**
- **Color**: `#e66101` (Orange/Red) for detected landslide areas.

**Response:**
- **307 Temporary Redirect**: Redirects to the Google Earth Engine tile URL.

### 2.2 Get Landslide Area Statistics
Calculates the total area of detected landslides within a specified boundary.

**Endpoint:**
`GET /api/v1/gee/landslide/stats`

**Query Parameters:**
- `dataset`: (Required) Dataset name.
- `country`, `province`, `district`: (Optional) Filter by location.

**Response (JSON):**
```json
{
  "dataset": "landslide_nov_dec_2025",
  "location": {
    "country": "Indonesia",
    "province": "Aceh",
    "district": null
  },
  "scale_used": 30,
  "area_sqm": 5000.00,
  "area_ha": 0.50
}
```

---

## 3. Commodity Analysis Service

Provides probability maps for key commodities using Forest Data Partnership models (2025a).

### 3.1 Get Commodity Map Tile
Retrieves a visualization tile for commodity plantations.

**Endpoint:**
`GET /api/v1/gee/commodity/tiles/{commodity}/{z}/{x}/{y}`

**Path Parameters:**
- `commodity`: The commodity identifier.
- `z`, `x`, `y`: Zoom level and tile coordinates.

**Query Parameters:**
- `country`, `province`, `district`: (Optional) Filter by location.

**Available Commodities:**
- `rubber`: Rubber plantations (Color: `#2c7bb6`)
- `palm`: Palm oil plantations (Color: `#abdda4`)
- `cocoa`: Cocoa plantations (Color: `#018571`)
- `coffee`: Coffee plantations (Color: `#a6611a`)

**Response:**
- **307 Temporary Redirect**: Redirects to the Google Earth Engine tile URL.

### 3.2 Get Commodity Area Statistics
Calculates the total area of the specified commodity plantation within a boundary.

**Endpoint:**
`GET /api/v1/gee/commodity/stats`

**Query Parameters:**
- `commodity`: (Required) Commodity name (e.g., `rubber`).
- `country`, `province`, `district`: (Optional) Filter by location.

**Response (JSON):**
```json
{
  "commodity": "rubber",
  "location": {
    "country": "Indonesia",
    "province": "Aceh",
    "district": "Aceh Barat"
  },
  "scale_used": 10,
  "area_sqm": 1250000.00,
  "area_ha": 125.00
}
```

---

## 4. Intersection Analysis Service

Provides intersection analysis between Commodity, Flood, and Landslide datasets.

### 4.1 Get Intersection Map Tile
Retrieves a visualization tile for the intersection.

**Endpoint:**
`GET /api/v1/gee/intersection/tiles/{type}/{commodity}/{z}/{x}/{y}`

**Path Parameters:**
- `type`: Intersection type.
    - `commodity_flood`: Commodity AND Flood Hazard (>0.1). (Color: Purple)
    - `commodity_landslide`: Commodity AND Landslide (Nov-Dec 2025). (Color: Red)
    - `commodity_flood_landslide`: Commodity AND Flood AND Landslide. (Color: Black)
- `commodity`: Commodity name (`rubber`, `palm`, `cocoa`, `coffee`).
- `z`, `x`, `y`: Zoom level and tile coordinates.

**Query Parameters:**
- `country`, `province`, `district`: (Optional) Filter by location.

**Response:**
- **307 Temporary Redirect**: Redirects to the Google Earth Engine tile URL.

### 4.2 Get Intersection Area Statistics
Calculates the total area of the intersection.

**Endpoint:**
`GET /api/v1/gee/intersection/stats`

**Query Parameters:**
- `type`: (Required) Intersection type.
- `commodity`: (Required) Commodity name.
- `country`, `province`, `district`: (Optional) Filter by location.

**Response (JSON):**
```json
{
  "analysis_type": "commodity_flood",
  "commodity": "rubber",
  "location": {
    "country": "Indonesia",
    "province": "Aceh",
    "district": null
  },
  "scale_used": 30,
  "area_sqm": 5000.00,
  "area_ha": 0.50
}
```

---

## Error Handling

All endpoints follow standard HTTP status codes:

- **200 OK**: Request successful.
- **307 Temporary Redirect**: Successful tile generation (redirects to image).
- **400 Bad Request**: Missing required parameters (e.g., missing `country` when calculating area).
- **404 Not Found**: Dataset/Commodity not found or Location (Country/Province/District) not found in GAUL database.
- **500 Internal Server Error**: Server-side error (e.g., Earth Engine computation timeout).
- **503 Service Unavailable**: Earth Engine initialization failed.
