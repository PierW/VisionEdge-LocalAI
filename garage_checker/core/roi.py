"""
garage_checker/core/roi.py

ROI (Region of Interest) management and overlap detection.
"""

import json
from pathlib import Path

class ROIManager:
    def __init__(self, rois_file: Path):
        self.rois_file = rois_file
        self.rois = []
        self.load_rois()

    def load_rois(self):
        if self.rois_file.exists():
            try:
                with open(self.rois_file, "r") as f:
                    self.rois = json.load(f)
            except Exception as e:
                print(f"❌ Error loading ROIs: {e}")
        else:
            print(f"⚠️ ROI file {self.rois_file} not found. Please run roi_configurator.py")

    def check_overlap(self, box, frame_size):
        """
        Checks if a bounding box (x1, y1, x2, y2) overlaps with any ROI.
        Returns the ID of the ROI it overlaps with, or None.
        
        The box from YOLO might be in different resolution than the ROI 
        if we resized the frame for display during ROI configuration.
        We assume ROIs are stored in the resolution they were selected in (1280x720).
        """
        x1, y1, x2, y2 = box
        
        # Scale box if needed? 
        # For now assume same resolution or normalized.
        
        for roi in self.rois:
            rx1, ry1, rx2, ry2 = roi["x1"], roi["y1"], roi["x2"], roi["y2"]
            
            # Simple intersection check
            if not (x2 < rx1 or x1 > rx2 or y2 < ry1 or y1 > ry2):
                return roi["id"]
        
        return None

    def get_all_rois(self):
        return self.rois
