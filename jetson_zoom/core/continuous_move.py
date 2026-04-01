"""Continuous Move Logic for Smooth Camera Control

Implements velocity-based zoom control with safety mechanisms:
- Velocity-controlled movement (0.1 - 1.0)
- Fixed interval-based application (e.g., 500ms)
- Mandatory STOP command after each move
- Queue-based command submission
"""

from typing import Optional
import logging

from jetson_zoom.config import ContinuousMoveConfig
from jetson_zoom.controllers.onvif_client import ONVIFClient, ZoomDirection
from jetson_zoom.logger import get_logger


class ContinuousMover:
    """Manages continuous zoom movement with safety mechanisms.

    Design Principles:
    1. Velocity-based control (smooth movement)
    2. Time-interval execution (e.g., 500ms bursts)
    3. Always STOP after movement (safety)
    4. Non-blocking command submission
    """

    def __init__(
        self,
        onvif_client: ONVIFClient,
        config: ContinuousMoveConfig,
    ) -> None:
        """Initialize continuous mover.

        Args:
            onvif_client: ONVIF client for sending commands
            config: Continuous move configuration
        """
        self.logger = get_logger(self.__class__.__name__)
        self.onvif_client = onvif_client
        self.config = config

        self._current_zoom_level: float = 1.0

    def zoom_in(
        self,
        velocity: Optional[float] = None,
        duration_ms: Optional[int] = None,
    ) -> bool:
        """Queue zoom-in command.

        Args:
            velocity: Zoom velocity (0.1-1.0). Uses config default if None.
            duration_ms: Command duration. Uses config default if None.

        Returns:
            True if command queued successfully
        """
        velocity = velocity or self.config.zoom_velocity
        duration_ms = duration_ms or self.config.move_interval_ms

        self.logger.info(f"Zoom IN: velocity={velocity}, duration={duration_ms}ms")

        success = self.onvif_client.queue_zoom_command(
            direction=ZoomDirection.IN,
            velocity=velocity,
            duration_ms=duration_ms,
        )

        if success:
            # Simulate zoom level update (real implementation would query camera)
            self._current_zoom_level = min(
                self._current_zoom_level * 1.1,
                self.config.zoom_max,
            )

        return success

    def zoom_out(
        self,
        velocity: Optional[float] = None,
        duration_ms: Optional[int] = None,
    ) -> bool:
        """Queue zoom-out command.

        Args:
            velocity: Zoom velocity (0.1-1.0). Uses config default if None.
            duration_ms: Command duration. Uses config default if None.

        Returns:
            True if command queued successfully
        """
        velocity = velocity or self.config.zoom_velocity
        duration_ms = duration_ms or self.config.move_interval_ms

        self.logger.info(f"Zoom OUT: velocity={velocity}, duration={duration_ms}ms")

        success = self.onvif_client.queue_zoom_command(
            direction=ZoomDirection.OUT,
            velocity=velocity,
            duration_ms=duration_ms,
        )

        if success:
            # Simulate zoom level update
            self._current_zoom_level = max(
                self._current_zoom_level / 1.1,
                self.config.zoom_min,
            )

        return success

    def stop_movement(self) -> bool:
        """Queue immediate STOP command.

        Returns:
            True if STOP command queued successfully
        """
        self.logger.info("Movement STOP requested")

        return self.onvif_client.queue_zoom_command(
            direction=ZoomDirection.STOP,
            velocity=0.0,
            duration_ms=0,
        )

    def get_zoom_level(self) -> float:
        """Get current zoom level (simulated).

        In production, this would query the camera for actual zoom position.

        Returns:
            Current zoom level
        """
        return self._current_zoom_level

    def set_zoom_level(self, level: float) -> None:
        """Set zoom level (for simulation/testing).

        Args:
            level: Target zoom level (clamped to min/max)
        """
        self._current_zoom_level = max(
            self.config.zoom_min,
            min(self.config.zoom_max, level),
        )
        self.logger.debug(f"Zoom level set to: {self._current_zoom_level}")
