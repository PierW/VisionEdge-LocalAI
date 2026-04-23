"""
garage_checker/config/settings.py

Centralized configuration for the Garage Checker system.
Loads environment variables and handles paths.
"""

import os
import torch
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=ROOT_DIR / ".env")

# ─── Device ──────────────────────────────────────────────────────────────────
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
if torch.cuda.is_available():
    DEVICE = "cuda"

# ─── Stream ──────────────────────────────────────────────────────────────────
RTSP_URL = os.getenv("RTSP_URL_TARGHE", "rtsp://127.0.0.1:554/stream")

# ─── Models ──────────────────────────────────────────────────────────────────
MODEL_VEHICLES = str(ROOT_DIR / "yolov8n.pt")
MODEL_PLATES   = str(ROOT_DIR / "yolov8n_plate.pt")
MODEL_OCR      = "cct-xs-v2-global-model"
TRACKER_CONFIG = str(ROOT_DIR / "botsort_custom.yaml")

# ─── Detection Logic ─────────────────────────────────────────────────────────
CONF_VEHICLES      = 0.4
CONF_PLATES        = 0.4
TIMEOUT_VEHICLE    = 6       # Seconds to wait before removing a vehicle from state
MAX_OCR_ATTEMPTS   = 10      # Max frames to try OCR per vehicle
MIN_OCR_CANDIDATES = 7       # Number of successful OCR reads needed for voting
PLATE_PAD_PX       = 15
PLATE_UPSCALE      = 3

# ─── File System ─────────────────────────────────────────────────────────────
MODULE_DIR    = ROOT_DIR / "garage_checker"
SAVE_DIR      = MODULE_DIR / "data" / "plates"
LOG_FILE      = MODULE_DIR / "data" / "access_log.csv"
WHITELIST_FILE = MODULE_DIR / "config" / "whitelist.json"
ROIS_FILE      = MODULE_DIR / "config" / "rois.json"

# Ensure directories exist
SAVE_DIR.mkdir(parents=True, exist_ok=True)
(MODULE_DIR / "config").mkdir(parents=True, exist_ok=True)

# ─── Day/Night Logic ─────────────────────────────────────────────────────────
# Hours for day mode (start, end)
DAY_HOURS = (7, 20)

# ─── Display ─────────────────────────────────────────────────────────────────
DISPLAY_WIDTH  = 1280
DISPLAY_HEIGHT = 720

# ─── Telegram ────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
