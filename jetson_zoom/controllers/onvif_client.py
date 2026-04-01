"""ONVIF Client - Worker Thread for Camera Control"""

import threading
import queue
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable
import logging

try:
    from zeep import Client
    from zeep.wsse.username import UsernameToken
except ImportError as e:
    raise ImportError("zeep library not found. Install with: pip install zeep") from e

from jetson_zoom.config import CameraConfig, ContinuousMoveConfig
from jetson_zoom.logger import get_logger


class ZoomDirection(Enum):
    """Zoom direction enumeration."""

    IN = 1.0
    OUT = -1.0
    STOP = 0.0


@dataclass
class MoveCommand:
    """PTZ/Zoom movement command."""

    direction: ZoomDirection
    velocity: float  # 0.1 - 1.0
    duration_ms: int = 500  # How long to apply movement


class ONVIFClient(threading.Thread):
    """Worker thread: Executes ONVIF/SOAP commands for camera control.

    Architecture:
    - Runs in daemon thread pool
    - Handles continuous move logic (velocity-based control)
    - Implements safety: always sends STOP after movement
    - Non-blocking command queue processing

    Workflow:
    1. Receive move command from queue
    2. Send velocity command to camera (SOAP)
    3. Wait for specified interval
    4. Send STOP command
    5. Ready for next command
    """

    def __init__(
        self,
        camera_config: CameraConfig,
        continuous_move_config: ContinuousMoveConfig,
        command_queue: queue.Queue,
        error_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Initialize ONVIF client.

        Args:
            camera_config: Camera connection settings
            continuous_move_config: Zoom movement parameters
            command_queue: Queue to receive movement commands
            error_callback: Optional callback for error messages
        """
        super().__init__(name="ONVIFClient", daemon=True)

        self.logger = get_logger(self.__class__.__name__)
        self.camera_config = camera_config
        self.continuous_move_config = continuous_move_config
        self.command_queue = command_queue
        self.error_callback = error_callback

        self._stop_event = threading.Event()
        self._client: Optional[Client] = None
        self._profile_token: Optional[str] = None

    def run(self) -> None:
        """Main thread execution: process ONVIF commands from queue."""
        try:
            self._connect_onvif()
            self.logger.info("ONVIF client initialized")

            while not self._stop_event.is_set():
                try:
                    # Non-blocking get with timeout
                    command = self.command_queue.get(timeout=1.0)
                    self._execute_move_command(command)
                except queue.Empty:
                    continue
                except Exception as e:
                    error_msg = f"Command execution error: {e}"
                    self.logger.error(error_msg, exc_info=True)
                    if self.error_callback:
                        self.error_callback(error_msg)

        except Exception as e:
            error_msg = f"ONVIF client error: {e}"
            self.logger.error(error_msg, exc_info=True)
            if self.error_callback:
                self.error_callback(error_msg)
        finally:
            self._cleanup()

    def _connect_onvif(self) -> None:
        """Establish ONVIF connection and get device profile.

        Raises:
            RuntimeError: If connection or profile retrieval fails
        """
        try:
            onvif_url = self.camera_config.build_onvif_url()
            self.logger.debug(f"Connecting to ONVIF: {onvif_url}")

            # Create SOAP client with authentication
            wsse = None
            if self.camera_config.username:
                wsse = UsernameToken(
                    self.camera_config.username,
                    self.camera_config.password,
                )

            self._client = Client(
                wsdl=onvif_url,
                wsse=wsse,
                settings=None,
            )

            # Get first PTZ profile token
            self._profile_token = self._get_ptz_profile()
            if not self._profile_token:
                raise RuntimeError("No PTZ profile found on camera")

            self.logger.info(f"ONVIF connected. Profile: {self._profile_token}")

        except Exception as e:
            raise RuntimeError(f"ONVIF connection failed: {e}") from e

    def _get_ptz_profile(self) -> Optional[str]:
        """Retrieve camera profile token for PTZ operations.

        Returns:
            Profile token string, or None if not found
        """
        try:
            # Simplified: assumes first available PTZ profile
            # Production code should validate PTZ capabilities
            return "default_profile"
        except Exception as e:
            self.logger.warning(f"Could not retrieve profile: {e}")
            return None

    def _execute_move_command(self, command: MoveCommand) -> None:
        """Execute a continuous move command with timeout.

        Workflow:
        1. Send velocity command
        2. Wait for specified duration
        3. Send STOP command
        4. Log completion

        Args:
            command: MoveCommand with direction and duration
        """
        self.logger.debug(f"Executing move command: {command}")

        try:
            # Clamp velocity to valid range
            velocity = max(0.1, min(1.0, command.velocity))

            # Send continuous move command
            direction_value = command.direction.value
            self._send_continuous_move(velocity * direction_value)

            # Wait for specified interval
            time.sleep(command.duration_ms / 1000.0)

            # Always send STOP to prevent motor runaway
            self._send_stop()

            self.logger.debug(f"Move command completed: {command.direction.name}")

        except Exception as e:
            self.logger.error(f"Move command failed: {e}", exc_info=True)
            # Attempt emergency stop
            try:
                self._send_stop()
            except Exception as stop_error:
                self.logger.error(f"Emergency stop failed: {stop_error}")

    def _send_continuous_move(self, velocity: float) -> None:
        """Send continuous move command to camera via ONVIF.

        This is a simplified implementation. Production code should:
        - Handle different camera models (different SOAP namespaces)
        - Validate velocity ranges
        - Implement retry logic with exponential backoff

        Args:
            velocity: Velocity value (typically -1.0 to 1.0)
        """
        if not self._client:
            raise RuntimeError("ONVIF client not initialized")

        # Simplified SOAP call structure
        # Real implementation depends on camera's WSDL definition
        self.logger.debug(f"Sending zoom command with velocity: {velocity}")

        # In real implementation:
        # self._client.service.ContinuousMove(
        #     ProfileToken=self._profile_token,
        #     Velocity={"Zoom": velocity}
        # )

    def _send_stop(self) -> None:
        """Send STOP command to halt all movement.

        Critical for safety: prevents motor from overshooting
        """
        if not self._client:
            raise RuntimeError("ONVIF client not initialized")

        self.logger.debug("Sending STOP command")

        # In real implementation:
        # self._client.service.Stop(ProfileToken=self._profile_token)

    def queue_zoom_command(
        self,
        direction: ZoomDirection,
        velocity: Optional[float] = None,
        duration_ms: int = 500,
    ) -> bool:
        """Queue a zoom command for execution.

        Args:
            direction: Zoom direction (IN/OUT/STOP)
            velocity: Velocity (0.1-1.0). Uses config default if None
            duration_ms: How long to apply command

        Returns:
            True if command queued successfully, False if queue is full
        """
        if velocity is None:
            velocity = self.continuous_move_config.zoom_velocity

        command = MoveCommand(
            direction=direction,
            velocity=velocity,
            duration_ms=duration_ms,
        )

        try:
            self.command_queue.put_nowait(command)
            self.logger.debug(f"Zoom command queued: {command}")
            return True
        except queue.Full:
            self.logger.warning("Command queue full, command dropped")
            return False

    def stop(self) -> None:
        """Stop the client gracefully."""
        self.logger.info("Stopping ONVIF client...")
        self._stop_event.set()

    def _cleanup(self) -> None:
        """Clean up ONVIF resources."""
        try:
            if self._client:
                self._send_stop()
        except Exception as e:
            self.logger.warning(f"Error during cleanup: {e}")
