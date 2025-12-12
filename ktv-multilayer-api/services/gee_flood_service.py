"""
Google Earth Engine Flood Analysis Service
Provides flood hazard mapping and tile generation using Sentinel-1 data
"""

import ee
import json
import os
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from loguru import logger
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()


class GEEFloodService:
    """Service for GEE flood analysis and visualization"""
    
    def __init__(self):
        """Initialize flood service with GEE authentication"""
        self.datasets = {}
        self.styles = self._get_visualization_styles()
        self._map_id_cache = {}  # Cache map IDs to avoid recomputation
        self._cache_timestamp = {}
        self.is_initialized = False  # Track EE initialization status
        
        # Initialize datasets (doesn't require EE)
        self._initialize_datasets()
        
        # Store bounds as raw coordinates (don't create ee.Geometry yet)
        self._default_bounds_coords = [95, -11, 141, 6]  # Indonesia [west, south, east, north]
        self._custom_bounds_coords = None  # Will be loaded from flood_test.geojson
        
        # Try to load custom bbox from flood_test.geojson if exists
        self._load_default_bbox()
        
        # Note: EE will be initialized on first tile request (lazy initialization)
    
    def _get_visualization_styles(self) -> Dict[str, Dict]:
        """Get available visualization styles for flood layers"""
        return {
            'flood_hazard': {
                'min': 0,
                'max': 1,
                'palette': ['white', 'pink', 'red']
            },
            'permanent_water': {
                'palette': ['blue']
            },
            'flood_binary': {
                'palette': ['cyan']
            },
            'water_wet': {
                'palette': ['navy']
            },
            'water_dry': {
                'palette': ['lightskyblue']
            }
        }
    
    def _initialize_datasets(self):
        """Initialize flood dataset definitions"""
        try:
            self.datasets = {
                'flood_hazard': {
                    'name': 'Flood Hazard Index',
                    'description': 'Composite flood hazard index (0-1) showing flood frequency across analysis years',
                    'type': 'continuous',
                    'style': 'flood_hazard',
                    'years': [2021, 2022, 2023, 2024, 2025]
                },
                'permanent_water': {
                    'name': 'Permanent Water Bodies',
                    'description': 'Areas identified as permanent water across all analysis periods',
                    'type': 'binary',
                    'style': 'permanent_water',
                    'years': [2021, 2022, 2023, 2024, 2025]
                },
                'flood_2025': {
                    'name': 'Flood 2025',
                    'description': 'Flood areas detected in 2025',
                    'type': 'binary',
                    'style': 'flood_binary',
                    'year': 2025
                },
                'flood_2024': {
                    'name': 'Flood 2024',
                    'description': 'Flood areas detected in 2024',
                    'type': 'binary',
                    'style': 'flood_binary',
                    'year': 2024
                },
                'flood_2023': {
                    'name': 'Flood 2023',
                    'description': 'Flood areas detected in 2023',
                    'type': 'binary',
                    'style': 'flood_binary',
                    'year': 2023
                },
                'flood_2022': {
                    'name': 'Flood 2022',
                    'description': 'Flood areas detected in 2022',
                    'type': 'binary',
                    'style': 'flood_binary',
                    'year': 2022
                },
                'flood_2021': {
                    'name': 'Flood 2021',
                    'description': 'Flood areas detected in 2021',
                    'type': 'binary',
                    'style': 'flood_binary',
                    'year': 2021
                }
            }
            logger.info("Flood datasets initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing flood datasets: {e}")
            raise
    
    def _authenticate_ee(self):
        """Authenticate Earth Engine with service account"""
        try:
            # Check if already initialized
            if self.is_initialized:
                logger.info("Earth Engine already initialized for flood service")
                return
            
            # Get service account path from environment
            service_account_path = os.getenv("EE_SINGLE_SERVICE_ACCOUNT_PATH")
            if not service_account_path:
                # Fallback to regular service account
                service_account_path = os.getenv("EE_SERVICE_ACCOUNT_PATH")
            
            if not service_account_path:
                raise ValueError("EE_SINGLE_SERVICE_ACCOUNT_PATH or EE_SERVICE_ACCOUNT_PATH not set in .env file")
            
            # Convert to absolute path if needed
            if not os.path.isabs(service_account_path):
                project_root = Path(__file__).parent.parent
                service_account_path = project_root / service_account_path
            else:
                service_account_path = Path(service_account_path)
            
            # Ensure path exists
            if not service_account_path.is_file():
                raise FileNotFoundError(f"Service account file not found: {service_account_path}")
            
            logger.info(f"Initializing Earth Engine with service account: {service_account_path}")
            
            # Initialize EE with service account
            credentials = ee.ServiceAccountCredentials(
                email=None,  # Will be read from the JSON file
                key_file=str(service_account_path)
            )
            ee.Initialize(credentials)
            
            self.is_initialized = True
            logger.success("Earth Engine initialized successfully for flood service")
            
        except Exception as e:
            logger.error(f"Failed to initialize Earth Engine: {e}")
            logger.warning("Flood service will initialize EE on first tile request")
            self.is_initialized = False
    
    def _load_default_bbox(self):
        """Load bbox from flood_test.geojson if it exists"""
        try:
            # Assuming the service is in services/ folder
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            geojson_path = os.path.join(base_dir, 'data', 'temp', 'flood_test.geojson')
            
            if os.path.exists(geojson_path):
                with open(geojson_path, 'r') as f:
                    geojson_data = json.load(f)
                    bbox = self._extract_bbox_from_geojson(geojson_data)
                    if bbox:
                        # Store as coords, will create ee.Geometry later when EE is initialized
                        self._custom_bounds_coords = bbox
                        logger.info(f"Loaded custom bbox from flood_test.geojson: {bbox}")
                    else:
                        logger.warning("Could not extract bbox from flood_test.geojson")
            else:
                logger.info("flood_test.geojson not found, using default Indonesia bounds")
        except Exception as e:
            logger.warning(f"Could not load bbox from flood_test.geojson: {e}")
    
    def _extract_bbox_from_geojson(self, geojson: Dict) -> Optional[List[float]]:
        """Extract bounding box [west, south, east, north] from GeoJSON"""
        try:
            if geojson['type'] == 'FeatureCollection':
                features = geojson.get('features', [])
                if not features:
                    return None
                coords = features[0]['geometry']['coordinates'][0]
            elif geojson['type'] == 'Feature':
                coords = geojson['geometry']['coordinates'][0]
            else:
                coords = geojson['coordinates'][0]
            
            # Extract min/max lon/lat
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            
            return [min(lons), min(lats), max(lons), max(lats)]  # [west, south, east, north]
        except Exception as e:
            logger.error(f"Error extracting bbox: {e}")
            return None
    
    def load_bbox_from_geojson(self, geojson_path: str) -> bool:
        """Load bbox from custom GeoJSON file"""
        try:
            with open(geojson_path, 'r') as f:
                geojson_data = json.load(f)
                bbox = self._extract_bbox_from_geojson(geojson_data)
                if bbox:
                    # Store as coords, will create ee.Geometry when needed
                    self._custom_bounds_coords = bbox
                    logger.info(f"Custom bbox loaded: {bbox}")
                    # Clear cache since bounds changed
                    self.clear_cache()
                    return True
                return False
        except Exception as e:
            logger.error(f"Error loading bbox from {geojson_path}: {e}")
            return False
    
    def get_active_bounds(self) -> ee.Geometry:
        """Get currently active bounds (custom if set, otherwise default)"""
        # Ensure EE is initialized
        if not self.is_initialized:
            self._authenticate_ee()
        
        # Create geometry from stored coordinates
        if self._custom_bounds_coords:
            return ee.Geometry.Rectangle(self._custom_bounds_coords)
        else:
            return ee.Geometry.Rectangle(self._default_bounds_coords)
    
    def _get_sentinel1_collection(self):
        """Get Sentinel-1 image collection"""
        return ee.ImageCollection('COPERNICUS/S1_GRD')
    
    def _process_seasonal_water(self, bounds: ee.Geometry, year: int, season_config: Dict) -> ee.Image:
        """
        Process seasonal water detection for a specific year and season
        
        Args:
            bounds: Area of interest geometry
            year: Year to analyze
            season_config: Dict with 'start', 'end', 'name' for season
        
        Returns:
            Water mask image for the season
        """
        s1 = self._get_sentinel1_collection()
        
        # Filter collection
        image = s1 \
            .filterBounds(bounds) \
            .filterDate(f"{year}{season_config['start']}", f"{year}{season_config['end']}") \
            .filter(ee.Filter.eq('transmitterReceiverPolarisation', ['VV', 'VH'])) \
            .select('VV')
        
        # Minimum composite with speckle filtering
        image_min = image.reduce(ee.Reducer.percentile([10])) \
            .clip(bounds) \
            .focalMean(50, 'square', 'meters')
        
        # Water mask (threshold -15 dB)
        water = image_min.lt(-15).toByte().rename(f"water_{season_config['name']}")
        
        return water
    
    def _analyze_flood_year(self, bounds: ee.Geometry, year: int) -> ee.Image:
        """
        Analyze flood for a single year
        
        Args:
            bounds: Area of interest geometry
            year: Year to analyze
        
        Returns:
            Image with flood and water bands
        """
        # Season configurations
        wet_season = {'name': 'wet', 'start': '-12-01', 'end': '-12-31'}
        dry_season = {'name': 'dry', 'start': '-08-01', 'end': '-08-31'}
        
        # Get water masks for both seasons
        water_wet = self._process_seasonal_water(bounds, year, wet_season)
        water_dry = self._process_seasonal_water(bounds, year, dry_season)
        
        # Flood = water in wet season AND no water in dry season
        flood = water_wet.And(water_dry.eq(0)).rename('flood').toByte()
        
        # All water = wet OR dry
        all_water = water_dry.Or(water_wet).rename('water')
        
        return ee.Image([flood.selfMask(), all_water]).set({
            'year': str(year),
            'year_num': year
        })
    
    def generate_flood_hazard(self, bounds: ee.Geometry, years: Optional[List[int]] = None) -> ee.Image:
        """
        Generate flood hazard index for multiple years
        
        Args:
            bounds: Area of interest geometry
            years: List of years to analyze (default: 2016-2023)
        
        Returns:
            Flood hazard index image (0-1)
        """
        if years is None:
            years = [2021, 2022, 2023, 2024, 2025]
        
        # Process each year
        images = ee.ImageCollection([
            self._analyze_flood_year(bounds, year) for year in years
        ])
        
        # Calculate flood hazard (frequency / total years)
        flood_hazard = images.select('flood').sum().divide(len(years))
        
        return flood_hazard
    
    def generate_permanent_water(self, bounds: ee.Geometry, years: Optional[List[int]] = None) -> ee.Image:
        """
        Generate permanent water mask
        
        Args:
            bounds: Area of interest geometry
            years: List of years to analyze
        
        Returns:
            Permanent water mask
        """
        if years is None:
            years = [2021, 2022, 2023, 2024, 2025]
        
        # Process each year
        images = ee.ImageCollection([
            self._analyze_flood_year(bounds, year) for year in years
        ])
        
        # Get flood hazard
        flood_hazard = images.select('flood').sum().divide(len(years))
        
        # Permanent water = water in all years AND not in flood areas
        water_permanent = images.select('water').reduce(ee.Reducer.allNonZero()) \
            .And(flood_hazard.mask().Not()).rename('water')
        
        return water_permanent.selfMask()
    
    def generate_flood_for_year(self, bounds: ee.Geometry, year: int) -> ee.Image:
        """
        Generate flood mask for specific year
        
        Args:
            bounds: Area of interest geometry
            year: Year to analyze
        
        Returns:
            Flood mask for the year
        """
        result = self._analyze_flood_year(bounds, year)
        return result.select('flood')
    
    def _get_or_create_map_id(self, dataset: str, bounds: ee.Geometry = None) -> Dict:
        """
        Get cached map ID or create new one
        
        Args:
            dataset: Dataset name
            bounds: Geometry bounds (if None, uses custom_bounds or default_bounds)
        
        Returns:
            Map ID dictionary
        """
        cache_key = f"{dataset}"
        
        # Check if cached and still valid (cache for 1 hour)
        if cache_key in self._map_id_cache:
            cached_time = self._cache_timestamp.get(cache_key, 0)
            if (datetime.now().timestamp() - cached_time) < 3600:  # 1 hour
                logger.info(f"Using cached map ID for {dataset}")
                return self._map_id_cache[cache_key]
        
        # Use active bounds if not specified
        if bounds is None:
            bounds = self.get_active_bounds()
        
        logger.info(f"Generating new map ID for {dataset}")
        
        # Generate appropriate image based on dataset
        if dataset == 'flood_hazard':
            image = self.generate_flood_hazard(bounds)
        elif dataset == 'permanent_water':
            image = self.generate_permanent_water(bounds)
        elif dataset.startswith('flood_'):
            year = int(dataset.split('_')[1])
            image = self.generate_flood_for_year(bounds, year)
        else:
            raise HTTPException(status_code=400, detail="Invalid dataset type")
        
        # Get visualization parameters
        style_name = self.datasets[dataset]['style']
        vis_params = self.styles[style_name]
        
        # Get map ID (this triggers GEE computation)
        try:
            map_id = image.getMapId(vis_params)
            
            # Cache it
            self._map_id_cache[cache_key] = map_id
            self._cache_timestamp[cache_key] = datetime.now().timestamp()
            
            logger.success(f"Map ID generated and cached for {dataset}")
            return map_id
            
        except Exception as e:
            logger.error(f"Error getting map ID from GEE: {e}")
            raise HTTPException(status_code=500, detail=f"GEE computation error: {str(e)}")
    
    def get_tile(self, dataset: str, z: int, x: int, y: int, 
                 bounds: Optional[ee.Geometry] = None) -> RedirectResponse:
        """
        Get map tile for flood dataset
        
        Args:
            dataset: Dataset name (flood_hazard, permanent_water, flood_YYYY)
            z, x, y: Tile coordinates
            bounds: Optional geometry bounds (default: Indonesia)
        
        Returns:
            Redirect to GEE tile URL
        """
        try:
            # Ensure EE is initialized
            if not self.is_initialized:
                logger.info("Earth Engine not initialized, initializing now...")
                self._authenticate_ee()
                
                if not self.is_initialized:
                    raise HTTPException(
                        status_code=503, 
                        detail="Earth Engine initialization failed. Check service account credentials."
                    )
            
            if dataset not in self.datasets:
                raise HTTPException(status_code=404, detail=f"Dataset '{dataset}' not found")
            
            # Get or create map ID (cached)
            map_id = self._get_or_create_map_id(dataset, bounds)
            
            # Generate tile URL
            tile_url = map_id['tile_fetcher'].url_format.format(x=x, y=y, z=z)
            
            return RedirectResponse(url=tile_url)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating flood tile: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    def clear_cache(self, dataset: Optional[str] = None):
        """
        Clear map ID cache
        
        Args:
            dataset: Specific dataset to clear, or None to clear all
        """
        if dataset:
            if dataset in self._map_id_cache:
                del self._map_id_cache[dataset]
                del self._cache_timestamp[dataset]
                logger.info(f"Cleared cache for {dataset}")
        else:
            self._map_id_cache.clear()
            self._cache_timestamp.clear()
            logger.info("Cleared all map ID cache")
    
    def get_available_datasets(self) -> Dict[str, Any]:
        """Get list of available flood datasets"""
        return {
            "status": "success",
            "total_datasets": len(self.datasets),
            "datasets": self.datasets,
            "visualization_styles": self.styles,
            "supported_years": [2021, 2022, 2023, 2024, 2025],
            "season_config": {
                "wet_season": "December (12-01 to 12-31)",
                "dry_season": "August (08-01 to 08-31)",
                "note": "Adjust season dates based on your region's climate"
            },
            "data_source": "Sentinel-1 GRD (COPERNICUS/S1_GRD)",
            "methodology": "VV polarization minimum composite with -15dB threshold",
            "default_bounds": "Indonesia (95°E to 141°E, 11°S to 6°N)",
            "active_bounds": "Custom bbox" if self._custom_bounds_coords else "Default (Indonesia)",
            "cache_info": {
                "enabled": True,
                "duration_seconds": 3600,
                "cached_datasets": list(self._map_id_cache.keys())
            }
        }
    
    def get_dataset_info(self, dataset: str, base_url: str) -> Dict[str, Any]:
        """
        Get detailed information for specific dataset
        
        Args:
            dataset: Dataset name
            base_url: Base URL for tile endpoints
        
        Returns:
            Dataset information with tile URL templates
        """
        if dataset not in self.datasets:
            raise HTTPException(status_code=404, detail=f"Dataset '{dataset}' not found")
        
        dataset_info = self.datasets[dataset]
        style_name = dataset_info['style']
        vis_params = self.styles[style_name]
        
        is_cached = dataset in self._map_id_cache
        
        return {
            "status": "success",
            "dataset": dataset,
            "info": dataset_info,
            "visualization": vis_params,
            "cached": is_cached,
            "tile_urls": {
                "template": f"{base_url}/api/v1/gee/flood/tiles/{dataset}/{{z}}/{{x}}/{{y}}",
                "leaflet": f"L.tileLayer('{base_url}/api/v1/gee/flood/tiles/{dataset}/{{z}}/{{x}}/{{y}}').addTo(map);",
                "openlayers": f"new ol.layer.Tile({{source: new ol.source.XYZ({{url: '{base_url}/api/v1/gee/flood/tiles/{dataset}/{{z}}/{{x}}/{{y}}'}})}});",
                "mapbox": f"map.addLayer({{id: '{dataset}', type: 'raster', source: {{type: 'raster', tiles: ['{base_url}/api/v1/gee/flood/tiles/{dataset}/{{z}}/{{x}}/{{y}}']}}}});"
            },
            "usage_note": "First tile request may be slow as it triggers GEE computation. Subsequent requests use cached map ID."
        }
    
    def analyze_flood_stats(self, geojson: Dict[str, Any], years: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Analyze flood statistics for a GeoJSON area
        
        Args:
            geojson: GeoJSON geometry
            years: List of years to analyze
        
        Returns:
            Flood statistics including area, hazard index, etc.
        """
        try:
            if years is None:
                years = [2021, 2022, 2023, 2024, 2025]
            
            # Convert GeoJSON to ee.Geometry
            if geojson['type'] == 'FeatureCollection':
                geometry = ee.FeatureCollection(geojson).geometry()
            else:
                geometry = ee.Geometry(geojson['geometry'] if 'geometry' in geojson else geojson)
            
            # Calculate total area
            total_area = geometry.area().divide(10000).getInfo()  # Convert to hectares
            
            # Generate flood hazard
            flood_hazard = self.generate_flood_hazard(geometry, years)
            
            # Calculate average hazard
            hazard_stats = flood_hazard.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geometry,
                scale=100,
                maxPixels=1e13
            ).getInfo()
            
            return {
                "status": "success",
                "analysis_period": f"{min(years)}-{max(years)}",
                "total_area_hectares": round(total_area, 2),
                "flood_hazard_index": round(hazard_stats.get('sum', 0), 3),
                "summary": {
                    "total_years_analyzed": len(years),
                    "risk_level": "High" if hazard_stats.get('sum', 0) > 0.5 else "Medium" if hazard_stats.get('sum', 0) > 0.2 else "Low"
                },
                "metadata": {
                    "data_source": "Sentinel-1 GRD",
                    "analysis_timestamp": datetime.utcnow().isoformat() + "Z",
                    "wet_season": "December",
                    "dry_season": "August"
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing flood stats: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# Global service instance
gee_flood_service = GEEFloodService()