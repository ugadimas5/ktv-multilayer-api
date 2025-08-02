"""
Google Earth Engine Dataset Service for Tile Services
Simplified version focusing on 6 key datasets for EUDR compliance
"""

import ee
import os
from typing import Optional, Dict, Any
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
from pathlib import Path
from loguru import logger

# Load environment variables
load_dotenv()

class GEEDatasetService:
    def __init__(self):
        self.ee_image = None
        self.is_initialized = False
        
    def authenticate_ee(self) -> None:
        """Initialize Earth Engine with service account"""
        try:
            service_account_path = os.getenv("EE_SERVICE_ACCOUNT_PATH")
            if not service_account_path:
                raise ValueError("EE_SERVICE_ACCOUNT_PATH not set in .env file")
            
            # Convert relative path to absolute path
            if not os.path.isabs(service_account_path):
                # Get project root directory (3 levels up from this file)
                project_root = Path(__file__).parent.parent.parent
                service_account_path = project_root / service_account_path
            
            service_account_path = str(service_account_path)
            
            if not os.path.exists(service_account_path):
                raise FileNotFoundError(f"Service account file not found: {service_account_path}")
            
            logger.info(f"Using service account: {service_account_path}")
            
            # Initialize EE with service account
            credentials = ee.ServiceAccountCredentials(
                email=None,  # Will be read from the JSON file
                key_file=service_account_path
            )
            ee.Initialize(credentials)
            
            # Load datasets
            self.ee_image = self._get_ee_datasets()
            self.is_initialized = True
            
            logger.info("Earth Engine initialized successfully for tile serving")
            
        except Exception as e:
            logger.error(f"Failed to initialize Earth Engine: {e}")
            raise HTTPException(status_code=500, detail=f"EE initialization failed: {str(e)}")
    
    def _get_ee_datasets(self) -> ee.Image:
        """Load simplified Earth Engine datasets focusing on 6 key datasets"""
        try:
            logger.info("Loading Earth Engine datasets...")
            
            # 1. GFW (Global Forest Watch) - Forest Cover
            gfc = ee.Image("UMD/hansen/global_forest_change_2024_v1_12")
            gfw_forest = gfc.select("treecover2000").gt(10).rename("gfw")
            
            # 2. GFW Loss (2021-2024) - Forest Loss
            loss_2021_2024 = gfc.select("lossyear").gte(21).And(gfc.select("lossyear").lte(24))
            gfw_loss = loss_2021_2024.selfMask().rename("gfw_loss")
            
            # 3. JRC (Joint Research Centre) - Forest Cover 2020
            eufo = ee.ImageCollection("JRC/GFC2020/V2").mosaic().rename("jrc").selfMask()
            
            # 4. JRC Loss (2021-2024) - JRC TMF Deforestation
            jrc_loss = self._get_jrc_tmf_deforestation().rename("jrc_loss")
            
            # 5. SBTN (Science Based Targets Network) - Natural Lands
            sbtn = ee.Image('WRI/SBTN/naturalLands/v1_1/2020').select('natural').rename('sbtn').selfMask()
            
            # 6. SBTN Loss (2021-2024) - Deforestation in SBTN areas
            sbtn_mask = sbtn.eq(1)
            sbtn_loss = loss_2021_2024.updateMask(sbtn_mask).selfMask().rename("sbtn_loss")
            
            # Combine all 6 datasets
            combined_image = gfw_forest.addBands(gfw_loss) \
                                      .addBands(eufo) \
                                      .addBands(jrc_loss) \
                                      .addBands(sbtn) \
                                      .addBands(sbtn_loss)
            
            logger.info("Earth Engine datasets loaded successfully")
            return combined_image
            
        except Exception as e:
            logger.error(f"Error loading datasets: {e}")
            raise HTTPException(status_code=500, detail=f"Error loading datasets: {str(e)}")
    
    def _get_jrc_tmf_deforestation(self):
        """Get JRC TMF deforestation data for 2021-2024"""
        try:
            logger.info("Loading JRC TMF v1_2024 deforestation data...")
            
            # Try to load JRC TMF v1_2024
            asset_id = "projects/JRC/TMF/v1_2024/AnnualChanges"
            tmf_image = ee.ImageCollection(asset_id).mosaic()
            
            jrc_total = ee.Image(0)
            
            # Process years 2021-2024
            for year in range(2021, 2025):
                band_name = f'Dec{year}'
                try:
                    # Value 3 = deforestation in JRC TMF
                    deforestation = tmf_image.select(band_name).eq(3)
                    jrc_total = jrc_total.add(deforestation)
                    logger.info(f"Added JRC TMF deforestation for {year}")
                except Exception as e:
                    logger.warning(f"Band {band_name} not found or error: {e}")
            
            jrc_total = jrc_total.gt(0).selfMask()
            logger.info("JRC TMF deforestation data loaded successfully")
            
            return jrc_total
            
        except Exception as e:
            logger.warning(f"Failed to load JRC TMF. Using fallback: {e}")
            # Fallback: return empty image
            return ee.Image(0).rename("jrc_loss")
    
    def get_available_datasets(self) -> Dict[str, Any]:
        """Get list of 6 available datasets for EUDR compliance"""
        datasets = {
            "gfw": {
                "name": "GFW Forest Cover",
                "description": "Global Forest Watch tree cover from Hansen dataset",
                "band": "gfw",
                "type": "forest_cover",
                "color": "#228B22"
            },
            "gfw_loss": {
                "name": "GFW Forest Loss 2021-2024",
                "description": "Global Forest Watch deforestation 2021-2024",
                "band": "gfw_loss",
                "type": "deforestation",
                "color": "#FF4500"
            },
            "jrc": {
                "name": "JRC Forest Cover 2020",
                "description": "Joint Research Centre Global Forest Cover 2020",
                "band": "jrc",
                "type": "forest_cover",
                "color": "#32CD32"
            },
            "jrc_loss": {
                "name": "JRC Forest Loss 2021-2024",
                "description": "JRC Tropical Moist Forest deforestation 2021-2024",
                "band": "jrc_loss",
                "type": "deforestation",
                "color": "#FF6347"
            },
            "sbtn": {
                "name": "SBTN Natural Lands 2020",
                "description": "Science Based Targets Network Natural Lands",
                "band": "sbtn",
                "type": "forest_cover",
                "color": "#90EE90"
            },
            "sbtn_loss": {
                "name": "SBTN Forest Loss 2021-2024",
                "description": "Deforestation in SBTN natural lands areas 2021-2024",
                "band": "sbtn_loss",
                "type": "deforestation",
                "color": "#FF8C00"
            }
        }
        
        return {
            "datasets": datasets,
            "total_count": len(datasets),
            "description": "6 core datasets for EUDR compliance monitoring"
        }
    
    def get_tile(self, dataset: str, z: int, x: int, y: int, style: str = "default") -> RedirectResponse:
        """Get map tile for specific dataset"""
        if not self.is_initialized or self.ee_image is None:
            logger.info("Initializing Earth Engine for tile service...")
            self.authenticate_ee()
        
        # Get available datasets
        available_datasets = self.get_available_datasets()["datasets"]
        
        if dataset not in available_datasets:
            raise HTTPException(status_code=404, detail=f"Dataset '{dataset}' not found")
        
        band_name = available_datasets[dataset]["band"]
        
        # Visualization parameters
        vis_params = self._get_visualization_params(dataset, style)
        
        try:
            logger.info(f"Generating tile for {dataset} at {z}/{x}/{y}")
            
            # Select band and create map tiles
            image_band = self.ee_image.select(band_name)
            
            # Apply masking for datasets that need it
            if dataset in ["gfw_loss", "jrc_loss", "sbtn_loss"]:
                image_band = image_band.updateMask(image_band.gt(0))
            
            # Get tile URL from Earth Engine
            map_id = image_band.getMapId(vis_params)
            tile_url = map_id['tile_fetcher'].url_format.format(z=z, x=x, y=y)
            
            logger.info(f"Redirecting to: {tile_url}")
            
            # Redirect to Earth Engine tile
            return RedirectResponse(url=tile_url)
            
        except Exception as e:
            logger.error(f"Error generating tile: {e}")
            raise HTTPException(status_code=500, detail=f"Error generating tile: {str(e)}")
    
    def _get_visualization_params(self, dataset: str, style: str) -> Dict[str, Any]:
        """Get visualization parameters for each dataset"""
        
        # Forest cover datasets (green colors)
        if dataset in ["gfw", "jrc", "sbtn"]:
            if style == "default":
                return {'min': 1, 'max': 1, 'palette': ['#228B22']}  # Forest Green
            elif style == "light_green":
                return {'min': 1, 'max': 1, 'palette': ['#90EE90']}  # Light Green
            elif style == "dark_green":
                return {'min': 1, 'max': 1, 'palette': ['#006400']}  # Dark Green
        
        # Deforestation datasets (orange/red colors)
        elif dataset in ["gfw_loss", "jrc_loss", "sbtn_loss"]:
            if style == "default":
                return {'min': 1, 'max': 1, 'palette': ['#FF4500']}  # Orange Red
            elif style == "red":
                return {'min': 1, 'max': 1, 'palette': ['#FF0000']}  # Red
            elif style == "orange":
                return {'min': 1, 'max': 1, 'palette': ['#FF8C00']}  # Dark Orange
        
        # Custom style overrides
        if style == "blue":
            return {'min': 1, 'max': 1, 'palette': ['#0000FF']}
        elif style == "purple":
            return {'min': 1, 'max': 1, 'palette': ['#800080']}
        
        # Fallback default
        return {'min': 1, 'max': 1, 'palette': ['#228B22']}

    def get_dataset_info(self, dataset: str, base_url: str = "http://localhost:8000") -> Dict[str, Any]:
        """Get dataset information and tile URL template"""
        datasets = self.get_available_datasets()
        
        if dataset not in datasets["datasets"]:
            raise HTTPException(status_code=404, detail=f"Dataset '{dataset}' not found")
        
        dataset_info = datasets["datasets"][dataset]
        
        return {
            "dataset": dataset,
            "info": dataset_info,
            "tile_url_template": f"{base_url}/api/v1/gee/tiles/{dataset}/{{z}}/{{x}}/{{y}}",
            "styles": ["default", "light_green", "dark_green", "red", "orange", "blue", "purple"],
            "example_urls": {
                "leaflet": f"{base_url}/api/v1/gee/tiles/{dataset}/{{z}}/{{x}}/{{y}}",
                "openlayers": f"{base_url}/api/v1/gee/tiles/{dataset}/{{z}}/{{x}}/{{y}}",
                "mapbox": f"{base_url}/api/v1/gee/tiles/{dataset}/{{z}}/{{x}}/{{y}}"
            },
            "usage_example": {
                "leaflet": f"L.tileLayer('{base_url}/api/v1/gee/tiles/{dataset}/{{z}}/{{x}}/{{y}}').addTo(map);",
                "openlayers": f"new ol.layer.Tile({{ source: new ol.source.XYZ({{ url: '{base_url}/api/v1/gee/tiles/{dataset}/{{z}}/{{x}}/{{y}}' }}) }});",
                "mapbox": f"map.addSource('{dataset}', {{ 'type': 'raster', 'tiles': ['{base_url}/api/v1/gee/tiles/{dataset}/{{z}}/{{x}}/{{y}}'] }});"
            }
        }
    
    def refresh_datasets(self) -> Dict[str, str]:
        """Refresh Earth Engine datasets"""
        try:
            if not self.is_initialized:
                self.authenticate_ee()
            else:
                self.ee_image = self._get_ee_datasets()
            return {
                "message": "Datasets refreshed successfully",
                "timestamp": ee.Date.now().format().getInfo(),
                "datasets_loaded": 6
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error refreshing datasets: {str(e)}")

# Create singleton instance
gee_dataset_service = GEEDatasetService()
