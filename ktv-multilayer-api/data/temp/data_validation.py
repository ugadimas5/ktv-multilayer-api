import pandas as pd
from loguru import logger


def validate_database_data(data_list):
    """Validate data before saving to database."""
    validated_list = []

    for item in data_list:
        validated_item = {}

        for key, value in item.items():
            if pd.isna(value):
                if key == "producer_detail_id":
                    logger.warning(f"Skipping item with NaN producer_detail_id: {item}")
                    break

                if key in [
                    "deforestation_status",
                    "land_approve_for_farm",
                    "plot_compliant",
                    "compliant_remarks",
                ]:
                    validated_item[key] = ""
                elif key in ["shipment_id"]:
                    validated_item[key] = str(0)
                else:
                    validated_item[key] = 0
            else:
                if key == "producer_detail_id":
                    # Accept producer_detail_id as is (string or numeric)
                    validated_item[key] = value
                elif key == "supplier_id":
                    try:
                        validated_item[key] = int(value) if not pd.isna(value) else 0
                    except (ValueError, TypeError):
                        validated_item[key] = 0
                else:
                    validated_item[key] = value

        if len(validated_item) == len(item):
            validated_list.append(validated_item)

    logger.info(
        f"Validated {len(validated_list)} of {len(data_list)} items for database save"
    )
    return validated_list
