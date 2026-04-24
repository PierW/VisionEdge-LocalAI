"""
garage_checker/main.py
Monitoraggio posti auto (ROI) nel garage - Versione Semplificata (No OCR).
"""

import cv2
import os
import sys
import time
import threading
import csv
import signal
from datetime import datetime
from ultralytics import YOLO

sys.path.insert(0, os.path.dirname(__file__))

import config as cfg
import telegram_bot as tg
from roi_detector import ROIDetector
from roi_configurator import ROIConfigurator

# ==========================================
# AVVIO E CONFIGURAZIONE
# ==========================================
rois = cfg.load_rois()
if not rois:
    print("ℹ️  ROI non trovate. Avvio configuratore...")
    conf = ROIConfigurator(cfg.RTSP_URL, cfg.ROI_FILE, cfg.DISPLAY_WIDTH, cfg.DISPLAY_HEIGHT)
    if not conf.configure():
        print("❌ Configurazione fallita. Esco.")
        sys.exit(1)
    rois = cfg.load_rois()

roi_detector = ROIDetector(rois)

print(f"🔧 Device: {cfg.DEVICE.upper()}")
model_veicoli = YOLO(cfg.MODEL_VEICOLI).to(cfg.DEVICE)

# ==========================================
# STATO GLOBALE (PER ROI)
# ==========================================
_state_lock = threading.Lock()
roi_states = {roi["id"]: {
    "occupata": False,
    "nome": roi["name"],
    "last_seen": 0,
} for roi in rois}

# ==========================================
# UTILS
# ==========================================
class RTSPStreamer:
    def __init__(self, url: str):
        self.url = url
        self.cap = cv2.VideoCapture(url)
        self.frame = None
        self.ret = False
        self.stopped = False
        self.lock = threading.Lock()
        threading.Thread(target=self._update, daemon=True).start()

    def _update(self):
        while not self.stopped:
            ret, frame = self.cap.read()
            if not ret:
                self.cap.release()
                time.sleep(2)
                self.cap = cv2.VideoCapture(self.url)
                continue
            with self.lock: self.ret, self.frame = ret, frame.copy()

    def read(self):
        with self.lock: return self.ret, (self.frame.copy() if self.frame is not None else None)

    def stop(self):
        self.stopped = True
        self.cap.release()

def log_evento(roi_id, azione, nome_veicolo):
    file_exists = os.path.isfile(cfg.LOG_FILE)
    with open(cfg.LOG_FILE, mode='a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "ROI_ID", "Evento", "Veicolo"])
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), roi_id, azione, nome_veicolo])

# ==========================================
# CALLBACK TG
# ==========================================
def _get_stato_live():
    with _state_lock:
        return {rid: (s["nome"] if s["occupata"] else None) for rid, s in roi_states.items()}

# ==========================================
# MAIN LOOP
# ==========================================
tg.set_get_stato_callback(_get_stato_live)
tg.start_bot()

stream = RTSPStreamer(cfg.RTSP_URL)
print(f"🚀 Garage Checker avviato su {cfg.DEVICE.upper()}. Premi 'q' per uscire.")

try:
    while True:
        ret, frame = stream.read()
        if frame is None:
            time.sleep(0.01)
            continue

        now = time.time()
        results = model_veicoli(frame, verbose=False, conf=cfg.CONF_VEHICOLI, classes=cfg.VEHICLE_CLASSES)
        
        currently_occupied = set()

        if results and results[0].boxes is not None:
            boxes = results[0].boxes.xyxy.int().cpu().tolist()
            for box in boxes:
                rid = roi_detector.get_best_roi(box)
                if rid: currently_occupied.add(rid)

        with _state_lock:
            for rid, state in roi_states.items():
                if rid in currently_occupied:
                    if not state["occupata"]:
                        print(f"🆕 [CHECK-IN] ROI {rid}: {state['nome']}")
                        tg.send_message(f"🚗 *{state['nome']}* è arrivato al posto {rid}")
                        log_evento(rid, "ENTRATA", state["nome"])
                        state["occupata"] = True
                    state["last_seen"] = now
                else:
                    if state["occupata"] and (now - state["last_seen"] > cfg.TIMEOUT_VEICOLO):
                        print(f"🏁 [CHECK-OUT] ROI {rid}: {state['nome']}")
                        tg.send_message(f"🏁 *{state['nome']}* è uscito dal posto {rid}")
                        log_evento(rid, "USCITA", state["nome"])
                        state["occupata"] = False

        # UI
        display_frame = cv2.resize(frame, (cfg.DISPLAY_WIDTH, cfg.DISPLAY_HEIGHT))
        scale = cfg.DISPLAY_WIDTH / frame.shape[1]
        roi_status = {}
        with _state_lock:
            for rid, s in roi_states.items():
                color = (0, 255, 0) if s["occupata"] else (100, 100, 100)
                label = f"{s['nome']} (Occupato)" if s["occupata"] else f"Libero {rid}"
                roi_status[rid] = {"color": color, "label": label}
        
        roi_detector.draw_roi_overlays(display_frame, roi_status, scale)
        cv2.imshow("Garage Checker", display_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

except KeyboardInterrupt: pass
finally:
    # Ordine inverso: prima bot, poi stream, poi OpenCV
    print("🛑 Chiusura in corso...")
    
    # Ferma bot (ignora errori)
    try:
        tg.stop_bot()
    except Exception as e:
        print(f"⚠️ Errore chiusura bot: {e}")
    
    # Ferma stream
    try:
        stream.stop()
    except Exception as e:
        print(f"⚠️ Errore chiusura stream: {e}")
    
    # OpenCV: chiudi solo waitKey, evita destroyAllWindows che causa segfault
    try:
        cv2.waitKey(1)
    except Exception:
        pass
    
    print("✅ Arrivederci!")
