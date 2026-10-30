import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from app.logging_utils import log_event


WORKBENCH_BUILD_DIRECTORY = Path(__file__).resolve().parents[2] / "web" / "dist"
logger = logging.getLogger("support_copilot.workbench")


def mount_workbench(
    app: FastAPI,
    *,
    build_directory: Path = WORKBENCH_BUILD_DIRECTORY,
) -> None:
    if (build_directory / "index.html").is_file():
        app.mount(
            "/workbench",
            StaticFiles(directory=build_directory, html=True),
            name="workbench",
        )
        return

    @app.get("/workbench/{asset_path:path}", include_in_schema=False)
    def workbench_unavailable(asset_path: str) -> None:
        log_event(
            logger,
            "workbench_assets_unavailable",
            build_directory=str(build_directory),
            requested_path=asset_path,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Workbench assets are not built. Run npm ci and npm run build "
                "in services/web, then restart the API; or rebuild the API image."
            ),
        )
