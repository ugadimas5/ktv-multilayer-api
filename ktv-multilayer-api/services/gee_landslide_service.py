# services/gee_landslide_service.py
from loguru import logger
from typing import Optional, Dict, Any
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
import ee

from services.ee_workload_tags import workload_tag, TILE_LANDSLIDE

class GEELandslideService:
    """
    Google Earth Engine Landslide Service
    Provides landslide detection and visualization using Sentinel-1 SAR and Sentinel-2 Optical imagery.
    """
    def __init__(self):
        self.is_initialized = False
        self._init_ee()
        self._default_bounds_coords = [95.0, -11.0, 141.0, 6.0]  # Indonesia
        self._custom_bounds_coords = None
        self._cache = {}

    def _init_ee(self):
        try:
            if not ee.data._initialized:
                ee.Initialize()
            self.is_initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize Earth Engine: {e}")
            self.is_initialized = False

    def get_available_datasets(self):
        """Return available landslide datasets"""
        return [
            {
                "id": "landslide_nov_dec_2025",
                "name": "Landslide Detection Nov-Dec 2025 (SAR)",
                "description": "Potential landslide zones detected by Sentinel-1 SAR backscatter change (Dec - Nov 2025)",
                "period": "2025-11 to 2025-12",
                "source": "Sentinel-1 SAR",
                "threshold": -2,
                "region": "Indonesia (default)"
            },
            {
                "id": "landslide_ndvi_nov_dec_2025",
                "name": "Landslide Detection Nov-Dec 2025 (NDVI)",
                "description": "Landslide detection using Sentinel-2 NDVI difference (Before: Nov 2025, After: Dec 2025)",
                "period": "2025-11 to 2025-12",
                "source": "Sentinel-2 Optical",
                "threshold": -0.1,
                "region": "Indonesia (default)"
            }
        ]

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
                # Check if any features exist
                count = filtered.size().getInfo()
                
                if count > 0:
                    logger.info(f"Found {count} boundary features. Returning geometry.")
                    return filtered.geometry()
                else:
                    logger.warning(f"No boundary features found for Country={country}, Province={province}, District={district}")
                    return None
                
            return None
            
        except Exception as e:
            logger.error(f"Error getting boundary geometry: {e}")
            return None

    def get_tile(self, dataset: str, z: int, x: int, y: int, 
                 bounds: Optional[ee.Geometry] = None,
                 country: Optional[str] = None,
                 province: Optional[str] = None,
                 district: Optional[str] = None) -> RedirectResponse:
        """Return tile URL for landslide visualization"""
        
        # Resolve geometry from location params if provided
        custom_bounds = None
        if country or province or district:
            custom_bounds = self._get_boundary_geometry(country, province, district)
            if custom_bounds:
                bounds = custom_bounds
            else:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Location not found: Country={country}, Province={province}, District={district}"
                )

        region = bounds if bounds else ee.Geometry.Rectangle(self._custom_bounds_coords or self._default_bounds_coords)
        
        if dataset == "landslide_nov_dec_2025":
            landslide_img = self._get_landslide_image_sar(region)
            vis_params = {"palette": ["#e66101"], "min": 0, "max": 1}
        elif dataset == "landslide_ndvi_nov_dec_2025":
            landslide_img = self._get_landslide_image_ndvi(region)
            vis_params = {"palette": ["#e66101"], "min": 0, "max": 1}
        else:
            raise ValueError("Unknown landslide dataset")
            
        # Clip to region
        landslide_img = landslide_img.clip(region)

        with workload_tag(TILE_LANDSLIDE):
            map_id = ee.Image(landslide_img).getMapId(vis_params)

        # Generate tile URL
        tile_url = map_id['tile_fetcher'].url_format.format(x=x, y=y, z=z)
            
        return RedirectResponse(url=tile_url)

    def calculate_area(self, dataset: str, country: Optional[str] = None, province: Optional[str] = None, district: Optional[str] = None) -> Dict[str, Any]:
        """Calculate area of landslide for the given boundary"""
        try:
            # Ensure EE is initialized
            if not self.is_initialized:
                self._init_ee()
                if not self.is_initialized:
                     raise HTTPException(status_code=503, detail="Earth Engine not initialized")

            # Get boundary
            bounds = self._get_boundary_geometry(country, province, district)
            if not bounds:
                if not country:
                     raise HTTPException(status_code=400, detail="At least country must be specified for area calculation")
                bounds = ee.Geometry.Rectangle(self._default_bounds_coords)

            if dataset == "landslide_nov_dec_2025":
                image = self._get_landslide_image_sar(bounds)
                # image is masked. Unmask to get 0s where masked, then check > 0?
                # Actually selfMask() or updateMask() makes pixels transparent.
                # We can just use the image itself as mask if it's binary 1s.
                # _get_landslide_image_sar returns masked image.
                mask = image.select('Change_dB').unmask(0).neq(0)
            elif dataset == "landslide_ndvi_nov_dec_2025":
                image = self._get_landslide_image_ndvi(bounds)
                mask = image.select('NDVI_Diff').unmask(0).neq(0)
            else:
                raise ValueError("Unknown dataset")

            # Calculate area
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

    def get_dataset_info(self, dataset, base_url):
        if dataset == "landslide_nov_dec_2025":
            return {
                "id": "landslide_nov_dec_2025",
                "name": "Landslide Detection Nov-Dec 2025 (SAR)",
                "tile_url_template": f"{base_url}/api/v1/gee/landslide/tiles/landslide_nov_dec_2025/{{z}}/{{x}}/{{y}}",
                "visualization": {"palette": ["#e66101"], "min": 0, "max": 1},
                "description": "Potential landslide zones detected by Sentinel-1 SAR backscatter change (Dec - Nov 2025)"
            }
        elif dataset == "landslide_ndvi_nov_dec_2025":
            return {
                "id": "landslide_ndvi_nov_dec_2025",
                "name": "Landslide Detection Nov-Dec 2025 (NDVI)",
                "tile_url_template": f"{base_url}/api/v1/gee/landslide/tiles/landslide_ndvi_nov_dec_2025/{{z}}/{{x}}/{{y}}",
                "visualization": {"palette": ["#e66101"], "min": 0, "max": 1},
                "description": "Landslide detection using Sentinel-2 NDVI difference (Before: Nov 2025, After: Dec 2025)"
            }
        else:
            raise ValueError("Unknown landslide dataset")

    def clear_cache(self):
        self._cache = {}

    def _get_landslide_image_sar(self, region):
        # Dates for Nov and Dec 2025
        nov_start = ee.Date('2025-11-01')
        nov_end = ee.Date('2025-12-01')
        dec_start = ee.Date('2025-12-01')
        dec_end = ee.Date('2026-01-01')
        def get_s1_collection(start, end):
            return ee.ImageCollection('COPERNICUS/S1_GRD')\
                .filterBounds(region)\
                .filterDate(start, end)\
                .filter(ee.Filter.eq('instrumentMode', 'IW'))\
                .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))\
                .filter(ee.Filter.eq('resolution_meters', 10))\
                .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING'))\
                .select('VV')
        def to_db(img):
            return ee.Image(10).multiply(img.log10()).copyProperties(img, img.propertyNames())
        nov_mean = get_s1_collection(nov_start, nov_end).map(to_db).mean()
        dec_mean = get_s1_collection(dec_start, dec_end).map(to_db).mean()
        backscatter_change = ee.Image(dec_mean).subtract(nov_mean).rename(['Change_dB'])
        landslide_mask = backscatter_change.lt(-2)
        landslide_zones = landslide_mask.updateMask(landslide_mask)
        return landslide_zones

    def _get_landslide_image_ndvi(self, region):
        """
        Sentinel-2 NDVI Difference Method
        Before: 2025-11-01 to 2025-12-01
        After: 2025-12-01 to 2026-01-01
        Threshold: NDVI Diff < -0.1
        """
        # Sentinel-2 before (November 2025)
        s2_before = ee.ImageCollection('COPERNICUS/S2_HARMONIZED') \
            .filterBounds(region) \
            .filterDate('2025-11-01', '2025-12-01') \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
            .select(['B4', 'B8'])

        # Sentinel-2 after (December 2025)
        s2_after = ee.ImageCollection('COPERNICUS/S2_HARMONIZED') \
            .filterBounds(region) \
            .filterDate('2025-12-01', '2026-01-01') \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
            .select(['B4', 'B8'])

        def add_ndvi(img):
            ndvi = img.normalizedDifference(['B8', 'B4']).rename('NDVI')
            return img.addBands(ndvi)

        # NDVI before
        before = s2_before.map(add_ndvi).median()

        # NDVI after
        after = s2_after.map(add_ndvi).median()

        # NDVI Difference
        ndvi_diff = after.select('NDVI').subtract(before.select('NDVI')).rename('NDVI_Diff')

        # Threshold landslide (NDVI Diff < -0.1)
        landslide_detected = ndvi_diff.lt(-0.1).selfMask()
        
        return landslide_detected

gee_landslide_service = GEELandslideService()
