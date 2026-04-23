"""
garage_checker/config.py

Configuration for Garage Checker system.
Contains ROI coordinates, detection thresholds, and system settings.

NOTE: Replace DEFAULT_ROIS with actual coordinates after running roi_tester.py
"""

# ==========================================
# DEVICE & PERFORMANCE
# ==========================================
DEVICE = "mps"  # "mps" for Apple Metal (Mac) or "cpu"

# ==========================================
# RTSP STREAM
# ==========================================
RTSP_URL = "rtsp://192.168.1.203:554/realmonitor?channel=0&stream=1.sdp"

# ==========================================
# ROI CONFIGURATION (3 zones for 3 machines)
# NOTE: Replace with actual coordinates from roi_tester.py output
# Format: {"id": n, "name": "...", "x1": x, "y1": y, "x2": x, "y2": y, "width": w, "height": h}
#
# DEFAULT_ROIS is a placeholder - update after running roi_tester.py
DEFAULT_ROIS = [
    {"id": 1, "name": "Machine 1 Zone", "x1": 100, "y1": 200, "x2": 250, "y2": 350, "width": 150, "height": 150},
    {"id": 2, "name": "Machine 2 Zone", "x1": 300, "y1": 200, "x2": 450, "y2": 350, "width": 150, "height": 150},
    {"id": 3, "name": "Machine 3 Zone", "x1": 500, "y1": 200, "x2": 650, "y2": 350, "width": 150, "height": 150},
]

# Load from JSON if available (after roi_tester.py runs)
try:
    import json
    with open("garage_checker_config.json", "r") as f:
        ROIS = json.load(f)
except FileNotFoundError:
    ROIS = DEFAULT_ROIS

# ==========================================
# DETECTION THRESHOLDS
# ==========================================
CONF_VEICOLI = 0.4      # YOLO vehicle confidence threshold
CONF_TARGA = 0.4       # OCR confidence threshold
CONF_TRACK = 0.5       # BoT-SORT tracking confidence

# ==========================================
# TRACKING & TIMEOUT
# ==========================================
TIMEOUT_VEICOLO = 6    # seconds before check-out
MAX_CANDIDATI = 7      # max plate candidates per ROI
MAX_TENTATIVI_OCR = 10 # max OCR attempts per ROI

# ==========================================
# YOLO & TRACKER
# ==========================================
YOLO_MODEL = "yolov8n.pt"  # General object detection (vehicles)
PLATE_MODEL = "yolov8n_plate.pt"  # License plate detection
TRACKER = "bytetrack.yaml"  # BoT-SORT tracker

# ==========================================
# DISPLAY
# ==========================================
DISPLAY_WIDTH = 960
DISPLAY_HEIGHT = 540
TARGET_FPS = 10.0

# ==========================================
# FILE PATHS
# ==========================================
OUTPUT_DIR = "garage_checker/targhe_salvate"
WHITELIST_FILE = "garage_checker/whitelist.json"
LOG_FILE = "garage_checker/accessi_veicoli.csv"

# Ensure directories exist
import os
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==========================================
# TELEGRAM
# ==========================================
# These are loaded from .env at runtime, but keeping here for reference
# TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
