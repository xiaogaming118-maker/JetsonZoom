"""Configuration management for JetsonZoom."""

from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import json
import os
from dotenv import load_dotenv


@dataclass
class CameraConfig:
    """Camera connection configuration."""

    # Network
    host: str
    port_rtsp: int = 554
    port_onvif: int = 80
    username: str = ""
    password: str = ""

    # RTSP
    rtsp_url: Optional[str] = None
    rtsp_timeout: int = 10

    # ONVIF
    onvif_url: Optional[str] = None
    onvif_timeout: int = 5

    def build_rtsp_url(self) -> str:
        """Build RTSP URL from components.

        Returns:
            Complete RTSP URL
        """
        if self.rtsp_url:
            return self.rtsp_url

        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"rtsp://{auth}{self.host}:{self.port_rtsp}/stream"

    def build_onvif_url(self) -> str:
        """Build ONVIF URL from components.

        Returns:
            Complete ONVIF URL
        """
        if self.onvif_url:
            return self.onvif_url

        return f"http://{self.host}:{self.port_onvif}/onvif/device_service"

    @classmethod
    def from_env(cls) -> "CameraConfig":
        """Load configuration from environment variables.

        Returns:
            CameraConfig instance
        """
        load_dotenv()
        return cls(
            host=os.getenv("CAMERA_HOST", "192.168.1.100"),
            port_rtsp=int(os.getenv("CAMERA_PORT_RTSP", "554")),
            port_onvif=int(os.getenv("CAMERA_PORT_ONVIF", "80")),
            username=os.getenv("CAMERA_USERNAME", ""),
            password=os.getenv("CAMERA_PASSWORD", ""),
            rtsp_url=os.getenv("CAMERA_RTSP_URL"),
            onvif_url=os.getenv("CAMERA_ONVIF_URL"),
        )

    @classmethod
    def from_file(cls, filepath: Path) -> "CameraConfig":
        """Load configuration from JSON file.

        Args:
            filepath: Path to JSON config file

        Returns:
            CameraConfig instance
        """
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)


@dataclass
class StreamingConfig:
    """Streaming and display settings."""

    # Display
    target_fps: int = 30
    display_width: int = 1920
    display_height: int = 1080

    # GStreamer pipeline
    gst_pipeline_template: str = (
        "rtspsrc location={rtsp_url} latency=0 ! "
        "rtph264depay ! h264parse ! nvv4l2decoder ! "
        "nvvidconv ! video/x-raw(memory:NVMM), format=RGBA ! "
        "appsink name=sink emit-signals=true"
    )


@dataclass
class ContinuousMoveConfig:
    """Continuous PTZ move configuration."""

    # Velocity settings (0.1 - 1.0)
    pan_velocity: float = 0.5
    tilt_velocity: float = 0.5
    zoom_velocity: float = 0.5

    # Interval for continuous move (milliseconds)
    move_interval_ms: int = 500
    move_timeout_s: int = 10

    # Zoom specific
    zoom_min: float = 1.0
    zoom_max: float = 30.0


@dataclass
class ApplicationConfig:
    """Main application configuration."""

    camera: CameraConfig
    streaming: StreamingConfig
    continuous_move: ContinuousMoveConfig

    # Threading
    queue_size: int = 100
    producer_thread_name: str = "RTSPProducer"
    worker_thread_pool_size: int = 4

    # Error handling
    max_reconnect_attempts: int = 5
    reconnect_delay_s: int = 2

    @classmethod
    def from_env(cls) -> "ApplicationConfig":
        """Load full application config from environment.

        Returns:
            ApplicationConfig instance
        """
        return cls(
            camera=CameraConfig.from_env(),
            streaming=StreamingConfig(),
            continuous_move=ContinuousMoveConfig(),
        )
