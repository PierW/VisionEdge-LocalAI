# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a person detection system using YOLOv8 that:
- Connects to an RTSP camera stream
- Detects people in the video feed using YOLOv8
- Captures snapshots when a person is detected
- Uses ONVIF protocol to query camera profiles and RTSP URLs

## Architecture

### main.py
Single-file application with the following components:

**Initialization (lines 1-19):**
- Loads YOLOv8 nano model from `yolov8n.pt`
- Opens RTSP stream from configured IP address
- Exits if stream fails to open

**State Variables (lines 25-27):**
- `frame_id`: Counter for frame tracking
- `last_snapshot_time`: Timestamp for snapshot cooldown

**Main Loop (lines 32-116):**
1. Reads frame from RTSP stream
2. Reconnects if stream fails (lines 39-51)
3. Resizes frame to 640x360 for inference (line 56)
4. Runs YOLO inference every 3rd frame for performance (lines 62-69)
5. Detects "person" class (lines 76-84)
6. Displays frame preview (lines 89, 108)
7. Captures snapshots when person detected with 5s cooldown (lines 94-103)
8. Cleans up resources on exit (lines 114-116)

### test_onvif.py
Utility script to discover RTSP URLs from ONVIF-compatible cameras:
- Uses `onvif` Python library
- Queries camera profiles via ONVIF media service
- Prints RTSP URLs for each profile

## Environment

Python virtual environment at `video-ai-env/` with Python 3.14.

Key dependencies:
- OpenCV (`cv2`) for video processing
- Ultralytics YOLO for object detection
- onvif library for camera discovery

## Common Commands

```bash
# Activate virtual environment
source video-ai-env/bin/Activate.ps1  # PowerShell
# or
source video-ai-env/bin/activate      # Bash

# Run main detection script
python main.py

# Test ONVIF camera discovery
python test_onvif.py

# Run with specific RTSP URL
python main.py  # Edit rtsp_url variable in main.py
```

## Configuration

Edit these variables in `main.py`:
- `rtsp_url`: RTSP stream URL (line 11)
- `yolov8n.pt`: Model path (line 9)

Edit these in `test_onvif.py`:
- `IP`: Camera IP address (line 3)
- `PORT`: Camera port, typically 8080, 8899, or 8000 (line 4)
- `USER`: Camera username (line 5)
- `PASS`: Camera password (line 6)

## Key Fixes Applied

The code includes several fixes for reliability:
1. RTSP reconnect on stream failure
2. Frame resizing to reduce inference time
3. Frame skipping (every 3rd frame) for performance
4. 5-second snapshot cooldown to prevent flooding
