"""
targhe_auto/main.py
Entry point — rilevamento veicoli, OCR targhe, whitelist, notifiche Telegram.
Modalità: SVILUPPO (log su terminale)

Avvio:  python targhe_auto/main.py
        oppure, dalla cartella targhe_auto/:  python main.py
"""

import cv2
import os
import sys
import time
import threading
import csv
import signal
import subprocess
import traceback
from datetime import datetime

import torch
from ultralytics import YOLO
from fast_plate_ocr import LicensePlateRecognizer

# Assicura che i moduli della stessa cartella siano trovati
sys.path.insert(0, os.path.dirname(__file__))

import config as cfg
import telegram_bot as tg
import whitelist_manager as wl

# ==========================================
# CARICAMENTO MODELLI
# ==========================================
print(f"🔧 Device: {cfg.DEVICE.upper()}")
model_veicoli = YOLO(cfg.MODEL_VEICOLI).to(cfg.DEVICE)
model_targhe  = YOLO(cfg.MODEL_TARGHE).to(cfg.DEVICE)

print("⏳ Caricamento modello OCR...")
ocr_model = LicensePlateRecognizer(cfg.MODEL_OCR)
print("✅ OCR caricato!")

# ==========================================
# STATO GLOBALE (protetto da lock)
# ==========================================
_state_lock         = threading.Lock()
veicoli_attivi      = {}   # { obj_id: last_seen_timestamp }
targhe_lette_per_id = {}   # { obj_id: 'OK' | int(tentativi) }
targa_per_id        = {}   # { obj_id: targa_str }
notifiche_inviate   = set()
action_eseguita     = set()

# ==========================================
# STREAMING RTSP
# ==========================================
class RTSPStreamer:
    def __init__(self, url: str):
        self.url     = url
        self.cap     = cv2.VideoCapture(url)
        self.ret     = False
        self.frame   = None
        self.stopped = False
        self.lock    = threading.Lock()

        print("✅ Stream connesso." if self.cap.isOpened() else "❌ Impossibile connettersi allo stream RTSP.")

        self.thread = threading.Thread(target=self._update, daemon=True, name="RTSPReader")
        self.thread.start()

    def _update(self):
        while not self.stopped:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                print("⚠️ Stream perso — riconnessione...")
                self.cap.release()
                time.sleep(2)
                self.cap = cv2.VideoCapture(self.url)
                print("✅ Riconnessione riuscita!" if self.cap.isOpened() else "❌ Riconnessione fallita, nuovo tentativo...")
                continue
            with self.lock:
                self.ret   = ret
                self.frame = frame.copy()

    def read(self):
        with self.lock:
            if self.frame is None:
                return False, None
            return self.ret, self.frame.copy()

    def stop(self):
        self.stopped = True
        if self.thread.is_alive():
            self.thread.join(timeout=2)
        self.cap.release()

# ==========================================
# UTILS
# ==========================================
def get_daily_dir() -> str:
    path = os.path.join(cfg.BASE_SAVE_DIR, datetime.now().strftime("%Y-%m-%d"))
    os.makedirs(path, exist_ok=True)
    return path


def log_evento(veicolo_id: int, azione: str, targa_file="",
               testo_targa="", nazione="", nome_proprietario=""):
    file_exists = os.path.isfile(cfg.LOG_FILE)
    with open(cfg.LOG_FILE, mode='a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "ID_Veicolo", "Evento",
                             "File_Targa", "Testo_Targa", "Nazione", "Proprietario"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            veicolo_id, azione, targa_file, testo_targa, nazione, nome_proprietario
        ])


def esegui_action(targa: str, nome: str):
    """Esegue action_autorizzato.py in background."""
    try:
        subprocess.Popen(
            [sys.executable, cfg.ACTION_SCRIPT, targa, nome],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        print(f"🚀 [ACTION] Script avviato per {targa} ({nome})")
    except Exception as e:
        print(f"⚠️ [ACTION] Errore avvio script: {e}")


# ==========================================
# CALLBACK PER IL BOT TELEGRAM
# ==========================================
def _get_stato_live() -> dict:
    """Snapshot thread-safe dello stato garage per /stato."""
    with _state_lock:
        return {obj_id: targa_per_id.get(obj_id) for obj_id in veicoli_attivi}


def _on_targa_registrata(targa: str, nome: str, autorizzato: bool):
    """Chiamata dal bot dopo che l'utente ha salvato la targa."""
    with _state_lock:
        id_attivi = [vid for vid, t in targa_per_id.items() if t == targa]

    if autorizzato and id_attivi:
        esegui_action(targa, nome)
        tg.send_message(f"🚗 *{nome}* — accesso consentito per `{targa}`")
    elif not autorizzato:
        tg.send_message(f"🚫 *{nome}* (`{targa}`) — accesso negato registrato.")

# ==========================================
# CTRL+C HANDLER
# ==========================================
def _signal_handler(sig, frame):
    print("\n🛑 Chiusura sicura in corso...")
    stream.stop()
    cv2.destroyAllWindows()
    sys.exit(0)

signal.signal(signal.SIGINT, _signal_handler)

# ==========================================
# AVVIO SERVIZI
# ==========================================
tg.set_on_registered_callback(_on_targa_registrata)
tg.set_get_stato_callback(_get_stato_live)
tg.start_bot()

stream = RTSPStreamer(cfg.RTSP_URL)
print(f"🚀 Sistema avviato su {cfg.DEVICE.upper()}. Premi 'q' per uscire.")

# ==========================================
# MAIN LOOP
# ==========================================
try:
    while True:
        ret, frame = stream.read()
        if frame is None:
            time.sleep(0.01)
            continue

        current_time = time.time()

        # ── 1. TRACKING VEICOLI ──────────────────────────────────────────────
        results = model_veicoli.track(
            frame,
            persist=True,
            tracker=cfg.TRACKER_CONFIG,
            classes=cfg.VEHICLE_CLASSES,
            verbose=False,
            conf=cfg.CONF_VEICOLI,
        )

        if results and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.int().cpu().tolist()
            ids   = results[0].boxes.id.int().cpu().tolist()

            for box, obj_id in zip(boxes, ids):

                # ── CHECK-IN ─────────────────────────────────────────────────
                with _state_lock:
                    is_new = obj_id not in veicoli_attivi
                    veicoli_attivi[obj_id] = current_time

                if is_new:
                    print(f"🆕 [CHECK-IN] Veicolo ID: {obj_id}")
                    log_evento(obj_id, "ENTRATA")

                # ── 2. OCR TARGA ─────────────────────────────────────────────
                with _state_lock:
                    stato              = targhe_lette_per_id.get(obj_id)
                    targa_ok           = stato == 'OK'
                    tentativi          = stato if isinstance(stato, int) else 0
                    tentativi_esauriti = isinstance(stato, int) and stato >= cfg.MAX_TENTATIVI_OCR

                if not targa_ok and not tentativi_esauriti:
                    x1, y1, x2, y2 = box
                    roi = frame[max(0, y1):y2, max(0, x1):x2]

                    if roi is not None and roi.size > 0:
                        res_t = model_targhe(roi, conf=cfg.CONF_TARGA, verbose=False)

                        if res_t and res_t[0].boxes is not None and len(res_t[0].boxes) > 0:
                            tx1, ty1, tx2, ty2 = res_t[0].boxes.xyxy.int().cpu().tolist()[0]

                            pad       = cfg.PLATE_PAD_PX
                            plate_crop = roi[
                                max(0, ty1 - pad) : min(roi.shape[0], ty2 + pad),
                                max(0, tx1 - pad) : min(roi.shape[1], tx2 + pad),
                            ]

                            if plate_crop is not None and plate_crop.size > 0:
                                # Pre-processing
                                plate_up = cv2.resize(plate_crop, None,
                                                      fx=cfg.PLATE_UPSCALE, fy=cfg.PLATE_UPSCALE,
                                                      interpolation=cv2.INTER_LANCZOS4)
                                gray     = cv2.cvtColor(plate_up, cv2.COLOR_BGR2GRAY)
                                clahe    = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                                enhanced = clahe.apply(gray)
                                denoised = cv2.bilateralFilter(enhanced, 5, 30, 30)
                                blur     = cv2.GaussianBlur(denoised, (0, 0), 1)
                                sharp    = cv2.addWeighted(denoised, 1.5, blur, -0.5, 0)

                                filename      = f"ID_{obj_id}_{datetime.now().strftime('%H%M%S%f')}.jpg"
                                full_filepath = os.path.join(get_daily_dir(), filename)
                                cv2.imwrite(full_filepath, sharp)
                                cv2.imwrite(full_filepath.replace('.jpg', '_orig.jpg'), plate_crop)

                                try:
                                    ocr_results = ocr_model.run(full_filepath)

                                    if ocr_results:
                                        pred        = ocr_results[0]
                                        testo_targa = pred.plate.upper()
                                        nazione     = pred.region

                                        if len(testo_targa) >= 5:
                                            print(f"📸 [OCR OK] ID: {obj_id} | {testo_targa} ({nazione})")
                                            entry = wl.get_entry(testo_targa)

                                            if entry:
                                                nome        = entry["nome"]
                                                autorizzato = entry["autorizzato"]
                                                wl.update_ultimo_accesso(testo_targa)
                                                log_evento(obj_id, "TARGA_RILEVATA", filename,
                                                           testo_targa, nazione, nome)

                                                if autorizzato:
                                                    print(f"✅ [AUTH] {nome} ({testo_targa})")
                                                    tg.send_message(
                                                        f"✅ *{nome}* ha effettuato il *check-in*\n"
                                                        f"🚗 Targa: `{testo_targa}`"
                                                    )
                                                    with _state_lock:
                                                        already = obj_id in action_eseguita
                                                    if not already:
                                                        esegui_action(testo_targa, nome)
                                                        with _state_lock:
                                                            action_eseguita.add(obj_id)
                                                else:
                                                    print(f"🚫 [DENIED] {nome} ({testo_targa})")
                                                    tg.send_message(
                                                        f"🚫 *{nome}* (`{testo_targa}`) — accesso *negato*."
                                                    )
                                            else:
                                                log_evento(obj_id, "TARGA_SCONOSCIUTA", filename,
                                                           testo_targa, nazione)
                                                with _state_lock:
                                                    gia_notificata = testo_targa in notifiche_inviate
                                                if not gia_notificata:
                                                    print(f"🔔 [TG] Alert targa sconosciuta: {testo_targa}")
                                                    tg.send_unknown_plate_alert(testo_targa)
                                                    with _state_lock:
                                                        notifiche_inviate.add(testo_targa)

                                            with _state_lock:
                                                targhe_lette_per_id[obj_id] = 'OK'
                                                targa_per_id[obj_id]        = testo_targa
                                        else:
                                            with _state_lock:
                                                targhe_lette_per_id[obj_id] = tentativi + 1
                                            if os.path.exists(full_filepath):
                                                os.remove(full_filepath)
                                    else:
                                        with _state_lock:
                                            targhe_lette_per_id[obj_id] = tentativi + 1
                                        if os.path.exists(full_filepath):
                                            os.remove(full_filepath)

                                except Exception as e:
                                    print(f"⚠️ Errore OCR ID {obj_id}: {e}")
                                    with _state_lock:
                                        targhe_lette_per_id[obj_id] = tentativi + 1
                                    if os.path.exists(full_filepath):
                                        os.remove(full_filepath)
                        else:
                            with _state_lock:
                                targhe_lette_per_id[obj_id] = tentativi + 1

                # ── 3. DISEGNO UI ─────────────────────────────────────────────
                with _state_lock:
                    stato_ui   = targhe_lette_per_id.get(obj_id)
                    targa_str  = targa_per_id.get(obj_id, "")

                letta_ok_ui           = stato_ui == 'OK'
                tentativi_esauriti_ui = isinstance(stato_ui, int) and stato_ui >= cfg.MAX_TENTATIVI_OCR

                if letta_ok_ui:
                    entry = wl.get_entry(targa_str) if targa_str else None
                    if entry and entry["autorizzato"]:
                        color = (0, 220, 0)
                        label = f"ID:{obj_id} ✅ {entry['nome']}"
                    elif entry:
                        color = (0, 0, 220)
                        label = f"ID:{obj_id} 🚫 {entry['nome']}"
                    else:
                        color = (200, 200, 0)
                        label = f"ID:{obj_id} ❓ {targa_str}"
                elif tentativi_esauriti_ui:
                    color = (0, 165, 255)
                    label = f"ID:{obj_id} | Non leggibile"
                else:
                    color = (255, 100, 0)
                    label = f"ID:{obj_id} | Ricerca..."

                cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), color, 2)
                font       = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.5
                (w, h), _  = cv2.getTextSize(label, font, font_scale, 1)
                bx1, by1   = box[0], box[1] - h - 10
                bx2, by2   = box[0] + w + 10, box[1]
                if by1 < 0:
                    by1, by2 = box[1], box[1] + h + 10
                cv2.rectangle(frame, (bx1, by1), (bx2, by2), color, -1)
                text_y = by2 - 5 if by1 == box[1] else by2 - 7
                cv2.putText(frame, label, (bx1 + 5, text_y),
                            font, font_scale, (255, 255, 255), 1, cv2.LINE_AA)

        # ── 4. CHECK-OUT ─────────────────────────────────────────────────────
        with _state_lock:
            ids_da_rimuovere = [
                v_id for v_id, last_time in veicoli_attivi.items()
                if current_time - last_time > cfg.TIMEOUT_VEICOLO
            ]

        for s_id in ids_da_rimuovere:
            with _state_lock:
                targa_uscita = targa_per_id.get(s_id, "")
                veicoli_attivi.pop(s_id, None)
                targhe_lette_per_id.pop(s_id, None)
                targa_per_id.pop(s_id, None)
                action_eseguita.discard(s_id)
                notifiche_inviate.discard(targa_uscita)

            entry        = wl.get_entry(targa_uscita) if targa_uscita else None
            nome_uscita  = entry["nome"] if entry else "Sconosciuto"
            targa_label  = targa_uscita or "N/D"

            print(f"🏁 [CHECK-OUT] ID: {s_id} | {targa_label} ({nome_uscita})")
            log_evento(s_id, "USCITA", testo_targa=targa_label, nome_proprietario=nome_uscita)

            if entry:
                emoji = "✅" if entry["autorizzato"] else "🚫"
                tg.send_message(
                    f"{emoji} *{nome_uscita}* ha effettuato il *check-out*\n"
                    f"🚗 Targa: `{targa_label}`"
                )

        # ── 5. OVERLAY ───────────────────────────────────────────────────────
        with _state_lock:
            n_attivi = len(veicoli_attivi)

        cv2.putText(frame, f"Veicoli: {n_attivi}", (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, datetime.now().strftime("%H:%M:%S"), (15, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        frame = cv2.resize(frame, (cfg.DISPLAY_WIDTH, cfg.DISPLAY_HEIGHT))
        cv2.imshow("VisionEdge — Targhe Auto", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except Exception as e:
    print(f"❌ Errore imprevisto nel main loop: {e}")
    traceback.print_exc()

finally:
    print("\n🧹 Chiusura sicura...")
    stream.stop()
    time.sleep(0.5)
    cv2.destroyAllWindows()
    print("✅ Risorse liberate.")