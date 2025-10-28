# Overview

This is an **EUDR Forest Compliance API** built with FastAPI that provides satellite-based deforestation monitoring and compliance analysis for the EU Deforestation Regulation. The system processes GeoJSON data through multiple Earth Engine datasets (GFW, JRC, SBTN) to detect forest loss and assess compliance risk. It features parallel processing using 16 Google service accounts for high-throughput analysis and supports various endpoints for commodity analysis, boundary data export, and tile visualization services.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Core Technology Stack

**Backend Framework**: FastAPI with Uvicorn ASGI server providing async request handling and automatic OpenAPI documentation generation.

**Geospatial Processing**: Google Earth Engine API for satellite imagery analysis, with support for datasets including Global Forest Watch (GFW), Joint Research Centre (JRC) tropical forest monitoring, and Science Based Targets Network (SBTN) natural lands classification.

**Data Storage**: PostgreSQL with PostGIS extension (hosted on Neon) for spatial boundary data and overlap analysis.

**Authentication**: Service account-based Earth Engine authentication with round-robin distribution across 16 accounts to bypass quota limitations.

## Application Structure

**Modular Router Architecture**: The application uses FastAPI's router system to separate concerns:

- `routers/general.py` - Health checks and API information endpoints
- `routers/eudr.py` - EUDR compliance analysis endpoints
- `routers/geojson.py` - GeoJSON file upload and bulk processing
- `routers/commodity_analysis.py` - Commodity-specific (rubber, cocoa, coffee, palm) probability analysis
- `routers/gaul.py` - FAO GAUL administrative boundary GeoJSON generation
- `routers/gaul_csv.py` - GAUL boundary data CSV export for Indonesia
- `routers/legacy.py` - Backward compatibility layer for deprecated endpoints

**Service Layer**: Business logic separated into dedicated services:

- `services/data/multilayer_service.py` - Core EUDR analysis engine with parallel processing
- `services/gee_dataset_service.py` - Earth Engine dataset management and tile serving
- `authentication/auth_helper.py` - Multi-account Earth Engine authentication handler

## Parallel Processing Design

**Problem**: Google Earth Engine imposes per-account quotas that limit throughput for bulk analysis requests.

**Solution**: Implemented a pool of 16 service accounts with round-robin distribution using Python's `ThreadPoolExecutor`. Each GeoJSON feature is processed by a different account in parallel, enabling analysis of large batches without hitting quota limits.

**Thread Safety**: Uses `threading.Lock()` to protect the account pool iterator and prevent race conditions during concurrent processing.

**Alternatives Considered**: Single-account sequential processing (too slow), account-per-request (authentication overhead), queue-based distribution (unnecessary complexity).

**Pros**: High throughput, automatic load balancing, graceful degradation to single account if multi-account setup fails.

**Cons**: Requires managing 16 separate Google Cloud projects and service accounts, increased authentication complexity.

## EUDR Analysis Logic

**Problem**: Need to determine forest loss compliance using multiple satellite datasets with different coverage and methodologies.

**Solution**: Three-dataset approach analyzing forest loss from 2021-2024:

1. **GFW Loss** - Global Forest Watch tree cover loss (Hansen dataset)
2. **JRC Loss** - Joint Research Centre tropical moist forest deforestation
3. **SBTN Loss** - Natural lands classification with forest loss overlay

**Risk Classification**: Binary system where ANY detected loss > 0 hectares = HIGH RISK (non-compliant), otherwise LOW RISK (compliant). Includes year-wise breakdown to identify peak deforestation periods.

**Alternatives Considered**: Weighted scoring system (too complex), single-dataset approach (less comprehensive), threshold-based classification (arbitrary cutoffs).

**Pros**: Clear binary output, consensus validation across datasets, transparent methodology.

**Cons**: Conservative (may flag areas with minimal loss), no severity gradation.

## File Upload Strategy

**Problem**: Need to support both programmatic API access and user-friendly file uploads through Swagger UI.

**Solution**: Dual endpoints - `/api/v1/process-geojson` accepts JSON payloads, `/api/v1/upload-geojson` accepts multipart file uploads. Both route to the same processing logic after format normalization.

**Validation**: File size limits (50MB), GeoJSON structure validation, feature count checks, coordinate system verification.

**Pros**: Flexible access methods, built-in Swagger UI testing, consistent processing pipeline.

**Cons**: Duplicate endpoint definitions, memory usage for large file buffers.

## Commodity Analysis Architecture

**Problem**: Need to assess crop probability (rubber, cocoa, coffee, palm) for supplied polygons using Forest Data Partnership models.

**Solution**: Binary zonal statistics using Earth Engine's `reduceRegion()` to count pixels above 0.5 probability threshold. Returns pixel counts, hectare areas, and tile URLs for visualization.

**Dataset Mapping**: Maps commodity names to Earth Engine asset IDs (`projects/forestdatapartnership/assets/{commodity}/model_2025a`).

**Pros**: Fast analysis, pre-trained models, visualization support through tiles.

**Cons**: Dependent on external Forest Data Partnership assets, fixed probability threshold.

## Configuration Management

**Environment Variables**: Uses `python-dotenv` to load configuration from `.env` file with fallbacks to defaults. Key settings include service account paths, parallel processing flags, database credentials, and Earth Engine quotas.

**Multi-Environment Support**: Checks `APP_ENV` variable to skip `.env` loading in production (relies on platform environment variables).

**Pros**: Secure credential management, easy local development, platform-agnostic deployment.

**Cons**: Requires manual environment variable setup on new platforms.

# External Dependencies

## Google Earth Engine

**Purpose**: Primary satellite imagery analysis platform providing access to petabyte-scale geospatial datasets.

**Authentication**: Service account authentication using JSON key files for 16 separate accounts (eudr-0.json through eudr-15.json).

**Key Datasets Used**:
- `UMD/hansen/global_forest_change_2024_v1_12` - Hansen Global Forest Change
- `projects/JRC/TMF/v1_2024/DeforestationYear` - JRC Tropical Moist Forests
- `WRI/SBTN/naturalLands/v1_1/2020` - SBTN Natural Lands
- `JRC/GFC2020/V2` - European Forest Observatory (EUFO)
- `projects/forestdatapartnership/assets/{commodity}/model_2025a` - Commodity probability models
- `FAO/GAUL/2015/level2` - Global Administrative Unit Layers

**Integration**: Python `earthengine-api` library with custom authentication helper module.

## PostgreSQL with PostGIS

**Purpose**: Spatial database for storing administrative boundaries and performing overlap analysis with Indonesian forest areas (BRWA).

**Host**: Neon serverless PostgreSQL (ep-silent-morning-afgiwp5c.c-2.us-west-2.aws.neon.tech)

**Schema**: Contains `brwa_idn` table with forest boundary polygons using PostGIS geometry types.

**Integration**: Direct `psycopg2` connections for spatial queries, intersection calculations, and boundary exports.

## Python Geospatial Stack

**Core Libraries**:
- `geopandas` - DataFrame-based geospatial operations
- `shapely` - Geometric object manipulation
- `rasterio` - Raster data I/O
- `fiona` - Vector data I/O
- `pyproj` - Coordinate system transformations

**Purpose**: Local geometry processing, format conversions, and validation before Earth Engine submission.

## Google Cloud Platform

**Service Accounts**: 16 separate GCP projects (eudr-deforestation through eudr-deforestation-15) each with dedicated service account for Earth Engine API access.

**Required Permissions**: Earth Engine Resource Viewer, Storage Object Viewer for accessing public datasets.

**Authentication Flow**: JSON key files → Google OAuth2 credentials → Earth Engine initialization.

## FastAPI Ecosystem

**Core Framework**: FastAPI 0.104.1 with Pydantic for request/response validation.

**Server**: Uvicorn with standard extras for production-grade ASGI serving.

**Middleware**: CORS middleware configured for cross-origin API access.

**Documentation**: Auto-generated OpenAPI/Swagger UI at `/docs` endpoint.

## Deployment Platform

**Platform**: Designed for Fly.io deployment (referenced in setup guides as eudr-multilayer-api.fly.dev).

**Configuration**: Environment variable-based configuration for cloud compatibility.

**Monitoring**: Health check endpoint at `/health` for platform availability monitoring.

## Third-Party API Integration

**RapidAPI Marketplace**: Configured for monetization through RapidAPI Hub with tiered pricing (Freemium $0, Basic $19.99, Professional $99.99, Enterprise $499.99).

**API Gateway**: RapidAPI acts as reverse proxy handling authentication, rate limiting, and payment processing.