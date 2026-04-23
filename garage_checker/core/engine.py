"""
garage_checker/core/engine.py

Main orchestrator for the Garage Checker system.
"""

import cv2
import time
import threading
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from garage_checker.config import settings as cfg
from garage_checker.core.roi import ROIManager
from garage_checker.core.state import StateManager, VehicleState
from garage_checker.modules.detector import VehicleDetector
from garage_checker.modules.ocr_pipeline import OCRPipeline
from garage_checker.modules.notifier import TelegramNotifier
from garage_checker.modules.whitelist import WhitelistManager

class GarageEngine:
    def __init__(self):
        # Initialize modules
        self.roi_manager = ROIManager(Path(cfg.ROIS_FILE))
        self.state_manager = StateManager(timeout=cfg.TIMEOUT_VEHICLE, min_candidates=cfg.MIN_OCR_CANDIDATES)
        self.detector = VehicleDetector(cfg.MODEL_VEHICLES, cfg.TRACKER_CONFIG, cfg.DEVICE)
        self.ocr_pipeline = OCRPipeline(cfg.MODEL_PLATES, cfg.MODEL_OCR, cfg.DEVICE)
        
        self.whitelist = WhitelistManager(Path(cfg.WHITELIST_FILE))
        self.notifier = TelegramNotifier(cfg.TELEGRAM_TOKEN, cfg.TELEGRAM_CHAT_ID, self.whitelist)
        
        # Setup callbacks
        self.notifier.get_status = self.get_live_status
        self.notifier.on_skip = self._on_skip
        self.notifier.on_correction = self._on_correction
        self.notifier.on_registered = self._on_registered

        self.running = False
        self.frame = None
        self.frame_lock = threading.Lock()

    def get_live_status(self):
        active = self.state_manager.get_all_active()
        return {v.obj_id: v.final_plate for v in active}

    def _on_skip(self, plate: str):
        print(f"⏭ [SKIP] {plate} ignored.")

    def _on_correction(self, orig: str, corrected: str):
        # Update state if vehicle still active
        active = self.state_manager.get_all_active()
        for v in active:
            if v.final_plate == orig:
                v.final_plate = corrected
                print(f"✏️ [CORRECTION] ID {v.obj_id}: {orig} -> {corrected}")

    def _on_registered(self, plate: str, name: str, authorized: bool):
        # Trigger action if authorized vehicle was just registered
        if authorized:
            # Find vehicle with this plate
            active = self.state_manager.get_all_active()
            for v in active:
                if v.final_plate == plate and not v.action_triggered:
                    self._execute_action(plate, name)
                    v.action_triggered = True
                    self.notifier.send_message(f"🚗 *{name}* — Access allowed for `{plate}`")

    def _execute_action(self, plate: str, name: str):
        try:
            # Path to action script (placeholder)
            script_path = cfg.MODULE_DIR.parent / "targhe_auto" / "action_autorizzato.py"
            subprocess.Popen([sys.executable, str(script_path), plate, name])
            print(f"🚀 [ACTION] Triggered for {plate} ({name})")
        except Exception as e:
            print(f"⚠️ [ACTION] Error: {e}")

    def _finalize_best_candidate(self, vehicle: VehicleState):
        if not vehicle.ocr_results:
            return None
        
        # Logic to pick best candidate
        plates = [res["plate"] for res in vehicle.ocr_results if res["plate"]]
        if not plates: return None
        
        # Simple majority vote
        from collections import Counter
        counts = Counter(plates)
        best_plate = counts.most_common(1)[0][0]
        
        # Find best confidence for that plate
        best_conf = max(res["confidence"] for res in vehicle.ocr_results if res["plate"] == best_plate)
        
        # Find best variant/mode for logging
        best_res = next(res for res in vehicle.ocr_results if res["plate"] == best_plate and res["confidence"] == best_conf)
        
        return best_plate, best_conf, best_res

    def _save_plate_image(self, vehicle_id: int, plate: str, crop: np.ndarray):
        today = datetime.now().strftime("%Y-%m-%d")
        save_path = cfg.SAVE_DIR / today
        save_path.mkdir(parents=True, exist_ok=True)
        
        ts = datetime.now().strftime("%H%M%S%f")
        filename = f"ID_{vehicle_id}_{ts}_{plate}.jpg"
        file_path = save_path / filename
        cv2.imwrite(str(file_path), crop)
        return file_path

    def run(self):
        self.notifier.start()
        self.running = True
        
        cap = cv2.VideoCapture(cfg.RTSP_URL)
        print(f"🚀 Engine Started. Device: {cfg.DEVICE}")
        
        while self.running:
            ret, frame = cap.read()
            if not ret:
                print("⚠️ Stream lost, reconnecting...")
                cap.release()
                time.sleep(2)
                cap = cv2.VideoCapture(cfg.RTSP_URL)
                continue

            # 1. Detection & Tracking
            detections = self.detector.track(frame, conf=cfg.CONF_VEHICLES)
            
            current_time = time.time()
            active_ids = []

            for box, obj_id in detections:
                active_ids.append(obj_id)
                
                # 2. ROI Check
                roi_id = self.roi_manager.check_overlap(box, (frame.shape[1], frame.shape[0]))
                
                # 3. State Update
                is_new = self.state_manager.update_vehicle(obj_id, roi_id)
                if is_new:
                    print(f"🆕 [CHECK-IN] ID: {obj_id}")

                # 4. OCR Triggering (only if in ROI and not finalized)
                vehicle = self.state_manager.get_vehicle(obj_id)
                if vehicle and vehicle.roi_id is not None and not vehicle.is_ocr_done():
                    if len(vehicle.ocr_results) < cfg.MAX_OCR_ATTEMPTS:
                        # Extract vehicle crop
                        x1, y1, x2, y2 = box
                        vehicle_crop = frame[max(0, y1):y2, max(0, x1):x2]
                        
                        if vehicle_crop.size > 0:
                            res = self.ocr_pipeline.process_vehicle(vehicle_crop, cfg.DAY_HOURS)
                            if res and res["plate"]:
                                count = self.state_manager.add_ocr_candidate(obj_id, res)
                                print(f"📸 [OCR] ID:{obj_id} | {res['plate']} ({count}/{cfg.MIN_OCR_CANDIDATES}) conf={res['confidence']:.2f}")
                                
                                # Check if we can finalize
                                if count >= cfg.MIN_OCR_CANDIDATES:
                                    best_p, best_c, best_res = self._finalize_best_candidate(vehicle)
                                    self.state_manager.finalize_vehicle(obj_id, best_p, best_c)
                                    
                                    # Handle registration/whitelist
                                    entry = self.whitelist.get_entry(best_p)
                                    if entry:
                                        name = entry["nome"]
                                        if entry["autorizzato"] and not vehicle.action_triggered:
                                            self._execute_action(best_p, name)
                                            vehicle.action_triggered = True
                                            self.notifier.send_message(f"✅ *{name}* (Spot {vehicle.roi_id})\n🚗 `{best_p}` — conf: {best_c:.0%}")
                                        else:
                                            self.notifier.send_message(f"🚫 *{name}* access denied.\n🚗 `{best_p}`")
                                    else:
                                        # Unknown plate
                                        if best_p not in self.notifier.skipped_plates:
                                            img_path = self._save_plate_image(obj_id, best_p, best_res["crop"])
                                            self.notifier.send_unknown_plate_alert(best_p, str(img_path))

            # 5. Cleanup and Checkout
            expired = self.state_manager.cleanup_expired()
            for v in expired:
                # If vehicle left but we had some candidates not finalized
                if not v.is_ocr_done() and v.ocr_results:
                    best_p, best_c, best_res = self._finalize_best_candidate(v)
                    print(f"⌛ [TIMEOUT] ID:{v.obj_id} finalized with {best_p}")
                    # (Logic similar to above for finalizing...)
                
                print(f"🏁 [CHECK-OUT] ID:{v.obj_id}")

            # 6. Visualization (Simplified for now)
            if os.environ.get("DISPLAY"):
                display_frame = cv2.resize(frame, (cfg.DISPLAY_WIDTH, cfg.DISPLAY_HEIGHT))
                # Add ROI overlay
                for roi in self.roi_manager.get_all_rois():
                    cv2.rectangle(display_frame, (roi["x1"], roi["y1"]), (roi["x2"], roi["y2"]), (255, 255, 0), 2)
                
                cv2.imshow("Garage Checker", display_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        cap.release()
        cv2.destroyAllWindows()
