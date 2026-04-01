# JetsonZoom - Quick Start Guide

## 5-Minute Setup

### 1. Clone & Initialize
```bash
cd JetsonZoom
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Camera
```bash
cp .env.example .env
# Edit .env with your camera IP/credentials
nano .env
```

**Example .env:**
```bash
CAMERA_HOST=192.168.1.70
CAMERA_USERNAME=admin
CAMERA_PASSWORD=12345
```

### 3. Run Application
```bash
python -m jetson_zoom
```

You should see:
```
2026-04-01 12:00:00 [INFO] JetsonZoom v1.0.0 - Realtime Camera Control
2026-04-01 12:00:00 [INFO] Step 1/6: Initializing RTSP stream...
2026-04-01 12:00:00 [INFO] Step 2/6: Initializing ONVIF controller...
2026-04-01 12:00:00 [INFO] Step 3/6: Setting up continuous zoom control...
2026-04-01 12:00:00 [INFO] Step 4/6: Creating event loop...
2026-04-01 12:00:00 [INFO] Step 5/6: Starting event loop...
```

## Keyboard Controls

| Key | Action |
|-----|--------|
| `i` | Zoom In |
| `o` | Zoom Out |
| `s` | Stop Movement |
| `q` | Quit |

## Understanding the Output

### Log Levels
- **INFO** (🟢): Normal operation steps
- **DEBUG** (🔵): Detailed internals (high frequency)
- **WARNING** (🟡): Frame drops, queue full, etc.
- **ERROR** (🔴): Connection failures, timeouts

### Performance Metrics
Logged every 10 seconds:
```
[INFO] Metrics - FPS: 29.8, Displayed: 300, Dropped: 0 (0.0%), Elapsed: 10.1s
```

**What to watch:**
- `FPS: 29.8` → Should match target (30 FPS in this case)
- `Dropped: 0` → 0 frames lost (good)
- Drop rate `> 5%` → Network congestion or slow camera

## File Structure for Users

```
jetson_zoom/
├── streams/rtsp_handler.py        ← RTSP pull
├── controllers/onvif_client.py    ← Zoom commands
├── core/event_loop.py             ← Main thread
├── config.py                      ← Configuration
└── logger.py                      ← Logging
```

Each module is self-contained:
- Can be tested independently
- Can be extended/customized
- Has full type hints for IDE support

## Common Issues

### Issue 1: "GStreamer bindings not found"
**Solution:**
```bash
sudo apt-get install python3-gi gir1.2-gstreamer-1.0
# Or use --system-site-packages when creating venv
```

### Issue 2: "ONVIF connection failed"
**Check:**
1. Camera IP address is correct
2. Camera is on same network
3. Username/password are correct
4. Camera supports ONVIF (check manual)

**Debug:**
```bash
# Test camera connectivity
ping 192.168.1.70

# Check ONVIF endpoint
curl http://192.168.1.70/onvif/device_service -v
```

### Issue 3: "Frame queue full" warnings
**Cause:** Network congestion or slow camera
**Solution:**
- Reduce target FPS in config (30 → 24)
- Check network bandwidth
- Move closer to WiFi router (if wireless)

### Issue 4: High dropped frame rate
**Check in log:**
```
[WARNING] Output queue full, frame dropped
```

**Solutions:**
1. Reduce resolution in config
2. Reduce framerate
3. Check for CPU-heavy background tasks

## Testing Without Camera

### Run Examples
```bash
python -m examples.demo
```

Shows:
- Configuration loading
- Queue synchronization
- Thread creation
- Error handling patterns

### Mock Mode (future)
```python
# In dev branch:
from jetson_zoom.mock import MockCamera

config.camera.mock = True
# Tests all logic without real camera
```

## Code Structure for Developers

### Adding Custom Zoom Velocity
**File:** `.env`
```bash
ZOOM_VELOCITY=0.7  # Default 0.5
```

Or **programmatically:**
```python
config = ApplicationConfig.from_env()
config.continuous_move.zoom_velocity = 0.7
```

### Custom Event Handling
```python
from jetson_zoom.core.event_loop import EventHandler

class MyHandler(EventHandler):
    def on_key_press(self, key):
        if key == "1":
            mover.zoom_in(velocity=0.3)
        elif key == "2":
            mover.zoom_out(velocity=0.3)
    
    def on_frame_received(self, frame):
        # Custom processing
        pass

# Use it:
event_loop = EventLoop(config, mover, rtsp_handler, MyHandler())
```

### Custom Error Handling
```python
def on_error(msg: str):
    print(f"⚠️ {msg}")
    # Send alert, log to file, etc.

rtsp = RTSPStreamHandler(
    camera_config=config.camera,
    streaming_config=config.streaming,
    output_queue=queue.Queue(),
    error_callback=on_error
)
```

## Performance Tips

### 1. Target FPS
```python
config.streaming.target_fps = 24  # Save 20% CPU vs 30
```

### 2. Zoom Speed
```python
config.continuous_move.move_interval_ms = 300  # Faster zooms
config.continuous_move.zoom_velocity = 0.7     # Higher velocity
```

### 3. Queue Sizes
```python
config.streaming.queue_size = 60  # Buffer more = smoother but higher latency
```

## Next Steps

1. **Read DESIGN.md**: Understand architecture (thread model, queues)
2. **Read IMPLEMENTATION.md**: See code organization & patterns
3. **Check examples/demo.py**: Practical usage examples
4. **Customize**: Replace EventHandler with your GUI framework

## Integration with GUI

### PyQt5 Integration Example
```python
from PyQt5.QtCore import QTimer
from jetson_zoom.core.event_loop import EventHandler

class PyQt5Handler(EventHandler, QWidget):
    def on_key_press(self, key):
        # Route to mover
        pass
    
    def on_frame_received(self, frame):
        # Render to QLabel with QPixmap
        pixmap = QPixmap.fromImage(...)
        self.label.setPixmap(pixmap)

# Create timer to call event_loop._process_frame
timer = QTimer()
timer.timeout.connect(lambda: event_loop._process_frame())
```

### OpenCV Integration Example
```python
import cv2

window_name = "JetsonZoom"
cv2.namedWindow(window_name)

while loop_running:
    frame = rtsp_queue.get(timeout=0.01)
    if frame:
        # Convert frame to numpy for OpenCV
        cv2.imshow(window_name, frame.buffer)
        
        key = cv2.waitKey(10) & 0xFF
        if key == ord('i'):
            mover.zoom_in()
```

## Getting Help

### Check Logs
Most issues logged with full traceback:
```bash
# View real-time logs
python -m jetson_zoom 2>&1 | grep ERROR

# Save to file
python -m jetson_zoom > app.log 2>&1
```

### Debug Mode
Code has logging at DEBUG level (change in logger.py):
```python
logger = get_logger(__name__, level=logging.DEBUG)
```

### Common Debug Checks
```python
# In Python REPL:
from jetson_zoom.config import ApplicationConfig

config = ApplicationConfig.from_env()
print(f"Camera: {config.camera.build_rtsp_url()}")
print(f"ONVIF: {config.camera.build_onvif_url()}")
```

---

**Status**: ✅ Production-ready framework | 🔧 Custom integration needed for GUI
