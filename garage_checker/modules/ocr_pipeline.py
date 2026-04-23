"""
garage_checker/modules/ocr_pipeline.py

Pipeline for license plate detection and recognition.
Includes preprocessing and ensemble voting.
"""

import os
import tempfile
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
from ultralytics import YOLO
from fast_plate_ocr import LicensePlateRecognizer

class OCRPipeline:
    def __init__(self, plate_model_path: str, ocr_model_name: str, device: str = "cpu"):
        self.plate_model = YOLO(plate_model_path).to(device)
        self.ocr_model = LicensePlateRecognizer(ocr_model_name)
        self.device = device

    def detect_plate(self, vehicle_crop: np.ndarray, conf: float = 0.4):
        """Detects plate within vehicle crop."""
        results = self.plate_model(vehicle_crop, conf=conf, verbose=False)
        if results and results[0].boxes:
            # Return first detection
            box = results[0].boxes.xyxy.int().cpu().tolist()[0]
            return box
        return None

    def preprocess(self, plate_crop: np.ndarray, day_hours: tuple = (7, 20)):
        """Preprocesses plate crop based on day/night metrics."""
        # Upscale
        h, w = plate_crop.shape[:2]
        plate_up = cv2.resize(plate_crop, (w*3, h*3), interpolation=cv2.INTER_LANCZOS4)
        
        gray = cv2.cvtColor(plate_up, cv2.COLOR_BGR2GRAY)
        
        # Analyze metrics
        brightness = float(np.mean(gray))
        
        # Day/Night decision
        now_hour = datetime.now().hour
        is_night = not (day_hours[0] <= now_hour < day_hours[1])
        if not is_night and brightness < 40: # Extremely dark day
            is_night = True

        if is_night:
            # Night variants
            return self._variant_night_a(gray), self._variant_night_b(gray), "night"
        else:
            # Day variants
            return plate_up, self._variant_day_b(gray), "day"

    def _variant_day_b(self, gray: np.ndarray) -> np.ndarray:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        denoised = cv2.bilateralFilter(enhanced, 5, 20, 20)
        blur = cv2.GaussianBlur(denoised, (0, 0), 1)
        return cv2.addWeighted(denoised, 1.5, blur, -0.5, 0)

    def _variant_night_a(self, gray: np.ndarray) -> np.ndarray:
        denoised = cv2.bilateralFilter(gray, 7, 25, 25)
        clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(4, 4))
        enhanced = clahe.apply(denoised)
        lut = np.array([min(255, int((i / 255.0) ** 0.65 * 255)) for i in range(256)], dtype=np.uint8)
        gamma = cv2.LUT(enhanced, lut)
        blur = cv2.GaussianBlur(gamma, (0, 0), 1.0)
        return cv2.addWeighted(gamma, 1.3, blur, -0.3, 0)

    def _variant_night_b(self, gray: np.ndarray) -> np.ndarray:
        denoised = cv2.bilateralFilter(gray, 9, 35, 35)
        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(4, 4))
        enhanced = clahe.apply(denoised)
        blur = cv2.GaussianBlur(enhanced, (0, 0), 0.8)
        return cv2.addWeighted(enhanced, 1.2, blur, -0.2, 0)

    def run_ocr_ensemble(self, variant_a: np.ndarray, variant_b: np.ndarray):
        """Runs OCR on two variants and returns the best result."""
        best_plate = ""
        best_conf = 0.0
        best_variant = None

        for variant in (variant_a, variant_b):
            tmp_path = None
            try:
                fd, tmp_path = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                cv2.imwrite(tmp_path, variant)

                results = self.ocr_model.run(tmp_path, return_confidence=True)
                if not results:
                    continue

                pred = results[0]
                text = pred.plate.upper() if pred.plate else ""
                conf = float(np.mean(pred.char_probs)) if pred.char_probs is not None else 0.0

                if len(text) >= 5 and conf > best_conf:
                    best_plate = text
                    best_conf = conf
                    best_variant = variant

            except Exception as e:
                print(f"⚠️ OCR Error: {e}")
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)

        return best_plate, best_conf, best_variant

    def process_vehicle(self, vehicle_crop: np.ndarray, day_hours: tuple):
        """Full pipeline: Detect -> Preprocess -> OCR."""
        plate_box = self.detect_plate(vehicle_crop)
        if plate_box:
            px1, py1, px2, py2 = plate_box
            pad = 15
            plate_crop = vehicle_crop[
                max(0, py1-pad):min(vehicle_crop.shape[0], py2+pad),
                max(0, px1-pad):min(vehicle_crop.shape[1], px2+pad)
            ]
            
            if plate_crop.size > 0:
                va, vb, mode = self.preprocess(plate_crop, day_hours)
                plate, conf, v_best = self.run_ocr_ensemble(va, vb)
                return {
                    "plate": plate,
                    "confidence": conf,
                    "mode": mode,
                    "crop": plate_crop,
                    "best_variant": v_best
                }
        return None
