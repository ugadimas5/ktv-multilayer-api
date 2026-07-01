"""
Shared Earth Engine initialization helper.

Attributes Earth Engine compute (including tile EECU and workload tags) to the
Cloud project named in GOOGLE_CLOUD_PROJECT_ID, so usage shows up in THAT
project's Cloud Monitoring / Metrics Explorer.

If the configured project can't be used yet — e.g. the service account hasn't
been granted `serviceusage.services.use` (roles/serviceusage.serviceUsageConsumer)
plus an Earth Engine role on it — we fall back to a project-less ("legacy")
init so tile serving keeps working. Only the per-project EECU / workload_tag
metrics are unavailable until that IAM grant is in place.
"""

import os

import ee
from loguru import logger


def initialize_ee(credentials) -> str:
    """Initialize Earth Engine; return the project actually used ("" if legacy)."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT_ID") or None

    if project:
        try:
            ee.Initialize(credentials, project=project)
            logger.success(f"Earth Engine initialized (project={project})")
            return project
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"Could not initialize Earth Engine under project '{project}': {e}. "
                "Falling back to legacy (no project). EECU / workload_tag metrics "
                f"will NOT appear under '{project}' until its service account is granted "
                "roles/serviceusage.serviceUsageConsumer and an Earth Engine role."
            )
            # A failed project init leaves the bad project in EE's global state.
            # ee.Reset() alone does NOT clear it, so the legacy fallback below
            # would keep hitting the forbidden project — clear it explicitly.
            if hasattr(ee, "Reset"):
                ee.Reset()
            try:
                ee.data._cloud_api_user_project = None
            except Exception:  # noqa: BLE001
                pass

    ee.Initialize(credentials)
    logger.success("Earth Engine initialized (legacy / no Cloud project)")
    return ""
