import cv2
import os
import time
import threading
import csv
import sys
from datetime import datetime
from collections import defaultdict
from ultralytics import YOLO
from dotenv import load_dotenv
import asyncio
import telegram

load_dotenv()

# ==========================================
# CONFIGURAZIONE
# ==========================================

device = "cpu"

RTSP_URL         = "rtsp://192.168.1.203:554/realmonitor?channel=0&stream=1.sdp"
OUTPUT_DIR       = "conteggio_log"
LOG_FILE         = os.path.join(OUTPUT_DIR, "passaggi.csv")

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

FRAME_SIZE       = (960, 540)
TARGET_FPS       = 10.0

# --- Linea virtuale ---
LINE_Y_RATIO     = 0.50          
LINE_COLOR_IN    = (0, 255, 0)   
LINE_COLOR_OUT   = (0, 0, 255)   

# --- Tracking ---
MIN_FRAMES_SIDE  = 4
CROSSING_COOLDOWN = 6.0
TRACK_HISTORY_LEN = 30
CONF_THRESHOLD   = 0.5

# ==========================================
# SETUP
# ==========================================

os.makedirs(OUTPUT_DIR, exist_ok=True)
model = YOLO("yolov8n.pt").to(device)

if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerow(["Timestamp", "Evento", "ID", "Totale_IN", "Totale_OUT", "Presenti"])

# ==========================================
# GESTIONE TELEGRAM
# ==========================================

telegram_buffer = {"IN": 0, "OUT": 0}
timer_active = False
buffer_lock = threading.Lock()

def send_telegram_summary(text: str):
    async def _send():
        try:
            async with telegram.Bot(token=TELEGRAM_TOKEN) as bot:
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
        except Exception as e:
            print(f"Telegram Error: {e}")

    # asyncio.run crea e distrugge il loop in modo pulito, niente loop orfani
    threading.Thread(target=lambda: asyncio.run(_send()), daemon=True).start()

def telegram_worker():
    global timer_active
    time.sleep(60)
    with buffer_lock:
        if telegram_buffer["IN"] > 0 or telegram_buffer["OUT"] > 0:
            msg = (f"📊 Riepilogo ultimo minuto:\n"
                   f"➡️ Entrati: {telegram_buffer['IN']}\n"
                   f"⬅️ Usciti: {telegram_buffer['OUT']}\n"
                   f"📍 Presenti totali: {max(0, count_in - count_out)}")
            send_telegram_summary(msg)
            telegram_buffer["IN"] = 0
            telegram_buffer["OUT"] = 0
        timer_active = False

def add_to_telegram_queue(evento: str):
    global timer_active
    with buffer_lock:
        telegram_buffer[evento] += 1
        if not timer_active:
            timer_active = True
            threading.Thread(target=telegram_worker, daemon=True).start()

# ==========================================
# RTSP STREAMER
# ==========================================

class RTSPStreamer:
    def __init__(self, url):
        self.url = url
        self.cap = cv2.VideoCapture(url)
        self.frame = None
        self.ret = False
        self.stopped = False
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def _update(self):
        while not self.stopped:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                self.cap.release()
                time.sleep(2)
                self.cap = cv2.VideoCapture(self.url)
                continue
            
            resized_frame = cv2.resize(frame, FRAME_SIZE)
            with self.lock:
                self.ret, self.frame = ret, resized_frame

    def read(self):
        with self.lock:
            return self.ret, self.frame.copy() if self.frame is not None else None

    def stop(self):
        self.stopped = True
        self.thread.join(timeout=2.0) # aspetta la fine del thread
        if self.cap and self.cap.isOpened():
            self.cap.release()

# ==========================================
# LOGICA CONTEGGIO
# ==========================================

count_in = 0
count_out = 0
track_history = defaultdict(list)
last_crossing = {}

def get_side(y: float, line_y: float) -> str:
    return "above" if y < line_y else "below"

def process_crossing(obj_id: int, history: list, line_y: float) -> str | None:
    if len(history) < MIN_FRAMES_SIDE * 2:
        return None

    ys = [p[1] for p in history]
    start_side = get_side(sum(ys[:MIN_FRAMES_SIDE]) / MIN_FRAMES_SIDE, line_y)
    current_side = get_side(sum(ys[-MIN_FRAMES_SIDE:]) / MIN_FRAMES_SIDE, line_y)

    if start_side == current_side or not (min(ys) < line_y < max(ys)):
        return None

    # pulisci la history dopo il crossing per evitare rimbalzi
    track_history[obj_id].clear()

    return "IN" if start_side == "below" else "OUT"

def log_passaggio(evento: str, obj_id: int):
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            evento, obj_id, count_in, count_out, max(0, count_in - count_out),
        ])

# ==========================================
# MAIN LOOP
# ==========================================

stream = RTSPStreamer(RTSP_URL)
line_y = int(FRAME_SIZE[1] * LINE_Y_RATIO)

print("🚀 Sistema avviato. Premi 'q' o Ctrl+C per uscire.")

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
            conf=CONF_THRESHOLD,
            tracker="bytetrack.yaml",
            verbose=False
        )

        if results and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.int().cpu().tolist()
            ids   = results[0].boxes.id.int().cpu().tolist()

            for box, obj_id in zip(boxes, ids):
                x1, y1, x2, y2 = box
                cx = (x1 + x2) // 2
                cy = int(y1 + (y2 - y1) * 0.2) # Testa/Spalle

                history = track_history[obj_id]
                history.append((cx, cy))
                if len(history) > TRACK_HISTORY_LEN: history.pop(0)

                crossing = process_crossing(obj_id, history, line_y)

                if crossing and (now - last_crossing.get(obj_id, 0)) > CROSSING_COOLDOWN:
                    last_crossing[obj_id] = now
                    
                    if crossing == "IN":
                        count_in += 1
                        log_passaggio("CHECK-IN", obj_id)
                        add_to_telegram_queue("IN")
                    else:
                        count_out += 1
                        log_passaggio("CHECK-OUT", obj_id)
                        add_to_telegram_queue("OUT")
                    
                    print(f"✨ {crossing} | ID {obj_id} | Presenti: {max(0, count_in - count_out)}")

                color = (0, 255, 100) if get_side(cy, line_y) == "above" else (100, 180, 255)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.circle(frame, (cx, cy), 4, (0, 0, 255), -1)

        cv2.line(frame, (0, line_y), (FRAME_SIZE[0], line_y), (255, 255, 0), 2)
        cv2.putText(frame, f"IN:{count_in} OUT:{count_out} PRES:{max(0, count_in-count_out)}", 
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.imshow("Crowded Area Counter", frame)
        
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

except KeyboardInterrupt:
    print("\n⚠️ Interruzione rilevata (Ctrl+C)...")

finally:
    print("🧹 Pulizia risorse e chiusura in corso...")
    stream.stop()  # con il join che ti ho suggerito prima
    cv2.destroyAllWindows()
    print("✅ Chiuso correttamente.")
# lascia che lo script finisca naturalmente