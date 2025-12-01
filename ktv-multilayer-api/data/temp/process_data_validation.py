import time
import uuid

import pandas as pd
from loguru import logger

from utils.geoprocessing.geometry_checker import (
    has_duplicate_polygons,
    has_duplicate_vertices,
    has_long_segments,
    has_not_ring,
    has_self_intersection,
    has_zero_area,
)


def process_row(row):
    try:
        duplicate_vertices, vertice_points = has_duplicate_vertices(row.geometry)
        duplicate_polygon = has_duplicate_polygons(row.geometry)
        self_intersection = has_self_intersection(row.geometry)
        not_ring = has_not_ring(row.geometry)
        long_segments = has_long_segments(row.geometry)
        empty_area = has_zero_area(row.geometry)
        # located_on_waterbodies = has_located_on_water(row.polygon)

        check = {
            "duplicated_vertices": duplicate_vertices,
            "duplicated_polygon": duplicate_polygon,
            "self_intersection": self_intersection,
            "major_overlapping": False,
            "minor_overlapping": False,
            "not_ring": not_ring,
            "zero_area": empty_area,
            "malformed": False,
            "long_segments": long_segments,
            "located_on_waterbodies": False,
        }

        issues_description = ", ".join([key for key, value in check.items() if value])

        return {
            "uid": uuid.uuid4(),
            "ProductionPlace": row.ProductionPlace,
            "polygon": row.geometry,
            "duplicated_vertices": duplicate_vertices,
            "duplicated_polygon": duplicate_polygon,
            "self_intersection": self_intersection,
            "major_overlapping": False,
            "minor_overlapping": False,
            "not_ring": not_ring,
            "long_segments": long_segments,
            "zero_area": empty_area,
            "malformed": False,
            "located_on_waterbodies": False,
            "issues_description": issues_description,
            "duplicate_vertex_coordinates": vertice_points,
        }

    except Exception as e:
        logger.error(f"Error processing row {row.name}: {str(e)}")
        return None


def process_data(gdf):
    try:
        logger.info("Processing data...")
        start_time = time.time()
        results = [process_row(row) for _, row in gdf.iterrows()]

        processed_results = [res for res in results if res is not None]

        end_time = time.time()
        logger.info(f"Data processing completed in {end_time - start_time:.2f} seconds")
        return pd.DataFrame(processed_results)

    except Exception as e:
        logger.error(f"An error occurred while processing the data: {str(e)}")
        return pd.DataFrame({"error": [str(e)]})
