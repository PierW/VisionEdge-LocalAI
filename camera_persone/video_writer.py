"""
camera_persone/video_writer.py
Gestione VideoWriter per la registrazione video.
"""

import os
import cv2

import config as cfg


def create_writer(timestamp: int):
    """
    Crea un VideoWriter H.264.
    Prova prima avc1 (H.264 nativo), poi mp4v come fallback.
    """
    os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)
    filename = os.path.join(cfg.OUTPUT_DIR, f"person_{timestamp}.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"avc1")
    writer = cv2.VideoWriter(filename, fourcc, cfg.TARGET_FPS, cfg.FRAME_SIZE)
    if not writer.isOpened():
        # fallback: XVID in avi (universalmente compatibile)
        filename = os.path.join(cfg.OUTPUT_DIR, f"person_{timestamp}.avi")
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        writer = cv2.VideoWriter(filename, fourcc, cfg.TARGET_FPS, cfg.FRAME_SIZE)
    return writer, filename


def close_writer(writer, filename: str, snapshot_frame):
    """Chiude il VideoWriter e invia lo snapshot su Telegram."""
    from telegram_bot import send_snapshot
    
    writer.release()
    snap_path = filename.rsplit(".", 1)[0] + "_snap.jpg"
    cv2.imwrite(snap_path, snapshot_frame)
    ts_str = "%s" % timestamp_to_string()
    caption = f"👤 Persona rilevata — {ts_str}\n📁 Video: {os.path.basename(filename)}"
    print(f"💾 Video salvato: {filename}")
    send_snapshot(snap_path, caption)


def timestamp_to_string():
    """Converte il timestamp corrente in stringa formattata."""
    import time
    return time.strftime("%d/%m/%Y %H:%M:%S")