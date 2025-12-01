import asyncio
import io
import json
import os
import shutil
import time
import uuid
import zipfile
from copy import deepcopy
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List

import aiohttp
import boto3
import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from loguru import logger
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from opensearchpy import OpenSearch
from shapely import Point, Polygon, wkt
from shapely.geometry.polygon import orient

from config.config_loader import ConfigLoader
from config.database.connection_manager import db_manager
from utils.geoprocessing import process_data_validation
from utils.geoprocessing.geojson_combine import GeojsonCombine
from utils.geoprocessing.geometry_checker import is_located_on_water
from utils.geoprocessing.overlap_checker import TopologyChecker
from utils.spatial_reader.data_processor import DataProcessor
from utils.spatial_reader.geometry_fixer import (
    fix_geometries,
    read_geometries,
    simplify_geometry,
)
from utils.spatial_reader.geometry_fixer_import import (
    fix_geometries as fg_import,
)
from utils.spatial_reader.geometry_validator import (
    create_spatial_index,
    detect_self_intersection_segments,
)

cfg = ConfigLoader().get_app_config()
opensearchCfg = ConfigLoader().get_opensearch_config()

combined_results_lock = Lock()
combined_results = []

satelligence_risk_responses = []


class SpatialReaderService:
    def __init__(self):
        self.dbGisMis = db_manager.pgsql
        self.dbGis = db_manager.pgsql_old
        self.dbMysql = db_manager.mysql
        self.dbMysqlTarget = db_manager.mysql_target
        self.data_processor = DataProcessor()
        self._noncocoa_service = None

    @property
    def noncocoa_service(self):
        if self._noncocoa_service is None:
            from services.data.noncocoa_service import NonCocoaService

            self._noncocoa_service = NonCocoaService()
        return self._noncocoa_service

    def serialize_result_shipment(self, row, from_shipment=False):
        self_intersection_segments = detect_self_intersection_segments(
            row.geometry
        )
        is_on_land = is_located_on_water(row.geometry)

        validity = {
            "has_area": row.geometry.area != 0,
            "is_not_ring": not row.geometry.is_ring,
            "has_unique_vertices": not row.vertice_duplicate,
            "no_self_intersection": row.geometry.is_simple,
        }

        validity_status = "Valid" if all(validity.values()) else "Invalid"

        if from_shipment:
            return {
                "ProducerDetailId": row.properties["ProducerDetailId"],
                "shipment_id": row.properties["shipment_id"],
                "supplier_id": row.properties["supplier_id"],
                "plot_number": row.properties["plot_number"],
                "RegID": row.get("kolmis"),
                "type": row.geometry.geom_type,
                "geometry_checks": validity,
                "geometry_validity": validity_status,
                "is_on_land": is_on_land,
                "duplicate_vertex_coordinates": (
                    row.duplicate_vertices if row.vertice_duplicate else []
                ),
                "self_intersection_segments": [
                    {"segment1": segment1.wkt, "segment2": segment2.wkt}
                    for segment1, segment2 in self_intersection_segments
                ],
                "country": row.get("country"),
                "province": row.get("province"),
                "district": row.get("district"),
                "Country": row.properties["ProducerCountry"],
                "Plot_Size": row.properties.get("area"),
                "ProducerId": row.properties.get("ProducerId"),
                "ProducerName": row.properties.get("ProducerName"),
                "ProductionPlace": row.properties.get("ProductionPlace"),
                "Geometry": row.geometry.wkt,
                "geometry_type": row.properties["geometry_type"],
            }
        else:
            return {
                "ProducerDetailId": row.properties["producer_detail_id"],
                "type": row.geometry.geom_type,
                "geometry_checks": validity,
                "geometry_validity": validity_status,
                "is_on_land": row.located_on_land,
                "duplicate_vertex_coordinates": (
                    row.duplicate_vertices if row.vertice_duplicate else []
                ),
                "self_intersection_segments": [
                    {"segment1": segment1.wkt, "segment2": segment2.wkt}
                    for segment1, segment2 in self_intersection_segments
                ],
                "country": row.get("country"),
                "province": row.get("province"),
                "district": row.get("district"),
                "commo_id": row.properties["commo_id"],
                "Geometry": row.geometry.wkt,
            }

    def serialize_result(self, row):
        self_intersection_segments = detect_self_intersection_segments(
            row.geometry
        )

        validity = {
            "has_area": row.geometry.area != 0,
            "is_not_ring": not row.geometry.is_ring,
            "has_unique_vertices": not row.vertice_duplicate,
            "no_self_intersection": row.geometry.is_simple,
        }

        validity_status = "Valid" if all(validity.values()) else "Invalid"

        result = {
            "ID": row.properties["ID"],
            "RegID": row.get("kolmis"),
            "ProcessUid": row.properties.get("ProcessUid"),
            "type": row.geometry.geom_type,
            "geometry_checks": validity,
            "geometry_validity": validity_status,
            "is_on_land": row.located_on_land,
            "duplicate_vertex_coordinates": (
                row.duplicate_vertices if row.vertice_duplicate else []
            ),
            "self_intersection_segments": [
                {"segment1": segment1.wkt, "segment2": segment2.wkt}
                for segment1, segment2 in self_intersection_segments
            ],
            "country": row.get("country"),
            "province": row.get("province"),
            "district": row.get("district"),
            "Country": row.properties["Country"],
            "Supplier": row.properties.get("Supplier"),
            "Plot_ID": row.properties.get("Plot_ID"),
            "Farmer_ID": row.properties.get("Farmer_ID"),
            "Plot_Size": row.properties.get("Plot_Size"),
            "Farmer_Name": row.properties.get("Farmer_Name"),
            "ProducerName": row.properties.get("ProducerName"),
            "ProductionPlace": row.properties.get("ProductionPlace"),
            "Gender": row.properties.get("Gender"),
            "Geometry": row.geometry.wkt,
        }
        return result

    async def read_shipment_data(
        self, shipment_id: str, include_satelligence=False
    ):
        if include_satelligence:
            return await self.read_lindt_data(shipment_id)
        else:
            return await self.noncocoa_service.final_function(shipment_id)

    async def read_lindt_data(self, shipment_id: str):
        try:
            start_time = time.time()
            logger.info(f"Reading shipment data for shipment_id: {shipment_id}")

            query = f"""
                SELECT DISTINCT
                    posi.shipment_id,
                    posipd.id AS pd_id,
                    posipd.producer_id,
                    posipd.producer_name,
                    posipd.producer_country,
                    posipd.production_place,
                    posipd.production_place,
                    posipd.area,
                    st_aswkt(posipp.submitted_polygon) AS polygon,
                    st_geometrytype (posipp.submitted_polygon) AS geometry_type,
                    posip.producer_id AS supplier_id,
                    posip.plot_number
                FROM purchase_order_shipment_items posi
                    INNER JOIN purchase_order_shipment_item_producers posip ON posi.id = posip.shipment_item_id
                    INNER JOIN purchase_order_shipment_item_producer_details posipd ON posip.producer_detail_id = posipd.id
                    INNER JOIN purchase_order_shipment_item_producer_polygons posipp ON posip.producer_detail_id = posipp.producer_id
                    WHERE posi.shipment_id = '{shipment_id}'
            """
            data = self.dbMysql.execute_query(query)
            logger.info(f"Total rows: {len(data)}")

            if not data or len(data) == 0:
                return {"error": "No data found for the given shipment ID"}

            results = {"type": "FeatureCollection", "features": []}

            for row in data:
                properties = {
                    "ID": str(uuid.uuid4()),
                    "ProducerDetailId": row["pd_id"],
                    "shipment_id": row["shipment_id"],
                    "ProducerId": row["producer_id"],
                    "ProducerName": row["producer_name"],
                    "ProducerCountry": row["producer_country"],
                    "ProductionPlace": row["production_place"],
                    "supplier_id": row["supplier_id"],
                    "plot_number": row["plot_number"],
                    "area": float(row["area"]),
                    "geometry_type": row["geometry_type"],
                }

                if isinstance(row["polygon"], str):
                    polygon = wkt.loads(row["polygon"])
                    if isinstance(polygon, Point):
                        polygon = polygon.buffer(0.00009)
                        row["polygon"] = polygon.wkt

                geometry = wkt.loads(row["polygon"])

                feature = {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [y, x]
                                for x, y in zip(
                                    geometry.exterior.xy[0],
                                    geometry.exterior.xy[1],
                                )
                            ]
                        ],
                    },
                }

                results["features"].append(feature)

            process = await self.process_geojson_data(results, True)
            process_geometry = await self.process_geometries(
                json.dumps(process["results"]), True, is_shipment=True
            )

            results = await self.process_all_data(
                process_geometry, shipment_id, True
            )

            print(results)
            is_comply = all([result["is_comply"] for result in results])
            logger.info(f"Compliance status to send to callback: {is_comply}")

            await self.callback_to_partner_api(shipment_id, is_comply, results)

            end_time = time.time()
            logger.info(
                f"Shipment data reading completed for shipment_id: {shipment_id}. Time taken: {end_time - start_time} seconds"
            )
            return
        except Exception as e:
            logger.error(f"An error occurred while reading the file: {str(e)}")
            return

    async def process_data_item(self, data_item, shipment_id, save_to_db):
        logger.info("Processing tasks data item...")
        send_to_satelligence_result = await self.send_to_satelligence(data_item)

        if not send_to_satelligence_result:
            return {"error": "No data found for the given shipment ID"}

        read_satelligence_risks = await self.read_satelligence_risk(
            send_to_satelligence_result, save_to_db
        )

        return read_satelligence_risks[0]

    async def process_all_data(self, process_geometry, shipment_id, save_to_db):
        tasks = []
        for item in process_geometry["features"]:
            task = asyncio.create_task(
                self.process_data_item(
                    {"features": [item]}, shipment_id, save_to_db
                )
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        return results

    async def process_geojson_data(
        self, geojson_data: Dict[str, Any], from_shipment
    ) -> Dict[str, Any]:
        try:
            start_time = time.time()

            gdf = gpd.GeoDataFrame.from_features(geojson_data["features"])

            if "geometry" not in gdf.columns:
                raise ValueError("GeoJSON data must contain a 'geometry' field")

            gdf = gdf.set_crs(epsg=4326, allow_override=True)
            gdf["properties"] = gdf.apply(
                lambda row: row.drop("geometry").to_dict(), axis=1
            )

            gdf = gdf[["geometry", "properties"]]

            spatial_index = create_spatial_index(gdf)
            country_boundaries = gpd.read_parquet("country_boundary.parquet")
            country_boundaries_index = create_spatial_index(country_boundaries)

            processed_gdf, missing_gdf = await self.data_processor.process_data(
                gdf, spatial_index, country_boundaries, country_boundaries_index
            )

            results = processed_gdf.apply(
                lambda row: pd.Series(
                    self.serialize_result_shipment(row, from_shipment)
                ),
                axis=1,
            ).to_dict(orient="records")
            missing_results = missing_gdf.apply(
                lambda row: pd.Series(
                    self.serialize_result_shipment(row, from_shipment)
                ),
                axis=1,
            ).to_dict(orient="records")

            if processed_gdf.empty and missing_gdf.empty:
                summary = {
                    "valid_count": 0,
                    "invalid_count": 0,
                    "total_count": 0,
                    "missing_count": 0,
                }
            else:
                valid_count = 0
                invalid_count = 0

                if "validity" in processed_gdf.columns:
                    valid_count += int(
                        (processed_gdf["validity"] == "Valid").sum()
                    )
                    invalid_count += int(
                        (processed_gdf["validity"] != "Valid").sum()
                    )

                if "validity" in missing_gdf.columns:
                    valid_count += int(
                        (missing_gdf["validity"] == "Valid").sum()
                    )
                    invalid_count += int(
                        (missing_gdf["validity"] != "Valid").sum()
                    )

                summary = {
                    "valid_count": valid_count,
                    "invalid_count": invalid_count,
                    "total_count": len(processed_gdf),
                    "missing_count": len(missing_gdf),
                }

            end_time = time.time()
            logger.info(
                f"Total processing time: {end_time - start_time:.2f} seconds"
            )

            combined_results = results + missing_results

            return {
                "results": combined_results,
                "missing_results": missing_results,
                "summary": summary,
            }
        except Exception as e:
            logger.error(
                f"An error occurred while processing the GeoJSON data: {str(e)}"
            )
            return {"error": str(e)}

    async def read_spatial_data(
        self, file_path: str, file_type: str
    ) -> Dict[str, Any]:
        try:
            start_time = time.time()
            logger.info("Read spatial datas")

            if file_type == "geojson":
                gdf = gpd.read_file(file_path)

                mandatory_fields = [
                    "Supplier",
                    "Plot_ID",
                    "Farmer_ID",
                    "Plot_Size",
                    "Farmer_Name",
                ]
                optional_fields = [
                    "ProcessUid",
                    "Farmer_Group",
                    "Gender",
                    "Year_Join",
                    "Date_Map",
                    "ProducerName",
                    "ProductionPlace",
                ]

                def create_properties(row):
                    props = {
                        "ID": str(uuid.uuid4()),
                        "Country": row.get("Country")
                        or row.get("ProducerCountry"),
                        **{field: row.get(field) for field in mandatory_fields},
                        **{
                            field: row.get(field)
                            for field in optional_fields
                            if field in row
                        },
                        "Gender": (
                            row.get("Gender", "na").lower()
                            if "Gender" in row
                            else "na"
                        ),
                        "Geometry": row.geometry.wkt,
                    }
                    return props

                gdf["properties"] = gdf.apply(create_properties, axis=1)
                gdf = gdf[["geometry", "properties"]]

            elif file_type in ["csv", "excel"]:
                df = (
                    pd.read_csv(file_path)
                    if file_type == "csv"
                    else pd.read_excel(file_path)
                )
                gdf = gpd.GeoDataFrame(
                    df, geometry=gpd.GeoSeries.from_wkt(df["geometry"])
                )
                gdf.crs = "EPSG:4326"
            else:
                return {"error": f"Unsupported file type: {file_type}"}

            spatial_index = create_spatial_index(gdf)
            country_boundaries = gpd.read_parquet("country_boundary.parquet")
            country_boundaries_index = create_spatial_index(country_boundaries)

            processed_gdf, missing_gdf = await self.data_processor.process_data(
                gdf, spatial_index, country_boundaries, country_boundaries_index
            )

            results = processed_gdf.apply(
                lambda row: pd.Series(self.serialize_result(row)), axis=1
            ).to_dict(orient="records")
            missing_results = missing_gdf.apply(
                lambda row: pd.Series(self.serialize_result(row)), axis=1
            ).to_dict(orient="records")

            end_time = time.time()
            logger.info(
                f"Total processing time: {end_time - start_time:.2f} seconds"
            )

            return {
                "results": results + missing_results,
            }
        except Exception as e:
            logger.error(f"An error occurred while reading the file: {str(e)}")
            return {"error": str(e)}

    def ensure_counter_clockwise(self, polygon_wkt):
        polygon = wkt.loads(polygon_wkt)
        return orient(polygon, sign=1.0)

    async def geojson_formatter(self, data):
        simplified_data = []

        for item in data:
            simplified_geometry_wkt = simplify_geometry(item["fixed_geometry"])

            simplified_data.append(
                {
                    "id": item["id"],
                    "producer_id": item["producer_id"],
                    "producer_detail_id": item["producer_detail_id"],
                    "commo_id": item["commo_id"]
                    if "commo_id" in item
                    else None,
                    "supplier_id": (
                        item["supplier_id"] if "supplier_id" in item else None
                    ),
                    "attr": item["attr"],
                    "fixed_geometry": simplified_geometry_wkt,
                }
            )

        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "id": item["id"],
                        "producer_id": item["producer_id"],
                        "producer_detail_id": item["producer_detail_id"],
                        "commo_id": item["commo_id"]
                        if "commo_id" in item
                        else None,
                        "supplier_id": (
                            item["supplier_id"]
                            if "supplier_id" in item
                            else None
                        ),
                        "attr": item["attr"],
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [round(x, 6), round(y, 6)]
                                for x, y in zip(
                                    oriented_polygon.exterior.xy[0],
                                    oriented_polygon.exterior.xy[1],
                                )
                            ]
                        ],
                    },
                }
                for item in simplified_data
                for oriented_polygon in [
                    self.ensure_counter_clockwise(item["fixed_geometry"])
                ]
            ],
        }

    async def process_geometries(
        self, json_data, as_geojson, is_shipment=False
    ):
        try:
            start_time = time.time()
            geojson_output = None
            data = json.loads(json_data)
            geometries = read_geometries(data)
            if is_shipment:
                fixed_geometries = await fix_geometries(geometries)
            else:
                fixed_geometries = await fg_import(geometries)

            if as_geojson:
                geojson_output = await self.geojson_formatter(fixed_geometries)

            end_time = time.time()
            logger.info(
                f"Total processing time: {end_time - start_time:.4f} seconds"
            )
            return geojson_output if as_geojson else fixed_geometries
        except Exception as e:
            logger.error(
                f"An error occurred while processing the geometries: {str(e)}"
            )
            return {"error": str(e)}

    async def send_to_satelligence(self, data):
        try:
            logger.info("Sending data to Satelligence...")
            features = data.get("features", [])
            batch_size = 5
            all_results = []

            client = OpenSearch(
                hosts=[
                    {
                        "host": opensearchCfg["host"],
                        "port": opensearchCfg["port"],
                    }
                ],
                http_auth=(opensearchCfg["user"], opensearchCfg["password"]),
                use_ssl=True,
                verify_certs=False,
                ssl_assert_hostname=False,
                ssl_show_warn=False,
            )

            client.indices.refresh(index=opensearchCfg["index"])
            lastcount = client.cat.count(
                index=opensearchCfg["index"], format="json"
            )

            async def process_feature(feature, index):
                max_retries = 3
                retry_delay = 1  # initial delay in seconds

                for attempt in range(max_retries):
                    try:
                        geometry = feature.get("geometry")
                        if geometry:
                            body = {"geometry": geometry}
                            async with aiohttp.ClientSession() as session:
                                timeout = aiohttp.ClientTimeout(
                                    total=30
                                )  # 30 seconds timeout
                                async with session.post(
                                    cfg["satelligence_url"],
                                    headers={
                                        "Content-Type": "application/json"
                                    },
                                    json=body,
                                    timeout=timeout,
                                ) as response:
                                    if response.status == 504:
                                        if attempt < max_retries - 1:
                                            wait_time = retry_delay * (
                                                2**attempt
                                            )  # exponential backoff
                                            logger.warning(
                                                f"Gateway timeout, retrying in {wait_time} seconds..."
                                            )
                                            await asyncio.sleep(wait_time)
                                            continue

                                    response_data = await response.json()
                                    lastcount1 = (
                                        int(lastcount[0]["count"]) + index
                                    )

                                    logger.info(
                                        "Indexing response data to Elasticsearch..."
                                    )
                                    client.index(
                                        index=opensearchCfg["index"],
                                        id=lastcount1,
                                        body=response_data,
                                    )
                                    logger.info(
                                        "Response data indexed successfully"
                                    )

                                    shipmentId = (
                                        feature["properties"]["id"]
                                        if "id" in feature["properties"]
                                        else None
                                    )
                                    producerId = (
                                        feature["properties"]["producer_id"]
                                        if "producer_id"
                                        in feature["properties"]
                                        else None
                                    )

                                    if response.status == 200:
                                        logger.success(
                                            f"Successfully sent data for Producer Detail ID: {feature['properties']['producer_detail_id']}"
                                        )
                                        return {
                                            "shipment_id": shipmentId,
                                            "producer_id": producerId,
                                            "producer_detail_id": feature[
                                                "properties"
                                            ]["producer_detail_id"],
                                            "supplier_id": (
                                                feature["properties"][
                                                    "supplier_id"
                                                ]
                                                if "supplier_id"
                                                in feature["properties"]
                                                else None
                                            ),
                                            "attr": feature["properties"][
                                                "attr"
                                            ],
                                            "geometry": geometry,
                                            "response": response_data,
                                        }
                                    else:
                                        logger.warning(
                                            f"Failed to send data for Producer Detail ID: {feature['properties']['producer_detail_id']}"
                                        )
                                        logger.warning(
                                            f"Err Response: {response_data}"
                                        )
                                        return {
                                            "shipment_id": shipmentId,
                                            "producer_id": producerId,
                                            "producer_detail_id": feature[
                                                "properties"
                                            ]["producer_detail_id"],
                                            "supplier_id": (
                                                feature["properties"][
                                                    "supplier_id"
                                                ]
                                                if "supplier_id"
                                                in feature["properties"]
                                                else None
                                            ),
                                            "attr": feature["properties"][
                                                "attr"
                                            ],
                                            "geometry": geometry,
                                            "response": response_data,
                                        }
                    except asyncio.TimeoutError:
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (2**attempt)
                            logger.warning(
                                f"Request timed out, retrying in {wait_time} seconds..."
                            )
                            await asyncio.sleep(wait_time)
                        else:
                            logger.error("Max retries reached, giving up")
                            raise
                    except Exception as e:
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (2**attempt)
                            logger.warning(
                                f"Error occurred: {str(e)}, retrying in {wait_time} seconds..."
                            )
                            await asyncio.sleep(wait_time)
                        else:
                            logger.error("Max retries reached, giving up")
                            raise
                return None

            # Process features in batches
            for i in range(0, len(features), batch_size):
                batch = features[i : i + batch_size]
                tasks = [
                    process_feature(feature, idx + i + 1)
                    for idx, feature in enumerate(batch)
                ]

                # Process batch
                batch_results = await asyncio.gather(
                    *tasks, return_exceptions=True
                )

                # Filter out None results and handle exceptions
                valid_results = [
                    r
                    for r in batch_results
                    if r is not None and not isinstance(r, Exception)
                ]
                all_results.extend(valid_results)

                # Add a small delay between batches to prevent overwhelming the system
                if i + batch_size < len(features):
                    await asyncio.sleep(1)

            if not all_results:
                logger.warning("No data to send to Satelligence.")

            return all_results

        except Exception as e:
            logger.error(
                f"An error occurred while sending data to Satelligence: {str(e)}"
            )
            return {"error": str(e)}

    async def read_satelligence_risk(self, data, save_to_db):
        try:
            if not data:
                raise ValueError("Input data cannot be empty")

            results = []

            for item in data:
                risk_info = item.get("response", {}).get("risk_info", {})
                year_to_month_deforestation = risk_info.get(
                    "yearToMonthToDeforestationHa", {}
                )
                protected_area_ha = risk_info.get("protectedAreasHa", 0)

                current_year = datetime.now().year
                deforestation_since_2021 = False

                for year in range(2021, current_year + 1):
                    year_str = str(year)
                    if year_str in year_to_month_deforestation:
                        months_data = year_to_month_deforestation[year_str]
                        if any(
                            float(value) > 0 for value in months_data.values()
                        ):
                            deforestation_since_2021 = True
                            break

                deforestation_status = (
                    "compliance"
                    if not deforestation_since_2021
                    else "non-compliance"
                )
                land_approve_for_farm = (
                    "compliance" if protected_area_ha == 0 else "non-compliance"
                )
                plot_compliant = (
                    "compliance"
                    if (
                        deforestation_status == "compliance"
                        and land_approve_for_farm == "compliance"
                    )
                    else "non-compliance"
                )

                compliant_remarks = None
                is_comply = (
                    deforestation_status == "compliance"
                    and land_approve_for_farm == "compliance"
                )

                if (
                    item.get("response", {}).get("error_code")
                    == "outside_monitoring_region"
                ):
                    deforestation_status = "non-compliance"
                    land_approve_for_farm = "non-compliance"
                    plot_compliant = "non-compliance"
                    compliant_remarks = "Polygon out of monitoring region"
                    is_comply = False

                results.append(
                    {
                        "shipment_id": item.get("shipment_id"),
                        "producer_id": item.get("producer_id"),
                        "producer_detail_id": item.get("producer_detail_id"),
                        "supplier_id": item.get("supplier_id"),
                        "deforestation_status": deforestation_status,
                        "land_approve_for_farm": land_approve_for_farm,
                        "compliant_remarks": compliant_remarks,
                        "plot_compliant": plot_compliant,
                        "attr": item.get("attr"),
                        "is_comply": is_comply,
                        "geometry": item.get("geometry"),
                        "response": item.get("response"),
                    }
                )

            if save_to_db:
                try:
                    tasks = [
                        asyncio.create_task(self.save_to_mis(results)),
                        asyncio.create_task(
                            self.insert_compliance_data_reporting(
                                results, results[0]["shipment_id"]
                            )
                        ),
                    ]

                    # Wait for both tasks to complete or for first error
                    done, pending = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_EXCEPTION
                    )

                    # Cancel any pending tasks if there was an error
                    for task in pending:
                        task.cancel()

                    # Check for exceptions
                    for task in done:
                        try:
                            await task
                        except Exception as e:
                            logger.error(f"Task failed with error: {str(e)}")
                            raise  # Re-raise the exception after logging

                    return results

                except Exception as e:
                    logger.error(f"Error in parallel operations: {str(e)}")
                    raise
            else:
                return results

        except Exception as e:
            error_msg = f"Error processing satelligence risk data: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}

    async def save_to_mis(self, data, non_cocoa: bool = False):
        try:
            update_query = """
                UPDATE purchase_order_shipment_item_producer_details pd
                SET pd.is_compliant          = :is_compliant,
                    pd.deforestation_status  = :deforestation_status,
                    pd.land_approved_farming = :land_approved_farming,
                    pd.compliant_remarks     = :compliant_remarks
                WHERE pd.id = :detail_id;
           """

            update_corrected_polygon_query = """
                UPDATE purchase_order_shipment_item_producer_polygons pp
                SET pp.corrected_polygon     = ST_GeomFromText(:corrected_polygon, 4326, 'axis-order=long-lat'),
                    pp.satelligence_response = :satelligence_response
                WHERE pp.producer_id = :producer_id;
             """

            for entry in data:
                is_compliant = None
                if entry["plot_compliant"] == "compliance":
                    is_compliant = 1
                elif entry["plot_compliant"] == "non-compliance":
                    is_compliant = 0

                params = {
                    "detail_id": entry["producer_detail_id"],
                    "is_compliant": is_compliant,
                    "deforestation_status": entry["deforestation_status"],
                    "land_approved_farming": entry["land_approve_for_farm"],
                    "compliant_remarks": entry["compliant_remarks"],
                }

                try:
                    self.dbMysql.execute_query_save(update_query, params)
                    logger.success(
                        f"Updated compliance status for detail_id: {entry['producer_detail_id']}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to update compliance status for detail_id: {entry['producer_detail_id']}, {e}"
                    )
                    return {"error": str(e)}

                if not non_cocoa:
                    try:
                        geometry_coords = entry["geometry"]["coordinates"]
                        polygon_geom = Polygon(geometry_coords[0])
                        polygon_wkt = f"{polygon_geom.wkt}"

                        params_corrected_polygon = {
                            "producer_id": entry["producer_detail_id"],
                            "corrected_polygon": polygon_wkt,
                            "satelligence_response": json.dumps(
                                await self._filter_response_from_2020(
                                    entry["response"]
                                )
                            ),
                        }

                        self.dbMysql.execute_query_save(
                            update_corrected_polygon_query,
                            params_corrected_polygon,
                        )
                        logger.success(
                            f"Updated corrected_polygon for producer_id: {entry['producer_detail_id']}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to update corrected_polygon for producer_id: {entry['producer_detail_id']}, {e}"
                        )

            return {"success": "Compliance data updated successfully"}

        except Exception as e:
            logger.error(
                f"An error occurred while updating the compliance data: {str(e)}"
            )
            return {"error": str(e)}

    async def _filter_response_from_2020(self, response_data):
        if not response_data:
            return response_data

        if "error_code" in response_data:
            return response_data

        if "risk_info" not in response_data:
            return response_data

        risk_info = response_data["risk_info"]
        if not risk_info or "yearToMonthToDeforestationHa" not in risk_info:
            return response_data

        year_data = risk_info["yearToMonthToDeforestationHa"]
        filtered_years = {
            year: data for year, data in year_data.items() if int(year) >= 2020
        }

        filtered_response = deepcopy(response_data)
        filtered_response["risk_info"]["yearToMonthToDeforestationHa"] = (
            filtered_years
        )

        return filtered_response

    def format_properties(self, results):
        formatted_attr = []

        for result in results:
            formatted_item = {
                "located_on_water": result["attr"]["located_on_water"],
                "polygon": {
                    "country_code_origin": result["attr"][
                        "country_code_origin"
                    ],
                    "country_code_actual": result["attr"][
                        "country_code_actual"
                    ],
                    "is_match_country": result["attr"]["is_match_country"],
                    "area_origin": result["attr"]["area_origin"],
                    "area_actual": result["attr"]["area_actual"],
                    "diff_area_percentage": result["attr"][
                        "diff_area_percentage"
                    ],
                },
                "producer_detail_id": result["producer_detail_id"],
            }
            formatted_attr.append(formatted_item)

        return formatted_attr

    async def callback_to_partner_api(
        self, shipment_id, is_comply: bool, properties
    ):
        try:
            url = "https://partner-api-staging.koltitrace.com/v1/gis/shipment-processed-callback"
            headers = {"Content-Type": "application/json"}

            formatted_properties = self.format_properties(properties)
            print(formatted_properties)
            data = {
                "is_comply": bool(is_comply),
                "shipment_id": shipment_id,
                "attr": formatted_properties,
            }
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            logger.success(
                f"Callback sent successfully for shipment_id: {shipment_id}"
            )
        except requests.exceptions.RequestException as e:
            logger.error(
                f"An error occurred while sending the callback: {str(e)}"
            )
            return {"error": str(e)}

    async def insert_compliance_data_reporting(
        self, compliance_data, shipment_id
    ):
        try:
            if not compliance_data or not isinstance(compliance_data, list):
                raise ValueError("compliance_data must be a non-empty list")

            select_query = """
                WITH purchase_info
                AS
                (
                    SELECT DISTINCT
                        posip.producer_id,
                        posip.plot_number,
                        po.ref_number,
                        pos.id AS shipment_id,
                        pos.shipment_number,
                        pos.document_type,
                        posipp.corrected_polygon,
                        posipp.submitted_polygon,
                        posipd.producer_country,
                        posipd.production_place,
                        po.business_id,
                        po.supplier_id
                    FROM purchase_order_shipments pos
                        INNER JOIN purchase_orders po ON pos.purchase_order_id = po.id
                        INNER JOIN purchase_order_shipment_items posi ON pos.id = posi.shipment_id
                        INNER JOIN purchase_order_shipment_item_producers posip ON posi.id = posip.shipment_item_id
                        INNER JOIN purchase_order_shipment_item_producer_details posipd ON posip.producer_detail_id = posipd.id
                        INNER JOIN purchase_order_shipment_item_producer_polygons posipp ON posip.producer_detail_id = posipp.producer_id
                    WHERE 1=1
                        AND pos.id = :shipment_id
                )
                ,supplier_addr
                AS
                (
                    SELECT DISTINCT
                        ks.SupplierID,
                        ks.SupplierDisplayID,
                        ks.SupplierName,
                        REGEXP_REPLACE(kse.Address, '\r|\n', '') AS Address
                    FROM ktv_supplier ks
                        LEFT JOIN ktv_supplier_ext kse ON ks.SupplierID = kse.SupplierID
                    WHERE 1=1
                        AND ks.EntID = 2
                        AND ks.StatusCode = 'active'
                )
                ,farm_info
                AS
                (
                    SELECT DISTINCT
                        sub_gar.SupplierID,
                        sub_gar.FarmNr,
                        sub_gar.FarmNrUser,
                        sub_gar.CommoID,
                        sub_gar.GardenHaUnCertified AS FarmArea,
                        sub_gar.Production,
                        sub_gar.LatLong,
                        sub_gar.DateCollection,
                        sub_gar.ResultDateUpdated
                    FROM ktv_survey_farm sub_gar
                        INNER JOIN
                        (
                            SELECT
                                lat_sur_g.SupplierID
                                ,lat_sur_g.FarmNr
                                ,lat_sur_g.CommoID
                                ,MAX(lat_sur_g.SurveyNr) AS SurveyNr
                            FROM ktv_survey_farm lat_sur_g
                            WHERE 1=1
                                AND lat_sur_g.SupplierID <> 0
                                AND lat_sur_g.FarmNr <> 0
                                AND lat_sur_g.CommoID <> 0
                                AND lat_sur_g.SupplierID = :supplier_id
                            GROUP BY
                                lat_sur_g.SupplierID
                                ,lat_sur_g.FarmNr
                                ,lat_sur_g.CommoID
                        ) AS sub_gar_lat ON sub_gar.SupplierID = sub_gar_lat.SupplierID
                                            AND sub_gar.FarmNr = sub_gar_lat.FarmNr
                                                AND sub_gar.CommoID = sub_gar_lat.CommoID
                                                    AND sub_gar.SurveyNr = sub_gar_lat.SurveyNr
                    WHERE 1=1
                        AND sub_gar.SupplierID <> 0
                        AND sub_gar.FarmNr <> 0
                        AND sub_gar.CommoID <> 0
                        AND sub_gar.SupplierID = :supplier_id
                )
                ,polg_info
                AS
                (
                    SELECT
                        ksfpg.SupplierID
                        ,ksfpg.FarmNr
                        ,ksfpg.CommoID
                        ,ksfpg.Revision
                        ,ksfpg.AreaHa
                        ,ksfpg.StatusCheck
                    FROM ktv_survey_farm_polygon_geo ksfpg
                        INNER JOIN
                        (
                            SELECT
                                ksfpg.SupplierID
                                ,ksfpg.FarmNr
                                ,ksfpg.CommoID
                                ,MAX(ksfpg.Revision) AS Revision
                            FROM ktv_survey_farm_polygon_geo ksfpg
                            WHERE 1=1
                                AND ksfpg.StatusCheck IN ('new','verified')
                                AND ksfpg.SupplierID = :supplier_id
                            GROUP BY
                                ksfpg.SupplierID
                                ,ksfpg.FarmNr
                                ,ksfpg.CommoID
                        ) ksfpg2 ON ksfpg.SupplierID = ksfpg2.SupplierID
                                        AND ksfpg.FarmNr = ksfpg2.FarmNr
                                            AND ksfpg.CommoID = ksfpg2.CommoID
                                                AND ksfpg.Revision = ksfpg2.Revision
                    WHERE 1=1
                        AND ksfpg.StatusCheck IN ('new','verified')
                        AND ksfpg.SupplierID = :supplier_id
                )
                SELECT DISTINCT
                    CONVERT_TZ(NOW(),'system','Asia/Jakarta') AS generateddate,
                    ksoa.PartnerID AS partnerid,
                    UPPER(kp.PartnerName) AS partnername,
                    ks3.PartnerID AS partnerid_prod,
                    ks3.PartnerName AS partner_prod,
                    ks1.SupplierID AS businessid,
                    ks1.SupplierDisplayID AS businessdisplayid,
                    ks1.SupplierName AS businessname,
                    ks1.Address AS businessaddress,
                    ks2.SupplierID AS supplierid,
                    ks2.SupplierDisplayID AS supplierdisplayid,
                    ks2.SupplierName AS suppliername,
                    ks2.Address AS supplieraddress,
                    ks.SupplierID AS producerid,
                    ks.ExternalID AS producerid_ext,
                    ks.SupplierDisplayID AS producerdisplayid,
                    ks.SupplierName AS producername,
                    ksfs.FarmNrUser AS farmnr,
                    ksfs.FarmNr AS farmnr_int,
                    ksfs.DateCollection AS farm_collectdate,
                    ksfs.ResultDateUpdated AS farm_updateddate,
                    CONCAT(ks.SupplierID,ksfs.FarmNr) AS plot,
                    ksfs.FarmArea AS farmarea,
                    ksfs.Production AS production,
                    krc.CommoID AS commoid,
                    krc.CommoName AS commoname,
                    rc.CountryID AS countryid,
                    rc.CountryName AS countryname,
                    rc.CountryCode AS countrycode,
                    rp.ProvinceID AS provinceid,
                    rp.ProvinceName AS provincename,
                    rd.DistrictID AS districtid,
                    rd.DistrictName AS districtname,
                    rs.SubDistrictName AS subdistrictname,
                    rv.VillageName AS villagename,
                    ST_Y(ksfs.latlong) AS longitude,
                    ST_X(ksfs.latlong) AS latitude,
                    NULL AS defyear,
                    NULL AS area_def,
                    ksfpg.AreaHa AS area_tot,
                    NULL AS statusdeforestation,
                    NULL AS statusapprvfarming,
                    NULL AS land_use_type,
                    NULL AS environmental_survey,
                    NULL AS land_legality_laf,
                    NULL AS plot_comp_final_leg,
                    NULL AS final_third_party,
                    NULL AS final_fpic,
                    NULL AS final_hlr,
                    NULL AS final_tactr,
                    NULL AS producer_survey_status,
                    NULL AS final_survey_status,
                    NULL AS final_catg_based,
                    NULL AS statuscompliant,
                    NULL AS statuscompliant_gis,
                    NULL AS statuscompliant_strict,
                    NULL AS producerstat,
                    NULL AS producerstat_gis,
                    NULL AS producerstat_strict,
                    pi.ref_number AS po_ref_number,
                    pi.shipment_id,
                    pi.shipment_number,
                    pi.document_type,
                    ce.CertificationTypeName AS cert_type,
                    ce.SupScore AS cert_type_score,
                    CONCAT(CONCAT(ks.SupplierID,ksfs.FarmNr),CONCAT(ksfs.CommoID,ksfpg.Revision)) AS row_id,
                    YEAR(CONVERT_TZ(NOW(),'system','Asia/Jakarta')) AS rptyear,
                    NULL AS issues,
                    NULL AS issues_description,
                    NULL AS polygon_corrected_catg,
                    ksfpg.StatusCheck AS statuscheck,
                    ST_AsText(IFNULL(pi.corrected_polygon, pi.submitted_polygon)) AS polygongeo,
                    pi.producer_country,
                    pi.production_place
                FROM purchase_info pi
                    INNER JOIN ktv_supplier ks ON pi.producer_id = ks.SupplierID AND ks.EntID = 1 AND ks.StatusCode = 'active'
                    INNER JOIN ktv_supchain_org kso ON ks.SupplierID = kso.SupChainOrgID AND kso.SupChainOrgType = 'supplier'
                    INNER JOIN ktv_supchain_org_access ksoa ON kso.SupChainID = ksoa.SupChainID
                    INNER JOIN ktv_partner kp ON ksoa.PartnerID = kp.PartnerID
                    INNER JOIN reg_region rr ON ks.RegID = rr.RegID
                    INNER JOIN reg_country rc ON rr.CountryID = rc.CountryID
                    LEFT JOIN reg_province rp ON rr.ProvinceID = rp.ProvinceID
                    LEFT JOIN reg_district rd ON rr.DistrictID = rd.DistrictID
                    LEFT JOIN reg_subdistrict rs ON rr.SubDistrictID = rs.SubDistrictID
                    LEFT JOIN reg_village rv ON rr.VillageID = rv.VillageID
                    INNER JOIN supplier_addr ks1 ON pi.business_id COLLATE utf8mb4_general_ci = ks1.SupplierID
                    INNER JOIN supplier_addr ks2 ON pi.supplier_id COLLATE utf8mb4_general_ci = ks2.SupplierID
                    INNER JOIN
                    (
                        SELECT DISTINCT
                            ks3.SupplierID,
                            ks3.PartnerID,
                            kp.PartnerName
                        FROM ktv_supplier ks3
                            INNER JOIN ktv_partner kp ON ks3.PartnerID = kp.PartnerID
                        WHERE
                            ks3.EntID = 1
                            AND ks3.StatusCode = 'active'
                    ) ks3 ON ks.SupplierID = ks3.SupplierID
                    INNER JOIN farm_info ksfs ON ks.SupplierID = ksfs.SupplierID
                    INNER JOIN polg_info ksfpg ON ksfs.SupplierID = ksfpg.SupplierID
                                                                    AND ksfs.FarmNr = ksfpg.FarmNr
                                                                        AND ksfs.CommoID = ksfpg.CommoID
                    INNER JOIN ktv_ref_commodity krc ON ksfs.CommoID = krc.CommoID
                    LEFT JOIN
                    (
                        SELECT DISTINCT
                            kscg.SupplierID,
                            krcgt.CertificationTypeName,
                            kscg.SupScore
                        FROM ktv_supplier_certification_general kscg
                            LEFT JOIN ktv_ref_certification_general_type krcgt ON kscg.SupCertificationTypeID = krcgt.CertificationTypeID
                                                                                    AND krcgt.CertificationTypeID = 1
                    ) ce ON pi.supplier_id = ce.SupplierID
            """

            delete_query = """
                DELETE \
                FROM ktv_eudr_shipment_summ_dtl
                WHERE shipment_id = :shipment_id
                 AND row_id = :row_id \
            """

            # UPSERT (update insert)
            insert_query = """
                INSERT INTO ktv_eudr_shipment_summ_dtl (generateddate, partnerid, partnername, \
                                                       partnerid_prod, partner_prod, \
                                                       businessid, businessdisplayid, businessname, \
                                                       businessaddress, \
                                                       supplierid, supplierdisplayid, suppliername, \
                                                       supplieraddress, \
                                                       producerid, producerid_ext, producerdisplayid, \
                                                       producername, \
                                                       farmnr, farm_collectdate, farm_updateddate, plot, \
                                                       farmarea, production, commoid, commoname, \
                                                       countryid, countryname, countrycode, provinceid, \
                                                       provincename, \
                                                       districtid, districtname, subdistrictname, \
                                                       villagename, \
                                                       longitude, latitude, defyear, area_def, \
                                                       area_tot, statusdeforestation, statusapprvfarming, \
                                                       land_use_type, \
                                                       environmental_survey, land_legality_laf, \
                                                       plot_comp_final_leg, final_third_party, \
                                                       final_fpic, final_hlr, final_tactr, \
                                                       producer_survey_status, \
                                                       final_survey_status, final_catg_based, \
                                                       statuscompliant, \
                                                       statuscompliant_gis, statuscompliant_strict, \
                                                       producerstat, \
                                                       producerstat_gis, producerstat_strict, po_ref_number, \
                                                       shipment_id, \
                                                       shipment_number, document_type, cert_type, \
                                                       cert_type_score, row_id, \
                                                       rptyear, issues, issues_description, \
                                                       polygon_corrected_catg, \
                                                       statuscheck, polygongeo, producer_country, \
                                                       production_place) \
                VALUES (:generateddate, :partnerid, UPPER(:partnername), :partnerid_prod, :partner_prod, \
                       :businessid, :businessdisplayid, :businessname, :businessaddress, \
                       :supplierid, :supplierdisplayid, :suppliername, :supplieraddress, \
                       :producerid, :producerid_ext, :producerdisplayid, :producername, \
                       :farmnr, :farm_collectdate, :farm_updateddate, :plot, \
                       :farmarea, :production, :commoid, :commoname, \
                       :countryid, :countryname, :countrycode, :provinceid, :provincename, \
                       :districtid, :districtname, :subdistrictname, :villagename, \
                       :longitude, :latitude, :defyear, :area_def, \
                       :area_tot, :statusdeforestation, :statusapprvfarming, :land_use_type, \
                       :environmental_survey, :land_legality_laf, :plot_comp_final_leg, :final_third_party, \
                       :final_fpic, :final_hlr, :final_tactr, :producer_survey_status, \
                       :final_survey_status, :final_catg_based, :statuscompliant, \
                       :statuscompliant_gis, :statuscompliant_strict, :producerstat, \
                       :producerstat_gis, :producerstat_strict, :po_ref_number, :shipment_id, \
                       :shipment_number, :document_type, :cert_type, :cert_type_score, :row_id, \
                       :rptyear, :issues, :issues_description, :polygon_corrected_catg, \
                       :statuscheck, ST_GeomFromText(:polygongeo), :producer_country, :production_place) \
                """

            operations = []
            operations_risk = []

            for compliance_item in compliance_data:
                supplierID = (
                    compliance_item.get("supplier_id")
                    if "supplier_id" in compliance_item
                    else None
                )

                logger.info(
                    f"Processing compliance item: shipment_id={compliance_item['shipment_id']}, supplier_id={supplierID}"
                )

                source_data = self.dbMysql.execute_query(
                    select_query,
                    {
                        "shipment_id": shipment_id,
                        "supplier_id": supplierID,
                    },
                )

                logger.info(
                    f"Found {len(source_data)} source records to process"
                )

                if not source_data:
                    logger.warning(
                        f"No source data found for shipment_id={compliance_item['shipment_id']}, supplier_id={supplierID}"
                    )
                    continue

                for source_row in source_data:
                    if source_row["row_id"] is None:
                        source_row["row_id"] = (
                            f"{source_row['shipment_id']}_{source_row.get('producerid_ext', '')}"
                        )

                        logger.info(
                            f"Generated fallback row_id: {source_row['row_id']}"
                        )

                    operations.append(
                        {
                            "query": delete_query,
                            "params": {
                                "shipment_id": shipment_id,
                                "row_id": source_row["row_id"],
                            },
                        }
                    )

                    logger.info(
                        f"Deleted existing record for row_id: {source_row['row_id']}"
                    )

                    insert_data = {
                        **source_row,
                        "polygongeo": (
                            wkt.loads(source_row["polygongeo"]).buffer(0.01).wkt
                            if source_row["polygongeo"].startswith("POINT")
                            else source_row["polygongeo"]
                        ),
                        "statusdeforestation": compliance_item.get(
                            "deforestation_status", "unknown"
                        ),
                        "statusapprvfarming": compliance_item.get(
                            "land_approve_for_farm", "unknown"
                        ),
                        "statuscompliant_gis": compliance_item.get(
                            "plot_compliant", "unknown"
                        ),
                        "generateddate": source_row.get("generateddate")
                        or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "rptyear": source_row.get("rptyear")
                        or datetime.now().year,
                    }

                    operations.append(
                        {"query": insert_query, "params": insert_data}
                    )

                    # RISK INFO
                    # Get attributes from compliance_item
                    attr_data = compliance_item.get("attr", {})
                    should_process_risk = True

                    # Check conditions for processing risk info
                    if attr_data:
                        is_match_country = attr_data.get(
                            "is_match_country", False
                        )
                        located_on_water = attr_data.get(
                            "located_on_water", True
                        )
                        diff_area_percentage = attr_data.get(
                            "diff_area_percentage", 0
                        )

                        # Take absolute value of diff_area_percentage to remove negative sign
                        diff_area_percentage_abs = abs(diff_area_percentage)

                        # Only process risk info if all conditions are met
                        should_process_risk = (
                            is_match_country == True
                            and located_on_water == False
                            and diff_area_percentage_abs <= 5
                        )

                    if should_process_risk:
                        # Delete existing record first
                        delete_risk_query = """
                                            DELETE \
                                            FROM ktv_survey_farm_status_risk
                                            WHERE SupplierID = :supplier_id
                                              AND FarmNr = :farmnr
                                              AND CommoID = :commo_id \
                                            """

                        delete_risk_params = {
                            "supplier_id": source_row["producerid"],
                            "farmnr": source_row["farmnr_int"],
                            "commo_id": source_row["commoid"],
                        }

                        # Add delete operation
                        operations_risk.append(
                            {
                                "query": delete_risk_query,
                                "params": delete_risk_params,
                            }
                        )

                        # Insert new record
                        insert_risk_query = """
                                            INSERT INTO ktv_survey_farm_status_risk (SupplierID, FarmNr, CommoID, \
                                                                                     FarmRiskStatus, DeforestRefEUDR, \
                                                                                     LandLegalityEUDR, ProcessedFrom, \
                                                                                     DateUpdated, LastModifiedBy) \
                                            VALUES (:supplier_id, :farmnr, :commo_id, :statuscompliant_gis, \
                                                    :statusdeforestation, :land_approve_for_farm, 3, NOW(), 101159) \
                                            """

                        # Include the located_on_water value in the risk_data
                        risk_data = {
                            "supplier_id": source_row["producerid"],
                            "farmnr": source_row["farmnr_int"],
                            "commo_id": source_row["commoid"],
                            "statuscompliant_gis": (
                                0
                                if compliance_item.get("plot_compliant")
                                == "non-compliance"
                                else 1
                            ),
                            "statusdeforestation": (
                                0
                                if compliance_item.get("deforestation_status")
                                == "non-compliance"
                                else 1
                            ),
                            "land_approve_for_farm": (
                                0
                                if compliance_item.get("land_approve_for_farm")
                                == "non-compliance"
                                else 1
                            ),
                        }

                        operations_risk.append(
                            {"query": insert_risk_query, "params": risk_data}
                        )
            try:
                result = self.dbMysqlTarget.execute_transaction(operations)
                logger.info(f"Transaction completed. Result: {result}")
                logger.success("Data reporting replaced successfully")

                if operations_risk:
                    result_risk = self.dbMysql.execute_transaction(
                        operations_risk
                    )
                    logger.info(
                        f"Risk data transaction completed. Result: {result_risk}"
                    )
                    logger.success("Risk data updated / inserted successfully")
                return {
                    "success": "Data replaced successfully",
                    "operations_count": len(operations),
                }
            except Exception as e:
                error_msg = f"Transaction failed: {str(e)}"
                logger.error(error_msg)
                return {"error": error_msg, "details": str(e)}

        except Exception as e:
            logger.error(f"An error occurred: {str(e)}")
            return {"error": str(e)}

    async def check_geojson_file_by_query(self, display_id):
        try:
            query = f"""
                SELECT *
                FROM report_eudr_dd
                WHERE DisplayID = '{display_id}'
            """

            datas = self.dbMysql.execute_query(query)

            if not datas:
                return {"error": "No data found for the given partner ID"}

            df = pd.DataFrame(datas)
            getUrl = df["UrlJSON"].values[0]

            folder_name = f"eudr_{display_id}"

            if os.path.exists(folder_name):
                shutil.rmtree(folder_name)
            os.makedirs(folder_name)

            zip_path = os.path.join(folder_name, "data.zip")
            response = requests.get(getUrl)
            with open(zip_path, "wb") as file:
                file.write(response.content)

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(folder_name)

            os.remove(zip_path)

            geojson_files = [
                f for f in os.listdir(folder_name) if f.endswith(".geojson")
            ]
            if len(geojson_files) > 1:
                combined_geojson = GeojsonCombine.combine(
                    display_id=display_id, folder_path=folder_name
                )
                combined_file_path = os.path.join(
                    folder_name, "combined.geojson"
                )
                with open(combined_file_path, "w") as f:
                    json.dump(combined_geojson, f)
                gdf = gpd.read_file(combined_file_path)
            else:
                gdf = gpd.read_file(os.path.join(folder_name, geojson_files[0]))

            if gdf.geometry.isnull().any():
                shutil.rmtree(folder_name)

                await self.generate_empty_excel(display_id)

                update_query = f"""
                    UPDATE report_eudr_dd
                    SET Status = 'Done'
                    WHERE DisplayID = '{display_id}'
                """
                self.dbMysql.execute_query_save(update_query)
                raise ValueError("Invalid geometry value in the GeoJSON file")

            return gdf

        except Exception as e:
            logger.error(f"An error occurred: {str(e)}")
            await self.generate_empty_excel(display_id)

    async def validate_geojson_by_query(self, data):
        try:
            start_time = time.time()

            # Handle JSON body format
            if isinstance(data, dict):
                display_id = data.get("display_id")
                excluded_geo_ids = data.get("excluded_geo_ids", [])
            else:
                # Fallback for backward compatibility
                display_id = data
                excluded_geo_ids = []

            if display_id is None:
                return {"error": "No display ID provided"}

            check_geojson = await self.check_geojson_file_by_query(display_id)

            if check_geojson is None:
                return {"error": "No data found for the given display ID"}

            # Check if the result is an error message
            if isinstance(check_geojson, dict) and "error" in check_geojson:
                return check_geojson

            # Handle empty geometry case
            if (
                isinstance(check_geojson, dict)
                and check_geojson.get("type") == "FeatureCollection"
                and len(check_geojson.get("features", [])) == 0
            ) or len(check_geojson) == 0:
                logger.warning(
                    f"Empty geometry detected for display_id: {display_id}"
                )

                # If excluded_geo_ids is not empty, generate Excel based on those IDs
                if excluded_geo_ids and len(excluded_geo_ids) > 0:
                    # Create an empty DataFrame with required columns
                    empty_df = pd.DataFrame(
                        columns=[
                            "ProducerID",
                            "PlotNr",
                            "PlotID",
                            "issues",
                            "issues_description",
                        ]
                    )
                    gen = await self.generate_excel(empty_df, excluded_geo_ids)

                    if gen:
                        query_update = f"""
                            UPDATE report_eudr_dd
                            SET Status = 'Done',
                                UrlPolygonIssue = '{gen["url"]}'
                            WHERE DisplayID = '{display_id}'
                        """
                        self.dbMysql.execute_query_save(query_update)

                    return {
                        "message": "Excel generated based on excluded_geo_ids",
                        "url": gen["url"] if gen else None,
                    }
                else:
                    # Generate empty Excel if no excluded_geo_ids
                    gen = await self.generate_empty_excel(display_id)
                    return {
                        "message": "Empty Excel generated",
                        "url": gen["url"] if gen else None,
                    }

            gdfs = gpd.GeoDataFrame.from_features(check_geojson)

            gdf = gdfs.set_geometry("geometry")
            gdf = gdfs.set_crs(epsg=4326, allow_override=True)

            gdf.geometry = gdf.geometry.apply(
                lambda geom: geom.buffer(0.00009)
                if geom.geom_type == "Point"
                else geom
            )

            logger.info(
                f"Validating GeoJSON total number of features: {len(gdf)} | display_id: {display_id}"
            )

            processed_gdf = process_data_validation.process_data(gdf)

            if processed_gdf is not None:
                checker = TopologyChecker()
                overlappedGeometries = checker.check_overlaps(processed_gdf)
                overlappedDf = pd.DataFrame(overlappedGeometries)

                processed_gdf["major_overlapping"] = False
                processed_gdf["minor_overlapping"] = False

                if not overlappedDf.empty:
                    processed_gdf["major_overlapping"] = (
                        overlappedDf["major_overlap"].fillna(False).astype(bool)
                    )

                    processed_gdf["minor_overlapping"] = (
                        overlappedDf["minor_overlap"].fillna(False)
                        & ~processed_gdf["major_overlapping"].astype(bool)
                    ).astype(bool)

                processed_gdf["malformed"] = (
                    processed_gdf["self_intersection"]
                    & processed_gdf["long_segments"]
                ) | (processed_gdf["long_segments"])

                issues_description = [
                    "self_intersection",
                    "major_overlapping",
                    "minor_overlapping",
                    "malformed",
                    "duplicated_vertices",
                    "duplicated_polygon",
                    "not_ring",
                    "located_on_waterbodies",
                    "zero_area",
                ]

                for col in issues_description:
                    if col in processed_gdf.columns:
                        processed_gdf[col] = (
                            processed_gdf[col].fillna(False).astype(bool)
                        )
                    else:
                        processed_gdf[col] = False

                processed_gdf["issues_description"] = processed_gdf[
                    issues_description
                ].apply(lambda row: ", ".join(row.index[row]), axis=1)

                processed_gdf["issues"] = processed_gdf.apply(
                    lambda row: (
                        "major"
                        if row["major_overlapping"]
                        or row["malformed"]
                        or row["zero_area"]
                        or row["located_on_waterbodies"]
                        else (
                            "minor"
                            if row["minor_overlapping"]
                            or row["issues_description"] != ""
                            else "normal"
                        )
                    ),
                    axis=1,
                )

                processed_gdf["polygon"] = processed_gdf["polygon"].apply(
                    lambda x: wkt.dumps(x) if x else None
                )

                processed_gdf["ProducerName"] = gdf["ProducerName"]
                processed_gdf["ProducerCountry"] = gdf["ProducerCountry"]

                uid_series = pd.Series(index=processed_gdf.index, dtype=object)
                if not overlappedDf.empty:
                    uid_series.update(overlappedDf["uid"])

                processed_gdf["ProductionPlace"] = np.where(
                    uid_series.notna(), uid_series, gdf["ProductionPlace"]
                )

                processed_gdf["ProducerID"] = processed_gdf[
                    "ProductionPlace"
                ].apply(
                    lambda x: (
                        x.split("-")[1].strip()
                        if "-" in str(x) and len(str(x).split("-")) > 1
                        else ""
                    )
                )

                processed_gdf["PlotID"] = processed_gdf[
                    "ProductionPlace"
                ].apply(
                    lambda x: (
                        x.split("-")[3].strip()
                        if "-" in str(x) and len(str(x).split("-")) > 2
                        else ""
                    )
                )

                processed_gdf["PlotNr"] = processed_gdf[
                    "ProductionPlace"
                ].apply(
                    lambda x: (
                        x.split("-")[2].strip()
                        if "-" in str(x) and len(str(x).split("-")) > 3
                        else ""
                    )
                )

                shutil.rmtree(f"eudr_{display_id}")
                gen = await self.generate_excel(processed_gdf, excluded_geo_ids)

                if (
                    processed_gdf["issues_description"].str.len().eq(0).all()
                    and gen
                ):
                    update_query = f"""
                        UPDATE report_eudr_dd
                        SET Status = 'Done',
                            UrlPolygonIssue = '{gen["url"]}'
                        WHERE DisplayID = '{display_id}'
                    """
                    self.dbMysql.execute_query_save(update_query)
                    logger.info("No issues found in the GeoJSON data")

                else:
                    query_update = f"""
                        UPDATE report_eudr_dd
                        SET Status = 'Done',
                            UrlPolygonIssue = '{gen["url"]}'
                        WHERE DisplayID = '{display_id}'
                    """
                    self.dbMysql.execute_query_save(query_update)

                end_time = time.time()
                logger.info(
                    f"Total processing time for display_id: {display_id} ::: {end_time - start_time:.2f} seconds"
                )
                logger.success(
                    f"GeoJSON data validated successfully for display_id: {display_id}"
                )
                return processed_gdf.to_dict(orient="records")
            return None

        except Exception as e:
            logger.error(
                f"An error occurred while validating the GeoJSON data: {str(e)}"
            )
            return {"error": str(e)}

    async def generate_empty_excel(self, display_id):
        try:
            empty_df = pd.DataFrame(
                columns=[
                    "ProducerID",
                    "PlotNr",
                    "PlotID",
                    "issues",
                    "issues_description",
                ]
            )
            excel_buffer = io.BytesIO()
            session = boto3.Session(
                aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
                aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
                region_name=os.getenv("S3_BUCKET_REGION"),
            )

            s3_client = session.resource("s3")
            bucket_name = os.getenv("S3_BUCKET")
            cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN")
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            s3_key = f"staging/polygon_validation/Issue_Log_{timestamp}.xlsx"

            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                empty_df.to_excel(writer, index=False, sheet_name="Data")

                worksheet = writer.sheets["Data"]
                for idx, col in enumerate(empty_df.columns):
                    max_length = (
                        max(
                            empty_df[col].astype(str).apply(len).max(),
                            len(str(col)),
                        )
                        + 2
                    )
                    worksheet.column_dimensions[
                        get_column_letter(idx + 1)
                    ].width = max_length

            excel_buffer.seek(0)

            s3_client.meta.client.upload_fileobj(
                excel_buffer,
                bucket_name,
                s3_key,
                ExtraArgs={
                    "ACL": "public-read",
                    "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                },
            )

            url = f"{cloudfront_domain}/{s3_key}"

            query_update = f"""
                UPDATE report_eudr_dd
                SET Status = 'Done',
                    UrlPolygonIssue = '{url}'
                WHERE DisplayID = '{display_id}'
            """
            self.dbMysql.execute_query_save(query_update)

            return {
                "bucket": bucket_name,
                "s3_key": s3_key,
                "url": f"{cloudfront_domain}/{s3_key}",
            }
        except Exception as e:
            logger.error(
                f"An error occurred while generating the Excel file: {str(e)}"
            )
            return {"error": str(e)}

    async def generate_excel(self, df, excluded_geo_ids=None):
        try:
            required_columns = [
                "ProducerID",
                "PlotNr",
                "PlotID",
                "issues",
                "issues_description",
            ]
            missing_columns = [
                col for col in required_columns if col not in df.columns
            ]
            if missing_columns:
                logger.error(f"Missing columns: {missing_columns}")
                return None

            # Add excluded_geo_ids to the dataframe with specific issue description
            if excluded_geo_ids and len(excluded_geo_ids) > 0:
                excluded_rows = []
                for geo_id in excluded_geo_ids:
                    if "-" in geo_id and len(geo_id.split("-")) > 3:
                        parts = geo_id.split("-")
                        excluded_rows.append(
                            {
                                "ProductionPlace": geo_id,
                                "ProducerID": (
                                    parts[1].strip() if len(parts) > 1 else ""
                                ),
                                "PlotNr": parts[2].strip()
                                if len(parts) > 2
                                else "",
                                "PlotID": parts[3].strip()
                                if len(parts) > 3
                                else "",
                                "issues": "normal",
                                "issues_description": "Need to check again the data survey",
                            }
                        )

                if excluded_rows:
                    # Create a dataframe from the excluded rows
                    excluded_df = pd.DataFrame(excluded_rows)

                    # Ensure all required columns exist in excluded_df
                    for col in df.columns:
                        if col not in excluded_df.columns:
                            excluded_df[col] = None

                    # Append the excluded rows to the main dataframe
                    df = pd.concat([df, excluded_df], ignore_index=True)

            df_filtered = df[df["issues_description"].str.len() > 0][
                required_columns
            ]

            excel_buffer = io.BytesIO()
            session = boto3.Session(
                aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
                aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
                region_name=os.getenv("S3_BUCKET_REGION"),
            )

            s3_client = session.resource("s3")
            bucket_name = os.getenv("S3_BUCKET")
            cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN")
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            s3_key = f"staging/polygon_validation/Issue_Log_{timestamp}.xlsx"

            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                if "ShipmentItemId" in df.columns:
                    for shipment_item_id, group in df_filtered.groupby(
                        "ShipmentItemId"
                    ):
                        sheet_name = f"Item_{str(shipment_item_id)[:31]}"
                        group.to_excel(
                            writer, index=False, sheet_name=sheet_name
                        )

                        self._style_worksheet(writer.sheets[sheet_name], group)
                else:
                    sheet_name = "Issues"
                    df_filtered.to_excel(
                        writer, index=False, sheet_name=sheet_name
                    )

                    self._style_worksheet(
                        writer.sheets[sheet_name], df_filtered
                    )

            excel_buffer.seek(0)
            s3_client.meta.client.upload_fileobj(
                excel_buffer,
                bucket_name,
                s3_key,
                ExtraArgs={
                    "ACL": "public-read",
                    "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                },
            )

            return {
                "bucket": bucket_name,
                "s3_key": s3_key,
                "url": f"{cloudfront_domain}/{s3_key}",
            }

        except Exception as e:
            logger.error(
                f"An error occurred while generating and uploading Excel file to S3: {str(e)}"
            )
            return None

    def _style_worksheet(self, worksheet, dataframe):
        header_fill = PatternFill(
            start_color="2E8B57", end_color="2E8B57", fill_type="solid"
        )
        header_font = Font(color="FFFFFF", bold=True)

        for cell in worksheet[1]:
            cell.fill = header_fill
            cell.font = header_font

        for cell in worksheet[1]:
            cell.value = str(cell.value).upper()

        for idx, col in enumerate(dataframe.columns):
            max_length = (
                max(
                    dataframe[col].astype(str).apply(len).max(),
                    len(str(col)),
                )
                + 2
            )
            worksheet.column_dimensions[
                get_column_letter(idx + 1)
            ].width = max_length

    def get_column_letter(idx):
        if idx < 1:
            raise ValueError("Index must be greater than 0")

        result = ""
        while idx:
            idx, remainder = divmod(idx - 1, 26)
            result = chr(65 + remainder) + result
        return result

    async def process_shipments_parallel(self, shipment_ids: list[str]):
        try:
            tasks = [
                self.read_lindt_data(shipment_id)
                for shipment_id in shipment_ids
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for shipment_id, result in zip(shipment_ids, results):
                if isinstance(result, Exception):
                    logger.error(
                        f"Error processing shipment {shipment_id}: {str(result)}"
                    )

            return results
        except Exception as e:
            logger.error(f"Error in parallel processing: {str(e)}")
            return []

    async def validate_polygon_import(
        self, import_item_id: str, data_plots: List[Dict[str, Any]]
    ):
        try:
            start_time = time.time()
            logger.info(
                f"Validating polygon import for import_item_id: {import_item_id}"
            )

            if not data_plots or len(data_plots) == 0:
                return {"error": "No data plots provided"}

            results = {"type": "FeatureCollection", "features": []}

            for plot in data_plots:
                properties = {
                    "ID": str(uuid.uuid4()),
                    "producer_detail_id": str(plot["id"]),
                    "import_item_id": import_item_id,
                    "commo_id": plot["commo_id"],
                }

                geometry = wkt.loads(plot["polygon"])

                feature = {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [y, x]
                                for x, y in zip(
                                    geometry.exterior.xy[0],
                                    geometry.exterior.xy[1],
                                )
                            ]
                        ],
                    },
                }

                results["features"].append(feature)

            process = await self.process_geojson_data(results, False)
            process_geometry = await self.process_geometries(
                json.dumps(process["results"]), True, is_shipment=False
            )

            results = await self.process_all_data(
                process_geometry, import_item_id, False
            )
            is_comply = all([result["is_comply"] for result in results])
            logger.info(f"Compliance status for import: {is_comply}")

            callback_data = [
                {
                    "import_item_id": import_item_id,
                    "data_plots": [
                        {
                            "id": result["producer_detail_id"],
                            "compliance_status": (
                                "comply"
                                if result["is_comply"]
                                else "not-comply"
                            ),
                        }
                        for result in results
                    ],
                }
            ]

            await self.callback_polygon_validation_url(
                callback_data, import_item_id
            )

            end_time = time.time()
            logger.info(
                f"Polygon validation completed for import_item_id: {import_item_id}. Time taken: {end_time - start_time} seconds"
            )
            return results

        except Exception as e:
            logger.error(
                f"An error occurred while validating polygons: {str(e)}"
            )
            return {"error": str(e)}

    async def callback_polygon_validation_url(
        self,
        datas: List[Dict[str, Any]],
        import_item_id: str,
    ):
        try:
            logger.info(
                f"Calling callback_polygon_validation_url for import_item_id: {import_item_id}"
            )
            url = ConfigLoader().get_app_config()[
                "callback_polygon_validation_url"
            ]
            headers = {"Content-Type": "application/json"}
            response = requests.post(url, json=datas[0], headers=headers)
            if response.status_code == 200:
                logger.info(
                    f"Callback successful for import_item_id: {import_item_id}"
                )
            else:
                logger.error(
                    f"Callback failed for import_item_id: {import_item_id}"
                )
                logger.error(response.json())
        except Exception as e:
            logger.error(
                f"An error occurred while calling callback_polygon_validation_url: {str(e)}"
            )

    # v2
    async def check_geojson_file_v2(self, display_id):
        try:
            logger.info(
                f"[check_geojson_file_v2] Starting for display_id: {display_id}"
            )
            query = f"""
                SELECT ReportID, DisplayID, UrlJSON
                FROM report_eudr_dd
                WHERE DisplayID = '{display_id}'
            """

            datas = self.dbMysql.execute_query(query)

            if not datas:
                logger.warning(
                    f"[check_geojson_file_v2] No data found for display_id: {display_id}"
                )
                return {"error": "No data found for the given display ID"}

            df = pd.DataFrame(datas)
            getUrl = df["UrlJSON"].values[0]

            folder_name = f"eudr_{display_id}"

            if os.path.exists(folder_name):
                shutil.rmtree(folder_name)
            os.makedirs(folder_name)

            zip_path = os.path.join(folder_name, "data.zip")
            response = requests.get(getUrl)
            with open(zip_path, "wb") as file:
                file.write(response.content)

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(folder_name)

            os.remove(zip_path)

            geojson_files = [
                f for f in os.listdir(folder_name) if f.endswith(".geojson")
            ]
            if len(geojson_files) > 1:
                logger.info(
                    f"[check_geojson_file_v2] Combining {len(geojson_files)} geojson files for display_id: {display_id}"
                )
                combined_geojson = GeojsonCombine.combine(
                    display_id=display_id, folder_path=folder_name
                )
                combined_file_path = os.path.join(
                    folder_name, "combined.geojson"
                )
                with open(combined_file_path, "w") as f:
                    json.dump(combined_geojson, f)
                gdf = gpd.read_file(combined_file_path)
            else:
                gdf = gpd.read_file(os.path.join(folder_name, geojson_files[0]))

            if gdf.geometry.isnull().any():
                logger.error(
                    f"[check_geojson_file_v2] Invalid geometry detected for display_id: {display_id}"
                )
                shutil.rmtree(folder_name)

                await self.generate_empty_excel_v2(display_id)
                raise ValueError(
                    f"Invalid geometry value in the GeoJSON file display id {display_id}"
                )

            gdf["ReportID"] = df["ReportID"].values[0]
            logger.info(
                f"[check_geojson_file_v2] Successfully processed {len(gdf)} features for display_id: {display_id}"
            )
            return gdf

        except Exception as e:
            logger.error(f"An error occurred display_id {display_id}: {str(e)}")
            await self.generate_empty_excel_v2(display_id)

            getReportID = f"""
                SELECT ReportID
                FROM report_eudr_dd
                WHERE DisplayID = '{display_id}'
            """
            report_id = self.dbMysql.execute_query(getReportID)
            await self.callback_to_partner_report(report_id[0]["ReportID"])

    async def validate_geojson_v2(self, data):
        try:
            start_time = time.time()
            logger.info("[validate_geojson_v2] Starting validation")

            if isinstance(data, dict):
                display_id = data.get("display_id")
                excluded_geo_ids = data.get(
                    "excluded_geo_ids_geospatial_issues", []
                )
                excluded_assesment_ids = data.get(
                    "excluded_geo_ids_assessment_results", []
                )
            else:
                display_id = data
                excluded_geo_ids = []
                excluded_assesment_ids = []

            if display_id is None:
                logger.warning("[validate_geojson_v2] No display_id provided")
                return {"error": "No display ID provided"}

            logger.info(
                f"[validate_geojson_v2] Processing display_id: {display_id}"
            )
            check_geojson = await self.check_geojson_file_v2(display_id)

            if check_geojson is None:
                logger.warning(
                    f"[validate_geojson_v2] No data found for display_id: {display_id}"
                )
                return {"error": "No data found for the given display ID"}

            if isinstance(check_geojson, dict) and "error" in check_geojson:
                return check_geojson

            if (
                isinstance(check_geojson, dict)
                and check_geojson.get("type") == "FeatureCollection"
                and len(check_geojson.get("features", [])) == 0
            ) or len(check_geojson) == 0:
                logger.warning(
                    f"[validate_geojson_v2] Empty geometry detected for display_id: {display_id}"
                )

                if excluded_geo_ids and len(excluded_geo_ids) > 0:
                    empty_df = pd.DataFrame(
                        columns=[
                            "ProducerID",
                            "PlotNr",
                            "PlotID",
                            "issues",
                            "issues_description",
                        ]
                    )

                    gen = await self.generate_excel_v2(
                        empty_df,
                        excluded_geo_ids,
                        excluded_assesment_ids,
                        display_id,
                    )

                    if gen:
                        query_update = f"""
                            UPDATE report_eudr_dd
                            SET UrlPolygonIssue = '{gen["url"]}'
                            WHERE DisplayID = '{display_id}'
                        """
                        self.dbMysql.execute_query_save(query_update)

                    return {
                        "message": "Excel generated based on excluded_geo_ids",
                        "url": gen["url"] if gen else None,
                    }
                else:
                    gen = await self.generate_empty_excel_v2(display_id)
                    return {
                        "message": "Empty Excel generated",
                        "url": gen["url"] if gen else None,
                    }

            gdfs = gpd.GeoDataFrame.from_features(check_geojson)

            gdf = gdfs.set_geometry("geometry")
            gdf = gdfs.set_crs(epsg=4326, allow_override=True)

            gdf.geometry = gdf.geometry.apply(
                lambda geom: geom.buffer(0.00009)
                if geom.geom_type == "Point"
                else geom
            )

            logger.info(
                f"[validate_geojson_v2] Validating {len(gdf)} features for display_id: {display_id}"
            )

            processed_gdf = process_data_validation.process_data(gdf)

            if processed_gdf is not None:
                checker = TopologyChecker()
                overlappedGeometries = checker.check_overlaps(processed_gdf)
                overlappedDf = pd.DataFrame(overlappedGeometries)

                overlappedDf.to_csv("overlapped.csv", index=False)
                exit()

                processed_gdf["major_overlapping"] = False
                processed_gdf["minor_overlapping"] = False

                if not overlappedDf.empty:
                    processed_gdf["major_overlapping"] = (
                        overlappedDf["major_overlap"].fillna(False).astype(bool)
                    )

                    processed_gdf["minor_overlapping"] = (
                        overlappedDf["minor_overlap"].fillna(False)
                        & ~processed_gdf["major_overlapping"].astype(bool)
                    ).astype(bool)

                processed_gdf["malformed"] = (
                    processed_gdf["self_intersection"]
                    & processed_gdf["long_segments"]
                ) | (processed_gdf["long_segments"])

                issues_description = [
                    "self_intersection",
                    "major_overlapping",
                    "minor_overlapping",
                    "malformed",
                    "duplicated_vertices",
                    "duplicated_polygon",
                    "not_ring",
                    "located_on_waterbodies",
                    "zero_area",
                ]

                for col in issues_description:
                    if col in processed_gdf.columns:
                        processed_gdf[col] = (
                            processed_gdf[col].fillna(False).astype(bool)
                        )
                    else:
                        processed_gdf[col] = False

                processed_gdf["issues_description"] = processed_gdf[
                    issues_description
                ].apply(lambda row: ", ".join(row.index[row]), axis=1)

                processed_gdf["issues"] = processed_gdf.apply(
                    lambda row: (
                        "major"
                        if row["major_overlapping"]
                        or row["malformed"]
                        or row["zero_area"]
                        or row["located_on_waterbodies"]
                        else (
                            "minor"
                            if row["minor_overlapping"]
                            or row["issues_description"] != ""
                            else "normal"
                        )
                    ),
                    axis=1,
                )

                processed_gdf["polygon"] = processed_gdf["polygon"].apply(
                    lambda x: wkt.dumps(x) if x else None
                )

                processed_gdf["ProducerName"] = gdf["ProducerName"]
                processed_gdf["ProducerCountry"] = gdf["ProducerCountry"]

                uid_series = pd.Series(index=processed_gdf.index, dtype=object)
                if not overlappedDf.empty:
                    uid_series.update(overlappedDf["uid"])

                processed_gdf["ProductionPlace"] = np.where(
                    uid_series.notna(), uid_series, gdf["ProductionPlace"]
                )

                processed_gdf["ProducerID"] = processed_gdf[
                    "ProductionPlace"
                ].apply(
                    lambda x: (
                        x.split("-")[1].strip()
                        if "-" in str(x) and len(str(x).split("-")) > 1
                        else ""
                    )
                )

                processed_gdf["PlotID"] = processed_gdf[
                    "ProductionPlace"
                ].apply(
                    lambda x: (
                        x.split("-")[3].strip()
                        if "-" in str(x) and len(str(x).split("-")) > 2
                        else ""
                    )
                )

                processed_gdf["PlotNr"] = processed_gdf[
                    "ProductionPlace"
                ].apply(
                    lambda x: (
                        x.split("-")[2].strip()
                        if "-" in str(x) and len(str(x).split("-")) > 3
                        else ""
                    )
                )

                shutil.rmtree(f"eudr_{display_id}")
                gen = await self.generate_excel_v2(
                    processed_gdf,
                    excluded_geo_ids,
                    excluded_assesment_ids,
                    display_id,
                )

                if (
                    processed_gdf["issues_description"].str.len().eq(0).all()
                    and gen
                ):
                    update_query = f"""
                        UPDATE report_eudr_dd
                        SET UrlPolygonIssue = '{gen["url"]}'
                        WHERE DisplayID = '{display_id}'
                    """
                    self.dbMysql.execute_query_save(update_query)
                    logger.info(
                        f"[validate_geojson_v2] No issues found for display_id: {display_id}"
                    )

                else:
                    query_update = f"""
                        UPDATE report_eudr_dd
                        SET UrlPolygonIssue = '{gen["url"]}'
                        WHERE DisplayID = '{display_id}'
                    """
                    self.dbMysql.execute_query_save(query_update)
                    logger.info(
                        f"[validate_geojson_v2] Issues found for display_id: {display_id}"
                    )

                # callback
                getReportID = f"""
                    SELECT ReportID
                    FROM report_eudr_dd
                    WHERE DisplayID = '{display_id}'
                """
                report_id = self.dbMysql.execute_query(getReportID)
                await self.callback_to_partner_report(report_id[0]["ReportID"])
                end_time = time.time()
                logger.info(
                    f"[validate_geojson_v2] Completed for display_id: {display_id} in {end_time - start_time:.2f}s"
                )
                return processed_gdf.to_dict(orient="records")
            return None

        except Exception as e:
            logger.error(
                f"An error occurred while validating the GeoJSON data display id {display_id}: {str(e)}"
            )
            return {"error": str(e)}

    async def callback_to_partner_report(self, report_id):
        callback_url = cfg["callback_to_partner_report_url"]
        headers = {"Content-Type": "application/json"}
        data = {"report_id": report_id}
        try:
            response = requests.post(callback_url, headers=headers, json=data)
            logger.info(f"Response: {response.json()}")
            logger.success(
                f"Callback sent successfully for report_id: {report_id}"
            )
        except requests.exceptions.RequestException as e:
            logger.error(
                f"An error occurred while sending the callback for report {report_id}: {str(e)}"
            )
            return {"error": str(e)}

    async def generate_excel_v2(
        self,
        df,
        excluded_geo_ids_geospatial_issues=None,
        excluded_geo_ids_assessment_results=None,
        display_id="",
    ):
        try:
            required_columns = [
                "ProducerID",
                "PlotNr",
                "PlotID",
                "issues",
                "issues_description",
            ]
            missing_columns = [
                col for col in required_columns if col not in df.columns
            ]
            if missing_columns:
                logger.error(f"Missing columns: {missing_columns}")
                return None

            if (
                excluded_geo_ids_assessment_results
                and len(excluded_geo_ids_assessment_results) > 0
            ):
                excluded_rows = []
                for geo_id in excluded_geo_ids_assessment_results:
                    if "-" in geo_id and len(geo_id.split("-")) > 3:
                        parts = geo_id.split("-")
                        excluded_rows.append(
                            {
                                "ProductionPlace": geo_id,
                                "ProducerID": (
                                    parts[1].strip() if len(parts) > 1 else ""
                                ),
                                "PlotNr": parts[2].strip()
                                if len(parts) > 2
                                else "",
                                "PlotID": parts[3].strip()
                                if len(parts) > 3
                                else "",
                                "issues": "normal",
                                "issues_description": "Please check polygon geometry",
                            }
                        )

                if excluded_rows:
                    excluded_df = pd.DataFrame(excluded_rows)
                    for col in df.columns:
                        if col not in excluded_df.columns:
                            excluded_df[col] = None

                    df = pd.concat([df, excluded_df], ignore_index=True)

            if (
                excluded_geo_ids_geospatial_issues
                and len(excluded_geo_ids_geospatial_issues) > 0
            ):
                excluded_rows = []
                for geo_id in excluded_geo_ids_geospatial_issues:
                    if "-" in geo_id and len(geo_id.split("-")) > 3:
                        parts = geo_id.split("-")
                        excluded_rows.append(
                            {
                                "ProductionPlace": geo_id,
                                "ProducerID": (
                                    parts[1].strip() if len(parts) > 1 else ""
                                ),
                                "PlotNr": parts[2].strip()
                                if len(parts) > 2
                                else "",
                                "PlotID": parts[3].strip()
                                if len(parts) > 3
                                else "",
                                "issues": "normal",
                                "issues_description": "Need to check again the data survey",
                            }
                        )

                if excluded_rows:
                    excluded_df = pd.DataFrame(excluded_rows)
                    for col in df.columns:
                        if col not in excluded_df.columns:
                            excluded_df[col] = None

                    df = pd.concat([df, excluded_df], ignore_index=True)

            df_filtered = df[df["issues_description"].str.len() > 0][
                required_columns
            ]

            # Group by ProductionPlace (ProducerID, PlotNr, PlotID) and merge issues
            if not df_filtered.empty and "ProducerID" in df_filtered.columns:
                grouped_data = []
                for (
                    producer_id,
                    plot_nr,
                    plot_id,
                ), group in df_filtered.groupby(
                    ["ProducerID", "PlotNr", "PlotID"], dropna=False
                ):
                    # Determine if any row has major issue
                    has_major = (group["issues"] == "major").any()

                    # Combine all unique issues_description
                    all_issues = []
                    for issues_desc in group["issues_description"]:
                        if pd.notna(issues_desc) and issues_desc.strip():
                            # Split by comma and add individual issues
                            all_issues.extend(
                                [i.strip() for i in str(issues_desc).split(",")]
                            )

                    # Remove duplicates while preserving order
                    unique_issues = []
                    seen = set()
                    for issue in all_issues:
                        if issue and issue not in seen:
                            unique_issues.append(issue)
                            seen.add(issue)

                    grouped_data.append(
                        {
                            "ProducerID": producer_id,
                            "PlotNr": plot_nr,
                            "PlotID": plot_id,
                            "issues": "major" if has_major else "minor",
                            "issues_description": ", ".join(unique_issues),
                        }
                    )

                df_filtered = pd.DataFrame(grouped_data)

            excel_buffer = io.BytesIO()
            session = boto3.Session(
                aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
                aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
                region_name=os.getenv("S3_BUCKET_REGION"),
            )

            s3_client = session.resource("s3")
            bucket_name = os.getenv("S3_BUCKET")
            cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN")
            print(display_id[2:])
            extracted_display_id = display_id[2:]

            s3_key = f"staging/polygon_validation/Issue_Log_{extracted_display_id}.xlsx"

            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                if "ShipmentItemId" in df.columns:
                    for shipment_item_id, group in df_filtered.groupby(
                        "ShipmentItemId"
                    ):
                        sheet_name = f"Item_{str(shipment_item_id)[:31]}"
                        group.to_excel(
                            writer, index=False, sheet_name=sheet_name
                        )

                        self._style_worksheet(writer.sheets[sheet_name], group)
                else:
                    sheet_name = "Issues"
                    df_filtered.to_excel(
                        writer, index=False, sheet_name=sheet_name
                    )

                    self._style_worksheet(
                        writer.sheets[sheet_name], df_filtered
                    )

            excel_buffer.seek(0)
            s3_client.meta.client.upload_fileobj(
                excel_buffer,
                bucket_name,
                s3_key,
                ExtraArgs={
                    "ACL": "public-read",
                    "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                },
            )

            return {
                "bucket": bucket_name,
                "s3_key": s3_key,
                "url": f"{cloudfront_domain}/{s3_key}",
            }

        except Exception as e:
            logger.error(
                f"An error occurred while generating and uploading Excel file to S3: {str(e)}"
            )
            return None

    async def generate_empty_excel_v2(self, display_id):
        try:
            empty_df = pd.DataFrame(
                columns=[
                    "ProducerID",
                    "PlotNr",
                    "PlotID",
                    "issues",
                    "issues_description",
                ]
            )
            excel_buffer = io.BytesIO()
            session = boto3.Session(
                aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
                aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
                region_name=os.getenv("S3_BUCKET_REGION"),
            )

            s3_client = session.resource("s3")
            bucket_name = os.getenv("S3_BUCKET")
            cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN")
            extracted_display_id = display_id[2:]

            s3_key = f"staging/polygon_validation/Issue_Log_{extracted_display_id}.xlsx"

            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                empty_df.to_excel(writer, index=False, sheet_name="Data")

                worksheet = writer.sheets["Data"]
                for idx, col in enumerate(empty_df.columns):
                    max_length = (
                        max(
                            empty_df[col].astype(str).apply(len).max(),
                            len(str(col)),
                        )
                        + 2
                    )
                    worksheet.column_dimensions[
                        get_column_letter(idx + 1)
                    ].width = max_length

            excel_buffer.seek(0)

            s3_client.meta.client.upload_fileobj(
                excel_buffer,
                bucket_name,
                s3_key,
                ExtraArgs={
                    "ACL": "public-read",
                    "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                },
            )

            url = f"{cloudfront_domain}/{s3_key}"

            query_update = f"""
                UPDATE report_eudr_dd
                SET UrlPolygonIssue = '{url}'
                WHERE DisplayID = '{display_id}'
            """
            self.dbMysql.execute_query_save(query_update)

            return {
                "bucket": bucket_name,
                "s3_key": s3_key,
                "url": f"{cloudfront_domain}/{s3_key}",
            }
        except Exception as e:
            logger.error(
                f"An error occurred while generating the Excel file for display id {display_id}: {str(e)}"
            )
            return {"error": str(e)}


spatial_reader_service = SpatialReaderService()
