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
candidati_per_id    = {}  # { obj_id: [ {targa, nazione, conf, file_orig, file_proc}, ... ] }
notifiche_inviate   = set()
action_eseguita     = set()

# ==========================================
# UTILS
# ==========================================
def finalize_best_candidate(obj_id: int):
    """
    Analizza i candidati raccolti e sceglie il migliore.
    Ritorna (targa, nazione, conf, file_orig, file_proc) o None.
    """
    with _state_lock:
        lista = candidati_per_id.get(obj_id, [])

    if not lista:
        return None

    # 1. Conta frequenze
    frequenze = {}
    for c in lista:
        t = c['targa']
        frequenze[t] = frequenze.get(t, 0) + 1

    # 2. Trova la targa più frequente
    max_freq = max(frequenze.values())
    most_frequent_plates = [t for t, f in frequenze.items() if f == max_freq]

    # 3. Tra le più frequenti, prendi quella con conf media più alta
    best_targa = None
    best_avg_conf = -1.0

    for t in most_frequent_plates:
        confs = [c['conf'] for c in lista if c['targa'] == t]
        avg_conf = sum(confs) / len(confs)
        if avg_conf > best_avg_conf:
            best_avg_conf = avg_conf
            best_targa = t

    # 4. Recupera i dettagli del migliore (quello con conf assoluta più alta per quella targa)
    best_info = max([c for c in lista if c['targa'] == best_targa], key=lambda x: x['conf'])

    # Debug in terminale
    print(f"\n🏆 [FINALIZER] ID:{obj_id} | Vincitore: {best_targa} (freq:{max_freq}, conf_avg:{best_avg_conf:.2f})")
    print(f"📊 Tutti i tentativi per ID:{obj_id}:")
    for i, c in enumerate(lista):
        print(f"   [{i+1}] {c['targa']} | conf: {c['conf']:.2f} | {c['modalita']}")
    print("")

    # 5. Pulizia file: tieni solo l'originale del vincitore (o sposta se serve)
    # Per ora lasciamo che i file restino lì, ma in produzione potremmo cancellare gli altri.
    # Utente ha chiesto: "keep in the folder only the image that had the highest confidence score"
    for c in lista:
        if c['file_orig'] != best_info['file_orig'] and os.path.exists(c['file_orig']):
            try: os.remove(c['file_orig'])
            except: pass
        if c['file_proc'] != best_info['file_proc'] and os.path.exists(c['file_proc']):
            try: os.remove(c['file_proc'])
            except: pass

    return (best_info['targa'], best_info['nazione'], best_info['conf'], 
            best_info['file_orig'], best_info['file_proc'], best_info['modalita'])

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
                    tentativi_falliti  = stato if isinstance(stato, int) else 0
                    
                    candidati = candidati_per_id.get(obj_id, [])
                    num_candidati = len(candidati)
                    
                    da_elaborare = (not targa_ok and 
                                   num_candidati < cfg.MAX_CANDIDATI and 
                                   tentativi_falliti < cfg.MAX_TENTATIVI_OCR)

                if da_elaborare:
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

                                # Ensemble OCR: 2 varianti preprocessate → vince la confidence più alta
                                testo_targa, nazione, conf, variante_vincente = ocr_ensemble(ocr_model, va, vb)

                                if testo_targa:
                                    # Salva temporaneamente per debug/collezione
                                    save_dir      = get_daily_dir()
                                    ts            = datetime.now().strftime('%H%M%S%f')
                                    filename      = f"ID_{obj_id}_{ts}_{modalita}.jpg"
                                    orig_filepath = os.path.join(save_dir, f"ID_{obj_id}_{ts}_orig.jpg")
                                    proc_filepath = os.path.join(save_dir, filename)
                                    cv2.imwrite(orig_filepath, plate_crop)
                                    if variante_vincente is not None:
                                        cv2.imwrite(proc_filepath, variante_vincente)
                                    else:
                                        proc_filepath = orig_filepath

                                    with _state_lock:
                                        if obj_id not in candidati_per_id:
                                            candidati_per_id[obj_id] = []
                                        candidati_per_id[obj_id].append({
                                            'targa': testo_targa,
                                            'nazione': nazione,
                                            'conf': conf,
                                            'file_orig': orig_filepath,
                                            'file_proc': proc_filepath,
                                            'modalita': modalita
                                        })
                                        num_candidati = len(candidati_per_id[obj_id])

                                    print(f"📸 [OCR/{modalita}] ID:{obj_id} | {testo_targa} ({num_candidati}/{cfg.MAX_CANDIDATI}) conf={conf:.2f}")

                                    # Se abbiamo raggiunto il numero desiderato, finalizziamo subito
                                    if num_candidati >= cfg.MAX_CANDIDATI:
                                        res_final = finalize_best_candidate(obj_id)
                                        if res_final:
                                            best_t, best_n, best_c, best_orig, best_proc, best_mod = res_final
                                            
                                            entry = wl.get_entry(best_t)
                                            if entry:
                                                nome        = entry["nome"]
                                                autorizzato = entry["autorizzato"]
                                                wl.update_ultimo_accesso(best_t)
                                                log_evento(obj_id, "TARGA_RILEVATA", os.path.basename(best_proc),
                                                           best_t, best_n, nome, best_mod, best_c)

                                                if autorizzato:
                                                    print(f"✅ [AUTH] {nome} ({best_t})")
                                                    tg.send_message(
                                                        f"✅ *{nome}* ha effettuato il *check-in*\n"
                                                        f"🚗 `{best_t}` — conf: {best_c:.0%}"
                                                    )
                                                    with _state_lock:
                                                        already = obj_id in action_eseguita
                                                    if not already:
                                                        esegui_action(best_t, nome)
                                                        with _state_lock:
                                                            action_eseguita.add(obj_id)
                                                else:
                                                    print(f"🚫 [DENIED] {nome} ({best_t})")
                                                    tg.send_message(
                                                        f"🚫 *{nome}* (`{best_t}`) — accesso *negato*."
                                                    )
                                            else:
                                                log_evento(obj_id, "TARGA_SCONOSCIUTA", os.path.basename(best_proc),
                                                           best_t, best_n, "", best_mod, best_c)
                                                with _state_lock:
                                                    gia_notificata = (
                                                        best_t in notifiche_inviate
                                                        or tg.is_skippata(best_t)
                                                    )
                                                if not gia_notificata:
                                                    print(f"🔔 [TG] Alert sconosciuta: {best_t} conf={best_c:.2f}")
                                                    tg.send_unknown_plate_alert(best_t, best_orig)
                                                    with _state_lock:
                                                        notifiche_inviate.add(best_t)

                                            with _state_lock:
                                                targhe_lette_per_id[obj_id] = 'OK'
                                                targa_per_id[obj_id]        = best_t
                                else:
                                    # Nessuna lettura valida da entrambe le varianti
                                    with _state_lock:
                                        targhe_lette_per_id[obj_id] = tentativi_falliti + 1
                        else:
                            with _state_lock:
                                targhe_lette_per_id[obj_id] = tentativi_falliti + 1

                # ── 3. UI ─────────────────────────────────────────────────────
                with _state_lock:
                    stato_ui  = targhe_lette_per_id.get(obj_id)
                    targa_str = targa_per_id.get(obj_id, "")
                    candidati = candidati_per_id.get(obj_id, [])
                    num_candidati = len(candidati)

                letta_ok_ui = stato_ui == 'OK'
                esauriti_ui = isinstance(stato_ui, int) and stato_ui >= cfg.MAX_TENTATIVI_OCR

                if letta_ok_ui:
                    entry = wl.get_entry(targa_str) if targa_str else None
                    if entry and entry["autorizzato"]:
                        color, label = (0, 220, 0),   f"ID:{obj_id} [OK] {entry['nome']}"
                    elif entry:
                        color, label = (0, 0, 220),   f"ID:{obj_id} [NO] {entry['nome']}"
                    else:
                        color, label = (200, 200, 0), f"ID:{obj_id} [?] {targa_str}"
                elif esauriti_ui:
                    color, label = (0, 165, 255), f"ID:{obj_id} | Non leggibile"
                else:
                    # Mostra progresso raccolta frame
                    color, label = (255, 100, 0), f"ID:{obj_id} | Lettura ({num_candidati}/{cfg.MAX_CANDIDATI})"

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
            # Se il veicolo esce e avevamo dei candidati ma non abbiamo ancora finalizzato 'OK'
            with _state_lock:
                gia_ok = targhe_lette_per_id.get(s_id) == 'OK'
                ha_candidati = len(candidati_per_id.get(s_id, [])) > 0
            
            if not gia_ok and ha_candidati:
                print(f"⌛ [TIMEOUT] ID:{s_id} uscito prima di {cfg.MAX_CANDIDATI} frame. Finalizzo il meglio che ho...")
                res_final = finalize_best_candidate(s_id)
                if res_final:
                    best_t, best_n, best_c, best_orig, best_proc, best_mod = res_final
                    # Log evento finale (se non già fatto)
                    entry = wl.get_entry(best_t)
                    nome = entry["nome"] if entry else "Sconosciuto"
                    log_evento(s_id, "TARGA_RILEVATA_TIMEOUT", os.path.basename(best_proc),
                               best_t, best_n, nome, best_mod, best_c)
                    with _state_lock:
                        targa_per_id[s_id] = best_t

            with _state_lock:
                t_uscita = targa_per_id.get(s_id, "")
                veicoli_attivi.pop(s_id, None)
                targhe_lette_per_id.pop(s_id, None)
                targa_per_id.pop(s_id, None)
                candidati_per_id.pop(s_id, None) # Pulisce la collezione
                action_eseguita.discard(s_id)
                notifiche_inviate.discard(t_uscita)

            entry = wl.get_entry(t_uscita) if t_uscita else None
            nome  = entry["nome"] if entry else "Sconosciuto"
            label = t_uscita or "N/D"
            print(f"🏁 [CHECK-OUT] ID:{s_id} | {label} ({nome})")
            log_evento(s_id, "USCITA", testo_targa=label, nome_proprietario=nome)

            if entry:
                if t_uscita:
                    wl.update_ultima_uscita(t_uscita)
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