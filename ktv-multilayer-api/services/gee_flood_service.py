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
        # Default bounds (Indonesia) if no geometry provided
        self._default_bounds_coords = [95, -11, 141, 6]  # Indonesia [west, south, east, north]
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
                'flood_nov_dec_2025': {
                    'name': 'Flood Nov-Dec 2025',
                    'description': 'Flood detection for Nov-Dec 2025 vs Baseline (Aug-Oct 2025)',
                    'type': 'binary',
                    'style': 'flood_binary',
                    'year': 2025
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
            logger.info("Credentials loaded, calling ee.Initialize()...")
            ee.Initialize(credentials)
            
            self.is_initialized = True
            logger.success("Earth Engine initialized successfully for flood service")
            
        except Exception as e:
            logger.error(f"Failed to initialize Earth Engine: {e}")
            import traceback
            logger.error(traceback.format_exc())
            logger.warning("Flood service will initialize EE on first tile request")
            self.is_initialized = False
    
    # REMOVED: _load_default_bbox, _extract_bbox_from_geojson, load_bbox_from_geojson, get_active_bounds
    # Bounds/geometry must now be provided explicitly to all methods (from session or request)
    
    def _get_sentinel1_collection(self):
        """Get Sentinel-1 image collection"""
        return ee.ImageCollection('COPERNICUS/S1_GRD')
    
    def _process_water_period(self, bounds: ee.Geometry, start_date: str, end_date: str) -> ee.Image:
        """
        Process water detection for a specific date range
        
        Args:
            bounds: Area of interest geometry
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            Water mask image
        """
        s1 = self._get_sentinel1_collection()
        
        # Filter collection
        image = s1 \
            .filterBounds(bounds) \
            .filterDate(start_date, end_date) \
            .filter(ee.Filter.eq('transmitterReceiverPolarisation', ['VV', 'VH'])) \
            .select('VV')
        
        # Minimum composite with speckle filtering
        # Apply focal mean BEFORE clipping to avoid edge effects
        image_min = image.reduce(ee.Reducer.percentile([10])) \
            .focalMean(50, 'square', 'meters') \
            .clip(bounds)
        
        # Water mask (threshold -15 dB)
        water = image_min.lt(-15).toByte().rename('water')
        
        return water

    def generate_flood_event(self, bounds: ee.Geometry, baseline_start: str, baseline_end: str, analysis_start: str, analysis_end: str) -> ee.Image:
        """
        Generate flood detection for a specific event compared to a baseline
        
        Args:
            bounds: Area of interest geometry
            baseline_start: Baseline start date
            baseline_end: Baseline end date
            analysis_start: Analysis start date
            analysis_end: Analysis end date
            
        Returns:
            Flood mask image
        """
        water_baseline = self._process_water_period(bounds, baseline_start, baseline_end)
        water_analysis = self._process_water_period(bounds, analysis_start, analysis_end)
        
        # Flood = water in analysis AND NOT water in baseline
        flood = water_analysis.And(water_baseline.eq(0)).rename('flood').toByte()
        
        return flood.selfMask()

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
        # Apply focal mean BEFORE clipping to avoid edge effects
        image_min = image.reduce(ee.Reducer.percentile([10])) \
            .focalMean(50, 'square', 'meters') \
            .clip(bounds)
        
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

    def _get_boundary_geometry(self, country: Optional[str], province: Optional[str], district: Optional[str]) -> Optional[ee.Geometry]:
        """
        Get geometry from GAUL datasets based on location parameters
        """
        if not country and not province and not district:
            return None

        try:
            logger.info(f"Fetching boundary geometry for: Country={country}, Province={province}, District={district}")
            # Define collections
            l1_coll = ee.FeatureCollection("projects/sat-io/open-datasets/FAO/GAUL/GAUL_2024_L1")
            l2_coll = ee.FeatureCollection("projects/sat-io/open-datasets/FAO/GAUL/GAUL_2024_L2")
            
            filtered = None
            
            if district:
                # Use L2 for district
                filtered = l2_coll.filter(ee.Filter.eq('gaul2_name', district))
                if province:
                    filtered = filtered.filter(ee.Filter.eq('gaul1_name', province))
                if country:
                    filtered = filtered.filter(ee.Filter.eq('gaul0_name', country))
                
            elif province:
                # Use L1 for province
                filtered = l1_coll.filter(ee.Filter.eq('gaul1_name', province))
                if country:
                    filtered = filtered.filter(ee.Filter.eq('gaul0_name', country))
                
            elif country:
                # Use L1 for country (aggregating provinces)
                filtered = l1_coll.filter(ee.Filter.eq('gaul0_name', country))
            
            if filtered:
                # Log the filter construction (lightweight)
                logger.debug("Boundary filter constructed, checking for features...")
                
                # Check if any features exist (synchronous call)
                count = filtered.size().getInfo()
                
                if count > 0:
                    logger.info(f"Found {count} boundary features. Returning geometry.")
                    return filtered.geometry()
                else:
                    logger.warning(f"No boundary features found for Country={country}, Province={province}, District={district}")
                    
                    # DEBUG: List available districts if province is found
                    if province and district:
                        try:
                            # Check if province exists
                            prov_check = l2_coll.filter(ee.Filter.eq('gaul1_name', province))
                            if country:
                                prov_check = prov_check.filter(ee.Filter.eq('gaul0_name', country))
                            
                            prov_count = prov_check.size().getInfo()
                            if prov_count > 0:
                                # List first 50 districts in this province
                                districts = prov_check.aggregate_array('gaul2_name').distinct().sort().slice(0, 50).getInfo()
                                logger.info(f"Available districts in {province}: {districts}")
                            else:
                                logger.warning(f"Province '{province}' not found either. Check spelling.")
                                
                                # List available provinces in this country
                                if country:
                                    country_check = l1_coll.filter(ee.Filter.eq('gaul0_name', country))
                                    c_count = country_check.size().getInfo()
                                    if c_count > 0:
                                        provs = country_check.aggregate_array('gaul1_name').distinct().sort().getInfo()
                                        logger.info(f"Available provinces in {country}: {provs}")
                                    else:
                                        logger.warning(f"Country '{country}' not found.")
                                        
                        except Exception as debug_e:
                            logger.error(f"Debug error: {debug_e}")

                    return None
                
            return None
            
        except Exception as e:
            logger.error(f"Error getting boundary geometry: {e}")
            return None
    
    def _get_or_create_map_id(self, dataset: str, bounds: ee.Geometry = None,
                              country: str = None, province: str = None, district: str = None) -> Dict:
        """
        Get cached map ID or create new one
        
        Args:
            dataset: Dataset name
            bounds: Geometry bounds (if None, uses custom_bounds or default_bounds)
            country: Country name filter
            province: Province name filter
            district: District name filter
        
        Returns:
            Map ID dictionary
        """
        cache_key = f"{dataset}_{country}_{province}_{district}"
        
        # Check if cached and still valid (cache for 1 hour)
        if cache_key in self._map_id_cache:
            cached_time = self._cache_timestamp.get(cache_key, 0)
            if (datetime.now().timestamp() - cached_time) < 3600:  # 1 hour
                logger.info(f"Using cached map ID for {dataset}")
                return self._map_id_cache[cache_key]
        
        # Resolve geometry from location params if provided
        custom_bounds = None
        if country or province or district:
            custom_bounds = self._get_boundary_geometry(country, province, district)
            if custom_bounds:
                bounds = custom_bounds
            else:
                # If user specified location but we couldn't find it, raise 404
                # This ensures we don't show the default map when a specific one was requested
                raise HTTPException(
                    status_code=404, 
                    detail=f"Location not found: Country={country}, Province={province}, District={district}"
                )
        
        # Use default bounds if not specified
        if bounds is None:
            import ee
            bounds = ee.Geometry.Rectangle(self._default_bounds_coords)
        
        logger.info(f"Generating new map ID for {dataset}")
        
        # Generate appropriate image based on dataset
        if dataset == 'flood_hazard':
            image = self.generate_flood_hazard(bounds)
        elif dataset == 'permanent_water':
            image = self.generate_permanent_water(bounds)
        elif dataset == 'flood_nov_dec_2025':
            image = self.generate_flood_event(
                bounds, 
                '2025-08-01', '2025-10-31', # Baseline
                '2025-11-01', '2025-12-31'  # Analysis
            )
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
            # Clip image to bounds if we have specific geometry
            # Only clip if we have custom bounds or if we want to restrict to default bounds
            # Using bounds (which is either custom or default) ensures we don't process/show world-wide
            image = image.clip(bounds)

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
                 bounds: Optional[ee.Geometry] = None,
                 country: Optional[str] = None,
                 province: Optional[str] = None,
                 district: Optional[str] = None) -> RedirectResponse:
        """
        Get map tile for flood dataset
        
        Args:
            dataset: Dataset name (flood_hazard, permanent_water, flood_YYYY)
            z, x, y: Tile coordinates
            bounds: Optional geometry bounds (default: Indonesia)
            country: Optional country filter
            province: Optional province filter
            district: Optional district filter
        
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
            map_id = self._get_or_create_map_id(dataset, bounds, country, province, district)
            
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
            "active_bounds": "Session geometry" if bounds else "Default (Indonesia)",
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
    
    def calculate_area(self, dataset: str, country: Optional[str] = None, province: Optional[str] = None, district: Optional[str] = None) -> Dict[str, Any]:
        """Calculate area of flood/water for the given boundary"""
        try:
            # Ensure EE is initialized
            if not self.is_initialized:
                self._authenticate_ee()
                if not self.is_initialized:
                     raise HTTPException(status_code=503, detail="Earth Engine not initialized")

            # Get boundary
            bounds = self._get_boundary_geometry(country, province, district)
            if not bounds:
                if not country:
                     raise HTTPException(status_code=400, detail="At least country must be specified for area calculation")
                bounds = ee.Geometry.Rectangle(self._default_bounds_coords)

            # Get image based on dataset
            if dataset == 'flood_hazard':
                image = self.generate_flood_hazard(bounds)
                # Flood hazard is 0-1 index. We calculate area where hazard > 0
                mask = image.gt(0)
            elif dataset == 'permanent_water':
                image = self.generate_permanent_water(bounds)
                mask = image.select('water').gt(0)
            elif dataset == 'flood_nov_dec_2025':
                image = self.generate_flood_event(
                    bounds, 
                    '2025-08-01', '2025-10-31', 
                    '2025-11-01', '2025-12-31'
                )
                mask = image.select('flood').gt(0)
            elif dataset.startswith('flood_'):
                year = int(dataset.split('_')[1])
                image = self.generate_flood_for_year(bounds, year)
                mask = image.select('flood').gt(0)
            else:
                raise HTTPException(status_code=404, detail=f"Dataset {dataset} not supported for area calculation")

            # Calculate area
            # pixelArea() gives area in square meters
            area_image = mask.multiply(ee.Image.pixelArea())
            
            # Determine appropriate scale to balance speed and accuracy
            scale = 10
            if not district:
                if province:
                    scale = 30  # Province level: 30m
                else:
                    scale = 100 # Country level: 100m
            
            logger.info(f"Calculating area for {dataset} with scale={scale}m")
            
            stats = area_image.reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=bounds,
                scale=scale,
                maxPixels=1e10,
                bestEffort=True,
                tileScale=4
            ).getInfo()
            
            # Get the first value from stats
            area_sqm = 0
            if stats:
                area_sqm = list(stats.values())[0]
                
            if area_sqm is None: area_sqm = 0
            area_ha = area_sqm / 10000
            
            return {
                "dataset": dataset,
                "location": {
                    "country": country,
                    "province": province,
                    "district": district
                },
                "scale_used": scale,
                "area_sqm": round(area_sqm, 2),
                "area_ha": round(area_ha, 2)
            }
            
        except Exception as e:
            logger.error(f"Error calculating area: {e}")
            raise HTTPException(status_code=500, detail=str(e))

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