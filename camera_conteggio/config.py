"""
camera_conteggio/config.py
Costanti per il conteggio persone con linea virtuale.
"""

import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# RTSP
RTSP_URL = os.getenv("RTSP_URL", "rtsp://192.168.1.203:554/realmonitor?channel=0&stream=1.sdp")

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Model
_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
MODEL_PERSONE = os.path.join(_ROOT, "yolov8n.pt")

# Output
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "conteggio_log")
LOG_FILE = os.path.join(OUTPUT_DIR, "passaggi.csv")

# Video
FRAME_SIZE = (960, 540)
TARGET_FPS = 10.0

# Linea virtuale
LINE_Y_RATIO = 0.50
LINE_COLOR_IN = (0, 255, 0)
LINE_COLOR_OUT = (0, 0, 255)

# Tracking
MIN_FRAMES_SIDE = 4
CROSSING_COOLDOWN = 6.0
TRACK_HISTORY_LEN = 30
CONF_THRESHOLD = 0.5