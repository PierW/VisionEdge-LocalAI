"""
garage_checker/modules/whitelist.py

Management of authorized vehicles.
"""

import json
import os
from datetime import datetime
from pathlib import Path

class WhitelistManager:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._ensure_exists()

    def _ensure_exists(self):
        if not self.file_path.exists():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, "w") as f:
                json.dump({}, f)

    def _load(self) -> dict:
        try:
            with open(self.file_path, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self, data: dict):
        with open(self.file_path, "w") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def get_entry(self, plate: str) -> dict:
        return self._load().get(plate)

    def add_or_update(self, plate: str, name: str, authorized: bool):
        db = self._load()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if plate not in db:
            db[plate] = {
                "targa": plate,
                "nome": name,
                "autorizzato": authorized,
                "prima_vista": now,
                "ultimo_accesso": now,
                "ultima_uscita": None,
            }
        else:
            db[plate]["nome"] = name
            db[plate]["autorizzato"] = authorized
            db[plate]["ultimo_accesso"] = now
        self._save(db)
        print(f"✅ [WHITELIST] {'AUTHORIZED' if authorized else 'DENIED'} -> {plate} ({name})")

    def update_access(self, plate: str, event_type: str = "entry"):
        db = self._load()
        if plate in db:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if event_type == "entry":
                db[plate]["ultimo_accesso"] = now
            else:
                db[plate]["ultima_uscita"] = now
            self._save(db)
