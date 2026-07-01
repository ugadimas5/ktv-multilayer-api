"""
Earth Engine workload tags for the GEE tile services.

A workload tag labels every Earth Engine request issued inside its context so
that EECU usage can be broken down per tile service in Cloud Monitoring /
Metrics Explorer. Earth Engine metrics (e.g. earthengine.googleapis.com/...)
expose a `workload_tag` label you can group/filter by.

Docs: https://developers.google.com/earth-engine/guides/usage#workload-tags

Tag values must be 1-63 characters, lowercase letters, digits and dashes,
beginning and ending with an alphanumeric character.
"""

import contextlib

import ee
from loguru import logger

# One tag per tile service so each can be isolated in Metrics Explorer.
# The shared "multilayer-tiles-" prefix also lets you aggregate across services.
TILE_DATASET = "multilayer-tiles-dataset"
TILE_FLOOD = "multilayer-tiles-flood"
TILE_COMMODITY = "multilayer-tiles-commodity"
TILE_LANDSLIDE = "multilayer-tiles-landslide"
TILE_INTERSECTION = "multilayer-tiles-intersection"
COMMODITY_ANALYSIS = "multilayer-commodity-analysis"


@contextlib.contextmanager
def workload_tag(tag: str):
    """Tag every Earth Engine request issued inside this block.

    Use it around tile-generating calls (getMapId) so the resulting EECU usage
    shows up under `tag` in Metrics Explorer::

        with workload_tag(TILE_FLOOD):
            map_id = image.getMapId(vis_params)

    Degrades to a no-op on earthengine-api versions that predate workload tags
    so tile serving never breaks because of monitoring instrumentation.
    """
    ctx = getattr(ee.data, "workloadTagContext", None)
    if ctx is None:
        logger.debug(
            "earthengine-api has no workloadTagContext; "
            f"skipping workload tag '{tag}'"
        )
        yield
        return

    with ctx(tag):
        yield
