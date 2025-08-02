# import sys
import os

# sys.path.insert(0, "/services/whisp_main/src")
import json
import ee
from dotenv import load_dotenv

from services.whisp_main.src.openforis_whisp.data_conversion import (
    convert_df_to_geojson,
)
from services.whisp_main.src.openforis_whisp.risk import whisp_risk
from services.whisp_main.src.openforis_whisp.stats import (
    whisp_formatted_stats_geojson_to_df,
)

from config.config_loader import ConfigLoader
from loguru import logger

cfg = ConfigLoader().get_app_config()


# Tambahkan ini untuk load .env dari root project
load_dotenv(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
)


# Inisialisasi Earth Engine dengan service account (jika pakai file JSON)
def authenticate_ee_with_service_account(
    service_account_path: str, print_status: bool = True
):
    """
    Initialize Earth Engine using a service account key file path.
    Args:
        service_account_path: Full path to the service account JSON key file
        print_status: Whether to print authentication status messages
    Raises:
        FileNotFoundError: If the service account key file doesn't exist
        ValueError: If the key file contains invalid JSON or authentication fails
    """
    if print_status:
        logger.info(
            f"Authenticating with Earth Engine using service account at '{service_account_path}'"
        )
    if not os.path.exists(service_account_path):
        raise FileNotFoundError(
            f"Service account key file not found at {service_account_path}"
        )
    try:
        with open(service_account_path) as f:
            credentials = json.load(f)
            email = credentials.get("client_email")
        if not email:
            raise ValueError(
                f"No client_email found in key file {service_account_path}"
            )
        ee.Initialize(ee.ServiceAccountCredentials(email, service_account_path))
        if print_status:
            logger.success(
                f"Successfully authenticated with Earth Engine using service account: {email}"
            )
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON in key file at {service_account_path}")
    except ee.EEException as e:
        raise ValueError(f"Failed to authenticate with Earth Engine: {e}")


authenticate_ee_with_service_account(cfg["ee_service_account_path"])


def process_geojson(input_geojson_path):
    # 1. Baca GeoJSON dan konversi ke DataFrame dengan kolom 'geo'
    with open(input_geojson_path) as f:
        gj = json.load(f)
    features = gj["features"]
    rows = []
    for feat in features:
        row = feat.get("properties", {}).copy()
        row["geo"] = json.dumps(feat["geometry"])  # simpan geometry sebagai string
        rows.append(row)
    import pandas as pd

    df = pd.DataFrame(rows)

    print("==== DEBUG DATAFRAME ====")
    print(df.head())
    print(df.columns)
    print(df.shape)
    print("==== END DEBUG ====")

    # 2. Tambahkan statistik/risiko (aktifkan baris berikut)
    df = whisp_formatted_stats_geojson_to_df(input_geojson_path)
    df = whisp_risk(df)

    # 3. Simpan ke GeoJSON
    output_geojson_path = os.path.join(os.path.dirname(__file__), "output.geojson")
    convert_df_to_geojson(df, output_geojson_path, geo_column="geo")
    logger.info(f"GeoJSON saved to {output_geojson_path}")

    # 4. (Opsional) Kembalikan hasil sebagai dict untuk response API
    with open(output_geojson_path) as f:
        return json.load(f)


# if __name__ == "__main__":
#     process_geojson("geojson_example.geojson")
