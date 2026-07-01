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

from services.ee_workload_tags import workload_tag, TILE_DATASET
from services.ee_auth import initialize_ee

# Load environment variables
load_dotenv()

class GEEDatasetService:
    def __init__(self):
        self.ee_image = None
        self.is_initialized = False
        self.map_id_cache = {}
        self.indonesia_map_id_cache = {}
        
    def _get_indonesia_mask(self):
        """Ambil geometry Indonesia dari GAUL level2 (ADM0_CODE=116) dan buat mask ee.Geometry"""
        try:
            # GAUL level2 asset
            gaul_fc = ee.FeatureCollection('FAO/GAUL/2015/level2')
            indonesia_fc = gaul_fc.filter(ee.Filter.eq('ADM0_CODE', 116))
            indonesia_geom = indonesia_fc.geometry()
            return indonesia_geom
        except Exception as e:
            logger.error(f"Error getting Indonesia mask: {e}")
            return None
    
    def _generate_map_id_cache_key(self, dataset: str, style: str) -> str:
        """Generate cache key for Map ID"""
        return f"{dataset}_{style}"
    
    def _get_or_create_map_id(self, dataset: str, style: str, image_band: ee.Image, vis_params: Dict[str, Any]) -> str:
        """Get cached Map ID or create new one"""
        cache_key = self._generate_map_id_cache_key(dataset, style)
        
        if cache_key in self.map_id_cache:
            logger.info(f"Using cached Map ID for {cache_key}")
            return self.map_id_cache[cache_key]
        
        logger.info(f"Generating new Map ID for {cache_key}")
        with workload_tag(TILE_DATASET):
            map_id = image_band.getMapId(vis_params)
        url_format = map_id['tile_fetcher'].url_format

        self.map_id_cache[cache_key] = url_format
        return url_format
    
    def _get_or_create_indonesia_map_id(self, dataset: str, style: str, image_band: ee.Image, vis_params: Dict[str, Any]) -> str:
        """Get cached Indonesia Map ID or create new one"""
        cache_key = self._generate_map_id_cache_key(dataset, style)
        
        if cache_key in self.indonesia_map_id_cache:
            logger.info(f"Using cached Indonesia Map ID for {cache_key}")
            return self.indonesia_map_id_cache[cache_key]
        
        logger.info(f"Generating new Indonesia Map ID for {cache_key}")
        with workload_tag(TILE_DATASET):
            map_id = image_band.getMapId(vis_params)
        url_format = map_id['tile_fetcher'].url_format

        self.indonesia_map_id_cache[cache_key] = url_format
        return url_format
    
    def pregenerate_map_ids(self):
        """Pre-generate Map IDs for all common datasets and styles for faster tile serving"""
        if not self.is_initialized or self.ee_image is None:
            logger.warning("Cannot pre-generate Map IDs: Earth Engine not initialized")
            return
        
        logger.info("Pre-generating Map IDs for common datasets...")
        
        datasets = ["gfw", "gfw_loss", "jrc", "jrc_loss", "sbtn", "sbtn_loss", "radd"]
        styles = ["default"]

        for dataset in datasets:
            for style in styles:
                try:
                    cache_key = self._generate_map_id_cache_key(dataset, style)

                    if cache_key not in self.map_id_cache:
                        band_name = self.get_available_datasets()["datasets"][dataset]["band"]
                        vis_params = self._get_visualization_params(dataset, style)

                        image_band = self.ee_image.select(band_name)

                        if dataset in ["gfw_loss", "jrc_loss", "sbtn_loss", "radd"]:
                            image_band = image_band.updateMask(image_band.gt(0))
                        
                        with workload_tag(TILE_DATASET):
                            map_id = image_band.getMapId(vis_params)
                        self.map_id_cache[cache_key] = map_id['tile_fetcher'].url_format

                        logger.info(f"Pre-generated Map ID for {cache_key}")
                        
                except Exception as e:
                    logger.warning(f"Failed to pre-generate Map ID for {dataset}/{style}: {e}")
        
        logger.info(f"Map ID cache ready with {len(self.map_id_cache)} entries")
    
    def get_tile_indonesia(self, dataset: str, z: int, x: int, y: int, style: str = "default") -> RedirectResponse:
        """Get map tile for specific dataset, masked to Indonesia only (ADM0_CODE=116)"""
        if not self.is_initialized or self.ee_image is None:
            logger.info("Initializing Earth Engine for tile service...")
            self.authenticate_ee(single_account=True)

        available_datasets = self.get_available_datasets()["datasets"]
        if dataset not in available_datasets:
            raise HTTPException(status_code=404, detail=f"Dataset '{dataset}' not found")
        band_name = available_datasets[dataset]["band"]
        vis_params = self._get_visualization_params(dataset, style)

        try:
            image_band = self.ee_image.select(band_name)
            
            indonesia_geom = self._get_indonesia_mask()
            if indonesia_geom:
                image_band = image_band.updateMask(image_band.gt(0)).clip(indonesia_geom)
            else:
                logger.warning("Indonesia geometry not found, returning global tile")
            
            url_format = self._get_or_create_indonesia_map_id(dataset, style, image_band, vis_params)
            tile_url = url_format.format(z=z, x=x, y=y)
            
            return RedirectResponse(url=tile_url)
        except Exception as e:
            logger.error(f"Error generating Indonesia tile: {e}")
            raise HTTPException(status_code=500, detail=f"Error generating Indonesia tile: {str(e)}")
        
    def authenticate_ee(self, single_account: bool = False) -> None:
        """
        Initialize Earth Engine with service account.
        If single_account=True, use EE_SINGLE_SERVICE_ACCOUNT_PATH.
        """
        try:
            if single_account:
                service_account_path = os.getenv("EE_SINGLE_SERVICE_ACCOUNT_PATH")
                if not service_account_path:
                    raise ValueError("EE_SINGLE_SERVICE_ACCOUNT_PATH not set in .env file")
            else:
                service_account_path = os.getenv("EE_SERVICE_ACCOUNT_PATH")
                if not service_account_path:
                    raise ValueError("EE_SERVICE_ACCOUNT_PATH not set in .env file")

            # Convert to absolute path if needed
            if not os.path.isabs(service_account_path):
                project_root = Path(__file__).parent.parent
                service_account_path = project_root / service_account_path
            else:
                service_account_path = Path(service_account_path)

            # Ensure path is a file
            if not service_account_path.is_file():
                raise FileNotFoundError(f"Service account file not found or is not a file: {service_account_path}")

            logger.info(f"Using service account: {service_account_path}")

            # Initialize EE with service account
            credentials = ee.ServiceAccountCredentials(
                email=None,  # Will be read from the JSON file
                key_file=str(service_account_path)
            )
            # Attribute compute (incl. tile EECU + workload tags) to the Cloud
            # project so it shows up in that project's Metrics Explorer.
            initialize_ee(credentials)

            # Load datasets
            self.ee_image = self._get_ee_datasets()
            self.is_initialized = True

            logger.info("Earth Engine initialized successfully for tile serving")
            
            # Pre-generate Map IDs for faster tile serving
            self.pregenerate_map_ids()

        except Exception as e:
            logger.error(f"Failed to initialize Earth Engine: {e}")
            raise HTTPException(status_code=500, detail=f"EE initialization failed: {str(e)}")
    
    def _get_ee_datasets(self) -> ee.Image:
        """Load EUDR compliance datasets with GFW/SBTN Loss 2021-2025 (GFC+GLAD)"""
        try:
            logger.info("Loading Earth Engine datasets (2021-2025 GFW/SBTN Loss)...")

            # 1. Primary forest data (GLAD Primary Humid Tropical Forests)
            primary_2001_raw = ee.ImageCollection("UMD/GLAD/PRIMARY_HUMID_TROPICAL_FORESTS/v1") \
                .select("Primary_HT_forests").mosaic()

            # 2. Global Forest Change data
            gfc = ee.Image("UMD/hansen/global_forest_change_2024_v1_12")
            loss_2001_2020 = gfc.select("lossyear").gte(1).And(gfc.select("lossyear").lte(20))

            # Primary forest 2020 (after loss 2001-2020)
            primary_2020 = primary_2001_raw.where(loss_2001_2020, 0).unmask(0)
            gfw_forest = primary_2020.rename("gfw")

            # 3. GFW Loss (2021-2024) - Forest Loss
            loss_2021_2024 = gfc.select("lossyear").gte(21).And(gfc.select("lossyear").lte(24))

            # 4. SBTN (Science Based Targets Network) - Natural Lands
            sbtn = ee.Image('WRI/SBTN/naturalLands/v1_1/2020').select('natural').rename('sbtn').selfMask()
            sbtn_mask = sbtn.eq(1)

            # 5. GFW Primary Forest 2020 (mask)
            primary_mask_2020 = primary_2020.unmask(0)

            # 6. GLAD Alerts 2025
            glad_col = ee.ImageCollection('projects/glad/alert/UpdResult').map(
                lambda img: img.select(['conf25', 'alertDate25', 'obsCount', 'obsDate'])
            )
            glad_latest = glad_col.mosaic()
            conf25 = glad_latest.select('conf25')
            alertDate25 = glad_latest.select('alertDate25')
            glad_2025_alerts = conf25.gt(0).And(alertDate25.gt(0))

            # 7. SBTN Loss 2021-2024 (GFC loss in SBTN areas)
            sbtn_loss_2021_2024 = loss_2021_2024.multiply(sbtn_mask).unmask(0)
            # 8. GFW Loss 2021-2024 (GFC loss in primary forest areas)
            gfw_loss_2021_2024 = loss_2021_2024.multiply(primary_mask_2020).unmask(0)

            # 9. SBTN GLAD 2025 (mask SBTN & alert 2025)
            sbtn_glad_2025 = glad_2025_alerts.multiply(sbtn_mask).unmask(0)
            # 10. GFW GLAD 2025 (mask primary & alert 2025)
            gfw_glad_2025 = glad_2025_alerts.multiply(primary_mask_2020).unmask(0)

            # 11. SBTN Loss 2021-2025: Gabungan SBTN loss (2021-2024) + SBTN GLAD 2025
            sbtn_loss = sbtn_loss_2021_2024.Or(sbtn_glad_2025).rename('sbtn_loss')
            # 12. GFW Loss 2021-2025: Gabungan GFW loss (2021-2024) + GFW GLAD 2025
            gfw_loss = gfw_loss_2021_2024.Or(gfw_glad_2025).rename('gfw_loss')

            # 12. JRC (Joint Research Centre) - Forest Cover 2020
            eufo = ee.ImageCollection("JRC/GFC2020/V2").mosaic().rename("jrc").selfMask()

            # 13. JRC Loss (2021-2024) - JRC TMF Deforestation
            jrc_loss = self._get_jrc_tmf_deforestation().rename("jrc_loss")

            # 14. RADD - Radar near real-time forest disturbance alerts
            radd = self._get_radd_alerts().rename("radd")

            # Combine all 7 datasets
            combined_image = gfw_forest.addBands(gfw_loss) \
                                      .addBands(eufo) \
                                      .addBands(jrc_loss) \
                                      .addBands(sbtn) \
                                      .addBands(sbtn_loss) \
                                      .addBands(radd)

            logger.info("Earth Engine datasets (2021-2025 GFW/SBTN Loss + RADD) loaded successfully")
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

    def _get_radd_alerts(self):
        """Get RADD (Radar for Detecting Deforestation) forest disturbance alerts.

        Source: projects/radar-wur/raddalert/v1 (Wageningen University), see
        https://gee-community-catalog.org/projects/radd/

        The 'Alert' band stores disturbance confidence: 2 = unconfirmed, 3 = confirmed.
        RADD alert images are cumulative per geography; sorting ascending by
        system:time_end before mosaic() keeps the latest cumulative alerts on top
        across all (spatially disjoint) geographies.
        """
        try:
            logger.info("Loading RADD alert data...")

            radd = ee.ImageCollection("projects/radar-wur/raddalert/v1")
            radd_alert = (radd.filterMetadata("layer", "contains", "alert")
                              .sort("system:time_end")
                              .mosaic()
                              .select("Alert"))

            logger.info("RADD alert data loaded successfully")
            return radd_alert

        except Exception as e:
            logger.warning(f"Failed to load RADD alerts. Using fallback: {e}")
            # Fallback: return empty image
            return ee.Image(0).rename("radd")

    def get_available_datasets(self) -> Dict[str, Any]:
        """Get list of 7 available datasets for EUDR compliance"""
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
            },
            "radd": {
                "name": "RADD Forest Disturbance Alerts",
                "description": "Radar for Detecting Deforestation (RADD) near real-time forest disturbance alerts from Wageningen University. Alert values: 2=unconfirmed, 3=confirmed.",
                "band": "radd",
                "type": "deforestation",
                "color": "#FF7F50"
            }
        }

        return {
            "datasets": datasets,
            "total_count": len(datasets),
            "description": "7 core datasets for EUDR compliance monitoring"
        }
    
    def get_tile(self, dataset: str, z: int, x: int, y: int, style: str = "default") -> RedirectResponse:
        """Get map tile for specific dataset with caching for improved performance"""
        if not self.is_initialized or self.ee_image is None:
            logger.info("Initializing Earth Engine for tile service...")
            self.authenticate_ee(single_account=True)
        
        available_datasets = self.get_available_datasets()["datasets"]
        
        if dataset not in available_datasets:
            raise HTTPException(status_code=404, detail=f"Dataset '{dataset}' not found")
        
        band_name = available_datasets[dataset]["band"]
        vis_params = self._get_visualization_params(dataset, style)
        
        try:
            image_band = self.ee_image.select(band_name)

            if dataset in ["gfw_loss", "jrc_loss", "sbtn_loss", "radd"]:
                image_band = image_band.updateMask(image_band.gt(0))

            url_format = self._get_or_create_map_id(dataset, style, image_band, vis_params)
            tile_url = url_format.format(z=z, x=x, y=y)
            
            return RedirectResponse(url=tile_url)
            
        except Exception as e:
            logger.error(f"Error generating tile: {e}")
            raise HTTPException(status_code=500, detail=f"Error generating tile: {str(e)}")
    
    def _get_visualization_params(self, dataset: str, style: str) -> Dict[str, Any]:
        """Get visualization parameters for each dataset"""

        # RADD alerts use a confidence scale (2=unconfirmed, 3=confirmed),
        # not a single binary value, so it needs its own visualization branch.
        if dataset == "radd":
            if style == "confirmed":
                # Only confirmed alerts, solid red
                return {'min': 3, 'max': 3, 'palette': ['#FF0000']}
            elif style == "red":
                return {'min': 2, 'max': 3, 'palette': ['#FF8C00', '#FF0000']}
            # Catalog default: blue (unconfirmed) -> coral (confirmed)
            return {'min': 2, 'max': 3, 'palette': ['blue', 'coral']}

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
            "styles": ["default", "light_green", "dark_green", "red", "orange", "blue", "purple", "confidence", "confirmed"],
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
                "datasets_loaded": 7
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error refreshing datasets: {str(e)}")

# Create singleton instance
gee_dataset_service = GEEDatasetService()
