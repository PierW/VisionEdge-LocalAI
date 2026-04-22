# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a local AI video monitoring system that:
- Connects to RTSP camera streams
- Detects people and vehicles using YOLOv8
- Tracks objects with persistent IDs using BoT-SORT
- Captures snapshots when detections occur
- Performs license plate recognition with adaptive preprocessing + ensemble OCR
- Logs all events to CSV files
- Uses Apple Metal (MPS) for GPU acceleration on Mac
- Integrates with Telegram bot for vehicle authorization

## Architecture

### camera_persone.py
Single-file application for person detection with video recording and Telegram notifications:

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

### camera_conteggio_persone.py
Person counting with virtual line crossing:

**Configuration:**
- LINE_Y_RATIO: 0.50 (virtual line position)
- MIN_FRAMES_SIDE: 4 (frames for crossing validation)
- CROSSING_COOLDOWN: 6.0s (prevent double-counting)
- TRACK_HISTORY_LEN: 30 (track history buffer)
- CONF_THRESHOLD: 0.5

**Logic:**
- Uses ByTetrack tracker (`bytetrack.yaml`)
- Tracks person centroid position over time
- Detects crossing when trajectory crosses virtual line
- Validates crossing with historical position analysis
- Logs to `conteggio_log/passaggi.csv`
- Sends Telegram summary every 60 seconds

**Output CSV columns:**
- Timestamp, Evento (CHECK-IN/CHECK-OUT), ID, Totale_IN, Totale_OUT, Presenti

### targhe_auto/main.py
Vehicle tracking with license plate OCR and whitelist management:

**Initialization:**
- Loads vehicle detection model (`yolov8n.pt`)
- Loads plate detection model (`yolov8n_plate.pt`)
- Loads OCR model (`LicensePlateRecognizer` with `cct-xs-v2-global-model`)
- Starts Telegram bot in background thread
- Initializes global state: `veicoli_attivi`, `candidati_per_id`, `targa_per_id`

**RTSPStreamer Class:**
- Threaded RTSP stream for non-blocking video feed
- Automatic reconnection on stream failure
- Thread-safe frame access with locks

**BoT-SORT Tracking (lines 246-250):**
- Uses `persist=True` for persistent object IDs across frames
- Vehicle classes: [2=car, 3=moto, 5=bus, 7=truck]
- Confidence threshold: 0.4

**Ensemble OCR (lines 296-299):**
- `processa_targa()`: Adaptive preprocessing → 2 variants (day/night)
- `ocr_ensemble()`: Runs OCR on both variants, returns best confidence result
- Max 4 candidates per vehicle (`MAX_CANDIDATI`)
- Max 10 OCR attempts per candidate (`MAX_TENTATIVI_OCR`)

**`finalize_best_candidate()` (lines 53-107):**
- Analyzes all candidates for a vehicle ID
- Voting logic: most frequent plate with highest average confidence
- Cleans up files: keeps only the winner's original image
- Returns (targa, nazione, conf, file_orig, file_proc, modalita)

**Check-in/Check-out Logic:**
- Check-in: First detection of vehicle ID (line 264)
- Check-out: Vehicle absent for TIMEOUT_VEICOLO (6s default) (lines 420-456)
- On check-out with candidates: finalize best candidate before clearing

**Telegram Integration:**
- Sends unknown plate alerts with 4 buttons: Allow/Deny/Skip/Edit
- On Allow/Deny: prompts for name, saves to whitelist
- On Edit: prompts for corrected plate, then allow/deny
- Network error throttling (30s cooldown)

**CSV Logging (lines 151-163):**
- Columns: Timestamp, ID_Veicolo, Evento, File_Targa, Testo_Targa, Nazione, Proprietario, Modalita_OCR, Confidence
- Events: ENTRATA, USCITA, TARGA_RILEVATA, TARGA_SCONOSCIUTA

### targhe_auto/config.py
All configurable constants:

```python
DEVICE = "mps" or "cpu"
RTSP_URL = "rtsp://..."
MODEL_VEICOLI = "yolov8n.pt"
MODEL_TARGHE = "yolov8n_plate.pt"
MODEL_OCR = "cct-xs-v2-global-model"
TRACKER_CONFIG = "botsort_custom.yaml"

CONF_VEICOLI = 0.4
CONF_TARGA = 0.4
TIMEOUT_VEICOLO = 6  # seconds for check-out
MAX_TENTATIVI_OCR = 10
MAX_CANDIDATI = 4
PLATE_PAD_PX = 15
PLATE_UPSCALE = 3

ORA_GIORNO = (7, 20)  # Daytime range for adaptive preprocessing
VEHICLE_CLASSES = [2, 3, 5, 7]  # car, moto, bus, truck
DISPLAY_WIDTH = 960
DISPLAY_HEIGHT = 540
```

### targhe_auto/plate_processor.py
Adaptive preprocessing + ensemble OCR:

**Night Detection (triple criterion):**
- `brightness < 80` → dark image
- `noise > 14` → high noise (high ISO, typical night)
- `contrast < 30` → low contrast (IR, fog, flat lighting)
- Time-of-day tiebreaker (7-20 = day, else night)

**Preprocessing Variants (4 total):**
- `_variant_day_a()`: Original color image (no enhancement)
- `_variant_day_b()`: CLAHE (2.0) + bilateral filter + sharpening
- `_variant_night_a()`: bilateral (7, 25, 25) → CLAHE (3.5, 4x4) → gamma (0.65) → sharpen
- `_variant_night_b()`: bilateral (9, 35, 35) → CLAHE (4.0, 4x4) → no gamma

**`ocr_ensemble()` (lines 93-138):**
- Runs OCR on both variants via temporary PNG files
- Confidence = mean of character probabilities
- Returns best result by confidence
- Cleans up temp files in finally block

**`processa_targa()` (lines 143-162):**
- Upscales plate crop 3x with LANCZOS4
- Analyzes brightness/contrast/noise
- Returns 2 variants + mode string + metrics dict

### targhe_auto/telegram_bot.py
Telegram bot for vehicle authorization:

**Commands:**
- `/stato`: Shows currently tracked vehicles with status

**State Variables:**
- `_pending_name`: {targa: autorizzato_bool} - waiting for owner name
- `_pending_correction`: {"correction": targa_originale} - waiting for plate correction
- `_skippate`: set of skipped plates this session

**Flow for Unknown Plate:**
1. Photo + plate + 4 buttons: [✅ Autorizza] [❌ Nega] [⏭ Skippa] [✏️ Modifica targa]
2a. Autorizza/Nega → prompts for name → saves to whitelist
2b. Skippa → ignores for this session
2c. Modifica targa → prompts for corrected plate → shows new Allow/Deny buttons → prompts for name → saves

**Network Error Handling:**
- Throttled logging (30s cooldown) for NetworkError/TimedOut
- Uses logging filter `_NetworkThrottleFilter`

**`send_unknown_plate_alert()`:**
- Sends photo (if available) + inline buttons
- Thread-safe with asyncio.run_coroutine_threadsafe

**`send_message()`:**
- Simple text message, thread-safe

### targhe_auto/whitelist_manager.py
Vehicle database management (JSON file):

**JSON Structure:**
```json
{
  "AB123CD": {
    "targa": "AB123CD",
    "nome": "Mario Rossi",
    "autorizzato": true,
    "prima_vista": "2025-01-15 10:30:00",
    "ultimo_accesso": "2025-01-20 08:00:00",
    "ultima_uscita": "2025-01-20 18:00:00"
  }
}
```

**Functions:**
- `is_known(targa)`: Plate exists in database
- `is_authorized(targa)`: Plate exists and authorized=true
- `get_entry(targa)`: Returns entry dict or None
- `add_or_update(targa, nome, autorizzato)`: Adds/updates entry
- `update_ultimo_accesso(targa)`: Updates last entry time
- `update_ultima_uscita(targa)`: Updates last exit time
- `list_all()`: Returns all entries

### botsort_custom.yaml
BoT-SORT tracker configuration:

```yaml
tracker_type: botsort
track_high_thresh: 0.45
track_low_thresh: 0.1
new_track_thresh: 0.5
track_buffer: 90
match_thresh: 0.7
fuse_score: True
with_reid: True
proximity_thresh: 0.5
appearance_thresh: 0.4
gmc_method: none
model: auto
```

## Environment

Python virtual environment at `video-ai-env/` with Python 3.14.

Key dependencies:
- OpenCV (`cv2`) for video processing
- Ultralytics YOLO for object detection
- fast_plate_ocr for license plate recognition
- telegram library for Telegram bot
- onvif library for camera discovery
- torch with MPS backend for Apple Silicon
- python-dotenv for environment variables

## Configuration

### camera_persone.py
Edit these variables in `camera_persone.py`:
- `rtsp_url`: RTSP stream URL (line 31)
- `yolov8n.pt`: Model path (line 30)
- `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`: Environment variables (lines 16-17)

### camera_conteggio_persone.py
Edit these variables in `camera_conteggio_persone.py`:
- `RTSP_URL`: RTSP stream URL (line 22)
- `LINE_Y_RATIO`: Virtual line position (line 33)
- `CONF_THRESHOLD`: Detection confidence (line 41)
- `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`: Environment variables (lines 26-27)

### targhe_auto/main.py
Config is loaded from `targhe_auto/config.py`:
- `RTSP_URL`: RTSP stream URL (config.py line 16)
- Environment variables from `.env` file

### targhe_auto/config.py
Edit these in `targhe_auto/config.py`:
- `RTSP_URL`: RTSP stream URL (line 16)
- `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`: .env file
- Model paths (lines 20-23)
- Confidence thresholds (lines 26-27)
- Timeout values (lines 28-30)
- `ORA_GIORNO`: Day/night range (line 43)

## Key Features

The code includes several features for reliability and efficiency:
1. RTSP reconnection on stream failure (all scripts)
2. Frame resizing to reduce inference time
3. Frame skipping for performance in person detection
4. Threaded RTSP streaming for non-blocking video feed
5. Persistent object tracking with unique IDs (BoT-SORT)
6. Adaptive preprocessing (day/night) for OCR
7. Ensemble OCR with voting logic
8. Max OCR attempts to prevent infinite loops
9. Date-based image organization
10. Comprehensive CSV logging of all events
11. Apple Metal (MPS) GPU acceleration support
12. Telegram bot integration for vehicle authorization
13. Whitelist management with JSON database

## Common Commands

```bash
# Activate virtual environment
source video-ai-env/bin/Activate.ps1  # PowerShell
# or
source video-ai-env/bin/activate      # Bash

# Run person detection with Telegram snapshots
python camera_persone.py

# Run person counting with virtual line
python camera_conteggio_persone.py

# Run vehicle tracking with OCR and Telegram bot
python targhe_auto/main.py

# Test ONVIF camera discovery
python test_onvif.py

# Test OCR on single image
python test_ocr.py

# Telegram bot commands
# /stato - Show currently tracked vehicles
```
