"""
garage_checker/roi_detector.py

ROI (Region of Interest) zone management and validation.
Checks if detected vehicles are inside the defined ROI boxes.

Each ROI corresponds to a machine zone in the garage.
Only vehicles inside an ROI trigger plate detection and OCR.
"""

import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional

from config import ROIS


class ROIDetector:
    """
    Manages ROI zones and validates vehicle positions.
    
    Attributes:
        rois: List of ROI dictionaries with coordinates
        frame_shape: Tuple (width, height) of video frame
    """

    def __init__(self, rois: List[Dict] = None, frame_shape: Tuple[int, int] = (960, 540)):
        """
        Initialize ROI detector.
        
        Args:
            rois: List of ROI dicts with keys: id, name, x1, y1, x2, y2, width, height
            frame_shape: Video frame dimensions (width, height)
        """
        self.rois = rois if rois is not None else ROIS
        self.frame_shape = frame_shape
        self.frame_width = frame_shape[0]
        self.frame_height = frame_shape[1]

    def is_in_roi(self, box: List[int], roi_id: int) -> bool:
        """
        Check if a vehicle bounding box intersects with an ROI zone.
        
        Uses intersection-over-union logic: returns True if ANY part of the
        vehicle box overlaps with the ROI zone.
        
        Args:
            box: Vehicle bounding box [x1, y1, x2, y2]
            roi_id: ROI index (0-based)
            
        Returns:
            True if vehicle is inside ROI, False otherwise
        """
        if roi_id < 0 or roi_id >= len(self.rois):
            return False
        
        roi = self.rois[roi_id]
        
        # Extract ROI coordinates
        roi_x1, roi_y1 = roi["x1"], roi["y1"]
        roi_x2, roi_y2 = roi["x2"], roi["y2"]
        
        # Vehicle coordinates
        x1, y1, x2, y2 = box
        
        # Check intersection (vehicle overlaps ROI)
        # Two rectangles don't intersect if one is completely to left, right, above, or below
        no_overlap = (
            x2 < roi_x1 or      # vehicle completely left of ROI
            x1 > roi_x2 or      # vehicle completely right of ROI
            y2 < roi_y1 or      # vehicle completely above ROI
            y1 > roi_y2         # vehicle completely below ROI
        )
        
        return not no_overlap

    def get_best_roi(self, box: List[int]) -> Optional[int]:
        """
        Find the best matching ROI for a vehicle.
        
        Returns the ROI with highest overlap, or None if no overlap.
        
        Args:
            box: Vehicle bounding box [x1, y1, x2, y2]
            
        Returns:
            ROI index (0-based) or None
        """
        best_roi_idx = None
        best_overlap = 0.0
        
        for idx, roi in enumerate(self.rois):
            if self.is_in_roi(box, idx):
                # Calculate IoU (Intersection over Union)
                overlap = self._calculate_iou(box, roi)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_roi_idx = idx
        
        return best_roi_idx if best_overlap > 0 else None

    def _calculate_iou(self, box1: List[int], box2: List[int]) -> float:
        """
        Calculate Intersection over Union between two bounding boxes.
        
        Args:
            box1: First box [x1, y1, x2, y2]
            box2: Second box [x1, y1, x2, y2]
            
        Returns:
            IoU ratio (0.0 to 1.0)
        """
        x1_max = max(box1[0], box2[0])
        y1_max = max(box1[1], box2[1])
        x2_min = min(box1[2], box2[2])
        y2_min = min(box1[3], box2[3])
        
        intersection = max(0, x2_min - x1_max) * max(0, y2_min - y1_max)
        
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        total_area = area1 + area2 - intersection
        
        if total_area == 0:
            return 0.0
        
        return intersection / total_area

    def get_roi_boxes(self, frame: np.ndarray) -> List[np.ndarray]:
        """
        Get ROI bounding boxes as numpy arrays for OpenCV drawing.
        
        Args:
            frame: Video frame
            
        Returns:
            List of ROI boxes [(x1, y1, x2, y2), ...]
        """
        boxes = []
        for roi in self.rois:
            x1, y1, x2, y2 = roi["x1"], roi["y1"], roi["x2"], roi["y2"]
            
            # Clamp to frame bounds
            x1 = max(0, min(x1, self.frame_width))
            y1 = max(0, min(y1, self.frame_height))
            x2 = max(x1, min(x2, self.frame_width))
            y2 = max(y1, min(y2, self.frame_height))
            
            boxes.append((x1, y1, x2, y2))
        
        return boxes

    def draw_roi_overlay(self, frame: np.ndarray) -> np.ndarray:
        """
        Draw all ROI zones on the frame with labels.
        
        Args:
            frame: Video frame to draw on
            
        Returns:
            Frame with ROI overlays
        """
        colors = [
            (0, 0, 255),      # Red for ROI 1
            (0, 255, 0),      # Green for ROI 2
            (255, 0, 0),      # Blue for ROI 3
            (255, 255, 0),    # Yellow for ROI 4+
        ]
        
        for idx, roi in enumerate(self.rois):
            x1, y1, x2, y2 = roi["x1"], roi["y1"], roi["x2"], roi["y2"]
            
            # Clamp to frame bounds
            x1 = max(0, min(x1, self.frame_width))
            y1 = max(0, min(y1, self.frame_height))
            x2 = max(x1, min(x2, self.frame_width))
            y2 = max(y1, min(y2, self.frame_height))
            
            # Draw rectangle
            color = colors[idx % len(colors)]
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Draw label
            label = f"ROI {idx + 1}: {roi['name']}"
            font_scale = 0.5
            font_thickness = 1
            
            # Calculate text size
            (text_w, text_h), baseline = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness
            )
            
            # Position text above ROI
            text_x = x1
            text_y = max(y1 - text_h - 5, 0)
            
            # Draw rounded background
            cv2.rectangle(frame,
                         (text_x - 3, text_y - text_h - 3),
                         (text_x + text_w + 3, text_y + baseline + 3),
                         (255, 255, 255), -1)
            
            # Draw text
            cv2.putText(frame, label,
                       (text_x, text_y + baseline),
                       cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), font_thickness)
            
            # Draw dimensions
            width = x2 - x1
            height = y2 - y1
            cv2.putText(frame, f"{width}x{height}",
                       (x1, y1 - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
        
        return frame

    def get_vehicles_in_rois(self, boxes: List[List[int]], ids: List[int]) -> Dict[int, List[Tuple[int, int]]]:
        """
        Group detected vehicles by their ROI.
        
        Args:
            boxes: List of vehicle bounding boxes
            ids: List of vehicle IDs (BoT-SORT)
            
        Returns:
            Dict mapping ROI index -> list of (obj_id, box) tuples
        """
        vehicles_by_roi = {i: [] for i in range(len(self.rois))}
        
        for box, obj_id in zip(boxes, ids):
            best_roi = self.get_best_roi(box)
            if best_roi is not None:
                vehicles_by_roi[best_roi].append((obj_id, box))
        
        return vehicles_by_roi

    def check_all_vehicles(self, boxes: List[List[int]], ids: List[int]) -> Dict[int, List[Tuple[int, int, bool, float]]]:
        """
        Check all vehicles against all ROIs.
        
        Returns detailed info for each vehicle:
        - Which ROIs they intersect
        - IoU with each ROI
        - Whether they're "inside" (IoU > 0.5)
        
        Args:
            boxes: List of vehicle bounding boxes
            ids: List of vehicle IDs
            
        Returns:
            Dict mapping obj_id -> list of (roi_id, is_inside, iou) tuples
        """
        vehicle_roi_info = {}
        
        for box, obj_id in zip(boxes, ids):
            roi_info = []
            for roi_idx in range(len(self.rois)):
                is_inside = self.is_in_roi(box, roi_idx)
                iou = self._calculate_iou(box, self.rois[roi_idx])
                roi_info.append((roi_idx, is_inside, iou))
            
            vehicle_roi_info[obj_id] = roi_info
        
        return vehicle_roi_info
