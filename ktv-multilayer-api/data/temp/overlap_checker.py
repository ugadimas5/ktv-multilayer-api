from functools import lru_cache
from typing import Dict, List, Optional

import geopandas as gpd
import numpy as np
import pandas as pd
from loguru import logger
from pydantic import BaseModel
from shapely.geometry import Polygon
from shapely.strtree import STRtree
from shapely.validation import make_valid


class CalculationResult(BaseModel):
    geom1_area: float
    geom2_area: float
    overlap_area: float


class TopologyChecker:
    def __init__(self):
        self.spatial_index = None
        self._utm_cache = {}
        self._transformed_geoms = {}

    @lru_cache(maxsize=1024)
    def get_utm_epsg(self, lat: float, lon: float) -> int:
        utm_band = str(int((lon + 180) / 6) + 1)
        return int(f"{'326' if lat > 0 else '327'}{utm_band.zfill(2)}")

    def _transform_to_utm(self, geom: Polygon, utm_epsg: int) -> Polygon:
        geom_hash = hash(geom.wkb)
        cache_key = (geom_hash, utm_epsg)

        if cache_key not in self._transformed_geoms:
            transformed = (
                gpd.GeoSeries([geom], crs="EPSG:4326")
                .to_crs(f"EPSG:{utm_epsg}")
                .iloc[0]
            )
            self._transformed_geoms[cache_key] = transformed

        return self._transformed_geoms[cache_key]

    def calculate_areas(
            self, geom1: Polygon, geom2: Polygon, overlap_geom: Polygon
    ) -> CalculationResult:
        centroid = geom1.centroid
        utm_epsg = self.get_utm_epsg(centroid.y, centroid.x)

        geom1_utm = self._transform_to_utm(geom1, utm_epsg)
        geom2_utm = self._transform_to_utm(geom2, utm_epsg)
        overlap_utm = self._transform_to_utm(overlap_geom, utm_epsg)

        return CalculationResult(
            geom1_area=geom1_utm.area,
            geom2_area=geom2_utm.area,
            overlap_area=overlap_utm.area,
        )

    def _determine_overlap_type(
            self, polygon_overlaps: Dict[str, Dict]
    ) -> Dict[str, str]:
        overlap_types: Dict[str, str] = {}

        for unique_id, data in polygon_overlaps.items():
            overlap_percentage = (data["total_overlap_area"] / data["original_area"]) * 100
            if overlap_percentage > 20:
                overlap_types[unique_id] = "major overlap"
            else:
                overlap_types[unique_id] = "minor overlap"

        overlap_graph = {}
        for unique_id, data in polygon_overlaps.items():
            overlap_graph[unique_id] = list(data["overlapping_with"])

        changes_made = True
        while changes_made:
            changes_made = False
            for unique_id, partners in overlap_graph.items():
                if overlap_types[unique_id] == "major overlap":
                    for partner_id in partners:
                        if partner_id in overlap_types and overlap_types[partner_id] == "minor overlap":
                            overlap_types[partner_id] = "major overlap"
                            changes_made = True

        return overlap_types


    def check_overlaps(
            self, gdf1: gpd.GeoDataFrame, gdf2: Optional[gpd.GeoDataFrame] = None
    ) -> List[dict]:
        if not isinstance(gdf1, gpd.GeoDataFrame):
            gdf1["geometry"] = gdf1["polygon"]
            gdf1 = gpd.GeoDataFrame(gdf1)
            gdf1.set_geometry("geometry", inplace=True)
            gdf1 = gdf1.set_crs("EPSG:4326")

        if "ProductionPlace" not in gdf1.columns:
            raise ValueError("GeoDataFrame must contain a 'ProductionPlace' column")

        gdf1 = gdf1 if gdf1.crs == "EPSG:4326" else gdf1.to_crs("EPSG:4326")
        if gdf2 is not None:
            if "ProductionPlace" not in gdf2.columns:
                raise ValueError(
                    "Second GeoDataFrame must contain a 'ProductionPlace' column"
                )
            gdf2 = gdf2 if gdf2.crs == "EPSG:4326" else gdf2.to_crs("EPSG:4326")
        else:
            gdf2, self_check = gdf1, True

        gdf1["unique_id"] = gdf1["ProductionPlace"]
        gdf2["unique_id"] = gdf2["ProductionPlace"]

        geometries = np.array(gdf2.geometry.values)
        unique_ids = np.array(gdf2["unique_id"].values)
        polygon_overlaps: Dict[str, Dict] = {}

        logger.info("Building STRtree spatial index...")
        tree = STRtree(geometries)

        batch_size = 1000
        total_overlap_pairs = 0

        for start_idx in range(0, len(gdf1), batch_size):
            end_idx = min(start_idx + batch_size, len(gdf1))
            batch_geoms = gdf1.geometry.values[start_idx:end_idx]
            batch_ids = gdf1["unique_id"].values[start_idx:end_idx]

            for idx1, (geom1, unique_id1) in enumerate(
                    zip(batch_geoms, batch_ids), start=start_idx
            ):
                try:
                    nearby_idxs = tree.query(geom1)

                    for idx2 in nearby_idxs:
                        unique_id2 = unique_ids[idx2]

                        if self_check and unique_id2 <= unique_id1:
                            continue

                        geom2 = geometries[idx2]

                        valid_geom1 = make_valid(geom1)
                        valid_geom2 = make_valid(geom2)

                        if valid_geom1.intersects(valid_geom2):
                            try:
                                overlap_geom = valid_geom1.intersection(valid_geom2)

                                if (
                                        hasattr(overlap_geom, "area")
                                        and overlap_geom.area > 0
                                        and overlap_geom.geom_type in ["Polygon", "MultiPolygon"]
                                ):
                                    areas = self.calculate_areas(geom1, geom2, overlap_geom)

                                    overlap_percent1 = (areas.overlap_area / areas.geom1_area) * 100
                                    overlap_percent2 = (areas.overlap_area / areas.geom2_area) * 100

                                    # Detect even very small overlaps (any overlap > 0.01%)
                                    if max(overlap_percent1, overlap_percent2) > 0.01:
                                        total_overlap_pairs += 1

                                        if unique_id1 not in polygon_overlaps:
                                            polygon_overlaps[unique_id1] = {
                                                "geometry": geom1,
                                                "total_overlap_area": 0,
                                                "overlapping_with": set(),
                                                "original_area": areas.geom1_area,
                                            }

                                        if unique_id2 not in polygon_overlaps[unique_id1]["overlapping_with"]:
                                            polygon_overlaps[unique_id1]["total_overlap_area"] += areas.overlap_area
                                            polygon_overlaps[unique_id1]["overlapping_with"].add(unique_id2)

                                        if not self_check or unique_id1 != unique_id2:
                                            if unique_id2 not in polygon_overlaps:
                                                polygon_overlaps[unique_id2] = {
                                                    "geometry": geom2,
                                                    "total_overlap_area": 0,
                                                    "overlapping_with": set(),
                                                    "original_area": areas.geom2_area,
                                                }

                                            if unique_id1 not in polygon_overlaps[unique_id2]["overlapping_with"]:
                                                polygon_overlaps[unique_id2]["total_overlap_area"] += areas.overlap_area
                                                polygon_overlaps[unique_id2]["overlapping_with"].add(unique_id1)

                            except Exception as e:
                                logger.debug(
                                    f"Error processing intersection between {unique_id1} and {unique_id2}: {e}")

                except Exception as e:
                    logger.debug(f"Error processing feature {unique_id1}: {e}")

            if len(self._transformed_geoms) > 10000:
                self._transformed_geoms.clear()

        logger.info(f"Found {total_overlap_pairs} overlap pairs")
        logger.info(f"Total polygons with overlaps: {len(polygon_overlaps)}")

        overlap_types = self._determine_overlap_type(polygon_overlaps)

        results = []
        for _, row in gdf1.iterrows():
            unique_id = row["ProductionPlace"]

            if unique_id in polygon_overlaps:
                data = polygon_overlaps[unique_id]
                overlap_type = overlap_types[unique_id]
                overlap_percentage = (data["total_overlap_area"] / data["original_area"]) * 100

                results.append({
                    "overlap_type": overlap_type,
                    "unique_id": unique_id,
                    "polygon": data["geometry"],
                    "overlap_percentage": round(overlap_percentage, 2),
                    "overlapping_with": ",".join(sorted(data["overlapping_with"])),
                })
            else:
                results.append({
                    "overlap_type": "no overlap",
                    "unique_id": unique_id,
                    "polygon": row["geometry"],
                    "overlap_percentage": 0,
                    "overlapping_with": "",
                })

        results_df = pd.DataFrame(results)
        results_df.to_csv("overlap_results.csv", index=False)

        overlap_summary = {}
        for result in results:
            overlap_type = result["overlap_type"]
            overlap_summary[overlap_type] = overlap_summary.get(overlap_type, 0) + 1

        logger.info("Overlap detection summary:")
        for overlap_type, count in overlap_summary.items():
            logger.info(f"  {overlap_type}: {count} polygons")

        return results
