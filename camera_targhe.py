import cv2
import os
import torch
import time
import threading
import csv
import signal
import sys
from datetime import datetime
from ultralytics import YOLO

# ==========================================
# CONFIGURAZIONE E OTTIMIZZAZIONE
# ==========================================
device = "mps" if torch.backends.mps.is_available() else "cpu"

RTSP_URL = "rtsp://192.168.1.218:554/realmonitor?channel=0&stream=0.sdp"
BASE_SAVE_DIR = "targhe_salvate"
LOG_FILE = "accessi_veicoli.csv"
TIMEOUT_VEICOLO = 30  # Secondi di assenza prima del Check-out

# Caricamento Modelli (Assicurati che i file .pt siano nella cartella)
model_veicoli = YOLO("yolov8n.pt").to(device)
model_targhe = YOLO("yolov8n_plate.pt").to(device)

# ==========================================
# GESTIONE STREAMING (THREADING & RECONNECT)
# ==========================================
class RTSPStreamer:
    def __init__(self, url):
        self.url = url
        self.cap = cv2.VideoCapture(url)
        self.ret = False
        self.frame = None
        self.stopped = False
        self.lock = threading.Lock()
        
        if self.cap.isOpened():
            print("✅ Stream connesso. Analisi in corso...")
        else:
            print("❌ Errore: Impossibile connettersi allo stream RTSP.")
            
        self.thread = threading.Thread(target=self.update, daemon=True)
        self.thread.start()

    def update(self):
        while not self.stopped:
            ret, frame = self.cap.read()
            
            # Gestione perdita di segnale e riconnessione
            if not ret or frame is None:
                print("⚠️ Stream perso - riconnessione in corso...")
                self.cap.release()
                time.sleep(2)
                self.cap = cv2.VideoCapture(self.url)
                
                if self.cap.isOpened():
                    print("✅ Riconnessione riuscita!")
                else:
                    print("❌ Riconnessione fallita, nuovo tentativo...")
                continue
            
            # Ridimensionamento per alleggerire l'inferenza
            frame = cv2.resize(frame, (640, 360))

            # Lock per evitare conflitti con il main thread
            with self.lock:
                self.ret = ret
                self.frame = frame.copy() # .copy() evita corruzioni dell'immagine

    def read(self):
        with self.lock:
            if self.frame is None:
                return False, None
            return self.ret, self.frame.copy()

    def stop(self):
        self.stopped = True
        
        # Chiusura sicura del thread
        if hasattr(self, 'thread') and self.thread.is_alive():
            self.thread.join(timeout=2)
            
        if self.cap:
            self.cap.release()

# ==========================================
# UTILS (LOG E FILE SYSTEM)
# ==========================================
def get_daily_dir():
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(BASE_SAVE_DIR, date_str)
    os.makedirs(path, exist_ok=True)
    return path

def log_evento(veicolo_id, azione, targa_file=""):
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, mode='a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "ID_Veicolo", "Evento", "File_Targa"])
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), veicolo_id, azione, targa_file])

# ==========================================
# CTRL+C SAFE HANDLER
# ==========================================
def signal_handler(sig, frame):
    print("\n🛑 Ctrl+C rilevato, chiusura sicura in corso...")
    if 'stream' in globals():
        stream.stop()
    cv2.destroyAllWindows()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# ==========================================
# MAIN LOOP
# ==========================================
veicoli_attivi = {}         # {id: last_seen_timestamp}
targhe_salvate_per_id = set() # ID che hanno già una foto targa in questa sessione

stream = RTSPStreamer(RTSP_URL)

print(f"🚀 Sistema avviato su {device.upper()}. Premi 'q' per uscire.")

try:
    while True:
        ret, frame = stream.read()
        
        if frame is None:
            time.sleep(0.01) # Evita di saturare la CPU se il frame non è ancora pronto
            continue

        current_time = time.time()
        
        # 1. TRACKING VEICOLI
        results = model_veicoli.track(frame, persist=True, classes=[2, 3, 5, 7], verbose=False, conf=0.4)
        
        if results and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.int().cpu().tolist()
            ids = results[0].boxes.id.int().cpu().tolist()

            for box, obj_id in zip(boxes, ids):
                # CHECK-IN
                if obj_id not in veicoli_attivi:
                    print(f"🆕 [CHECK-IN] Veicolo ID: {obj_id}")
                    log_evento(obj_id, "ENTRATA")
                
                veicoli_attivi[obj_id] = current_time # Aggiorna timestamp avvistamento
                
                # 2. RILEVAMENTO TARGA
                if obj_id not in targhe_salvate_per_id:
                    x1, y1, x2, y2 = box
                    roi = frame[max(0, y1):y2, max(0, x1):x2]
                    
                    if roi is not None and roi.size > 0:
                        res_t = model_targhe(roi, conf=0.3, verbose=False)
                        
                        if res_t and res_t[0].boxes is not None and len(res_t[0].boxes) > 0:
                            t_box = res_t[0].boxes.xyxy.int().cpu().tolist()[0]
                            tx1, ty1, tx2, ty2 = t_box
                            
                            plate_crop = roi[max(0, ty1-5):ty2+5, max(0, tx1-5):tx2+5]
                            
                            if plate_crop is not None and plate_crop.size > 0:
                                save_path = get_daily_dir()
                                filename = f"ID_{obj_id}_{datetime.now().strftime('%H%M%S')}.jpg"
                                cv2.imwrite(os.path.join(save_path, filename), plate_crop)
                                
                                print(f"📸 [TARGA] Salvata per ID: {obj_id} -> {filename}")
                                log_evento(obj_id, "TARGA_RILEVATA", filename)
                                targhe_salvate_per_id.add(obj_id)

                # ==========================================
                # DISEGNO PROFESSIONALE UI
                # ==========================================
                color = (255, 0, 0) # Blu
                cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), color, 2)

                label = f"Auto ID: {obj_id}"
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.5
                thickness = 1
                
                (w, h), baseline = cv2.getTextSize(label, font, font_scale, thickness)
                
                back_x1, back_y1 = box[0], box[1] - h - 10
                back_x2, back_y2 = box[0] + w + 10, box[1]
                
                # Evita che l'etichetta esca fuori dallo schermo in alto
                if back_y1 < 0:
                    back_y1, back_y2 = box[1], box[1] + h + 10

                cv2.rectangle(frame, (back_x1, back_y1), (back_x2, back_y2), color, -1)
                
                text_y = back_y2 - 5 if back_y1 == box[1] else back_y2 - 7
                cv2.putText(frame, label, (back_x1 + 5, text_y), 
                            font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

        # 3. GESTIONE CHECK-OUT
        ids_da_rimuovere = []
        for v_id, last_time in veicoli_attivi.items():
            if current_time - last_time > TIMEOUT_VEICOLO:
                ids_da_rimuovere.append(v_id)

        for s_id in ids_da_rimuovere:
            print(f"🏁 [CHECK-OUT] Veicolo ID: {s_id} uscito.")
            log_evento(s_id, "USCITA")
            # Metodo sicuro per rimuovere dai dizionari/set
            veicoli_attivi.pop(s_id, None)
            targhe_salvate_per_id.discard(s_id)

        # 4. OVERLAY GENERALE
        cv2.putText(frame, f"Veicoli: {len(veicoli_attivi)}", (15, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow("Monitor Check-In/Out", frame)

        # Chiusura con tasto 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except Exception as e:
    print(f"❌ Errore imprevisto nel main loop: {e}")

finally:
    print("\n🧹 Avvio procedura di chiusura sicura...")
    stream.stop()
    time.sleep(0.5) # Piccolo delay per permettere ai thread di morire in pace
    cv2.destroyAllWindows()
    print("✅ Risorse liberate. Log salvato in accessi_veicoli.csv.")