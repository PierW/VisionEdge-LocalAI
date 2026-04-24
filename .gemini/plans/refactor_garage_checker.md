# Plan: Refactor Garage Checker

Refactor the `garage_checker` module to fix circular imports, resolution-dependent ROI coordinates, and streamline the ROI-based detection process.

## Objective
- Eliminate tracking and use 3 fixed ROI zones for vehicle detection.
- Implement a robust ROI configuration flow that runs on first start.
- Fix coordinate scaling issues between configurator and detection loop.
- Clean up redundant code and fix circular dependencies.

## Key Files & Context
- `garage_checker/config.py`: Configuration constants and ROI loading.
- `garage_checker/main.py`: Main execution loop.
- `garage_checker/roi_configurator.py`: ROI drawing tool.
- `garage_checker/roi_detector.py` (New): Encapsulate ROI logic.

## Implementation Steps

### 1. Refactor `garage_checker/config.py`
- Remove the top-level `ROIS = _ensure_rois_configured()` call and the dependency on `roi_configurator`.
- Convert `_load_rois` into a clean, public `load_rois()` function that simply reads the JSON or returns defaults.
- Ensure all constants (YOLO models, thresholds) match `targhe_auto` where appropriate but stay specific to the garage use case (e.g., `RTSP_URL_GARAGE`).

### 2. Rewrite `garage_checker/roi_configurator.py`
- **Resolution Mapping**: Implement logic to map mouse clicks on the display window (960x540) back to the original stream resolution.
- **Strict 3-ROI Logic**: Enforce the creation of exactly 3 ROI boxes.
- **Independence**: Move all specific imports inside functions to prevent circular dependencies with `config.py`.

### 3. Create `garage_checker/roi_detector.py`
- **Class `ROIDetector`**:
  - `__init__(rois)`: Store ROI coordinates.
  - `get_best_roi(vehicle_box)`: Identify which ROI a vehicle belongs to (using center-point overlap).
  - `draw_rois(frame, active_rois_status)`: Draw the 3 zones with status-based colors (e.g., Grey = Empty, Yellow = Processing, Green = Authorized, Red = Denied).

### 4. Refactor `garage_checker/main.py`
- **Bootstrapping**: 
  - On start, check if `rois.json` exists.
  - If not, instantiate `ROIConfigurator` and run it before continuing.
- **ROI-Centric Logic**:
  - Remove all YOLO tracking code (`persist=True`, tracker configs).
  - Use simple `model_veicoli(frame)` detection.
  - Maintain state in a dictionary indexed by `roi_id` (1, 2, 3).
  - Each `roi_id` state tracks: `last_seen_timestamp`, `ocr_candidates`, `finalized_plate`, `action_done`.
- **OCR Integration**: Reuse the `processa_targa` and `ocr_ensemble` logic from `targhe_auto` via `plate_processor.py`.

### 5. Cleanup & Synchronization
- Delete `garage_checker/test_roi_config.py`.
- Synchronize `plate_processor.py`, `telegram_bot.py`, and `whitelist_manager.py` with `targhe_auto` to ensure they use the latest improvements (adaptive preprocessing, ensemble OCR).

## Verification & Testing
- Run `roi_configurator.py` standalone to verify coordinate scaling.
- Run `main.py` without `rois.json` to verify the automatic configuration flow.
- Test with sample video or RTSP stream to verify ROI-based OCR trigger.
- Verify Telegram alerts and logging.
