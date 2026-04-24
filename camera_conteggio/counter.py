"""
camera_conteggio/counter.py
Logica di conteggio persone con attraversamento linea virtuale.
"""

from collections import defaultdict
from datetime import datetime

import config as cfg


# Stato globale del conteggio
count_in = 0
count_out = 0
track_history = defaultdict(list)
last_crossing = {}


def get_side(y: float, line_y: float) -> str:
    """Restituisce il lato della linea in cui si trova il punto."""
    return "above" if y < line_y else "below"


def process_crossing(obj_id: int, history: list, line_y: float) -> str | None:
    """Elabora un possibile attraversamento della linea virtuale."""
    if len(history) < cfg.MIN_FRAMES_SIDE * 2:
        return None

    ys = [p[1] for p in history]
    start_side = get_side(sum(ys[:cfg.MIN_FRAMES_SIDE]) / cfg.MIN_FRAMES_SIDE, line_y)
    current_side = get_side(sum(ys[-cfg.MIN_FRAMES_SIDE:]) / cfg.MIN_FRAMES_SIDE, line_y)

    if start_side == current_side or not (min(ys) < line_y < max(ys)):
        return None

    # Pulisci la history dopo il crossing per evitare rimbalzi
    track_history[obj_id].clear()

    return "IN" if start_side == "below" else "OUT"


def log_passaggio(evento: str, obj_id: int):
    """Registra il passaggio nel file CSV."""
    import csv
    with open(cfg.LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            evento, obj_id, count_in, count_out, max(0, count_in - count_out),
        ])


def add_crossing(direction: str, obj_id: int):
    """Aggiunge un attraversamento al conteggio."""
    global count_in, count_out
    
    if direction == "IN":
        count_in += 1
        log_passaggio("CHECK-IN", obj_id)
    else:
        count_out += 1
        log_passaggio("CHECK-OUT", obj_id)
    
    print(f"✨ {direction} | ID {obj_id} | Presenti: {max(0, count_in - count_out)}")


def get_counts():
    """Restituisce i conteggi correnti."""
    return count_in, count_out