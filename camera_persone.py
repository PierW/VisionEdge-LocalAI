import cv2
import time
import os
import threading
import asyncio
import telegram
from ultralytics import YOLO
from dotenv import load_dotenv
load_dotenv()


# =========================
# CONFIG TELEGRAM
# =========================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =========================
# CARTELLA OUTPUT
# =========================

OUTPUT_DIR = "video_salvati"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# =========================
# INIT MODELLO
# =========================

model = YOLO("yolov8n.pt")
rtsp_url = "rtsp://192.168.1.203:554/realmonitor?channel=0&stream=1.sdp"

# =========================
# PARAMETRI
# =========================

FRAME_SIZE = (640, 360)
TARGET_FPS = 10.0          # FPS reali dello stream (misura e adatta)
FRAME_SKIP = 2           # esegui YOLO 1 frame su 2
PERSON_ABSENT_GRACE = 2  # secondi di assenza prima di chiudere il video
LOG_COOLDOWN = 5         # secondi tra un log di detection e il successivo

# =========================
# HELPERS TELEGRAM
# =========================

def send_telegram_snapshot(image_path: str, caption: str):
    """Invia snapshot su Telegram in background."""
    def _run():
        async def _send():
            try:
                async with telegram.Bot(token=TELEGRAM_TOKEN) as bot:
                    with open(image_path, "rb") as f:
                        await bot.send_photo(
                            chat_id=TELEGRAM_CHAT_ID,
                            photo=f,
                            caption=caption,
                            read_timeout=20,
                            write_timeout=30,
                        )
                print(f"📤 Snapshot inviato su Telegram")
            except Exception as e:
                print(f"❌ Errore Telegram: {e}")
        asyncio.run(_send())
    threading.Thread(target=_run, daemon=True).start()

# =========================
# HELPERS VIDEO
# =========================

def create_writer(timestamp: int):
    """
    Crea un VideoWriter H.264.
    Prova prima avc1 (H.264 nativo), poi mp4v come fallback.
    """
    filename = os.path.join(OUTPUT_DIR, f"person_{timestamp}.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"avc1")
    writer = cv2.VideoWriter(filename, fourcc, TARGET_FPS, FRAME_SIZE)
    if not writer.isOpened():
        # fallback: XVID in avi (universalmente compatibile)
        filename = os.path.join(OUTPUT_DIR, f"person_{timestamp}.avi")
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        writer = cv2.VideoWriter(filename, fourcc, TARGET_FPS, FRAME_SIZE)
    return writer, filename

def close_and_notify(writer, filename: str, snapshot_frame):
    """Chiude il VideoWriter e invia lo snapshot su Telegram."""
    writer.release()
    duration = time.time()  # calcolato fuori, passiamo solo il frame
    snap_path = filename.rsplit(".", 1)[0] + "_snap.jpg"
    cv2.imwrite(snap_path, snapshot_frame)
    ts_str = time.strftime("%d/%m/%Y %H:%M:%S")
    caption = f"👤 Persona rilevata — {ts_str}\n📁 Video: {os.path.basename(filename)}"
    print(f"💾 Video salvato: {filename}")
    send_telegram_snapshot(snap_path, caption)

# =========================
# CONNESSIONE RTSP
# =========================

def open_capture(url):
    cap = cv2.VideoCapture(url)
    return cap

cap = open_capture(rtsp_url)
if not cap.isOpened():
    print("❌ Stream non aperto")
    exit()
print("✅ Stream connesso. Avvio detection...")

# =========================
# STATE
# =========================

frame_id = 0
video_writer = None
current_filename = None
first_frame_of_session = None  # snapshot da inviare a fine sessione
last_seen_person = 0           # timestamp ultima detection positiva
last_log_time = 0              # per throttle dei log
is_recording = False

# =========================
# MAIN LOOP
# =========================

try:
    while True:
        ret, frame = cap.read()

        # --- Reconnect RTSP ---
        if not ret or frame is None:
            print("⚠️ Frame perso — riconnessione...")
            cap.release()
            time.sleep(2)
            cap = open_capture(rtsp_url)
            print("✅ Riconnesso" if cap.isOpened() else "❌ Riconnessione fallita")
            continue

        frame = cv2.resize(frame, FRAME_SIZE)
        frame_id += 1

        # --- Frame skip: YOLO non ogni frame ---
        run_yolo = (frame_id % FRAME_SKIP == 0)

        person_detected = False

        if run_yolo:
            results = model(frame, verbose=False)
            person_detected = any(
                model.names[int(box.cls[0])] == "person"
                for r in results
                for box in r.boxes
            )

        now = time.time()

        # --- Logica registrazione ---
        if person_detected:
            last_seen_person = now

            # Log throttled
            if now - last_log_time > LOG_COOLDOWN:
                print(f"👤 Persona in scena — registrazione {'in corso' if is_recording else 'avviata'}")
                last_log_time = now

            if not is_recording:
                video_writer, current_filename = create_writer(int(now))
                first_frame_of_session = frame.copy()
                is_recording = True
                print(f"🎥 Avvio registrazione: {current_filename}")

        else:
            # Persona assente: aspetta PERSON_ABSENT_GRACE secondi prima di chiudere
            if is_recording and (now - last_seen_person > PERSON_ABSENT_GRACE):
                print("🏁 Persona uscita dall'inquadratura — chiusura video")
                close_and_notify(video_writer, current_filename, first_frame_of_session)
                video_writer = None
                current_filename = None
                first_frame_of_session = None
                is_recording = False

        # Scrivi frame nel video corrente (tutti i frame, non solo quelli YOLO)
        if is_recording and video_writer is not None:
            video_writer.write(frame)

        # --- Preview ---
        if is_recording:
            cv2.circle(frame, (20, 20), 8, (0, 0, 220), -1)   # cerchio rosso pieno
            cv2.putText(frame, "REC", (35, 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 220), 2)
        else:
            cv2.circle(frame, (20, 20), 8, (200, 200, 200), 1) # cerchio grigio vuoto
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
        close_and_notify(video_writer, current_filename, first_frame_of_session)
    cap.release()
    cv2.destroyAllWindows()
    print("🧹 Pulizia completata")