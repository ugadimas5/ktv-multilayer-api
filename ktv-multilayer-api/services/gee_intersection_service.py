"""
Google Earth Engine Intersection Service
Provides intersection analysis between Commodity, Flood, and Landslide datasets.
"""

import ee
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from loguru import logger
from typing import Dict, Optional, Any
from datetime import datetime

from services.gee_commodity_service import gee_commodity_service
from services.gee_flood_service import gee_flood_service
from services.gee_landslide_service import gee_landslide_service
from services.ee_workload_tags import workload_tag, TILE_INTERSECTION

class GEEIntersectionService:
    """Service for GEE intersection analysis and visualization"""
    
    def __init__(self):
        self.styles = {
            'commodity_flood': {'min': 0, 'max': 1, 'palette': ['#984ea3']}, # Purple
            'commodity_landslide': {'min': 0, 'max': 1, 'palette': ['#e41a1c']}, # Red
            'commodity_flood_landslide': {'min': 0, 'max': 1, 'palette': ['#000000']} # Black
        }
        self._map_id_cache = {}
        self._cache_timestamp = {}
        self._default_bounds_coords = [95, -11, 141, 6]  # Indonesia

    def _get_boundary_geometry(self, country: Optional[str], province: Optional[str], district: Optional[str]) -> Optional[ee.Geometry]:
        """Reuse boundary logic from commodity service"""
        return gee_commodity_service._get_boundary_geometry(country, province, district)

    def _get_intersection_image(self, type: str, commodity: str, bounds: ee.Geometry) -> ee.Image:
        """Generate intersection image based on type"""
        
        # Ensure services are initialized
        if not gee_commodity_service.is_initialized: gee_commodity_service._authenticate_ee()
        if not gee_flood_service.is_initialized: gee_flood_service._authenticate_ee()
        if not gee_landslide_service.is_initialized: gee_landslide_service._init_ee()

        # Get Commodity Image (Binary)
        comm_img = gee_commodity_service._get_commodity_image(commodity, bounds)

        if type == 'commodity_flood':
            # Intersect with Flood Hazard (> 0.1)
            flood_img = gee_flood_service.generate_flood_hazard(bounds)
            flood_mask = flood_img.gt(0.1)
            return comm_img.And(flood_mask).selfMask()
        
        elif type == 'commodity_landslide':
            # Intersect with Landslide (SAR Nov-Dec 2025)
            landslide_img = gee_landslide_service._get_landslide_image_sar(bounds)
            # Landslide image is masked. Unmask to get 0/1.
            landslide_mask = landslide_img.select('Change_dB').unmask(0).neq(0)
            return comm_img.And(landslide_mask).selfMask()
            
        elif type == 'commodity_flood_landslide':
            # Intersect with Flood AND Landslide
            flood_img = gee_flood_service.generate_flood_hazard(bounds)
            flood_mask = flood_img.gt(0.1)
            
            landslide_img = gee_landslide_service._get_landslide_image_sar(bounds)
            landslide_mask = landslide_img.select('Change_dB').unmask(0).neq(0)
            
            return comm_img.And(flood_mask).And(landslide_mask).selfMask()
            
        else:
            raise ValueError(f"Unknown intersection type: {type}")

    def get_tile(self, type: str, commodity: str, z: int, x: int, y: int,
                 country: Optional[str] = None,
                 province: Optional[str] = None,
                 district: Optional[str] = None) -> RedirectResponse:
        """Get map tile for intersection"""
        try:
            # Get bounds
            bounds = self._get_boundary_geometry(country, province, district)
            if not bounds:
                bounds = ee.Geometry.Rectangle(self._default_bounds_coords)

            # Generate cache key
            cache_key = f"{type}_{commodity}_{country}_{province}_{district}"
            
            # Check cache
            if cache_key in self._map_id_cache:
                cached_time = self._cache_timestamp.get(cache_key, 0)
                if (datetime.now().timestamp() - cached_time) < 3600:
                    map_id = self._map_id_cache[cache_key]
                    tile_url = map_id['tile_fetcher'].url_format.format(x=x, y=y, z=z)
                    return RedirectResponse(url=tile_url)

            # Generate image
            image = self._get_intersection_image(type, commodity, bounds)
            
            # Clip if boundary exists
            if country or province or district:
                image = image.clip(bounds)

            # Get Map ID
            vis_params = self.styles.get(type, {'min': 0, 'max': 1})
            with workload_tag(TILE_INTERSECTION):
                map_id = image.getMapId(vis_params)

            # Cache
            self._map_id_cache[cache_key] = map_id
            self._cache_timestamp[cache_key] = datetime.now().timestamp()
            
            tile_url = map_id['tile_fetcher'].url_format.format(x=x, y=y, z=z)
            return RedirectResponse(url=tile_url)
            
        except Exception as e:
            logger.error(f"Error generating intersection tile: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def calculate_area(self, type: str, commodity: str,
                       country: Optional[str] = None,
                       province: Optional[str] = None,
                       district: Optional[str] = None) -> Dict[str, Any]:
        """Calculate area of intersection"""
        try:
            # Get bounds
            bounds = self._get_boundary_geometry(country, province, district)
            if not bounds:
                if not country:
                     raise HTTPException(status_code=400, detail="At least country must be specified for area calculation")
                bounds = ee.Geometry.Rectangle(self._default_bounds_coords)

            # Get image
            image = self._get_intersection_image(type, commodity, bounds)
            
            # Calculate area
            area_image = image.multiply(ee.Image.pixelArea())
            
            # Determine scale
            scale = 10
            if not district:
                if province:
                    scale = 30
                else:
                    scale = 100
            
            logger.info(f"Calculating area for {type} ({commodity}) with scale={scale}m")
            
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
                # The reducer output key is usually 'probability' or similar depending on the band name.
                # Since we didn't rename the band explicitly in _get_intersection_image (it inherits from And()),
                # it might be 'probability' (from commodity) or 'flood' etc.
                # But reduceRegion with one band returns a dict with one key.
                area_sqm = list(stats.values())[0]
                
            if area_sqm is None: area_sqm = 0
            area_ha = area_sqm / 10000
            
            return {
                "analysis_type": type,
                "commodity": commodity,
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
            logger.error(f"Error calculating intersection area: {e}")
            raise HTTPException(status_code=500, detail=str(e))

# Global instance
gee_intersection_service = GEEIntersectionService()
