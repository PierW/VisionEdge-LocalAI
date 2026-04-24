"""
camera_persone/config.py
Costanti per il rilevamento persone con registrazione video.
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

# Video
OUTPUT_DIR = os.path.join(_ROOT, "video_salvati")
FRAME_SIZE = (640, 360)
TARGET_FPS = 10.0

# Detection
FRAME_SKIP = 2  # esegui YOLO 1 frame su 2
PERSON_ABSENT_GRACE = 2  # secondi di assenza prima di chiudere il video
LOG_COOLDOWN = 5  # secondi tra un log di detection e il successivo