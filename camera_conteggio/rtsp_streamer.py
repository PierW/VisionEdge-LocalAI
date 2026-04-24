"""
camera_conteggio/rtsp_streamer.py
Gestione stream RTSP con riconnessione automatica.
"""

import cv2
import time
import threading

import config as cfg


class RTSPStreamer:
    def __init__(self, url):
        self.url = url
        self.cap = cv2.VideoCapture(url)
        self.frame = None
        self.ret = False
        self.stopped = False
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def _update(self):
        while not self.stopped:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                self.cap.release()
                time.sleep(2)
                self.cap = cv2.VideoCapture(self.url)
                continue
            
            resized_frame = cv2.resize(frame, cfg.FRAME_SIZE)
            with self.lock:
                self.ret, self.frame = ret, resized_frame

    def read(self):
        with self.lock:
            return self.ret, self.frame.copy() if self.frame is not None else None

    def stop(self):
        self.stopped = True
        self.thread.join(timeout=2.0)
        if self.cap and self.cap.isOpened():
            self.cap.release()