"""JetsonZoom - Main Entry Point (Operational Workflow)

This module implements the complete operational workflow as described in README.md:

Step 1: Activate virtual environment and initialize ONVIF connection
Step 2: Open RTSP stream via GPU Jetson
Step 3: Run event loop for user input
Step 4: When command received, spawn worker thread for control
Step 5: Auto-focus trigger after zoom completes
Step 6: Deactivate environment on exit
"""

import sys
import queue
import signal
from pathlib import Path

from jetson_zoom.logger import get_logger
from jetson_zoom.config import ApplicationConfig
from jetson_zoom.streams.rtsp_handler import RTSPStreamHandler
from jetson_zoom.controllers.onvif_client import ONVIFClient
from jetson_zoom.core.continuous_move import ContinuousMover
from jetson_zoom.core.event_loop import EventLoop


def create_application(config: ApplicationConfig):
    """Factory function to create and wire up all application components.

    Args:
        config: ApplicationConfig instance

    Returns:
        Tuple of (rtsp_handler, onvif_client, continuous_mover, event_loop)
    """
    logger = get_logger("JetsonZoom")

    # Step 1: Initialize frame queue (RTSP producer -> main thread)
    frame_queue = queue.Queue(maxsize=config.streaming.target_fps)

    # Step 2: Create RTSP stream handler (Producer thread)
    logger.info("Step 1/6: Initializing RTSP stream...")
    rtsp_handler = RTSPStreamHandler(
        camera_config=config.camera,
        streaming_config=config.streaming,
        output_queue=frame_queue,
    )
    rtsp_handler.start()

    # Step 3: Initialize command queue (main thread -> ONVIF worker)
    command_queue = queue.Queue(maxsize=10)

    # Step 4: Create ONVIF client (Worker thread)
    logger.info("Step 2/6: Initializing ONVIF controller...")
    onvif_client = ONVIFClient(
        camera_config=config.camera,
        continuous_move_config=config.continuous_move,
        command_queue=command_queue,
    )
    onvif_client.start()

    # Step 5: Create continuous move handler
    logger.info("Step 3/6: Setting up continuous zoom control...")
    continuous_mover = ContinuousMover(
        onvif_client=onvif_client,
        config=config.continuous_move,
    )

    # Step 6: Create event loop (Main thread)
    logger.info("Step 4/6: Creating event loop...")
    event_loop = EventLoop(
        config=config,
        continuous_mover=continuous_mover,
        rtsp_handler=rtsp_handler,
    )

    return rtsp_handler, onvif_client, continuous_mover, event_loop


def main() -> int:
    """Main entry point for JetsonZoom application.

    Workflow:
    1. Load configuration
    2. Create application components
    3. Run event loop
    4. Cleanup on exit

    Returns:
        Exit code (0 = success)
    """
    logger = get_logger("JetsonZoom.main")

    try:
        logger.info("=" * 60)
        logger.info("JetsonZoom v1.0.0 - Realtime Camera Control")
        logger.info("=" * 60)

        # Load configuration from environment
        logger.info("Loading configuration...")
        config = ApplicationConfig.from_env()

        # Create application components
        rtsp_handler, onvif_client, continuous_mover, event_loop = create_application(
            config
        )

        # Setup signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating shutdown...")
            event_loop.stop()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Run main event loop
        logger.info("Step 5/6: Starting event loop...")
        event_loop.run()

        logger.info("Step 6/6: Application shutdown complete")
        logger.info("=" * 60)

        return 0

    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
