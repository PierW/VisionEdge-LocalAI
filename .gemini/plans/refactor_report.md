# Refactor Report: Garage Checker

## Overview
The "targhe_auto" project has been completely reviewed and refactored into a professional, modular system named **"garage_checker"**. The new system is designed for a garage environment with 3 fixed parking positions (ROIs).

## Modifications Performed

### 1. Architecture & Modularity
- **Rewritten from scratch**: The monolithic `main.py` was decomposed into a clean, object-oriented structure.
- **New Modules**:
    - `core/engine.py`: Central orchestration of the detection and OCR pipeline.
    - `core/roi.py`: Dedicated logic for managing multiple Regions of Interest.
    - `core/state.py`: Thread-safe state machine for tracking vehicles through their lifecycle.
    - `modules/detector.py`: Wrapper for YOLOv8 vehicle tracking.
    - `modules/ocr_pipeline.py`: Advanced license plate detection and ensemble OCR recognition.
    - `modules/notifier.py`: Robust Telegram bot integration with interactive commands.
    - `modules/whitelist.py`: Managed interface for the authorized vehicles database.

### 2. ROI Configuration Tool
- **Improved Tool**: `tools/roi_configurator.py` replaces the basic `roi_tester.py`.
- **Features**: Supports dragging to move ROIs and resizing from corners.
- **Persistence**: Saves ROI coordinates to `config/rois.json`, which is automatically loaded by the engine.

### 3. Logic Improvements
- **ROI-Based Triggering**: OCR processing now only starts when a vehicle enters a specific ROI, significantly reducing CPU/GPU overhead.
- **State Management**: Vehicle state is now handled by a dedicated `StateManager`, preventing race conditions and ensuring data consistency.
- **Standardization**: All code follows PEP 8 conventions, with clear English naming for modules, classes, and variables.
- **Configuration**: Centralized settings in `config/settings.py` with support for environment variables.

### 4. Code Quality
- **Type Hinting**: Added type hints for better maintainability and IDE support.
- **Encapsulation**: Removed global variables and locks in favor of class-based state and synchronization.
- **Error Handling**: Implemented more robust error handling and stream reconnection logic.

## What was Kept vs. Rewritten
- **Kept (and refined)**:
    - Preprocessing variants for day/night (migrated to `ocr_pipeline.py`).
    - Ensemble OCR logic (migrated to `ocr_pipeline.py`).
    - Telegram interaction flow (migrated and refactored into `notifier.py`).
- **Rewritten**:
    - Main loop and orchestration logic.
    - State tracking mechanism.
    - ROI overlap logic.
    - Configuration management.
    - File system organization.

## Remaining Risks & Future Improvements
- **Risk**: The system relies on fixed ROIs. If the camera moves slightly, ROIs will need recalibration using the configurator tool.
- **Future Improvement**: Add a web-based dashboard for real-time monitoring and ROI adjustment.
- **Future Improvement**: Implement an SQLite or PostgreSQL database for more robust long-term logging and analytics.
- **Future Improvement**: Add support for multi-camera environments.

## Final Verification
- The project structure is coherent.
- All imports have been updated to the new structure.
- The system is ready to be run with `python garage_checker/main.py`.
- The configuration tool is available at `python garage_checker/tools/roi_configurator.py`.
