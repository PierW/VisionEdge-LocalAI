"""
garage_checker/tools/roi_configurator.py

Interactive tool to select 3 ROIs (Region of Interest) for the garage monitor.
Each ROI represents a parking spot where plate recognition should be triggered.

Features:
- Drag to move ROI
- Drag corners to resize
- Save to config/rois.json
- Support for 3 independent ROIs
"""

import cv2
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path for imports if needed
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

# Default RTSP URL
RTSP_URL = os.getenv("RTSP_URL_TARGHE", "rtsp://127.0.0.1:554/stream")

# Appearance Constants
COLORS = [
    (0, 0, 255),    # ROI 1: Red
    (0, 255, 0),    # ROI 2: Green
    (255, 0, 0)     # ROI 3: Blue
]
COLOR_SELECTED = (255, 255, 0)  # Cyan/Yellow
COLOR_TEXT = (255, 255, 255)
FONT = cv2.FONT_HERSHEY_SIMPLEX

# Interaction Constants
HANDLE_SIZE = 8
MIN_ROI_SIZE = 20


class ROIConfigurator:
    def __init__(self, rtsp_url):
        self.rtsp_url = rtsp_url
        self.rois = []  # List of dicts: {"x1":, "y1":, "x2":, "y2":}
        self.selected_idx = -1
        self.dragging_idx = -1
        self.dragging_handle = None  # None for whole ROI, or "tl", "tr", "bl", "br"
        self.drag_start_pos = None
        self.running = True
        self.window_name = "Garage ROI Configurator"
        
        # Load existing ROIs if available
        self.load_rois()

    def load_rois(self):
        config_path = PROJECT_ROOT / "garage_checker" / "config" / "rois.json"
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    self.rois = json.load(f)
                print(f"✅ Loaded {len(self.rois)} ROIs from {config_path}")
            except Exception as e:
                print(f"⚠️ Could not load existing ROIs: {e}")

    def save_rois(self):
        config_dir = PROJECT_ROOT / "garage_checker" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "rois.json"
        
        # Ensure we have 3 ROIs or at least some
        save_data = []
        for i, roi in enumerate(self.rois):
            # Normalize: x1, y1 should be top-left
            x1, y1 = min(roi["x1"], roi["x2"]), min(roi["y1"], roi["y2"])
            x2, y2 = max(roi["x1"], roi["x2"]), max(roi["y1"], roi["y2"])
            save_data.append({
                "id": i + 1,
                "name": f"Spot {i + 1}",
                "x1": int(x1),
                "y1": int(y1),
                "x2": int(x2),
                "y2": int(y2),
                "width": int(x2 - x1),
                "height": int(y2 - y1)
            })

        with open(config_path, "w") as f:
            json.dump(save_data, f, indent=4)
        
        print(f"✅ Saved {len(save_data)} ROIs to {config_path}")

    def get_handle_under_mouse(self, x, y):
        for i, roi in enumerate(self.rois):
            x1, y1, x2, y2 = roi["x1"], roi["y1"], roi["x2"], roi["y2"]
            handles = {
                "tl": (x1, y1),
                "tr": (x2, y1),
                "bl": (x1, y2),
                "br": (x2, y2)
            }
            for handle_name, (hx, hy) in handles.items():
                if abs(x - hx) < HANDLE_SIZE and abs(y - hy) < HANDLE_SIZE:
                    return i, handle_name
            
            # Check if inside ROI for moving
            if min(x1, x2) < x < max(x1, x2) and min(y1, y2) < y < max(y1, y2):
                return i, "move"
        return -1, None

    def mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            idx, handle = self.get_handle_under_mouse(x, y)
            if idx != -1:
                self.selected_idx = idx
                self.dragging_idx = idx
                self.dragging_handle = handle
                self.drag_start_pos = (x, y)
            elif len(self.rois) < 3:
                # Start new ROI
                self.rois.append({"x1": x, "y1": y, "x2": x + 50, "y2": y + 30})
                self.selected_idx = len(self.rois) - 1
                self.dragging_idx = self.selected_idx
                self.dragging_handle = "br"
                self.drag_start_pos = (x, y)

        elif event == cv2.EVENT_MOUSEMOVE:
            if self.dragging_idx != -1:
                roi = self.rois[self.dragging_idx]
                dx = x - self.drag_start_pos[0]
                dy = y - self.drag_start_pos[1]
                
                if self.dragging_handle == "move":
                    roi["x1"] += dx
                    roi["y1"] += dy
                    roi["x2"] += dx
                    roi["y2"] += dy
                elif self.dragging_handle == "tl":
                    roi["x1"] = x
                    roi["y1"] = y
                elif self.dragging_handle == "tr":
                    roi["x2"] = x
                    roi["y1"] = y
                elif self.dragging_handle == "bl":
                    roi["x1"] = x
                    roi["y2"] = y
                elif self.dragging_handle == "br":
                    roi["x2"] = x
                    roi["y2"] = y
                
                self.drag_start_pos = (x, y)

        elif event == cv2.EVENT_LBUTTONUP:
            self.dragging_idx = -1
            self.dragging_handle = None

        elif event == cv2.EVENT_RBUTTONDOWN:
            idx, _ = self.get_handle_under_mouse(x, y)
            if idx != -1:
                self.rois.pop(idx)
                self.selected_idx = -1

    def draw(self, frame):
        h, w = frame.shape[:2]
        
        for i, roi in enumerate(self.rois):
            color = COLORS[i % len(COLORS)]
            if i == self.selected_idx:
                color = COLOR_SELECTED
            
            x1, y1, x2, y2 = int(roi["x1"]), int(roi["y1"]), int(roi["x2"]), int(roi["y2"])
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Draw handles
            for hx, hy in [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]:
                cv2.rectangle(frame, (hx - 4, hy - 4), (hx + 4, hy + 4), color, -1)
            
            # Label
            label = f"Spot {i+1}"
            cv2.putText(frame, label, (min(x1, x2), min(y1, y2) - 10), FONT, 0.6, color, 2)

        # Instructions
        y_off = 30
        instructions = [
            "Left Click: Add ROI (max 3)",
            "Left Drag ROI: Move",
            "Left Drag Corner: Resize",
            "Right Click: Delete ROI",
            "S: Save and Quit",
            "Q: Quit without saving"
        ]
        for text in instructions:
            cv2.putText(frame, text, (10, y_off), FONT, 0.5, (0, 255, 0), 1)
            y_off += 20

        return frame

    def run(self):
        cap = cv2.VideoCapture(self.rtsp_url)
        if not cap.isOpened():
            print(f"❌ Error: Could not open stream {self.rtsp_url}")
            return

        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(self.window_name, self.mouse_callback)

        print("🚀 ROI Configurator Started")
        print("   Stream:", self.rtsp_url)

        while self.running:
            ret, frame = cap.read()
            if not ret:
                print("⚠️ Stream lost, reconnecting...")
                cap.release()
                cap = cv2.VideoCapture(self.rtsp_url)
                continue

            frame = cv2.resize(frame, (1280, 720))
            draw_frame = self.draw(frame.copy())
            
            cv2.imshow(self.window_name, draw_frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('s'):
                self.save_rois()
                break
            elif key == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    configurator = ROIConfigurator(RTSP_URL)
    configurator.run()
