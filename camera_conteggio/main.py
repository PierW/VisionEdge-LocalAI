"""
camera_conteggio/main.py
Conteggio persone con attraversamento linea virtuale e notifica Telegram.
"""

import os
import sys
import cv2
import time

from ultralytics import YOLO
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

import config as cfg
import telegram_bot as tg
from rtsp_streamer import RTSPStreamer
from counter import (
    count_in, count_out,
    track_history, last_crossing,
    get_side, process_crossing, add_crossing, get_counts
)


# ==========================================
# INIZIALIZZAZIONE
# ==========================================

os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)

# Inizializza file CSV se non esiste
if not os.path.exists(cfg.LOG_FILE):
    import csv
    with open(cfg.LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerow(["Timestamp", "Evento", "ID", "Totale_IN", "Totale_OUT", "Presenti"])

print("🔄 Caricamento modello YOLO...")
model = YOLO(cfg.MODEL_PERSONE).to("cpu")
print("✅ Modello caricato")

print("🔄 Connessione allo stream RTSP...")
stream = RTSPStreamer(cfg.RTSP_URL)
time.sleep(1)
ret, test_frame = stream.read()
if test_frame is None:
    print("❌ Stream non aperto")
    sys.exit(1)
print("✅ Stream connesso. Avvio conteggio...")

line_y = int(cfg.FRAME_SIZE[1] * cfg.LINE_Y_RATIO)

print("🚀 Sistema avviato. Premi 'q' o Ctrl+C per uscire.")

# ==========================================
# MAIN LOOP
# ==========================================

try:
    while True:
        ret, frame = stream.read()
        if frame is None:
            time.sleep(0.01)
            continue

        now = time.time()

        results = model.track(
            frame,
            persist=True,
            classes=[0],
            conf=cfg.CONF_THRESHOLD,
            tracker="bytetrack.yaml",
            verbose=False
        )

        if results and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.int().cpu().tolist()
            ids = results[0].boxes.id.int().cpu().tolist()

            for box, obj_id in zip(boxes, ids):
                x1, y1, x2, y2 = box
                cx = (x1 + x2) // 2
                cy = int(y1 + (y2 - y1) * 0.2)  # Testa/Spalle

                history = track_history[obj_id]
                history.append((cx, cy))
                if len(history) > cfg.TRACK_HISTORY_LEN:
                    history.pop(0)

                crossing = process_crossing(obj_id, history, line_y)

                if crossing and (now - last_crossing.get(obj_id, 0)) > cfg.CROSSING_COOLDOWN:
                    last_crossing[obj_id] = now
                    add_crossing(crossing, obj_id)
                    tg.add_to_telegram_queue(crossing, get_counts)

                color = (0, 255, 100) if get_side(cy, line_y) == "above" else (100, 180, 255)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.circle(frame, (cx, cy), 4, (0, 0, 255), -1)

        # Disegna linea virtuale
        cv2.line(frame, (0, line_y), (cfg.FRAME_SIZE[0], line_y), (255, 255, 0), 2)
        cv2.putText(
            frame, f"IN:{count_in} OUT:{count_out} PRES:{max(0, count_in-count_out)}",
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2
        )

        cv2.imshow("Crowded Area Counter", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

except KeyboardInterrupt:
    print("\n⚠️ Interruzione rilevata (Ctrl+C)...")

finally:
    print("🧹 Pulizia risorse e chiusura in corso...")
    stream.stop()
    cv2.destroyAllWindows()
    print("✅ Chiuso correttamente.")