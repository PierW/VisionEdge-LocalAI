"""
garage_checker/modules/detector.py

Vehicle detection and tracking wrapper.
"""

from ultralytics import YOLO
import numpy as np

class VehicleDetector:
    def __init__(self, model_path: str, tracker_config: str, device: str = "cpu"):
        self.model = YOLO(model_path).to(device)
        self.tracker_config = tracker_config
        self.classes = [2, 3, 5, 7] # car, motorcycle, bus, truck (COCO)

    def track(self, frame: np.ndarray, conf: float = 0.4):
        """
        Tracks vehicles in the frame.
        Returns a list of (box, obj_id) tuples.
        """
        results = self.model.track(
            frame, 
            persist=True, 
            tracker=self.tracker_config,
            classes=self.classes, 
            verbose=False, 
            conf=conf
        )
        
        detections = []
        if results and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.int().cpu().tolist()
            ids = results[0].boxes.id.int().cpu().tolist()
            for box, obj_id in zip(boxes, ids):
                detections.append((box, obj_id))
        
        return detections
