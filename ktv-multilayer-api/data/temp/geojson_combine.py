import json
import os

import geopandas as gpd
from loguru import logger


class GeojsonCombine:
    def __init__(self, geojson_data=None):
        self.geojson_data = (
            geojson_data
            if geojson_data
            else {"type": "FeatureCollection", "features": []}
        )

    @staticmethod
    def combine(display_id=None, folder_path=None):
        combined = {"type": "FeatureCollection", "features": []}

        if folder_path:
            geojson_files = [
                f for f in os.listdir(folder_path) if f.endswith(".geojson")
            ]

            if len(geojson_files) > 0:
                for filename in geojson_files:
                    file_path = os.path.join(folder_path, filename)
                    try:
                        gdf = gpd.read_file(file_path)
                        geojson = json.loads(gdf.to_json())
                        if isinstance(geojson, dict):
                            if geojson.get("type") == "FeatureCollection":
                                combined["features"].extend(geojson.get("features", []))
                            elif geojson.get("type") == "Feature":
                                combined["features"].append(geojson)
                    except Exception as e:
                        logger.error(f"Error processing file {filename}: {str(e)}")
                        continue

        return combined
