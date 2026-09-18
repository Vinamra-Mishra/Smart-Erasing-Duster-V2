from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import calibration, camera, perception, planner, reference, replay, simulator, stream, twin, ws
from app.api.stream import FrameStreamer
from app.core.config import AppConfig, get_config, load_config
from app.core.state import AppStateManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def telemetry_broadcast_worker(app: FastAPI) -> None:
    """Periodic telemetry broadcast at ~20 Hz with live perception state."""
    manager: AppStateManager = app.state.manager
    while True:
        try:
            telemetry = manager.get_telemetry()
            telemetry_dict = telemetry.model_dump()
            if hasattr(app.state, "streamer") and app.state.streamer is not None:
                telemetry_dict["fps"] = getattr(app.state.streamer, "measured_fps", 30)
                lp = getattr(app.state.streamer, "_last_perception", None)
                if lp:
                    telemetry_dict["evidence_score"] = lp.get("fused_score_mean", 0.0)
                    telemetry_dict["glare"] = lp.get("glare", False)
                    telemetry_dict["shadow"] = lp.get("shadow", False)
                    telemetry_dict["projector_likelihood"] = lp.get("projector_likelihood", 0.0)
                    telemetry_dict["perception"] = lp
            await manager.event_bus.broadcast_telemetry(telemetry_dict)
            await asyncio.sleep(0.025)  # 40 Hz synced with planner kinematics

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug("Telemetry worker error: %s", e)
            await asyncio.sleep(0.1)


async def rtp_stream_worker(app: FastAPI) -> None:
    """Continuous RTP stream worker at configured FPS (30 fps)."""
    streamer: FrameStreamer = app.state.streamer
    interval = 1.0 / streamer.config.system.fps
    while True:
        try:
            _, jpeg_bytes = streamer.generate_frame()
            streamer.broadcast_rtp(jpeg_bytes)
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug("RTP worker loop error: %s", e)
            await asyncio.sleep(0.1)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Modern lifespan context manager for startup and clean shutdown."""
    logger.info("Initializing Smart Erasing Duster V2.1 Digital Twin Backend...")

    # Ensure state is initialized
    if not hasattr(app.state, "config") or app.state.config is None:
        app.state.config = get_config()
    if not hasattr(app.state, "manager") or app.state.manager is None:
        app.state.manager = AppStateManager(app.state.config)
        app.state.streamer = FrameStreamer(
            app.state.config,
            app.state.manager.twin_store,
            app.state.manager.execution_store,
            manager=app.state.manager,
        )

    config = app.state.config
    manager = app.state.manager
    streamer = app.state.streamer

    # Start Background Worker Tasks
    telemetry_task = asyncio.create_task(telemetry_broadcast_worker(app))
    rtp_task = asyncio.create_task(rtp_stream_worker(app))

    logger.info(
        "Backend initialized. Board: %.0fx%.0f mm, Home Dock: %s, RTP: %s:%d",
        config.system.board_width_mm,
        config.system.board_height_mm,
        config.get_home_dock(),
        config.system.transport.rtp_host,
        config.system.transport.rtp_port,
    )

    yield

    # Clean shutdown
    logger.info("Shutting down background workers and transport channels...")
    telemetry_task.cancel()
    rtp_task.cancel()
    await asyncio.gather(telemetry_task, rtp_task, return_exceptions=True)

    streamer.close()
    await manager.event_bus.close()
    logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    """Application factory for FastAPI prototype."""
    application = FastAPI(
        title="Smart Erasing Duster Digital Twin V2.1",
        version="2.1.0",
        description="High-performance dual-channel Digital Twin backend (RTP + WebSockets)",
        lifespan=lifespan,
    )

    # Pre-populate state for non-lifespan test environments
    config = get_config()
    manager = AppStateManager(config)
    streamer = FrameStreamer(config, manager.twin_store, manager.execution_store, manager=manager)
    application.state.config = config
    application.state.manager = manager
    application.state.streamer = streamer

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register Routers
    application.include_router(camera.router)
    application.include_router(calibration.router)
    application.include_router(perception.router)
    application.include_router(planner.router)
    application.include_router(reference.router)
    application.include_router(replay.router)
    application.include_router(simulator.router)
    application.include_router(twin.router)
    application.include_router(ws.router)

    @application.get("/health", tags=["system"])
    async def health_check():
        return {"status": "ok", "version": "2.1.0"}

    @application.get("/api/config", tags=["system"])
    async def get_system_config():
        cfg: AppConfig = application.state.config
        return {
            "config": cfg.model_dump(),
            "home_dock": cfg.get_home_dock(),
        }

    # Mount static frontend dashboard if built (e.g. in Docker or production)
    static_dirs = [
        Path(__file__).resolve().parent.parent.parent / "frontend" / "out",
        Path("frontend/out"),
        Path("/app/frontend_out"),
        Path("static_frontend"),
    ]
    for s_dir in static_dirs:
        if s_dir.exists() and (s_dir / "index.html").exists():
            from starlette.staticfiles import StaticFiles
            application.mount("/", StaticFiles(directory=str(s_dir), html=True), name="frontend")
            logger.info("Mounted static frontend dashboard from %s", s_dir)
            break

    return application


app = create_app()

