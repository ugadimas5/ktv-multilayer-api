import ee
import geojson
import json
import pandas as pd
from typing import Dict, Any, List
import tempfile
import os

def get_ktv_datasets():
    """Load hanya 3 dataset untuk KTV: GFW loss, JRC loss, SBTN loss"""
    # Global Forest Change data
    gfc = ee.Image("UMD/hansen/global_forest_change_2024_v1_12")
    
    # 1. GFW Loss (2021-2024)
    gfw_loss_bands = []
    for year in range(2021, 2025):
        year_code = year - 2000
        loss_year = gfc.select("lossyear").eq(year_code).And(gfc.select("treecover2000").gt(10))
        gfw_loss_year = loss_year.rename(f'gfw_loss_{year}')
        gfw_loss_bands.append(gfw_loss_year)
    
    # GFW combined loss 2021-2024
    gfw_combined = gfc.select("lossyear").gte(21).And(gfc.select("lossyear").lte(24))
    gfw_combined = gfw_combined.And(gfc.select("treecover2000").gt(10)).rename('gfw_loss_combined')
    
    # 2. SBTN Loss 
    sbtn = ee.Image('WRI/SBTN/naturalLands/v1_1/2020').select('natural')
    sbtn_mask = sbtn.eq(1)
    sbtn_loss_bands = []
    for year in range(2021, 2025):
        year_code = year - 2000
        loss_year = gfc.select("lossyear").eq(year_code).And(gfc.select("treecover2000").gt(10))
        sbtn_loss_year = loss_year.updateMask(sbtn_mask).rename(f'sbtn_loss_{year}')
        sbtn_loss_bands.append(sbtn_loss_year)
    
    # SBTN combined loss
    sbtn_combined = gfc.select("lossyear").gte(21).And(gfc.select("lossyear").lte(24))
    sbtn_combined = sbtn_combined.And(gfc.select("treecover2000").gt(10))
    sbtn_combined = sbtn_combined.updateMask(sbtn_mask).rename('sbtn_loss_combined')
    
    # 3. JRC Loss
    eufo = ee.ImageCollection("JRC/GFC2020/V2").mosaic()
    eufo_mask = eufo.gt(0)
    tmf_def = ee.ImageCollection("projects/JRC/TMF/v1_2024/DeforestationYear").mosaic()
    
    jrc_loss_bands = []
    for year in range(2021, 2025):
        year_deforestation = tmf_def.eq(year).updateMask(eufo_mask).rename(f'jrc_loss_{year}')
        jrc_loss_bands.append(year_deforestation)
    
    # JRC combined loss
    jrc_combined = tmf_def.gte(2021).And(tmf_def.lte(2024))
    jrc_combined = jrc_combined.updateMask(eufo_mask).rename('jrc_loss_combined')
    
    # Build final image dengan 3 dataset saja
    img = gfw_combined.addBands(sbtn_combined).addBands(jrc_combined)
    
    # Tambahkan band per tahun
    for band in gfw_loss_bands + sbtn_loss_bands + jrc_loss_bands:
        img = img.addBands(band)
    
    return img

def process_ktv_multilayer(geojson_path: str) -> Dict[str, Any]:
    """Process GeoJSON dengan 3 dataset dan generate stats"""
    # Load GeoJSON
    with open(geojson_path, 'r') as f:
        geojson_data = json.load(f)
    
    # Initialize Earth Engine image
    ee_image = get_ktv_datasets()
    
    results = []
    
    for feature in geojson_data['features']:
        try:
            # Get geometry dan properties
            geometry = feature['geometry']
            properties = feature.get('properties', {})
            plot_id = properties.get('plot_id', 'unknown')
            country_name = properties.get('country_name', 'unknown')
            
            # Convert ke EE geometry
            ee_geometry = ee.Geometry(geometry)
            
            # Hitung statistik untuk setiap dataset
            result = {
                'plot_id': plot_id,
                'country_name': country_name
            }
            
            # 1. GFW Loss statistics
            gfw_stats = calculate_loss_stats(ee_image, ee_geometry, 'gfw_loss', [2021, 2022, 2023, 2024])
            result.update(gfw_stats)
            
            # 2. JRC Loss statistics  
            jrc_stats = calculate_loss_stats(ee_image, ee_geometry, 'jrc_loss', [2021, 2022, 2023, 2024])
            result.update(jrc_stats)
            
            # 3. SBTN Loss statistics
            sbtn_stats = calculate_loss_stats(ee_image, ee_geometry, 'sbtn_loss', [2021, 2022, 2023, 2024])
            result.update(sbtn_stats)
            
            # Update geometry
            result['geometry'] = geometry
            
            results.append(result)
            
        except Exception as e:
            print(f"Error processing feature {plot_id}: {e}")
            continue
    
    # Convert ke GeoJSON format
    output_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {k: v for k, v in result.items() if k != 'geometry'},
                "geometry": result['geometry']
            }
            for result in results
        ]
    }
    
    return output_geojson

def calculate_loss_stats(ee_image: ee.Image, geometry: ee.Geometry, dataset_prefix: str, years: List[int]) -> Dict[str, Any]:
    """Hitung statistik loss untuk dataset tertentu"""
    stats = {}
    
    try:
        # Hitung total area polygon
        total_area = geometry.area().divide(10000).getInfo()  # Convert to hectares
        
        # Hitung area loss combined
        combined_band = f'{dataset_prefix}_combined'
        if ee_image.select(combined_band):
            loss_area = ee_image.select(combined_band).reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=geometry,
                scale=30,
                maxPixels=1e9
            ).getInfo()
            
            loss_area_ha = (loss_area.get(combined_band, 0) * 900) / 10000  # Convert pixels to hectares
            loss_percent = (loss_area_ha / total_area * 100) if total_area > 0 else 0
            
            # Determine risk level - jika ada loss area > 0, langsung high
            if loss_area_ha > 0:
                risk_stat = "high"
            else:
                risk_stat = "low"
            
            stats[f'{dataset_prefix}_stat'] = risk_stat
            stats[f'{dataset_prefix}_percent'] = round(loss_percent, 2)
            stats[f'{dataset_prefix}_area'] = round(loss_area_ha, 2)
            
            # Jika tidak ada loss sama sekali, set compilation ke None
            if loss_area_ha <= 0:
                stats[f'{dataset_prefix}_year_compilation'] = None
            else:
                # Cari tahun dengan loss terbanyak
                year_losses = {}
                for year in years:
                    year_band = f'{dataset_prefix}_{year}'
                    try:
                        year_loss = ee_image.select(year_band).reduceRegion(
                            reducer=ee.Reducer.sum(),
                            geometry=geometry,
                            scale=30,
                            maxPixels=1e9
                        ).getInfo()
                        year_losses[year] = year_loss.get(year_band, 0)
                    except:
                        year_losses[year] = 0
                
                # Tahun dengan loss tertinggi, tapi hanya jika ada loss
                years_with_actual_loss = [year for year, loss in year_losses.items() if loss > 0]
                if years_with_actual_loss:
                    max_year = max(years_with_actual_loss, key=lambda k: year_losses[k])
                    stats[f'{dataset_prefix}_year_compilation'] = max_year
                else:
                    stats[f'{dataset_prefix}_year_compilation'] = None
            
        else:
            # Default values jika band tidak ada
            stats[f'{dataset_prefix}_stat'] = "low"
            stats[f'{dataset_prefix}_percent'] = 0
            stats[f'{dataset_prefix}_area'] = 0
            stats[f'{dataset_prefix}_year_compilation'] = None
            
    except Exception as e:
        print(f"Error calculating stats for {dataset_prefix}: {e}")
        # Default values on error
        stats[f'{dataset_prefix}_stat'] = "low"
        stats[f'{dataset_prefix}_percent'] = 0
        stats[f'{dataset_prefix}_area'] = 0
        stats[f'{dataset_prefix}_year_compilation'] = None
    
    return stats