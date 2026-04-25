"""
Wrapper compatibile per sostituire `fast_plate_ocr` usando `easyocr`.

Classe esposta: `LicensePlateRecognizer()` con metodo `run(path, return_confidence=True)`
che ritorna una lista di oggetti con attributi: `plate` (str), `char_probs` (Optional[List[float]]), `region` (Optional[str]).

Questo permette di mantenere invariato il codice in `main.py` e `plate_processor.py`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

import easyocr


@dataclass
class PlatePred:
    plate: str
    char_probs: Optional[List[float]]
    region: Optional[str]


class LicensePlateRecognizer:
    def __init__(self, model_name: Optional[str] = None, lang_list=None, gpu: bool = False):
        """
        Inizializza il riconoscitore OCR basato su EasyOCR.

        Args:
            model_name: Ignorato (mantenuto per compatibilità con chiamate esistenti).
            lang_list:  Lista di linguaggi per EasyOCR (default: ['en']).
            gpu:        Se True usa GPU/CUDA; su Mac MPS EasyOCR non supporta MPS,
                        quindi lasciamo False di default e gestiamo via CPU.
        """
        # model_name è ignorato: easyocr utilizza modelli pre-addestrati integrati
        self.lang_list = lang_list or ['en']
        self.gpu = gpu
        # easyocr carica modelli pesanti; manteniamo il reader in memoria
        self.reader = easyocr.Reader(self.lang_list, gpu=self.gpu)

    def run(self, image_path: str, return_confidence: bool = True):
        """Esegue OCR su `image_path`.

        Ritorna lista di PlatePred. Viene presa la prima stringa riconosciuta
        (se presente). Il campo `char_probs` è una lista di valori identici
        pari alla confidence complessiva, utile per calcoli compatibili col codice esistente.
        """
        if not os.path.exists(image_path):
            return []

        try:
            results = self.reader.readtext(image_path, detail=1)
        except Exception:
            return []

        preds: List[PlatePred] = []
        for bbox, text, conf in results:
            if not text or text.strip() == '':
                continue
            plate = text.strip()
            # Distribuiamo la confidence su tutti i caratteri per compatibilità
            char_probs = [float(conf)] * len(plate) if return_confidence and conf is not None else None
            # region come stringa della bbox
            region = ','.join([str(int(x)) for p in bbox for x in p]) if bbox is not None else None
            preds.append(PlatePred(plate=plate, char_probs=char_probs, region=region))

        return preds
