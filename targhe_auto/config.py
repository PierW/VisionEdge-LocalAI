"""
targhe_auto/config.py
Tutte le costanti configurabili del modulo targhe_auto.
Importa questo file invece di disperdere magic numbers nel codice.
"""

import os
import torch
from dotenv import load_dotenv

# .env è nella root del progetto (un livello sopra targhe_auto/)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# ─── Device ──────────────────────────────────────────────────────────────────
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"

# ─── Telecamera ──────────────────────────────────────────────────────────────
RTSP_URL = os.getenv("RTSP_URL_TARGHE", "rtsp://192.168.1.218:554/realmonitor?channel=0&stream=0.sdp")

# ─── Modelli ─────────────────────────────────────────────────────────────────
# I .pt stanno nella root del progetto, un livello sopra
_ROOT = os.path.join(os.path.dirname(__file__), '..')
MODEL_VEICOLI  = os.path.join(_ROOT, "yolov8n.pt")
MODEL_TARGHE   = os.path.join(_ROOT, "yolov8n_plate.pt")
MODEL_OCR      = "cct-xs-v2-global-model"
TRACKER_CONFIG = os.path.join(_ROOT, "botsort_custom.yaml")

# ─── Logica rilevamento ───────────────────────────────────────────────────────
CONF_VEICOLI      = 0.4    # confidence minima rilevamento veicolo
CONF_TARGA        = 0.4    # confidence minima rilevamento targa
TIMEOUT_VEICOLO   = 6      # secondi di assenza prima del check-out
MAX_TENTATIVI_OCR = 10     # tentativi OCR massimi per veicolo
PLATE_PAD_PX      = 15     # pixel di padding intorno al crop della targa
PLATE_UPSCALE     = 3      # fattore di ingrandimento pre-OCR

# ─── File system ─────────────────────────────────────────────────────────────
# Percorsi relativi alla root del progetto
BASE_SAVE_DIR = os.path.join(_ROOT, "targhe_salvate")
LOG_FILE      = os.path.join(_ROOT, "accessi_veicoli.csv")
WHITELIST_FILE = os.path.join(os.path.dirname(__file__), "whitelist.json")

# ─── Script azione autorizzato ────────────────────────────────────────────────
ACTION_SCRIPT = os.path.join(os.path.dirname(__file__), "action_autorizzato.py")

# ─── Classi YOLO da tracciare (COCO) ─────────────────────────────────────────
# 2=car, 3=motorcycle, 5=bus, 7=truck
VEHICLE_CLASSES = [2, 3, 5, 7]

# ─── Display ─────────────────────────────────────────────────────────────────
DISPLAY_WIDTH  = 960
DISPLAY_HEIGHT = 540