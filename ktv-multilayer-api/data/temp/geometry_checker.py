import hashlib
import os
import time
from functools import lru_cache

import ee
import geopandas as gpd
import numpy as np
from loguru import logger
from shapely import (
    LineString,
    MultiLineString,
    MultiPolygon,
    Polygon,
    STRtree,
    make_valid,
)
from shapely.validation import explain_validity

from utils.geoprocessing.overlap_checker import TopologyChecker
from config.database.pgsql import PgsqlConnection

def polygon_hash(polygon):
    return hashlib.md5(polygon.wkb).hexdigest()


def km_to_degrees(km):
    return km / 111.32


def has_zero_area(geometry):
    if geometry.area == 0:
        return True


def has_narrow_spike(geometry, angle_threshold=10):
    try:

        def calculate_angle(p1, p2, p3):
            try:
                v1 = np.array([p1[0] - p2[0], p1[1] - p2[1]])
                v2 = np.array([p3[0] - p2[0], p3[1] - p2[1]])

                norm_v1 = np.linalg.norm(v1)
                norm_v2 = np.linalg.norm(v2)

                if norm_v1 == 0 or norm_v2 == 0:
                    return None
                cos_angle = np.dot(v1, v2) / (norm_v1 * norm_v2)
                cos_angle = np.clip(cos_angle, -1.0, 1.0)
                angle = np.arccos(cos_angle)
                return np.degrees(angle)

            except Exception as e:
                logger.error(f"An error occurred while calculating the angle: {str(e)}")
                return None

        def check_spike(p1, p2, p3):
            angle = calculate_angle(p1, p2, p3)
            return angle is not None and angle < angle_threshold

        spike_points = []

        if isinstance(geometry, Polygon):
            coords = list(geometry.exterior.coords)
            for i in range(len(coords) - 2):
                if check_spike(coords[i], coords[i + 1], coords[i + 2]):
                    spike_points.append(coords[i + 1])

            if check_spike(coords[-2], coords[0], coords[1]):
                spike_points.append(coords[0])

        elif isinstance(geometry, LineString):
            coords = list(geometry.coords)
            for i in range(len(coords) - 2):
                if check_spike(coords[i], coords[i + 1], coords[i + 2]):
                    spike_points.append(coords[i + 1])

        has_spike = len(spike_points) > 0
        return has_spike, spike_points

    except Exception as e:
        logger.error(f"An error occurred while detecting narrow spikes: {str(e)}")
        return False, None


def has_duplicate_vertices(polygon, precision=None, tolerance=1e-8):
    if not isinstance(polygon, Polygon):
        return False, None

    try:
        coords = np.array(polygon.exterior.coords)
        if np.allclose(coords[0], coords[-1]):
            coords = coords[:-1]

        if precision is not None:
            coords = np.round(coords, precision)

        unique_coords, indices, counts = np.unique(
            coords,
            axis=0,
            return_index=True,
            return_counts=True,
            equal_nan=True,
        )
        duplicates = [(int(i), tuple(coords[i])) for i in indices[counts > 1]]

        return len(duplicates) > 0, duplicates

    except Exception as e:
        logger.error(f"An error occurred while checking for duplicate points: {str(e)}")
        return False, None


def has_duplicate_polygons(polygons):
    try:
        if not isinstance(polygons, list):
            return False

        unique_hashes = set()
        duplicate_polygons = []

        for polygon in polygons:
            poly_hash = polygon_hash(polygon)
            if poly_hash in unique_hashes:
                duplicate_polygons.append(polygon)
            else:
                unique_hashes.add(poly_hash)

        return len(duplicate_polygons) > 0

    except Exception as e:
        logger.error(
            f"An error occurred while checking for duplicate polygons: {str(e)}"
        )
        return False


def has_self_intersection(geometry):
    try:
        if not isinstance(geometry, (Polygon, MultiPolygon)):
            return False

        explanation = explain_validity(geometry)
        return (
            "Self-intersection" in explanation
            or "Ring Self-intersection" in explanation
        )

    except Exception as e:
        logger.error(
            f"An error occurred while checking for self-intersection: {str(e)}"
        )
        return False


def has_not_ring(polygon):
    try:
        if not isinstance(polygon, Polygon):
            return False

        if not polygon.exterior.is_ring:
            return True

        return False

    except Exception as e:
        logger.error(f"An error occurred while checking for not-ring: {str(e)}")
        return False


def has_long_segments(polygon, threshold_length=2):
    threshold_length = km_to_degrees(threshold_length)

    try:
        if not isinstance(polygon, Polygon):
            logger.warning("Input is not a Polygon.")
            return False

        def check_ring(ring):
            ring_length = km_to_degrees(ring.length)
            if ring_length > threshold_length:
                return True
            for i in range(len(ring.coords) - 1):
                segment_length = LineString([ring.coords[i], ring.coords[i + 1]]).length
                if segment_length > threshold_length:
                    return True
            return False

        if check_ring(polygon.exterior):
            return True

        for interior in polygon.interiors:
            if check_ring(interior):
                return True

        return False

    except Exception as e:
        logger.error(f"An error occurred while checking for long segments: {str(e)}")
        return False


def is_located_on_water(polygon):
    try:
        if not isinstance(polygon, Polygon) and not isinstance(polygon, MultiPolygon):
            logger.warning("Input is not a valid Polygon or MultiPolygon")
            return False

        polygon = make_valid(polygon)

        try:
            db_conn = PgsqlConnection()
            wkt_polygon = polygon.wkt
            
            query = """
            SELECT COUNT(*) as intersection_count
            FROM gis_int_eudr_lc_lake
            WHERE ST_Intersects(geom, ST_GeomFromText(:polygon_wkt, 4326))
            """
            
            result = db_conn.execute_query(query, {"polygon_wkt": wkt_polygon})
            
            if result and len(result) > 0:
                intersection_count = result[0].get('intersection_count', 0)
                if intersection_count > 0:
                    return True
        except Exception as e:
            logger.warning(f"Database check failed, falling back to geojson: {str(e)}")

        worldadmin_path = os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ),
            "worldadmin.geojson",
        )

        worldadmin = gpd.read_file(worldadmin_path)

        if worldadmin.empty:
            logger.warning("No data found in worldadmin.geojson")
            return False

        geometries = worldadmin.geometry.tolist()
        spatial_index = STRtree(geometries)
        possible_intersections = spatial_index.query(polygon)

        total_intersection_area = 0
        for idx in possible_intersections:
            geometries[idx] = make_valid(geometries[idx])
            
            if polygon.intersects(geometries[idx]):
                intersection = polygon.intersection(geometries[idx])
                total_intersection_area += intersection.area

        THRESHOLD = 0.05
        water_ratio = 1 - (total_intersection_area / polygon.area)

        return water_ratio > (1 - THRESHOLD)

    except Exception as e:
        logger.error(f"An error occurred while checking for located on water: {str(e)}")
        return False


def has_overlapped_areas(df):
    try:
        start_time = time.time()
        logger.info(f"Starting to check for overlapped areas in {len(df)} polygons.")

        checker = TopologyChecker()
        gdf = gpd.GeoDataFrame(df)
        gdf = gdf.set_geometry("polygon", crs="EPSG:4326")
        gdf["geometry"] = gdf["polygon"]
        overlaps = checker.check_overlaps(gdf)

        end_time = time.time()
        logger.info(
            f"Finished checking for overlapped areas in {len(df)} polygons. Time taken: {end_time - start_time} seconds."
        )
        return overlaps
    except Exception as e:
        logger.error(f"Error processing overlapped areas: {e}")
        return []

def water_bodies_from_gee(geometry):
    try:
        coords = list(geometry.exterior.coords)
        ee_polygon = ee.Geometry.Polygon(coords)

        gsw = ee.Image("JRC/GSW1_4/GlobalSurfaceWater")
        water_occurrence = gsw.select("occurrence")

        water_mask = water_occurrence.gt(50)

        intersection = water_mask.clip(ee_polygon)
        stats = intersection.reduceRegion(
            reducer=ee.Reducer.sum(), geometry=ee_polygon, scale=30, maxPixels=1e9
        )

        water_pixels = ee.Number(stats.get("occurrence")).getInfo()
        is_on_water = water_pixels > 0

        return is_on_water
    except Exception as e:
        logger.error(f"Error processing water bodies from GEE: {e}")
        return False


@lru_cache(maxsize=None)
def clean_geometry(geom):
    if not geom.is_valid:
        return make_valid(geom)
    return geom
