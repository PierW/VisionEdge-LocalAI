"""
garage_checker/roi_detector.py
Gestione delle Region of Interest (ROI) per il garage.
"""

import cv2
import numpy as np

class ROIDetector:
    def __init__(self, rois):
        """
        rois: lista di dict {"id": n, "name": "...", "x1": x, "y1": y, "x2": x, "y2": y}
        Le coordinate devono essere quelle della risoluzione ORIGINALE dello stream.
        """
        self.rois = rois

    def get_best_roi(self, vehicle_box):
        """
        Determina in quale ROI si trova il veicolo basandosi sul centro del box.
        vehicle_box: [x1, y1, x2, y2]
        Ritorna l'ID della ROI o None.
        """
        x1, y1, x2, y2 = vehicle_box
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2

        for roi in self.rois:
            rx1, ry1, rx2, ry2 = roi["x1"], roi["y1"], roi["x2"], roi["y2"]
            if rx1 <= cx <= rx2 and ry1 <= cy <= ry2:
                return roi["id"]
        
        return None

    def draw_roi_overlays(self, frame, roi_status=None, scale_factor=1.0):
        """
        Disegna i box delle ROI sul frame.
        roi_status: dict {roi_id: {"color": (b,g,r), "label": "..."}}
        scale_factor: fattore di scala se il frame è ridimensionato rispetto alle coordinate ROI.
        """
        for roi in self.rois:
            x1 = int(roi["x1"] * scale_factor)
            y1 = int(roi["y1"] * scale_factor)
            x2 = int(roi["x2"] * scale_factor)
            y2 = int(roi["y2"] * scale_factor)

            status = (roi_status or {}).get(roi["id"], {})
            color = status.get("color", (100, 100, 100)) # Default grigio
            label = status.get("label", roi["name"])

            # Box ROI
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Etichetta
            font = cv2.FONT_HERSHEY_SIMPLEX
            (w, h), _ = cv2.getTextSize(label, font, 0.5, 1)
            cv2.rectangle(frame, (x1, y1 - h - 10), (x1 + w + 10, y1), color, -1)
            cv2.putText(frame, label, (x1 + 5, y1 - 5), font, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        
        return frame
