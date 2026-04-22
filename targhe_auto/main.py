"""
targhe_auto/main.py
Entry point — rilevamento veicoli, OCR targhe, whitelist, notifiche Telegram.
Modalità: SVILUPPO
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

from ultralytics import YOLO
from fast_plate_ocr import LicensePlateRecognizer

sys.path.insert(0, os.path.dirname(__file__))

import config as cfg
import telegram_bot as tg
import whitelist_manager as wl
from plate_processor import processa_targa, ocr_ensemble

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
# STATO GLOBALE
# ==========================================
_state_lock         = threading.Lock()
veicoli_attivi      = {}
targhe_lette_per_id = {}
targa_per_id        = {}
notifiche_inviate   = set()
action_eseguita     = set()

# ==========================================
# STREAMING RTSP
# ==========================================
class RTSPStreamer:
    def __init__(self, url: str):
        self.url     = url
        self.cap     = cv2.VideoCapture(url)
        self.stopped = False
        self.ret     = False
        self.frame   = None
        self.lock    = threading.Lock()
        print("✅ Stream connesso." if self.cap.isOpened() else "❌ Impossibile connettersi.")
        threading.Thread(target=self._update, daemon=True, name="RTSPReader").start()

    def _update(self):
        while not self.stopped:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                print("⚠️ Stream perso — riconnessione...")
                self.cap.release()
                time.sleep(2)
                self.cap = cv2.VideoCapture(self.url)
                print("✅ Riconnessione riuscita!" if self.cap.isOpened() else "❌ Ritento...")
                continue
            with self.lock:
                self.ret, self.frame = ret, frame.copy()

    def read(self):
        with self.lock:
            return (False, None) if self.frame is None else (self.ret, self.frame.copy())

    def stop(self):
        self.stopped = True
        time.sleep(0.3)
        self.cap.release()

# ==========================================
# UTILS
# ==========================================
def get_daily_dir() -> str:
    path = os.path.join(cfg.BASE_SAVE_DIR, datetime.now().strftime("%Y-%m-%d"))
    os.makedirs(path, exist_ok=True)
    return path


def log_evento(veicolo_id, azione, targa_file="", testo_targa="",
               nazione="", nome_proprietario="", modalita_ocr="", confidence=0.0):
    file_exists = os.path.isfile(cfg.LOG_FILE)
    with open(cfg.LOG_FILE, mode='a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "ID_Veicolo", "Evento", "File_Targa",
                             "Testo_Targa", "Nazione", "Proprietario", "Modalita_OCR", "Confidence"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            veicolo_id, azione, targa_file, testo_targa,
            nazione, nome_proprietario, modalita_ocr, f"{confidence:.3f}"
        ])


def esegui_action(targa: str, nome: str):
    try:
        subprocess.Popen(
            [sys.executable, cfg.ACTION_SCRIPT, targa, nome],
            stdout=sys.stdout, stderr=sys.stderr,
        )
        print(f"🚀 [ACTION] {targa} ({nome})")
    except Exception as e:
        print(f"⚠️ [ACTION] {e}")


# ==========================================
# CALLBACK PER IL BOT
# ==========================================
def _get_stato_live() -> dict:
    with _state_lock:
        return {oid: targa_per_id.get(oid) for oid in veicoli_attivi}


def _on_targa_registrata(targa: str, nome: str, autorizzato: bool):
    with _state_lock:
        id_attivi = [v for v, t in targa_per_id.items() if t == targa]
    if autorizzato and id_attivi:
        esegui_action(targa, nome)
        tg.send_message(f"🚗 *{nome}* — accesso consentito per `{targa}`")
    elif not autorizzato:
        tg.send_message(f"🚫 *{nome}* (`{targa}`) — accesso negato registrato.")


def _on_skip(targa: str):
    with _state_lock:
        notifiche_inviate.add(targa)
    print(f"⏭ [SKIP] {targa} ignorata per questa sessione.")


def _on_correction(targa_originale: str, targa_corretta: str):
    with _state_lock:
        for obj_id, t in list(targa_per_id.items()):
            if t == targa_originale:
                targa_per_id[obj_id] = targa_corretta
                print(f"✏️ [CORRECTION] ID {obj_id}: {targa_originale} → {targa_corretta}")
        notifiche_inviate.discard(targa_corretta)


# ==========================================
# CTRL+C
# ==========================================
def _signal_handler(sig, frame):
    print("\n🛑 Chiusura sicura...")
    stream.stop()
    cv2.destroyAllWindows()
    sys.exit(0)

signal.signal(signal.SIGINT, _signal_handler)

# ==========================================
# AVVIO SERVIZI
# ==========================================
tg.set_on_registered_callback(_on_targa_registrata)
tg.set_on_skip_callback(_on_skip)
tg.set_on_correction_callback(_on_correction)
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

        # ── 1. TRACKING ──────────────────────────────────────────────────────
        results = model_veicoli.track(
            frame, persist=True, tracker=cfg.TRACKER_CONFIG,
            classes=cfg.VEHICLE_CLASSES, verbose=False, conf=cfg.CONF_VEICOLI,
        )

        if results and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.int().cpu().tolist()
            ids   = results[0].boxes.id.int().cpu().tolist()

            for box, obj_id in zip(boxes, ids):

                # CHECK-IN
                with _state_lock:
                    is_new = obj_id not in veicoli_attivi
                    veicoli_attivi[obj_id] = current_time

                if is_new:
                    print(f"🆕 [CHECK-IN] ID: {obj_id}")
                    log_evento(obj_id, "ENTRATA")

                # ── 2. OCR ───────────────────────────────────────────────────
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
                            pad = cfg.PLATE_PAD_PX
                            plate_crop = roi[
                                max(0, ty1 - pad):min(roi.shape[0], ty2 + pad),
                                max(0, tx1 - pad):min(roi.shape[1], tx2 + pad),
                            ]

                            if plate_crop is not None and plate_crop.size > 0:
                                # Pre-processing adattivo → 2 varianti
                                va, vb, modalita, metrics = processa_targa(plate_crop)

                                print(
                                    f"🔬 [PP/{modalita}] ID:{obj_id} "
                                    f"bright={metrics['brightness']:.0f} "
                                    f"contrast={metrics['contrast']:.0f} "
                                    f"noise={metrics['noise']:.0f}"
                                )

                                # Ensemble OCR: 2 varianti preprocessate → vince la confidence più alta
                                testo_targa, nazione, conf, variante_vincente = ocr_ensemble(ocr_model, va, vb)

                                if testo_targa:
                                    print(f"📸 [OCR/{modalita}] ID:{obj_id} | {testo_targa} ({nazione}) conf={conf:.2f}")

                                    # Salva su disco solo quando OCR ha successo → meno file
                                    # orig = crop grezzo (per consultazione umana e per alert Telegram)
                                    # proc = variante che ha vinto l'ensemble (per debug preprocessing)
                                    save_dir      = get_daily_dir()
                                    ts            = datetime.now().strftime('%H%M%S%f')
                                    filename      = f"ID_{obj_id}_{ts}_{modalita}.jpg"
                                    orig_filepath = os.path.join(save_dir, f"ID_{obj_id}_{ts}_orig.jpg")
                                    proc_filepath = os.path.join(save_dir, filename)
                                    cv2.imwrite(orig_filepath, plate_crop)
                                    if variante_vincente is not None:
                                        cv2.imwrite(proc_filepath, variante_vincente)

                                    entry = wl.get_entry(testo_targa)

                                    if entry:
                                        nome        = entry["nome"]
                                        autorizzato = entry["autorizzato"]
                                        wl.update_ultimo_accesso(testo_targa)
                                        log_evento(obj_id, "TARGA_RILEVATA", filename,
                                                   testo_targa, nazione, nome, modalita, conf)

                                        if autorizzato:
                                            print(f"✅ [AUTH] {nome} ({testo_targa})")
                                            tg.send_message(
                                                f"✅ *{nome}* ha effettuato il *check-in*\n"
                                                f"🚗 `{testo_targa}` — conf: {conf:.0%}"
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
                                        # Targa sconosciuta
                                        log_evento(obj_id, "TARGA_SCONOSCIUTA", filename,
                                                   testo_targa, nazione, "", modalita, conf)
                                        with _state_lock:
                                            gia_notificata = (
                                                testo_targa in notifiche_inviate
                                                or tg.is_skippata(testo_targa)
                                            )
                                        if not gia_notificata:
                                            print(f"🔔 [TG] Alert sconosciuta: {testo_targa} conf={conf:.2f}")
                                            tg.send_unknown_plate_alert(testo_targa, orig_filepath)
                                            with _state_lock:
                                                notifiche_inviate.add(testo_targa)

                                    with _state_lock:
                                        targhe_lette_per_id[obj_id] = 'OK'
                                        targa_per_id[obj_id]        = testo_targa
                                else:
                                    # Nessuna lettura valida da entrambe le varianti
                                    with _state_lock:
                                        targhe_lette_per_id[obj_id] = tentativi + 1
                        else:
                            with _state_lock:
                                targhe_lette_per_id[obj_id] = tentativi + 1

                # ── 3. UI ─────────────────────────────────────────────────────
                with _state_lock:
                    stato_ui  = targhe_lette_per_id.get(obj_id)
                    targa_str = targa_per_id.get(obj_id, "")

                letta_ok_ui = stato_ui == 'OK'
                esauriti_ui = isinstance(stato_ui, int) and stato_ui >= cfg.MAX_TENTATIVI_OCR

                if letta_ok_ui:
                    entry = wl.get_entry(targa_str) if targa_str else None
                    if entry and entry["autorizzato"]:
                        color, label = (0, 220, 0),   f"ID:{obj_id} ✅ {entry['nome']}"
                    elif entry:
                        color, label = (0, 0, 220),   f"ID:{obj_id} 🚫 {entry['nome']}"
                    else:
                        color, label = (200, 200, 0), f"ID:{obj_id} ❓ {targa_str}"
                elif esauriti_ui:
                    color, label = (0, 165, 255), f"ID:{obj_id} | Non leggibile"
                else:
                    # Mostra tentativi rimasti per debug visivo
                    rim = cfg.MAX_TENTATIVI_OCR - (stato_ui or 0)
                    color, label = (255, 100, 0), f"ID:{obj_id} | Ricerca ({rim})"

                cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), color, 2)
                font = cv2.FONT_HERSHEY_SIMPLEX
                (w, h), _ = cv2.getTextSize(label, font, 0.5, 1)
                bx1, by1  = box[0], box[1] - h - 10
                bx2, by2  = box[0] + w + 10, box[1]
                if by1 < 0: by1, by2 = box[1], box[1] + h + 10
                cv2.rectangle(frame, (bx1, by1), (bx2, by2), color, -1)
                cv2.putText(frame, label, (bx1 + 5, by2 - 5),
                            font, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

        # ── 4. CHECK-OUT ─────────────────────────────────────────────────────
        with _state_lock:
            usciti = [v for v, t in veicoli_attivi.items()
                      if current_time - t > cfg.TIMEOUT_VEICOLO]

        for s_id in usciti:
            with _state_lock:
                t_uscita = targa_per_id.get(s_id, "")
                veicoli_attivi.pop(s_id, None)
                targhe_lette_per_id.pop(s_id, None)
                targa_per_id.pop(s_id, None)
                action_eseguita.discard(s_id)
                notifiche_inviate.discard(t_uscita)

            entry = wl.get_entry(t_uscita) if t_uscita else None
            nome  = entry["nome"] if entry else "Sconosciuto"
            label = t_uscita or "N/D"
            print(f"🏁 [CHECK-OUT] ID:{s_id} | {label} ({nome})")
            log_evento(s_id, "USCITA", testo_targa=label, nome_proprietario=nome)

            if entry:
                e = "✅" if entry["autorizzato"] else "🚫"
                tg.send_message(f"{e} *{nome}* check-out\n🚗 `{label}`")

        # ── 5. OVERLAY ───────────────────────────────────────────────────────
        with _state_lock:
            n = len(veicoli_attivi)

        cv2.putText(frame, f"Veicoli: {n}", (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, datetime.now().strftime("%H:%M:%S"), (15, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        frame = cv2.resize(frame, (cfg.DISPLAY_WIDTH, cfg.DISPLAY_HEIGHT))
        cv2.imshow("VisionEdge — Targhe Auto", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except Exception as e:
    print(f"❌ Errore main loop: {e}")
    traceback.print_exc()

finally:
    print("\n🧹 Chiusura...")
    stream.stop()
    time.sleep(0.5)
    cv2.destroyAllWindows()
    print("✅ Fatto.")