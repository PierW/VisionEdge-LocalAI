"""
garage_checker/core/state.py

Thread-safe management of vehicle tracking and OCR states.
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class VehicleState:
    obj_id: int
    first_seen: float
    last_seen: float
    roi_id: Optional[int] = None
    ocr_results: List[dict] = field(default_factory=list)
    final_plate: Optional[str] = None
    final_conf: float = 0.0
    action_triggered: bool = False
    checkout_done: bool = False
    
    def is_ocr_done(self) -> bool:
        return self.final_plate is not None

class StateManager:
    def __init__(self, timeout: float = 6.0, min_candidates: int = 7):
        self.timeout = timeout
        self.min_candidates = min_candidates
        self.vehicles: Dict[int, VehicleState] = {}
        self.lock = threading.Lock()

    def update_vehicle(self, obj_id: int, roi_id: Optional[int] = None):
        with self.lock:
            now = time.time()
            if obj_id not in self.vehicles:
                self.vehicles[obj_id] = VehicleState(
                    obj_id=obj_id,
                    first_seen=now,
                    last_seen=now,
                    roi_id=roi_id
                )
                return True # New vehicle
            else:
                self.vehicles[obj_id].last_seen = now
                # Update ROI only if it was None (entering an ROI)
                if self.vehicles[obj_id].roi_id is None:
                    self.vehicles[obj_id].roi_id = roi_id
                return False

    def add_ocr_candidate(self, obj_id: int, candidate: dict):
        with self.lock:
            if obj_id in self.vehicles:
                self.vehicles[obj_id].ocr_results.append(candidate)
                return len(self.vehicles[obj_id].ocr_results)
        return 0

    def get_vehicle(self, obj_id: int) -> Optional[VehicleState]:
        with self.lock:
            return self.vehicles.get(obj_id)

    def finalize_vehicle(self, obj_id: int, plate: str, conf: float):
        with self.lock:
            if obj_id in self.vehicles:
                self.vehicles[obj_id].final_plate = plate
                self.vehicles[obj_id].final_conf = conf

    def mark_action_triggered(self, obj_id: int):
        with self.lock:
            if obj_id in self.vehicles:
                self.vehicles[obj_id].action_triggered = True

    def cleanup_expired(self) -> List[VehicleState]:
        """Removes and returns expired vehicles."""
        now = time.time()
        expired = []
        with self.lock:
            to_delete = []
            for obj_id, state in self.vehicles.items():
                if now - state.last_seen > self.timeout:
                    expired.append(state)
                    to_delete.append(obj_id)
            for obj_id in to_delete:
                del self.vehicles[obj_id]
        return expired

    def get_active_count(self) -> int:
        with self.lock:
            return len(self.vehicles)

    def get_all_active(self) -> List[VehicleState]:
        with self.lock:
            return list(self.vehicles.values())
