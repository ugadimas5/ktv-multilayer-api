"""
Google Earth Engine Commodity Service
Provides commodity mapping and tile generation using Forest Data Partnership datasets
"""

import ee
import os
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from loguru import logger
from typing import Dict, Optional, Any
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()


class GEECommodityService:
    """Service for GEE commodity analysis and visualization"""
    
    def __init__(self):
        """Initialize commodity service"""
        self.datasets = {}
        self.styles = self._get_visualization_styles()
        self._map_id_cache = {}
        self._cache_timestamp = {}
        self.is_initialized = False
        
        # Initialize datasets
        self._initialize_datasets()
        
        # Store bounds as raw coordinates (lazy initialization)
        self._default_bounds_coords = [95, -11, 141, 6]  # Indonesia
        self._custom_bounds_coords = None
        
        # Load custom bbox if exists
        self._load_default_bbox()
        
        # Initialize Earth Engine
        try:
            self._authenticate_ee()
        except Exception as e:
            logger.warning(f"Failed to initialize EE at startup: {e}")
            logger.info("Will retry on first tile request")
    
    def _get_visualization_styles(self) -> Dict[str, Dict]:
        """Get visualization styles for commodity layers"""
        return {
            'rubber': {
                'min': 1,
                'max': 1,
                'palette': ['8B4513']  # Saddle Brown
            },
            'palm': {
                'min': 1,
                'max': 1,
                'palette': ['228B22']  # Forest Green
            },
            'cocoa': {
                'min': 1,
                'max': 1,
                'palette': ['654321']  # Dark Brown
            },
            'coffee': {
                'min': 1,
                'max': 1,
                'palette': ['6F4E37']  # Coffee Brown
            }
        }
    
    def _initialize_datasets(self):
        """Initialize commodity dataset definitions"""
        try:
            self.datasets = {
                'rubber': {
                    'name': 'Rubber Plantations',
                    'description': 'Rubber plantation probability map from Forest Data Partnership',
                    'asset_id': 'projects/forestdatapartnership/assets/rubber/model_2025a',
                    'band': 'probability',
                    'threshold': 0.5,
                    'style': 'rubber'
                },
                'palm': {
                    'name': 'Palm Oil Plantations',
                    'description': 'Palm oil plantation probability map from Forest Data Partnership',
                    'asset_id': 'projects/forestdatapartnership/assets/palm/model_2025a',
                    'band': 'probability',
                    'threshold': 0.5,
                    'style': 'palm'
                },
                'cocoa': {
                    'name': 'Cocoa Plantations',
                    'description': 'Cocoa plantation probability map from Forest Data Partnership',
                    'asset_id': 'projects/forestdatapartnership/assets/cocoa/model_2025a',
                    'band': 'probability',
                    'threshold': 0.5,
                    'style': 'cocoa'
                },
                'coffee': {
                    'name': 'Coffee Plantations',
                    'description': 'Coffee plantation probability map from Forest Data Partnership',
                    'asset_id': 'projects/forestdatapartnership/assets/coffee/model_2025a',
                    'band': 'probability',
                    'threshold': 0.5,
                    'style': 'coffee'
                }
            }
            logger.info("Commodity datasets initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing commodity datasets: {e}")
            raise
    
    def _authenticate_ee(self):
        """Authenticate Earth Engine with service account"""
        try:
            if self.is_initialized:
                logger.info("Earth Engine already initialized for commodity service")
                return
            
            # Get service account path
            service_account_path = os.getenv("EE_SINGLE_SERVICE_ACCOUNT_PATH")
            if not service_account_path:
                service_account_path = os.getenv("EE_SERVICE_ACCOUNT_PATH")
            
            if not service_account_path:
                raise ValueError("EE_SINGLE_SERVICE_ACCOUNT_PATH or EE_SERVICE_ACCOUNT_PATH not set in .env file")
            
            # Convert to absolute path
            if not os.path.isabs(service_account_path):
                project_root = Path(__file__).parent.parent
                service_account_path = project_root / service_account_path
            else:
                service_account_path = Path(service_account_path)
            
            if not service_account_path.is_file():
                raise FileNotFoundError(f"Service account file not found: {service_account_path}")
            
            logger.info(f"Initializing Earth Engine for commodity service: {service_account_path}")
            
            credentials = ee.ServiceAccountCredentials(
                email=None,
                key_file=str(service_account_path)
            )
            ee.Initialize(credentials)
            
            self.is_initialized = True
            logger.success("Earth Engine initialized successfully for commodity service")
            
        except Exception as e:
            logger.error(f"Failed to initialize Earth Engine: {e}")
            logger.warning("Commodity service will initialize EE on first tile request")
            self.is_initialized = False
    
    def _load_default_bbox(self):
        """Load bbox from flood_test.geojson if exists"""
        try:
            import json
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            geojson_path = os.path.join(base_dir, 'data', 'temp', 'flood_test.geojson')
            
            if os.path.exists(geojson_path):
                with open(geojson_path, 'r') as f:
                    geojson_data = json.load(f)
                    
                    # Extract bbox
                    if geojson_data['type'] == 'FeatureCollection':
                        coords = geojson_data['features'][0]['geometry']['coordinates'][0]
                    else:
                        coords = geojson_data['geometry']['coordinates'][0]
                    
                    lons = [c[0] for c in coords]
                    lats = [c[1] for c in coords]
                    bbox = [min(lons), min(lats), max(lons), max(lats)]
                    
                    self._custom_bounds_coords = bbox
                    logger.info(f"Loaded custom bbox for commodity: {bbox}")
            else:
                logger.info("flood_test.geojson not found, using default Indonesia bounds")
        except Exception as e:
            logger.warning(f"Could not load bbox from flood_test.geojson: {e}")
    
    def get_active_bounds(self) -> ee.Geometry:
        """Get currently active bounds"""
        if not self.is_initialized:
            self._authenticate_ee()
        
        if self._custom_bounds_coords:
            return ee.Geometry.Rectangle(self._custom_bounds_coords)
        else:
            return ee.Geometry.Rectangle(self._default_bounds_coords)
    
    def _get_commodity_image(self, commodity: str, bounds: ee.Geometry) -> ee.Image:
        """
        Get commodity image for specific commodity type
        
        Args:
            commodity: Commodity name (rubber, palm, cocoa, coffee)
            bounds: Area of interest
        
        Returns:
            Binary commodity image (0 or 1)
        """
        if commodity not in self.datasets:
            raise HTTPException(status_code=404, detail=f"Commodity '{commodity}' not found")
        
        dataset = self.datasets[commodity]
        
        try:
            # Try as ImageCollection first
            img = ee.ImageCollection(dataset['asset_id']).mosaic().select(dataset['band'])
        except Exception:
            # Fallback to Image
            img = ee.Image(dataset['asset_id']).select(dataset['band'])
        
        # Apply threshold and clip to bounds
        binary_image = img.gt(dataset['threshold']).clip(bounds)
        
        return binary_image
    
    def _get_or_create_map_id(self, commodity: str, bounds: ee.Geometry = None) -> Dict:
        """Get cached map ID or create new one"""
        cache_key = f"{commodity}"
        
        # Check cache (1 hour validity)
        if cache_key in self._map_id_cache:
            cached_time = self._cache_timestamp.get(cache_key, 0)
            if (datetime.now().timestamp() - cached_time) < 3600:
                logger.info(f"Using cached map ID for {commodity}")
                return self._map_id_cache[cache_key]
        
        # Use active bounds if not specified
        if bounds is None:
            bounds = self.get_active_bounds()
        
        logger.info(f"Generating new map ID for {commodity}")
        
        # Get commodity image
        image = self._get_commodity_image(commodity, bounds)
        
        # Apply selfMask to make 0 transparent
        viz_image = image.selfMask()
        
        # Get visualization parameters
        vis_params = self.styles[commodity]
        
        try:
            map_id = viz_image.getMapId(vis_params)
            
            # Cache it
            self._map_id_cache[cache_key] = map_id
            self._cache_timestamp[cache_key] = datetime.now().timestamp()
            
            logger.success(f"Map ID generated and cached for {commodity}")
            return map_id
            
        except Exception as e:
            logger.error(f"Error getting map ID from GEE: {e}")
            raise HTTPException(status_code=500, detail=f"GEE computation error: {str(e)}")
    
    def get_tile(self, commodity: str, z: int, x: int, y: int,
                 bounds: Optional[ee.Geometry] = None) -> RedirectResponse:
        """
        Get map tile for commodity dataset
        
        Args:
            commodity: Commodity name (rubber, palm, cocoa, coffee)
            z, x, y: Tile coordinates
            bounds: Optional geometry bounds
        
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
            
            if commodity not in self.datasets:
                raise HTTPException(status_code=404, detail=f"Commodity '{commodity}' not found")
            
            # Get or create map ID (cached)
            map_id = self._get_or_create_map_id(commodity, bounds)
            
            # Generate tile URL
            tile_url = map_id['tile_fetcher'].url_format.format(x=x, y=y, z=z)
            
            return RedirectResponse(url=tile_url)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating commodity tile: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    def clear_cache(self, commodity: Optional[str] = None):
        """Clear map ID cache"""
        if commodity:
            if commodity in self._map_id_cache:
                del self._map_id_cache[commodity]
                del self._cache_timestamp[commodity]
                logger.info(f"Cleared cache for {commodity}")
        else:
            self._map_id_cache.clear()
            self._cache_timestamp.clear()
            logger.info("Cleared all commodity cache")
    
    def get_available_datasets(self) -> Dict[str, Any]:
        """Get list of available commodity datasets"""
        return {
            "status": "success",
            "total_datasets": len(self.datasets),
            "datasets": self.datasets,
            "visualization_styles": self.styles,
            "data_source": "Forest Data Partnership",
            "model_version": "2025a",
            "default_threshold": 0.5,
            "active_bounds": "Custom bbox" if self._custom_bounds_coords else "Default (Indonesia)",
            "cache_info": {
                "enabled": True,
                "duration_seconds": 3600,
                "cached_datasets": list(self._map_id_cache.keys())
            }
        }
    
    def get_dataset_info(self, commodity: str, base_url: str) -> Dict[str, Any]:
        """Get detailed information for specific commodity"""
        if commodity not in self.datasets:
            raise HTTPException(status_code=404, detail=f"Commodity '{commodity}' not found")
        
        dataset_info = self.datasets[commodity]
        vis_params = self.styles[commodity]
        is_cached = commodity in self._map_id_cache
        
        return {
            "status": "success",
            "commodity": commodity,
            "info": dataset_info,
            "visualization": vis_params,
            "cached": is_cached,
            "tile_urls": {
                "template": f"{base_url}/api/v1/gee/commodity/tiles/{commodity}/{{z}}/{{x}}/{{y}}",
                "leaflet": f"L.tileLayer('{base_url}/api/v1/gee/commodity/tiles/{commodity}/{{z}}/{{x}}/{{y}}').addTo(map);",
                "openlayers": f"new ol.layer.Tile({{source: new ol.source.XYZ({{url: '{base_url}/api/v1/gee/commodity/tiles/{commodity}/{{z}}/{{x}}/{{y}}'}})}});",
                "mapbox": f"map.addLayer({{id: '{commodity}', type: 'raster', source: {{type: 'raster', tiles: ['{base_url}/api/v1/gee/commodity/tiles/{commodity}/{{z}}/{{x}}/{{y}}']}}}});"
            },
            "usage_note": "First tile request may be slow as it triggers GEE computation. Subsequent requests use cached map ID."
        }


# Global service instance
gee_commodity_service = GEECommodityService()
