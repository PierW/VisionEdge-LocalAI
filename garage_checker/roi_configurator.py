"""
garage_checker/roi_configurator.py
Tool interattivo per configurare 3 ROI e assegnare nomi ai veicoli.
"""

import cv2
import json
import os
import sys

class ROIConfigurator:
    def __init__(self, rtsp_url, output_file, display_w=960, display_h=540):
        self.rtsp_url = rtsp_url
        self.output_file = output_file
        self.display_w = display_w
        self.display_h = display_h
        self.rois = []
        self.current_box = None
        self.drawing = False
        self.ix, self.iy = -1, -1
        self.original_w = 0
        self.original_h = 0

    def _mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(self.rois) >= 3: return
            self.drawing = True
            self.ix, self.iy = x, y
        elif event == cv2.EVENT_MOUSEMOVE:
            if self.drawing: self.current_box = (self.ix, self.iy, x, y)
        elif event == cv2.EVENT_LBUTTONUP:
            if self.drawing:
                self.drawing = False
                x1, y1, x2, y2 = self.ix, self.iy, x, y
                nx1, nx2 = min(x1, x2), max(x1, x2)
                ny1, ny2 = min(y1, y2), max(y1, y2)
                if (nx2 - nx1) > 20 and (ny2 - ny1) > 20:
                    scale_x = self.original_w / self.display_w
                    scale_y = self.original_h / self.display_h
                    self.rois.append({
                        "id": len(self.rois) + 1,
                        "x1": int(nx1 * scale_x),
                        "y1": int(ny1 * scale_y),
                        "x2": int(nx2 * scale_x),
                        "y2": int(ny2 * scale_y)
                    })
                self.current_box = None

    def configure(self):
        cap = cv2.VideoCapture(self.rtsp_url)
        if not cap.isOpened(): return False
        self.original_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.original_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if self.original_w == 0:
            ret, f = cap.read()
            if ret: self.original_h, self.original_w = f.shape[:2]
            else: return False

        win_name = "Configurazione ROI - Disegna 3 box"
        cv2.namedWindow(win_name)
        cv2.setMouseCallback(win_name, self._mouse_callback)

        print("\n--- 🅿️ CONFIGURAZIONE POSTI AUTO ---")
        print("Disegna i 3 box per i posti auto, poi premi 's' per salvare.")

        while True:
            ret, frame = cap.read()
            if not ret: break
            display_frame = cv2.resize(frame, (self.display_w, self.display_h))
            for roi in self.rois:
                sx, sy = self.display_w / self.original_w, self.display_h / self.original_h
                cv2.rectangle(display_frame, (int(roi["x1"]*sx), int(roi["y1"]*sy)), 
                              (int(roi["x2"]*sx), int(roi["y2"]*sy)), (0, 255, 0), 2)
            if self.current_box:
                cv2.rectangle(display_frame, (self.current_box[0], self.current_box[1]), 
                              (self.current_box[2], self.current_box[3]), (255, 255, 0), 2)
            cv2.imshow(win_name, display_frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('s') and len(self.rois) == 3: break
            elif key == ord('r'): self.rois = []
            elif key == ord('q'): 
                cap.release(); cv2.destroyAllWindows(); return False

        cap.release()
        cv2.destroyAllWindows()

        # Richiesta nomi veicoli
        print("\n--- 📝 ASSEGNAZIONE NOMI ---")
        for roi in self.rois:
            nome = input(f"Inserisci il nome del veicolo per il Box {roi['id']}: ").strip()
            roi["name"] = nome or f"Veicolo {roi['id']}"

        with open(self.output_file, 'w') as f:
            json.dump(self.rois, f, indent=2)
        print(f"✅ ROI salvate in {self.output_file}")
        return True
