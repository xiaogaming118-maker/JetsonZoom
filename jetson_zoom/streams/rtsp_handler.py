"""RTSP Stream Handler - Producer Thread

Handles RTSP stream acquisition using GStreamer pipeline with hardware acceleration
(NVDEC on Jetson). Runs in a separate thread to decouple video capture from main UI.
"""

import threading
import queue
import time
from dataclasses import dataclass
from typing import Optional, Callable
import logging

try:
    import gi
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst, GLib
except (ImportError, ValueError) as e:
    raise ImportError(
        "GStreamer bindings not found. Install with: "
        "sudo apt-get install python3-gi gir1.2-gstreamer-1.0 on Jetson"
    ) from e

from jetson_zoom.config import StreamingConfig, CameraConfig
from jetson_zoom.logger import get_logger


@dataclass
class VideoFrame:
    """Represents a single video frame."""

    timestamp: float
    width: int
    height: int
    buffer: bytes

    def __repr__(self) -> str:
        return f"VideoFrame(ts={self.timestamp:.2f}s, {self.width}x{self.height})"


class RTSPStreamHandler(threading.Thread):
    """Producer thread: Acquires RTSP stream and pushes frames to queue.

    Architecture:
    - Runs in separate thread (daemon mode)
    - Uses GStreamer pipeline with NVIDIA hardware acceleration (NVDEC)
    - Implements non-blocking frame push to output queue
    - Provides status monitoring and error handling

    Attributes:
        daemon: Set to True to run as background thread
    """

    def __init__(
        self,
        camera_config: CameraConfig,
        streaming_config: StreamingConfig,
        output_queue: queue.Queue,
        error_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Initialize RTSP stream handler.

        Args:
            camera_config: Camera connection settings
            streaming_config: Streaming pipeline settings
            output_queue: Queue to push decoded frames
            error_callback: Optional callback for error messages
        """
        super().__init__(name="RTSPProducer", daemon=True)

        self.logger = get_logger(self.__class__.__name__)
        self.camera_config = camera_config
        self.streaming_config = streaming_config
        self.output_queue = output_queue
        self.error_callback = error_callback

        self._stop_event = threading.Event()
        self._pipeline: Optional[object] = None
        self._main_loop: Optional[object] = None

        # Performance tracking
        self._frame_count = 0
        self._start_time = time.time()

    def run(self) -> None:
        """Main thread execution: setup GStreamer pipeline and process stream.

        This method:
        1. Initializes GStreamer
        2. Creates hardware-accelerated pipeline
        3. Starts event loop
        4. Handles cleanup on stop
        """
        try:
            Gst.init(None)
            self.logger.info("GStreamer initialized")

            self._create_pipeline()
            self._start_pipeline()

            self._main_loop = GLib.MainLoop()
            self.logger.info(f"RTSP stream started: {self.camera_config.build_rtsp_url()}")

            self._main_loop.run()

        except Exception as e:
            error_msg = f"RTSP stream error: {e}"
            self.logger.error(error_msg, exc_info=True)
            if self.error_callback:
                self.error_callback(error_msg)
        finally:
            self._cleanup()

    def _create_pipeline(self) -> None:
        """Create GStreamer pipeline with hardware acceleration.

        Pipeline structure:
        rtspsrc (network) -> rtph264depay -> h264parse -> nvv4l2decoder (GPU) ->
        nvvidconv -> appsink (Python queue)

        This ensures:
        - Network I/O doesn't block file system
        - H.264 decoding offloaded to NVIDIA hardware
        - Format conversion done on GPU
        - Minimal CPU usage
        """
        rtsp_url = self.camera_config.build_rtsp_url()

        pipeline_str = self.streaming_config.gst_pipeline_template.format(
            rtsp_url=rtsp_url
        )

        self.logger.debug(f"Pipeline: {pipeline_str}")

        try:
            self._pipeline = Gst.parse_launch(pipeline_str)
        except Exception as e:
            raise RuntimeError(f"Failed to create GStreamer pipeline: {e}") from e

        # Connect to appsink signals
        appsink = self._pipeline.get_by_name("sink")
        if appsink:
            appsink.connect("new-sample", self._on_new_sample)
            self.logger.debug("AppSink connected to signal handler")

    def _start_pipeline(self) -> None:
        """Start the GStreamer pipeline."""
        if not self._pipeline:
            raise RuntimeError("Pipeline not created")

        state_change = self._pipeline.set_state(Gst.State.PLAYING)
        if state_change == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("Failed to start pipeline")

        self.logger.info("GStreamer pipeline started")

    def _on_new_sample(self, appsink: object) -> int:
        """Callback when new frame is available from sink.

        Args:
            appsink: GStreamer appsink element

        Returns:
            Gst.FlowReturn.OK on success
        """
        try:
            sample = appsink.emit("pull-sample")
            if sample is None:
                return Gst.FlowReturn.OK

            buffer = sample.get_buffer()
            caps = sample.get_caps()

            # Extract resolution from caps
            width, height = self._extract_resolution(caps)

            # Convert buffer to bytes
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                return Gst.FlowReturn.OK

            try:
                frame_data = bytes(map_info.data)

                frame = VideoFrame(
                    timestamp=time.time(),
                    width=width,
                    height=height,
                    buffer=frame_data,
                )

                # Non-blocking push: drop frame if queue is full
                try:
                    self.output_queue.put_nowait(frame)
                    self._frame_count += 1
                except queue.Full:
                    self.logger.warning("Output queue full, frame dropped")

                return Gst.FlowReturn.OK

            finally:
                buffer.unmap(map_info)

        except Exception as e:
            self.logger.error(f"Error processing sample: {e}", exc_info=True)
            return Gst.FlowReturn.ERROR

    @staticmethod
    def _extract_resolution(caps: object) -> tuple[int, int]:
        """Extract width and height from GStreamer caps.

        Args:
            caps: GStreamer capabilities object

        Returns:
            Tuple of (width, height)
        """
        try:
            struct = caps.get_structure(0)
            width = struct.get_int("width")[1]
            height = struct.get_int("height")[1]
            return width, height
        except Exception as e:
            logging.warning(f"Could not extract resolution: {e}")
            return 1920, 1080  # Default fallback

    def stop(self) -> None:
        """Stop the stream handler gracefully."""
        self.logger.info("Stopping RTSP stream...")
        self._stop_event.set()

        if self._main_loop:
            self._main_loop.quit()

    def _cleanup(self) -> None:
        """Clean up GStreamer resources."""
        if self._pipeline:
            self._pipeline.set_state(Gst.State.NULL)

        # Calculate and log performance metrics
        elapsed = time.time() - self._start_time
        if elapsed > 0:
            fps = self._frame_count / elapsed
            self.logger.info(
                f"Stream stopped - Frames: {self._frame_count}, "
                f"Avg FPS: {fps:.1f}, Duration: {elapsed:.1f}s"
            )

    def get_stats(self) -> dict:
        """Get current stream statistics.

        Returns:
            Dictionary with performance metrics
        """
        elapsed = time.time() - self._start_time
        return {
            "frame_count": self._frame_count,
            "elapsed_seconds": elapsed,
            "avg_fps": self._frame_count / elapsed if elapsed > 0 else 0,
            "queue_size": self.output_queue.qsize(),
        }
