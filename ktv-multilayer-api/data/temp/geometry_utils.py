from typing import Optional

import geopandas as gpd
import pandas as pd
from loguru import logger
from shapely import wkt


def create_empty_gfw_result_for_polygon(polygon_row: pd.Series) -> gpd.GeoDataFrame:
    """Create an empty GFW result for a single polygon."""
    result = {
        "shipment_id": polygon_row.get("shipment_id"),
        "supplier_id": polygon_row.get("supplier_id"),
        "producer_id": polygon_row.get("producer_id"),
        "producer_detail_id": polygon_row.get("producer_detail_id"),
        "geom_intersect": None,
        "def_area_gfw": 0,
        "def_year_gfw": None,
        "deforestationstatus": False,  # Default to no deforestation (compliant)
    }

    return gpd.GeoDataFrame([result], geometry="geom_intersect", crs="EPSG:4326")


def create_empty_wdpa_result_for_polygon(polygon_row: pd.Series) -> pd.DataFrame:
    """Create an empty WDPA result for a single polygon."""
    wdpa_columns = [
        "laf_cat_wdpa_1a",
        "laf_cat_wdpa_1b",
        "laf_cat_wdpa_2",
        "laf_cat_wdpa_3",
        "laf_cat_wdpa_4",
        "laf_cat_wdpa_5",
        "laf_cat_wdpa_6",
        "laf_cat_wdpa_not_applicable",
        "laf_cat_wdpa_not_assigned",
        "laf_cat_wdpa_not_reported",
    ]

    producer_detail_id = polygon_row.get("producer_detail_id")

    result = {
        "shipment_id": polygon_row.get("shipment_id"),
        "supplier_id": polygon_row.get("supplier_id"),
        "producer_id": polygon_row.get("producer_id"),
        "producer_detail_id": producer_detail_id,
        "wdpa_status": "compliant",  # Default to compliant when no data
        **{col: None for col in wdpa_columns},
    }

    logger.info(
        f"Created empty WDPA result for polygon {producer_detail_id} with default status 'compliant'"
    )
    return pd.DataFrame([result])


def create_empty_gfw_result(shipment_data: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Create an empty GFW result for all polygons in shipment data."""
    results = []
    for i in range(len(shipment_data)):
        row = shipment_data.iloc[i]
        results.append(
            {
                "shipment_id": row["shipment_id"],
                "supplier_id": row["supplier_id"],
                "producer_id": row["producer_id"],
                "producer_detail_id": row["producer_detail_id"],
                "geom_intersect": None,
                "def_area_gfw": 0,
                "def_year_gfw": None,
                "deforestationstatus": False,  # Default to no deforestation (compliant)
            }
        )
    return gpd.GeoDataFrame(results, geometry="geom_intersect", crs="EPSG:4326")


def create_empty_wdpa_result(shipment_data: gpd.GeoDataFrame) -> pd.DataFrame:
    """Create an empty WDPA result for all polygons in shipment data."""
    wdpa_columns = [
        "laf_cat_wdpa_1a",
        "laf_cat_wdpa_1b",
        "laf_cat_wdpa_2",
        "laf_cat_wdpa_3",
        "laf_cat_wdpa_4",
        "laf_cat_wdpa_5",
        "laf_cat_wdpa_6",
        "laf_cat_wdpa_not_applicable",
        "laf_cat_wdpa_not_assigned",
        "laf_cat_wdpa_not_reported",
    ]

    results = []
    for i in range(len(shipment_data)):
        row = shipment_data.iloc[i]
        results.append(
            {
                "shipment_id": row["shipment_id"],
                "supplier_id": row["supplier_id"],
                "producer_id": row["producer_id"],
                "producer_detail_id": row["producer_detail_id"],
                "wdpa_status": "compliant",  # Default to compliant when no WDPA data exists
                **{col: None for col in wdpa_columns},
            }
        )
    return pd.DataFrame(results)
