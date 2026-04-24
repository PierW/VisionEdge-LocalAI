# Update CLAUDE.md and README.md

## Context

This project is a local AI video monitoring system with multiple specialized applications:
1. **camera_persone.py** - Person detection with video recording and Telegram notifications
2. **camera_conteggio_persone.py** - Person counting with virtual line crossing
3. **targhe_auto/main.py** - Vehicle tracking with license plate OCR and whitelist management
4. **telegram_bot.py** - Telegram bot for plate authorization
5. **whitelist_manager.py** - Vehicle database management
6. **plate_processor.py** - Adaptive preprocessing + ensemble OCR

## Why This Change Is Needed

The current CLAUDE.md and README.md are outdated and don't reflect:
1. The new `targhe_auto/` module structure (replaced old `camera_targhe.py`)
2. The `camera_conteggio_persone.py` script (person counting)
3. The Telegram bot integration details
4. The `whitelist_manager.py` and `plate_processor.py` modules
5. The BoT-SORT tracking configuration
6. The ensemble OCR with day/night adaptive preprocessing
7. The updated configuration values (TIMEOUT_VEICOLO = 6s, MAX_CANDIDATI = 4)

## Recommended Approach

### 1. Update CLAUDE.md
Add/update sections for:
- `camera_conteggio_persone.py` - Person counting architecture
- `targhe_auto/` module structure (main.py, config.py, plate_processor.py, whitelist_manager.py, telegram_bot.py)
- Telegram bot command (`/stato`) and flow
- Whitelist JSON structure
- BoT-SORT tracking configuration
- Adaptive preprocessing (day/night)
- Ensemble OCR logic

### 2. Update README.md
Add/update sections for:
- New script: `camera_conteggio_persone.py`
- Telegram bot commands and features
- Whitelist management via JSON
- BoT-SORT tracker configuration
- Adaptive preprocessing details
- Ensemble OCR explanation
- Updated configuration values
- Additional features (Telegram notifications, person counting)

## Critical Files to Reference

### targhe_auto/main.py
- Entry point with vehicle tracking, OCR, whitelist, Telegram notifications
- RTSPStreamer class for non-blocking video feed
- `finalize_best_candidate()` - ensemble voting for best plate
- BoT-SORT tracking with persistent IDs
- Check-in/check-out logic with 6s timeout
- Max 4 candidates per vehicle

### targhe_auto/config.py
- DEVICE: MPS (Apple Metal) or CPU
- TIMEOUT_VEICOLO: 6 seconds (check-out threshold)
- MAX_TENTATIVI_OCR: 10 max OCR attempts
- MAX_CANDIDATI: 4 max plate candidates
- CONF_VEICOLI/TARGA: 0.4 confidence thresholds
- ORA_GIORNO: (7, 20) for day/night adaptive preprocessing

### targhe_auto/plate_processor.py
- `_is_night()` - Triple criterion: brightness < 80, noise > 14, contrast < 30
- 4 preprocessing variants: day_a, day_b, night_a, night_b
- `ocr_ensemble()` - Runs OCR on 2 variants, returns best confidence
- `processa_targa()` - Returns (variant_a, variant_b, mode, metrics)

### targhe_auto/telegram_bot.py
- Commands: `/stato` (show active vehicles)
- Flow: Unknown plate → 4 buttons (Allow/Deny/Skip/Edit)
- Pending states: `_pending_name`, `_pending_correction`, `_skippate`
- Callback handlers for inline buttons
- Network error throttling (30s cooldown)

### targhe_auto/whitelist_manager.py
- JSON structure with targa, nome, autorizzato, prima_vista, ultimo_accesso, ultima_uscita
- Functions: `is_known()`, `is_authorized()`, `get_entry()`, `add_or_update()`, `update_ultimo_accesso()`, `update_ultima_uscita()`, `list_all()`

### botsort_custom.yaml
- tracker_type: botsort
- track_high_thresh: 0.45
- track_low_thresh: 0.1
- new_track_thresh: 0.5
- track_buffer: 90
- match_thresh: 0.7
- fuse_score: True
- with_reid: True
- proximity_thresh: 0.5
- appearance_thresh: 0.4

## Verification

1. Run `python camera_persone.py` - Person detection with Telegram snapshots
2. Run `python camera_conteggio_persone.py` - Person counting with virtual line
3. Run `python targhe_auto/main.py` - Vehicle tracking with OCR and Telegram bot
4. Test `/stato` command in Telegram
5. Test whitelist CRUD operations
6. Verify CSV logging in `accessi_veicoli.csv`
