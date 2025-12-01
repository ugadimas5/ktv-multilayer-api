import pandas as pd
from loguru import logger


async def map_wdpa_to_grouped_dict(wdpa_dict):
    """Map WDPA results to a grouped dictionary format."""
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

    grouped_dict = {}

    for category, entries in wdpa_dict.items():
        for entry in entries:
            producer_id = entry["producer_id"]
            shipment_id = entry["shipment_id"]
            producer_detail_id = entry["producer_detail_id"]
            supplier_id = entry["supplier_id"]

            # Create a proper composite key for dictionary
            key = (shipment_id, producer_id, producer_detail_id)

            if key not in grouped_dict:
                grouped_dict[key] = {
                    "shipment_id": shipment_id,
                    "supplier_id": supplier_id,
                    "producer_id": producer_id,
                    "producer_detail_id": producer_detail_id,
                    "wdpa_status": entry.get(
                        "wdpa_status", "compliant"
                    ),  # Default to compliant
                    **{col: None for col in wdpa_columns},
                }

            wdpa_column = entry.get("wdpa_column")
            if wdpa_column in wdpa_columns:
                grouped_dict[key][wdpa_column] = 1

            # Override to non_compliant if any entry has that status
            if entry.get("wdpa_status") == "non_compliant":
                grouped_dict[key]["wdpa_status"] = "non_compliant"

    result_list = list(grouped_dict.values())
    result_df = pd.DataFrame(result_list)

    # Log the WDPA non-compliance count
    non_compliant_count = sum(
        1 for item in result_list if item.get("wdpa_status") == "non_compliant"
    )
    logger.info(
        f"WDPA analysis found {non_compliant_count} non-compliant polygons out of {len(result_list)} total"
    )

    return result_df


async def calculate_plot_status(statusdeforestation, statusapprvfarming):
    """Calculate plot status based on deforestation and farming approval statuses."""
    if statusdeforestation == "compliance" and statusapprvfarming == "compliance":
        return "Compliance"
    elif statusdeforestation == "compliance" and statusapprvfarming == "non_compliance":
        return "Non Compliance"
    elif statusdeforestation == "compliance" and statusapprvfarming == "indicative":
        return "Indicative"
    elif statusdeforestation == "non_compliance" and statusapprvfarming == "compliance":
        return "Non Compliance"
    elif (
        statusdeforestation == "non_compliance"
        and statusapprvfarming == "non_compliance"
    ):
        return "Non Compliance"
    elif statusdeforestation == "non_compliance" and statusapprvfarming == "indicative":
        return "Non Compliance"
    else:
        return "Non Compliance"  # Default case if other cases don't match
