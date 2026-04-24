"""
targhe_auto/plate_processor.py

Pre-processing adattivo giorno/notte + ensemble OCR su 2 varianti.

REGOLA BASE:
  Passiamo sempre un file path al modello OCR — è la libreria stessa
  a leggere, convertire in grayscale e ridimensionare. Zero ambiguità
  sul formato del tensore, zero dipendenza dalla versione della cache ONNX.

ENSEMBLE:
  Processiamo il crop con 2 varianti di preprocessing, salviamo entrambe
  in file temporanei distinti, lanciamo OCR su entrambe con
  return_confidence=True, teniamo il risultato con mean(char_probs) più alto.
  Overhead reale: ~1 OCR extra su un crop piccolo (~3-5ms su MPS).

RILEVAMENTO GIORNO/NOTTE — criterio triplo (basta uno):
  brightness < 80  → immagine scura
  noise      > 14  → alto rumore (ISO elevato, tipico notturno)
  contrast   < 30  → basso contrasto (IR, nebbia, illuminazione piatta)
  Se nessuno scatta usa l'orario come tiebreak.
"""

import os
import tempfile

import cv2
import numpy as np
from datetime import datetime

from config import ORA_GIORNO, PLATE_UPSCALE


# ─── Analisi immagine ─────────────────────────────────────────────────────────

def _analizza(gray: np.ndarray) -> dict:
    brightness = float(np.mean(gray))
    contrast   = float(gray.std())
    noise      = float(np.std(cv2.Laplacian(gray, cv2.CV_64F)))
    return {"brightness": brightness, "contrast": contrast, "noise": noise}


def _is_night(metrics: dict) -> bool:
    # Priorità all'orario
    ora = datetime.now().hour
    is_ora_notte = not (ORA_GIORNO[0] <= ora < ORA_GIORNO[1])
    
    # Se è orario diurno, passa a notte SOLO se è estremamente buio
    if not is_ora_notte and metrics["brightness"] < 40:
        return True
        
    return is_ora_notte


# ─── Varianti di preprocessing ────────────────────────────────────────────────

def _variant_day_a(img: np.ndarray) -> np.ndarray:
    """Diurna principale: Originale a colori (solo ridimensionato in processa_targa)."""
    return img


def _variant_day_b(gray: np.ndarray) -> np.ndarray:
    """Diurna alternativa: CLAHE moderato + sharpening deciso."""
    clahe    = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    denoised = cv2.bilateralFilter(enhanced, 5, 20, 20)
    blur     = cv2.GaussianBlur(denoised, (0, 0), 1)
    return cv2.addWeighted(denoised, 1.5, blur, -0.5, 0)


def _variant_night_a(gray: np.ndarray) -> np.ndarray:
    """Notturna principale: denoising → CLAHE → gamma → sharpening leggero."""
    denoised = cv2.bilateralFilter(gray, 7, 25, 25)
    clahe    = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(4, 4))
    enhanced = clahe.apply(denoised)
    lut      = np.array([min(255, int((i / 255.0) ** 0.65 * 255)) for i in range(256)], dtype=np.uint8)
    gamma    = cv2.LUT(enhanced, lut)
    blur     = cv2.GaussianBlur(gamma, (0, 0), 1.0)
    return cv2.addWeighted(gamma, 1.3, blur, -0.3, 0)


def _variant_night_b(gray: np.ndarray) -> np.ndarray:
    """Notturna alternativa: denoising più aggressivo, senza gamma."""
    denoised = cv2.bilateralFilter(gray, 9, 35, 35)
    clahe    = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(denoised)
    blur     = cv2.GaussianBlur(enhanced, (0, 0), 0.8)
    return cv2.addWeighted(enhanced, 1.2, blur, -0.2, 0)


# ─── Ensemble OCR ─────────────────────────────────────────────────────────────

def ocr_ensemble(ocr_model, variant_a: np.ndarray, variant_b: np.ndarray) -> tuple[str, str, float, np.ndarray | None, str]:
    """
    Lancia OCR su due varianti preprocessate, ritorna il risultato migliore.

    - Salva ogni variante in un file .png temporaneo (mkstemp → no lock su macOS)
    - Passa il path al modello: è la libreria a gestire grayscale/resize/normalize
    - Confidence = mean(pred.char_probs) — campo reale di PlatePrediction
    - Vince la variante con confidence più alta
    - I file temporanei vengono sempre cancellati nel blocco finally

    Ritorna (testo_targa, nazione, confidence, variante_vincente, tipo_variante) oppure ("", "", 0.0, None, "") se fallisce.
    """
    best_plate   = ""
    best_region  = ""
    best_conf    = 0.0
    best_variant: np.ndarray | None = None
    best_type    = ""

    for i, variant in enumerate((variant_a, variant_b)):
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            cv2.imwrite(tmp_path, variant)

            results = ocr_model.run(tmp_path, return_confidence=True)
            if not results:
                continue

            pred   = results[0]
            testo  = pred.plate.upper() if pred.plate else ""
            conf   = float(np.mean(pred.char_probs)) if pred.char_probs is not None else 0.0
            region = pred.region or ""

            if len(testo) >= 5 and conf > best_conf:
                best_plate   = testo
                best_region  = region
                best_conf    = conf
                best_variant = variant
                best_type    = "originale" if i == 0 else "modificata"

        except Exception as e:
            print(f"⚠️ [ENSEMBLE] OCR error: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    return best_plate, best_region, best_conf, best_variant, best_type


# ─── API pubblica ─────────────────────────────────────────────────────────────

def processa_targa(plate_crop_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, str, dict]:
    # 1. Upscale (mantenendo i colori BGR)
    plate_up = cv2.resize(
        plate_crop_bgr, None,
        fx=PLATE_UPSCALE, fy=PLATE_UPSCALE,
        interpolation=cv2.INTER_LANCZOS4,
    )
    
    # 2. Crea la versione in grigio (serve per analizzare la luminosità e per le altre varianti)
    gray = cv2.cvtColor(plate_up, cv2.COLOR_BGR2GRAY)
    metrics = _analizza(gray)

    if _is_night(metrics):
        # Notturna: variante A = crop originale upscalato (a colori), variante B = leggermente modificata (denoising + CLAHE)
        return plate_up, _variant_night_a(gray), "notturna", metrics
    else:
        # DI GIORNO: 
        # Variante A -> riceve 'plate_up' (A COLORI)
        # Variante B -> riceve 'gray' (elaborata con CLAHE/sharpening)
        return _variant_day_a(plate_up), _variant_day_b(gray), "diurna", metrics