# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a local AI video monitoring system that:
- Connects to RTSP camera streams
- Detects people and vehicles using YOLOv8
- Tracks objects with persistent IDs
- Captures snapshots when detections occur
- Performs license plate recognition with OCR
- Logs all events to CSV files
- Uses Apple Metal (MPS) for GPU acceleration on Mac

## Architecture

### camera_persone.py
Single-file application for person detection with video recording:

**Initialization (lines 1-42):**
- Loads YOLOv8 nano model from `yolov8n.pt`
- Opens RTSP stream from configured IP address
- Exits if stream fails to open
- Config: FRAME_SIZE (640x360), TARGET_FPS (10), FRAME_SKIP (2), PERSON_ABSENT_GRACE (2s), LOG_COOLDOWN (5s)

**State Variables (lines 114-122):**
- `frame_id`: Counter for frame tracking
- `video_writer`: OpenCV VideoWriter for recording
- `current_filename`: Path to current recording
- `first_frame_of_session`: First frame for snapshot
- `last_seen_person`: Timestamp of last person detection
- `last_log_time`: Cooldown for logging
- `is_recording`: Boolean flag for recording state

**Main Loop (lines 127-200):**
1. Reads frame from RTSP stream
2. Reconnects if stream fails (lines 131-138)
3. Resizes frame to 640x360 for inference (line 140)
4. Runs YOLO inference every 2nd frame (FRAME_SKIP=2) (line 144)
5. Detects "person" class (lines 150-154)
6. Starts recording when person detected (lines 167-171)
7. Stops recording after PERSON_ABSENT_GRACE seconds (lines 175-181)
8. Writes all frames to video (line 185)
9. Displays REC/LIVE indicator (lines 189-195)
10. Captures snapshot on close and sends to Telegram (lines 94, 207)

### camera_targhe.py
Advanced vehicle tracking and license plate recognition:

**Configuration (lines 14-26):**
- Device selection: MPS for Mac GPU or CPU
- RTSP URL configuration
- Save directory and log file paths
- Vehicle timeout (30s) and max OCR attempts (10)
- Loads vehicle detection model (`yolov8n.pt`)
- Loads plate detection model (`yolov8n_plate.pt`)
- Loads OCR model (`LicensePlateRecognizer` with `cct-xs-v2-global-model`)

**RTSPStreamer Class (lines 36-87):**
- Threaded RTSP stream for non-blocking video feed
- Automatic reconnection on stream failure
- Thread-safe frame access with locks
- Background update loop with `update()` method
- `read()` method to get latest frame
- `stop()` method for graceful shutdown

**Utility Functions (lines 91-103):**
- `get_daily_dir()`: Creates date-based subdirectory for saved plates
- `log_evento()`: Writes events to CSV (ENTRATA/USCITA/TARGA_RILEVATA)

**Signal Handler (lines 108-115):**
- Safe Ctrl+C handler that stops stream and cleans up resources

**Main Loop (lines 120-270):**
1. Reads frame from RTSP stream (threaded)
2. Tracks vehicles with persistent IDs using `model_veicoli.track()`
3. Detects vehicle classes: car (2), motorcycle (3), van (5), bus (7)
4. For each tracked vehicle:
   - Records check-in on first detection
   - Extracts ROI for plate detection
   - Runs plate detection model on ROI
   - Crops plate region with padding
   - Runs OCR on saved plate image
   - Extracts plate text and country
   - Increments failure counter on OCR errors
   - Removes failed images if max attempts exceeded
5. Manages check-out when vehicle timeout exceeded
6. Draws UI overlay with detection status and active vehicle count
7. Cleans up resources on exit

**Event Logging:**
- ENTRATA: Vehicle first detected (check-in)
- USCITA: Vehicle timeout exceeded (check-out)
- TARGA_RILEVATA: Plate successfully read with OCR

### test_onvif.py
Utility script to discover RTSP URLs from ONVIF-compatible cameras:
- Uses `onvif` Python library
- Queries camera profiles via ONVIF media service
- Prints RTSP URLs for each profile

### test_ocr.py
Utility script to test OCR on single images:
- Loads `LicensePlateRecognizer` model
- Runs OCR on specified image path
- Prints extracted plate text and country

## Environment

Python virtual environment at `video-ai-env/` with Python 3.14.

Key dependencies:
- OpenCV (`cv2`) for video processing
- Ultralytics YOLO for object detection
- fast_plate_ocr for license plate recognition
- onvif library for camera discovery
- torch with MPS backend for Apple Silicon

## Configuration

### camera_persone.py
Edit these variables in `camera_persone.py`:
- `rtsp_url`: RTSP stream URL (line 11)
- `yolov8n.pt`: Model path (line 9)

### camera_targhe.py
Edit these variables in `camera_targhe.py`:
- `RTSP_URL`: RTSP stream URL (line 18)
- `BASE_SAVE_DIR`: Directory for saving plate images (line 19)
- `LOG_FILE`: CSV log file path (line 20)
- `TIMEOUT_VEICOLO`: Vehicle timeout in seconds (line 21)
- `MAX_TENTATIVI_OCR`: Max OCR attempts before giving up (line 22)
- Model paths (lines 25-26)
- OCR model name (line 30)

### test_onvif.py
Edit these in `test_onvif.py`:
- `IP`: Camera IP address (line 3)
- `PORT`: Camera port, typically 8080, 8899, or 8000 (line 4)
- `USER`: Camera username (line 5)
- `PASS`: Camera password (line 6)

## Key Features

The code includes several features for reliability and efficiency:
1. RTSP reconnection on stream failure (both scripts)
2. Frame resizing to reduce inference time
3. Frame skipping (every 3rd frame) for performance in person detection
4. 5-second snapshot cooldown to prevent flooding
5. Threaded RTSP streaming for non-blocking video feed
6. Persistent object tracking with unique IDs
7. Max OCR attempts to prevent infinite loops
8. Date-based image organization
9. Comprehensive CSV logging of all events
10. Apple Metal (MPS) GPU acceleration support

## Common Commands

```bash
# Activate virtual environment
source video-ai-env/bin/Activate.ps1  # PowerShell
# or
source video-ai-env/bin/activate      # Bash

# Run person detection
python camera_persone.py

# Run vehicle tracking and plate recognition
python camera_targhe.py

# Test ONVIF camera discovery
python test_onvif.py

# Test OCR on single image
python test_ocr.py
```
