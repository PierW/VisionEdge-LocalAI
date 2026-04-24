"""
camera_persone/main.py
Rilevamento persone con registrazione video e notifica Telegram.
"""

import os
import sys
import cv2
import time

from ultralytics import YOLO

sys.path.insert(0, os.path.dirname(__file__))

import config as cfg
import telegram_bot as tg
from rtsp_streamer import RTSPStreamer
from video_writer import create_writer, close_writer, timestamp_to_string


# ==========================================
# INIZIALIZZAZIONE
# ==========================================

print("🔄 Caricamento modello YOLO...")
model = YOLO(cfg.MODEL_PERSONE)
print("✅ Modello caricato")

print("🔄 Connessione allo stream RTSP...")
stream = RTSPStreamer(cfg.RTSP_URL)
# Aspetta che lo stream sia pronto
time.sleep(1)
ret, test_frame = stream.read()
if test_frame is None:
    print("❌ Stream non aperto")
    sys.exit(1)
print("✅ Stream connesso. Avvio detection...")

# ==========================================
# STATO
# ==========================================

frame_id = 0
video_writer = None
current_filename = None
first_frame_of_session = None
last_seen_person = 0
last_log_time = 0
is_recording = False

# ==========================================
# MAIN LOOP
# ==========================================

try:
    while True:
        ret, frame = stream.read()
        if frame is None:
            time.sleep(0.01)
            continue

        frame_id += 1
        now = time.time()

        # Frame skip: YOLO non ogni frame
        run_yolo = (frame_id % cfg.FRAME_SKIP == 0)
        person_detected = False

        if run_yolo:
            results = model(frame, verbose=False)
            person_detected = any(
                model.names[int(box.cls[0])] == "person"
                for r in results
                for box in r.boxes
            )

        # Logica registrazione
        if person_detected:
            last_seen_person = now

            # Log throttled
            if now - last_log_time > cfg.LOG_COOLDOWN:
                print(f"👤 Persona in scena — registrazione {'in corso' if is_recording else 'avviata'}")
                last_log_time = now

            if not is_recording:
                video_writer, current_filename = create_writer(int(now))
                first_frame_of_session = frame.copy()
                is_recording = True
                print(f"🎥 Avvio registrazione: {current_filename}")

        else:
            # Persona assente: aspetta GRACE secondi prima di chiudere
            if is_recording and (now - last_seen_person > cfg.PERSON_ABSENT_GRACE):
                print("🏁 Persona uscita dall'inquadratura — chiusura video")
                close_writer(video_writer, current_filename, first_frame_of_session)
                video_writer = None
                current_filename = None
                first_frame_of_session = None
                is_recording = False

        # Scrivi frame nel video corrente
        if is_recording and video_writer is not None:
            video_writer.write(frame)

        # Preview
        if is_recording:
            cv2.circle(frame, (20, 20), 8, (0, 0, 220), -1)
            cv2.putText(frame, "REC", (35, 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 220), 2)
        else:
            cv2.circle(frame, (20, 20), 8, (200, 200, 200), 1)
            cv2.putText(frame, "LIVE", (35, 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
        cv2.imshow("AI Camera", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except KeyboardInterrupt:
    print("\n🛑 Stop manuale (CTRL+C)")

finally:
    if is_recording and video_writer is not None:
        print("💾 Chiusura video in corso...")
        close_writer(video_writer, current_filename, first_frame_of_session)
    stream.stop()
    cv2.destroyAllWindows()
    print("🧹 Pulizia completata")