"""
garage_checker/config.py
Costanti per il monitoraggio posti auto nel garage.
"""

import os
import torch
import json
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
RTSP_URL = os.getenv("RTSP_URL_GARAGE", "rtsp://192.168.1.218:554/realmonitor?channel=0&stream=0.sdp")

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
MODEL_VEICOLI = os.path.join(_ROOT, "yolov8n.pt")

ROI_FILE = os.path.join(os.path.dirname(__file__), "rois.json")

def load_rois():
    if os.path.exists(ROI_FILE):
        try:
            with open(ROI_FILE, "r") as f:
                return json.load(f)
        except: pass
    return []

# Soglie
CONF_VEHICOLI   = 0.4
TIMEOUT_VEICOLO = 5  # secondi di assenza per confermare l'uscita

# File system
_MODULE_DIR = os.path.dirname(__file__)
LOG_FILE    = os.path.join(_MODULE_DIR, "accessi_garage.csv")

# Classi YOLO (COCO)
VEHICLE_CLASSES = [2, 3, 5, 7] # car, moto, bus, truck

# Display
DISPLAY_WIDTH  = 960
DISPLAY_HEIGHT = 540
