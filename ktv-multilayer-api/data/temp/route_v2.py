from typing import Any, Dict

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
)

from services.data.spatial_reader_service import SpatialReaderService

routerv2 = APIRouter()

spatial_reader_service = SpatialReaderService()

@routerv2.post("/validate_geometry", tags=["Spatial Processing"])
async def validate_geojson_by_query(
    data: Dict[str, Any] = Body(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    try:
        background_tasks.add_task(
            spatial_reader_service.validate_geojson_v2,
            data,
        )
        return {
            "status": "Data sent successfully",
        }

    except Exception as e:
        return {"error": str(e)}
