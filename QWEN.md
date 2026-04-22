# VisionEdge-LocalAI — Project Context

## Overview

**VisionEdge-LocalAI** is a local AI video monitoring system for person detection, vehicle tracking with license plate recognition, and whitelist management via Telegram. All processing runs offline on local hardware with Apple Metal (MPS) acceleration for Mac.

### Core Modules

| Module | Purpose |
|--------|---------|
| `camera_persone.py` | Real-time person detection with video recording and Telegram notifications |
| `camera_conteggio_persone.py` | Person counting with virtual line crossing detection |
| `targhe_auto/` | Vehicle tracking + OCR + whitelist management (main application) |
| `telegram_bot.py` | Telegram bot for whitelist authorization |
| `whitelist_manager.py` | JSON-based vehicle database |
| `plate_processor.py` | Adaptive day/night preprocessing + ensemble OCR |

---

## Architecture

### targhe_auto/ (Main Application)

```
targhe_auto/
├── main.py              # Entry point: RTSP streaming + YOLO tracking + OCR loop
├── config.py            # All configurable constants
├── plate_processor.py   # Adaptive preprocessing + ensemble OCR
├── whitelist_manager.py # JSON database operations
├── telegram_bot.py      # Telegram bot handlers
└── action_autorizzato.py # Hook for authorized vehicle actions
```

### Data Flow

1. **RTSP Stream** → `RTSPStreamer` class (non-blocking thread)
2. **Vehicle Detection** → YOLOv8 with BoT-SORT tracking (`persist=True`)
3. **License Plate OCR** → Adaptive preprocessing → Ensemble voting (2 variants)
4. **Whitelist Check** → `whitelist_manager.py` (JSON)
5. **Telegram Notification** → `/stato` command + unknown plate alerts
6. **Check-out** → 6s timeout triggers final candidate selection

---

## Key Technologies

- **YOLOv8** (`ultralytics==8.4.37`) — Object detection
- **BoT-SORT** (`botsort_custom.yaml`) — Persistent ID tracking
- **fast-plate-ocr** (`fast-plate-ocr==1.1.0`) — License plate OCR
- **OpenCV** (`opencv-python==4.13.0`) — Video processing
- **python-telegram-bot** (`python-telegram-bot==22.7`) — Telegram integration
- **ONNX Runtime** (`onnxruntime==1.24.4`) — Model inference
- **Apple MPS** — GPU acceleration on Mac (`DEVICE = "mps"`)

---

## Configuration

### Environment Variables (`.env`)

```env
TELEGRAM_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
RTSP_URL_TARGHE=rtsp://your_camera_ip:port/stream
```

### targhe_auto/config.py

```python
DEVICE = "mps" or "cpu"
TIMEOUT_VEICOLO = 6  # seconds before check-out
MAX_TENTATIVI_OCR = 10  # max OCR attempts
MAX_CANDIDATI = 7  # max plate candidates per vehicle
CONF_VEICOLI = 0.4  # YOLO confidence threshold
CONF_TARGA = 0.4    # OCR confidence threshold
ORA_GIORNO = (7, 20)  # day/night split: 07:00 - 20:00
```

### botsort_custom.yaml

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
```

---

## Adaptive OCR (plate_processor.py)

### Day/Night Detection (Triple Criterion)

Night mode activates if ANY of these conditions are met:
- `brightness < 80` (dark image)
- `noise > 14` (high noise, typical of night)
- `contrast < 30` (low contrast, IR/nebula)
- Time-based fallback outside 07:00-20:00 range

### Preprocessing Variants

| Mode | Description |
|------|-------------|
| `day_a` | Original color image (only upscaled) |
| `day_b` | CLAHE + bilateral filter + Gaussian blur + sharpening |
| `night_a` | Bilateral filter → CLAHE → gamma correction → sharpening |
| `night_b` | Aggressive bilateral filter → CLAHE (no gamma) |

### Ensemble Logic

1. Generate 2 variants (one color + one grayscale enhanced, or both grayscale for night)
2. Run OCR on both variants → save to temporary files
3. Compare confidence scores (`mean(char_probs)`)
4. Return the variant with highest confidence
5. Auto-cleanup of temporary files

---

## Telegram Bot Flow

### Commands

- `/stato` — Show currently tracked vehicles in garage

### Unknown Plate Flow

1. **Alert sent** with photo + 4 buttons:
   - ✅ Autorizza (authorize)
   - ❌ Nega (deny)
   - ⏭ Skippa (skip session)
   - ✏️ Modifica targa (correct plate)

2. **After Authorize/Deny** → prompt for owner name → save to whitelist

3. **After Modifica targa** → prompt for corrected plate → re-show Authorize/Deny buttons

### Internal State

- `_pending_name`: `{targa: autorizzato_bool}` — awaiting owner name
- `_pending_correction`: `{"correction": targa_originale}` — awaiting correction
- `_skippate`: set of skipped plates (session-only)

---

## Whitelist Structure (whitelist.json)

```json
{
  "AB123CD": {
    "targa": "AB123CD",
    "nome": "Mario Rossi",
    "autorizzato": true,
    "prima_vista": "2026-01-15 10:30:00",
    "ultimo_accesso": "2026-01-20 08:00:00",
    "ultima_uscita": "2026-01-20 18:00:00"
  }
}
```

### API Functions

```python
is_known(targa)           # bool: plate in database?
is_authorized(targa)      # bool: plate authorized?
get_entry(targa)          # dict | None: plate entry
add_or_update(targa, nome, autorizzato)  # save entry
update_ultimo_accesso(targa)  # update last entry time
update_ultima_uscita(targa)   # update exit time
list_all()                # list all entries
```

---

## Logging

### accessi_veicoli.csv (targhe_auto/)

| Column | Description |
|--------|-------------|
| Timestamp | Date/time |
| ID_Veicolo | BoT-SORT object ID |
| Evento | ENTRATA/USCITA/TARGA_RILEVATA/TARGA_SCONOSCIUTA |
| File_Targa | Image filename |
| Testo_Targa | Recognized plate |
| Nazione | Region/country |
| Proprietario | Owner name |
| Modalita_OCR | day/notte |
| Confidence | OCR confidence score |

### passaggi.csv (conteggio_log/)

| Column | Description |
|--------|-------------|
| Timestamp | Date/time |
| Evento | CHECK-IN/CHECK-OUT |
| ID | Object ID |
| Totale_IN | Total entries |
| Totale_OUT | Total exits |
| Presenti | Currently present |

---

## Usage

### Start Person Detection

```bash
python camera_persone.py
```

- Detects YOLOv8 "person" class
- Records video when person detected
- Auto-closes after 2s absence
- Sends snapshot to Telegram
- Shows REC/LIVE indicator overlay

### Start Person Counting

```bash
python camera_conteggio_persone.py
```

- Virtual line at 50% frame height
- Crossing validation with position history
- Logs to `conteggio_log/passaggi.csv`
- Telegram summary every 60s

### Start Vehicle Tracking + OCR

```bash
python targhe_auto/main.py
```

Press `q` to exit.

---

## Development Conventions

### Code Style

- Python 3.10+ syntax
- Type hints used liberally
- Docstrings for all public functions
- Inline comments for complex logic
- Italian comments in source, English in this QWEN.md

### Testing

- `test_ocr.py` — Single image OCR testing
- `test_cropocr_quality.py` — Quality validation
- `test_onvif.py` — RTSP URL discovery utility

### File Organization

- Models in project root: `yolov8n.pt`, `yolov8n_plate.pt`
- YOLO configs: `botsort_custom.yaml`
- Daily saves in `targhe_auto/targhe_salvate/YYYY-MM-DD/`
- Logs in dedicated directories

### Git Exclusions

```
video-ai-env/
targhe_auto/targhe_salvate/
targhe_auto/accessi_veicoli.csv
conteggio_log/
__pycache__
```

---

## Environment Setup

```bash
# Create virtual environment
python3 -m venv video-ai-env
source video-ai-env/bin/activate  # Linux/Mac
# or: video-ai-env\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Copy .env.sample to .env and fill in credentials
cp .env.sample .env
# Edit .env with your Telegram credentials and RTSP URL
```

---

## Roadmap

- [ ] LLM Integration — Contextual event analysis
- [ ] Web Dashboard — Live monitoring interface
- [ ] Deduplication — Avoid duplicate saves
- [ ] Business Rules — Database validation
- [ ] Notifications — Email/SMS/Telegram alerts

---

## Models

| Model | Path | Purpose |
|-------|------|---------|
| YOLOv8n | `yolov8n.pt` | General object detection |
| YOLOv8n Plate | `yolov8n_plate.pt` | License plate detection |
| CCT-OCR | `cct-xs-v2-global-model` | License plate OCR (fast-plate-ocr) |

---

## Key Files Reference

### targhe_auto/main.py
- `RTSPStreamer` class — Non-blocking video feed
- `finalize_best_candidate()` — Ensemble voting for best plate
- Vehicle tracking loop with check-in/check-out
- UI overlay with ID labels and colors

### targhe_auto/config.py
- All configurable constants
- Device detection (MPS/CPU)
- File paths and thresholds

### targhe_auto/plate_processor.py
- `_is_night()` — Day/night detection
- `ocr_ensemble()` — Two-variant OCR voting
- `processa_targa()` — Returns (variant_a, variant_b, mode, metrics)

### targhe_auto/telegram_bot.py
- Inline button handlers
- Pending state management
- Network error throttling (30s cooldown)

### targhe_auto/whitelist_manager.py
- JSON CRUD operations
- Timestamp tracking

### camera_persone.py
- Person detection with video recording
- Grace period for person absence (2s)
- Telegram snapshot notifications

### camera_conteggio_persone.py
- Virtual line crossing detection
- Position history tracking (30 frames)
- Minimum frames for crossing validation (4)
- Telegram summary every 60s

---

## Quick Reference

### Start Services

```bash
# Person detection
python camera_persone.py

# Person counting
python camera_conteggio_persone.py

# Vehicle tracking + OCR
python targhe_auto/main.py
```

### Telegram Commands

```
/stato  — Show garage status
```

### Exit Scripts

```
Press 'q' in the OpenCV window
Or Ctrl+C in terminal
```
