import subprocess
import sys
def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

install('pydantic')
# install('shapely')
install('psycopg2')

import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
import os
import config
import time
from psycopg2.extras import execute_values

class PartnerRequest(BaseModel):
    partner_id: int

DB_HOST = os.getenv('postgisHost')
DB_PORT = os.getenv('postgisPort')
DB_NAME = os.getenv('postgisDatabase')
DB_USER = os.getenv('postgisUsername')
DB_PASSWORD = os.getenv('postgisPassword')

table_p0g = "ktv_dash_ghg_summ_dtl_p0g" #"ktv_dash_eudr_summ_dtl_p0g"
table_deforestation = "gis_int_deforestation"
table_deforestation_tmp = "gis_int_deforestation_tmp"
# table_luc_total = "gis_int_idn_gfw_luc_total_2022" 
table_luc_total = "gis_int_luc_ghg_deforestation" #"gis_int_luc_ghg_deforestation"


def intersect_deforestation(partner_id): #country_id
    # select_country_id = str(country_id).zfill(3)
    
    cursor = conn.cursor()
    # record start time
    start = time.time()
    
    cursor.execute(f"""
        SELECT b.year_def, b.forest_typ, a.supplier_id, a.supplier_display_id, a.farmnr, a.commo_id, a.revision, a.country_id,
        a.province_id, a.district_id, a.total_area, a.row_id, a.geom_polygon,
        ST_Force2D(ST_Union(st_intersection(a.geom_polygon, b.geom))) as geom_intersect,
        ST_Area(ST_Union(st_intersection(a.geom_polygon, b.geom))::geography) / 10000 :: numeric AS area_def,
        CASE
            WHEN ST_Area(a.geom_polygon) ::numeric *100 != 0 THEN
            round(
                ST_Area(ST_Union(st_intersection(a.geom_polygon, b.geom))) :: numeric /
                ST_Area(a.geom_polygon) ::numeric *100
            , 4)
            ELSE 0
        END AS percent_def
        FROM {table_deforestation_tmp} AS a, {table_luc_total} AS b
        WHERE st_intersects(a.geom_polygon, b.geom)
        GROUP by b.year_def, b.forest_typ, a.supplier_id, a.supplier_display_id, a.farmnr, a.commo_id, a.revision, a.country_id,
        a.province_id, a.district_id, a.total_area, a.row_id, a.geom_polygon
    """)

 
    # AND a.country_id = {country_id} AND a.is_processed = 0 
    rowComps = cursor.fetchall()
    
    datap0g = 0
    # Initialize an empty list to store insert
    insert_data = []
    if rowComps:
        for rowComp in rowComps:            
            insert_data.append((rowComp['supplier_id'], rowComp['supplier_display_id'], rowComp['farmnr'], rowComp['commo_id'], rowComp['revision'], 
                    rowComp['country_id'], rowComp['province_id'], rowComp['district_id'], rowComp['total_area'], rowComp['geom_polygon'], 
                    rowComp['geom_intersect'], str(rowComp['year_def'])[:4], rowComp['area_def'], rowComp['percent_def'], rowComp['forest_typ'], rowComp['row_id']))
            datap0g += 1
        # Insert query template
        insert_query = f"""INSERT INTO {table_deforestation} (
                        supplier_id, supplier_display_id, farmnr, commo_id, revision, 
                        country_id, province_id, district_id, total_area, geom_polygon, 
                        geom_intersect, year_def, area_def, percent_def, forest_type, row_id
                    ) VALUES %s"""
                    
        # Execute the query with execute_values
        execute_values(cur, insert_query, insert_data)
        conn.commit()

        print(f"Inserted {len(rowComps)} rows into {table_deforestation} partner_id {partner_id}")
        end = time.time()
                
        # print the difference between start 
        # and end time in seconds
        print("The time of execution is :", ((end-start) * 10**3) / 60000, "m")
    else:
        print(f"Updated 0 rows into {table_deforestation} partner_id {partner_id}")
    
    # get country id from gis_int_deforestation    
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT DISTINCT(country_id) FROM {table_deforestation} ORDER BY country_id DESC"
    )
    
    country_rows = cursor.fetchall()    
    if country_rows:
        for country_row in country_rows:
            calculate_deforestation(partner_id, country_row["country_id"])


def calculate_deforestation(partner_id, country_id):
    # select_country_id = str(country_id).zfill(3)
    
    cursor = conn.cursor()
    # record start time
    start = time.time()

    cursor.execute(f"""
                WITH calculate AS (
            SELECT
                def.id,
                def.area_def,
                def.total_area,
                def.forest_type,
                CASE 
                    WHEN def.forest_type = 'Secondary Forest' THEN 
                        CAST(def.area_def AS NUMERIC) * (
                            SELECT CAST(value AS NUMERIC)
                            FROM parameter_def_forest_biomass
                            WHERE name = 'Secondary'
                            AND biomass = 'Both'
                            AND country_id = {country_id}
                        )
                    WHEN def.forest_type = 'Primary Forest' THEN 
                        CAST(def.area_def AS NUMERIC) * (
                            SELECT CAST(value AS NUMERIC)
                            FROM parameter_def_forest_biomass
                            WHERE name = 'Primary'
                            AND biomass = 'Both'
                            AND country_id = {country_id}
                        )
                    ELSE 0
                END AS gross_co2,
                (
                    (
                        CAST(def.area_def AS NUMERIC) * 
                        CAST(pdb.b AS NUMERIC) * 
                        CAST(pdb.comfi AS NUMERIC) * 
                        CAST(pdb.g_n2o AS NUMERIC)
                    ) * CAST(0.001 AS NUMERIC)
                ) * CAST(pdb.gwp_n2o AS NUMERIC) AS gross_n2o,
                (
                    (
                        CAST(def.area_def AS NUMERIC) * 
                        CAST(pdb.b AS NUMERIC) * 
                        CAST(pdb.comfi AS NUMERIC) * 
                        CAST(pdb.g_ch4 AS NUMERIC)
                    ) * CAST(0.001 AS NUMERIC)
                ) * CAST(pdb.gwp_ch4 AS NUMERIC) AS gross_ch4,
                (
                    CASE 
                        WHEN def.forest_type = 'Secondary Forest' THEN 
                            CAST(def.area_def AS NUMERIC) * (
                                SELECT CAST(value AS NUMERIC)
                                FROM parameter_def_forest_biomass
                                WHERE name = 'Secondary'
                                AND biomass = 'Both'
                                AND country_id = {country_id}
                            )
                        WHEN def.forest_type = 'Primary Forest' THEN 
                            CAST(def.area_def AS NUMERIC) * (
                                SELECT CAST(value AS NUMERIC)
                                FROM parameter_def_forest_biomass
                                WHERE name = 'Primary'
                                AND biomass = 'Both'
                                AND country_id = {country_id}
                            )
                        ELSE 0
                    END
                    +
                    (
                        (
                            CAST(def.area_def AS NUMERIC) * 
                            CAST(pdb.b AS NUMERIC) * 
                            CAST(pdb.comfi AS NUMERIC) * 
                            CAST(pdb.g_n2o AS NUMERIC)
                        ) * CAST(0.001 AS NUMERIC)
                    ) * CAST(pdb.gwp_n2o AS NUMERIC)
                    +
                    (
                        (
                            CAST(def.area_def AS NUMERIC) * 
                            CAST(pdb.b AS NUMERIC) * 
                            CAST(pdb.comfi AS NUMERIC) * 
                            CAST(pdb.g_ch4 AS NUMERIC)
                        ) * CAST(0.001 AS NUMERIC)
                    ) * CAST(pdb.gwp_ch4 AS NUMERIC)
                ) AS total_gross_emission,
                (CAST(def.total_area AS NUMERIC) * (CAST(pdcs.agb AS NUMERIC) + CAST(pdcs.bgb AS NUMERIC))) AS post_carbon_stock,
                (CAST(def.area_def AS NUMERIC) * (CAST(pdcs.agb AS NUMERIC) + CAST(pdcs.bgb AS NUMERIC))) AS post_luc_ccs_with_area_def

            FROM 
                {table_deforestation} AS def
                JOIN parameter_def_burning AS pdb
                    ON (
                        CASE 
                            WHEN def.forest_type = 'Primary Forest'   THEN 'Primary'
                            WHEN def.forest_type = 'Secondary Forest' THEN 'Secondary'
                            ELSE def.forest_type
                        END
                    ) = pdb.forest
                    AND pdb.country_id = {country_id}
                JOIN parameter_def_carbon_stock AS pdcs
                    ON pdcs.id = 3
            WHERE 
                def.geom_intersect IS NOT NULL
        )
        SELECT
            id,
            gross_co2,
            gross_n2o,
            gross_ch4,
            total_gross_emission,
            post_carbon_stock,
            post_luc_ccs_with_area_def,
            area_def,
            forest_type,
            ((gross_co2 + gross_n2o + gross_ch4) + (soc_emission_constant * area_def))
                AS gross_emission_with_soc_cons,
            CASE 
                WHEN area_def != 0 THEN post_luc_ccs_with_area_def / area_def
                ELSE 0
            END AS post_luc_ccs_without_soc_with_hectare,
            CASE 
                WHEN area_def != 0 THEN 
                    (post_luc_ccs_with_area_def / area_def) * total_area
                ELSE 0
            END AS post_luc_ccs_without_soc_with_farm_polygon
        FROM calculate,
        (
            SELECT soc_emission_constant 
            FROM gis_int_def_param_soc_constanta 
            WHERE id = 4
        ) soc_emission_constant;                   
    """)
    
    rows = cursor.fetchall()
        
    update_calculate_data = []
    if rows:
        for row in rows:     
            # row["area_def"],       
            update_calculate_data.append((row["gross_co2"], row["gross_n2o"], row["gross_ch4"], 
                row["total_gross_emission"], row["post_carbon_stock"], row["post_luc_ccs_with_area_def"], 
                row["gross_emission_with_soc_cons"], row["post_luc_ccs_without_soc_with_hectare"], 
                row["post_luc_ccs_without_soc_with_farm_polygon"], row["id"]))

        # SQL query
        sql_update = f"""
            UPDATE {table_deforestation} AS a SET
                gross_co2 = COALESCE(a.gross_co2, data.gross_co2),
                gross_n2o = COALESCE(a.gross_n2o, data.gross_n2o),
                gross_ch4 = COALESCE(a.gross_ch4, data.gross_ch4),
                total_gross_emission = COALESCE(a.total_gross_emission, data.total_gross_emission),
                post_carbon_stock = COALESCE(a.post_carbon_stock, data.post_carbon_stock),
                post_luc_ccs_with_area_def = COALESCE(a.post_luc_ccs_with_area_def, data.post_luc_ccs_with_area_def),
                gross_emission_with_soc_cons = COALESCE(a.gross_emission_with_soc_cons, data.gross_emission_with_soc_cons),
                post_luc_ccs_without_soc_with_hectare = COALESCE(a.post_luc_ccs_without_soc_with_hectare, data.post_luc_ccs_without_soc_with_hectare),
                post_luc_ccs_without_soc_with_farm_polygon = COALESCE(a.post_luc_ccs_without_soc_with_farm_polygon, data.post_luc_ccs_without_soc_with_farm_polygon)
            FROM (VALUES %s) AS data(
                gross_co2, gross_n2o, gross_ch4, total_gross_emission, 
                post_carbon_stock, post_luc_ccs_with_area_def, 
                gross_emission_with_soc_cons, post_luc_ccs_without_soc_with_hectare, 
                post_luc_ccs_without_soc_with_farm_polygon, id
            )
            WHERE a.id = data.id
        """
        # Execute the query with execute_values
        execute_values(cur, sql_update, update_calculate_data)
        conn.commit()

        print(f"Updated {len(rows)} rows into {table_deforestation} partner_id {partner_id}")
        end = time.time()
                
        # print the difference between start 
        # and end time in seconds
        print("The time of execution is :", ((end-start) * 10**3) / 60000, "m")
    else:
        print(f"Updated 0 rows into {table_deforestation} partner_id {partner_id}")

def connect_to_db():
    retries = 5
    while retries > 0:
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                cursor_factory=RealDictCursor,
                connect_timeout=10,  # Timeout in seconds
            )
            return conn
        except psycopg2.OperationalError as error:
            print(f"Connection failed: {error}, retrying in 5 seconds...")
            retries -= 1
            time.sleep(5)
    raise Exception("Could not connect to the database after multiple retries")

if __name__ == "__main__":
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor,
        connect_timeout=10,  # Timeout in seconds
    )
    
    cur = conn.cursor()
    cur.execute(f'TRUNCATE {table_deforestation_tmp} RESTART IDENTITY;')
    cur.execute(f'TRUNCATE {table_deforestation} RESTART IDENTITY;')
    # Commit the transaction
    conn.commit()
    
    #record start time
    start = time.time()

    cur.execute(
        f"""SELECT 
                supplier_id, supplier_display_id, farmnr, commo_id, revision, country_id, province_id, district_id, 
                ST_MakeValid(ST_SetSRID(polygeom, 4326)) AS polygeom, total_area, row_id 
            FROM {table_p0g}
        """
    )
    # where country_id = 10
    rowComps = cur.fetchall()
    datap0g = 0
    # Initialize an empty list to store insert
    insert_data = []
    if rowComps:
        for rowComp in rowComps:            
            insert_data.append((rowComp['supplier_id'], rowComp['supplier_display_id'], rowComp['farmnr'], rowComp['commo_id'], rowComp['revision'], 
                    rowComp['country_id'], rowComp['province_id'], rowComp['district_id'], rowComp['polygeom'], rowComp['total_area'], rowComp['row_id']))
            datap0g += 1
        # Insert query template
        insert_query = f"""INSERT INTO {table_deforestation_tmp} (
                        supplier_id, supplier_display_id, farmnr, commo_id, revision, 
                        country_id, province_id, district_id, geom_polygon, 
                        total_area, row_id
                    ) VALUES %s"""

        # Execute the query with execute_values
        execute_values(cur, insert_query, insert_data)
        conn.commit()

        print(f"Inserted {datap0g} rows into {table_deforestation_tmp}")
        # record end time
        end = time.time()
        print("The time of execution is :", ((end-start) * 10**3) / 60000, "m")
        
        # record start time
        start = time.time()
        
        # SQL query to reindex a table
        reindex_query = f"""REINDEX TABLE {table_deforestation};"""

        # Execute the reindex query
        cur.execute(reindex_query)

        # Commit the transaction
        conn.commit()        
        
        cur.close()
        # record end time
        end = time.time()
        print("Reindexing completed successfully :", ((end-start) * 10**3) / 60000, "m")
        
    # Create a cursor object
    cur = conn.cursor()    
    partner_list = ['161']    
    
    try:
        for partner in partner_list:
            # record start time
            #start = time.time()   
            intersect_deforestation(partner)
            
    except Exception as e:
        # If any error occurs, rollback the transaction
        conn.rollback()
        print(f"An error occurred: {e}")

    finally:
        # Clean up by closing the cursor and connection
        cur.close()
        conn.close()
    