"""
targhe_auto/config.py
Tutte le costanti configurabili del modulo targhe_auto.
"""

import os
import torch
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# ─── Device ──────────────────────────────────────────────────────────────────
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"

# ─── Telecamera ──────────────────────────────────────────────────────────────
RTSP_URL = os.getenv("RTSP_URL_TARGHE", "rtsp://192.168.1.218:554/realmonitor?channel=0&stream=0.sdp")

# ─── Modelli (root del progetto) ──────────────────────────────────────────────
_ROOT          = os.path.join(os.path.dirname(__file__), '..')
MODEL_VEICOLI  = os.path.join(_ROOT, "yolov8n.pt")
MODEL_TARGHE   = os.path.join(_ROOT, "yolov8n_plate.pt")
MODEL_OCR      = "cct-xs-v2-global-model"
TRACKER_CONFIG = os.path.join(_ROOT, "botsort_custom.yaml")

# ─── Logica rilevamento ───────────────────────────────────────────────────────
CONF_VEICOLI      = 0.4
CONF_TARGA        = 0.4
TIMEOUT_VEICOLO   = 6
MAX_TENTATIVI_OCR = 10
MAX_CANDIDATI     = 7
OCR_FRAME_INTERVAL_SEC = 0.3  # Tempo minimo (sec) tra acquisizioni di candidati per lo stesso veicolo (es. 0.3s ≈ 3 frame @ 10fps)
PLATE_PAD_PX      = 15
PLATE_UPSCALE     = 3

# ─── File system (tutto dentro targhe_auto/) ─────────────────────────────────
_MODULE_DIR   = os.path.dirname(__file__)
BASE_SAVE_DIR = os.path.join(_MODULE_DIR, "targhe_salvate")
LOG_FILE      = os.path.join(_MODULE_DIR, "accessi_veicoli.csv")
WHITELIST_FILE = os.path.join(_MODULE_DIR, "whitelist.json")
ACTION_SCRIPT  = os.path.join(_MODULE_DIR, "action_autorizzato.py")

# ─── Orari giorno/notte per preprocessing adattivo ───────────────────────────
# Formato 24h: (ora_inizio, ora_fine)
ORA_GIORNO = (7, 20)   # 07:00 – 20:00 → pipeline diurna
                       # fuori da questo range → pipeline notturna

# ─── Classi YOLO (COCO): 2=car 3=moto 5=bus 7=truck ─────────────────────────
VEHICLE_CLASSES = [2, 3, 5, 7]

# ─── Display ─────────────────────────────────────────────────────────────────
DISPLAY_WIDTH  = 960
DISPLAY_HEIGHT = 540