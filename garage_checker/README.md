# Garage Checker

Sistema per rilevazione veicoli in garage con 3 zone ROI (Region of Interest).

## Overview

Questo sistema estende la funzionalità di rilevazione targhe per scenari di garage dove:
- **3 macchine** sono posizionate in zone specifiche
- Un veicolo deve entrare **dentro una zona ROI** per attivare la rilevazione targa
- Le ROI sono **più piccole di un'auto** (es. 150x80 pixel)
- Tracking per-ROI invece che globale

## Architecture

```
garage_checker/
├── main.py              # Entry point: RTSP + ROI detection + OCR loop
├── config.py            # ROI coordinates + thresholds
├── roi_detector.py      # Zone validation logic
├── README.md            # This file
├── targhe_salvate/      # Daily saved plates
└── accessi_veicoli.csv  # Access log
```

## Quick Start

### 1. Select ROI Zones

Run the interactive ROI selector:

```bash
python roi_tester.py
```

This will:
- Load your RTSP stream
- Show 3 empty rectangles
- Click to place corners
- Drag to resize (boxes smaller than car)
- Save coordinates to `garage_checker_config.json`

### 2. Configure

The `garage_checker_config.json` file will be generated automatically.

Or manually edit `garage_checker/config.py` and update `ROIS`:

```python
ROIS = [
    {"id": 1, "name": "Machine 1", "x1": 100, "y1": 200, "x2": 250, "y2": 350},
    {"id": 2, "name": "Machine 2", "x1": 300, "y1": 200, "x2": 450, "y2": 350},
    {"id": 3, "name": "Machine 3", "x1": 500, "y1": 200, "x2": 650, "y2": 350},
]
```

### 3. Run

```bash
python garage_checker/main.py
```

Press `q` to exit.

## How It Works

### Detection Flow

```
RTSP Stream → YOLO Vehicle Detection → Check ROI → 
    ↓
Vehicle inside ROI? → NO: Ignore
                    ↓ YES
    ↓
YOLO Plate Detection → OCR → Whitelist Check → 
    ↓
Authorized → Log entry
Unauthorized → Telegram alert
```

### Key Features

1. **ROI-Based Trigger**: OCR only runs when vehicle is inside ROI zone
2. **Per-ROI Tracking**: Each machine zone has independent vehicle tracking
3. **Timeout Check-out**: Vehicles leave ROI after `TIMEOUT_VEICOLO` seconds
4. **Visual Feedback**: UI shows which ROI each vehicle is in
5. **Reused Modules**: Uses existing `plate_processor.py`, `whitelist_manager.py`, `telegram_bot.py`

## Configuration

Edit `garage_checker/config.py`:

```python
# ROI zones (update after roi_tester.py)
ROIS = [...]

# Detection thresholds
CONF_VEICOLI = 0.4      # YOLO vehicle confidence
CONF_TARGA = 0.4       # OCR confidence
TIMEOUT_VEICOLO = 6    # seconds before check-out
MAX_CANDIDATI = 7      # max plate candidates
MAX_TENTATIVI_OCR = 10 # max OCR attempts

# Device
DEVICE = "mps"  # Apple Metal for Mac, or "cpu"
```

## File Structure

### Output Files

- `garage_checker/targhe_salvate/YYYY-MM-DD/` — Daily plate saves
- `garage_checker/accessi_veicoli.csv` — Access log with ROI_ID column
- `garage_checker_config.json` — ROI coordinates (JSON format)

### CSV Log Format

```csv
Timestamp,ROI_ID,ID_Veicolo,Evento,File_Targa,Testo_Targa,Nazione,Proprietario,Modalita_OCR,Confidence
2026-01-20 08:00:00,1,1,ENTRATA,AB123CD.jpg,AB123CD,Lombardia,Mario Rossi,diurna,0.95
```

## API Reference

### ROIDetector Class

```python
from garage_checker.roi_detector import ROIDetector

detector = ROIDetector(ROIS, (960, 540))

# Check if vehicle is in ROI
is_inside = detector.is_in_roi(vehicle_box, roi_id)

# Get best matching ROI
best_roi = detector.get_best_roi(vehicle_box)

# Draw overlays
frame = detector.draw_roi_overlay(frame)

# Group vehicles by ROI
vehicles_by_roi = detector.get_vehicles_in_rois(boxes, ids)
```

## Differences from targhe_auto

| Feature | targhe_auto | garage_checker |
|---------|-------------|----------------|
| Detection trigger | Any vehicle | Vehicle inside ROI |
| ROI | None | 3 fixed zones |
| Box size | Full frame | Small (< car) |
| Use case | Gate/entrance | Garage with machines |
| Tracking | Global | Per-ROI |

## Troubleshooting

### ROI not detecting vehicles

1. Check ROI coordinates are correct (run `roi_tester.py` again)
2. Verify vehicle detection is working (YOLO model)
3. Check confidence thresholds (`CONF_VEICOLI`)

### No OCR results

1. Verify plate detection model loads
2. Check plate crop is visible in debug mode
3. Increase `CONF_TARGA` threshold

### Vehicles not timing out

- Increase `TIMEOUT_VEICOLO`
- Check vehicle is actually leaving ROI (visual feedback)

## Future Enhancements

- [ ] Per-ROI whitelist rules
- [ ] Machine association (ROI 1 → Machine 1)
- [ ] Different timeouts per zone
- [ ] Web dashboard for monitoring
- [ ] Deduplication of saves

## Notes

- ROI boxes should be **smaller than a car** but large enough to contain license plate
- Typical ROI size: 150x80 pixels (adjust based on camera angle)
- Use BoT-SORT for persistent tracking across frames
- All modules are designed to be modular and reusable
