"""
targhe_auto/whitelist_manager.py
Gestione anagrafica veicoli — legge/scrive whitelist.json.

Struttura JSON:
{
  "AB123CD": {
    "targa": "AB123CD",
    "nome": "Mario Rossi",
    "autorizzato": true,
    "prima_vista": "2025-01-15 10:30:00",
    "ultimo_accesso": "2025-01-20 08:00:00"
  }
}
"""

import json
import os
from datetime import datetime

# Il percorso viene impostato da config.py; fallback locale per comodità
try:
    from config import WHITELIST_FILE
except ImportError:
    WHITELIST_FILE = os.path.join(os.path.dirname(__file__), "whitelist.json")


def _load() -> dict:
    if not os.path.exists(WHITELIST_FILE):
        return {}
    with open(WHITELIST_FILE, "r") as f:
        return json.load(f)


def _save(data: dict):
    with open(WHITELIST_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_known(targa: str) -> bool:
    """Targa già presente in anagrafica (autorizzata O negata)."""
    return targa in _load()


def is_authorized(targa: str) -> bool:
    """Targa presente e con autorizzato=True."""
    db = _load()
    entry = db.get(targa)
    return entry is not None and entry.get("autorizzato", False)


def get_entry(targa: str) -> dict | None:
    return _load().get(targa)


def add_or_update(targa: str, nome: str, autorizzato: bool):
    """Aggiunge o aggiorna una targa in anagrafica."""
    db  = _load()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if targa not in db:
        db[targa] = {
            "targa": targa,
            "nome": nome,
            "autorizzato": autorizzato,
            "prima_vista": now,
            "ultimo_accesso": now,
        }
    else:
        db[targa]["nome"]         = nome
        db[targa]["autorizzato"]  = autorizzato
        db[targa]["ultimo_accesso"] = now
    _save(db)
    stato = "AUTORIZZATO" if autorizzato else "NEGATO"
    print(f"✅ [WHITELIST] {stato} → {targa} ({nome})")


def update_ultimo_accesso(targa: str):
    db = _load()
    if targa in db:
        db[targa]["ultimo_accesso"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _save(db)


def list_all() -> list[dict]:
    return list(_load().values())