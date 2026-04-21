from fast_plate_ocr import LicensePlateRecognizer
import cv2
import os
import torch
from ultralytics import YOLO
from datetime import datetime

# ================= CONFIG =================
# metti qui la tua foto con la macchina intera
image_path = "foto_test.png" # <--- CAMBIA con il nome del tuo file

device = "mps" if torch.backends.mps.is_available() else "cpu"
# ==========================================

if not os.path.exists(image_path):
    print(f"❌ Errore: Il file {image_path} non esiste!")
    exit()

print("⏳ Carico modelli...")
model_targhe = YOLO("yolov8n_plate.pt").to(device)
ocr = LicensePlateRecognizer('cct-xs-v2-global-model')
print("✅ Pronto")

# 1. leggi immagine
frame = cv2.imread(image_path)
res_t = model_targhe(frame, conf=0.4, verbose=False, device=device)

if not res_t or len(res_t[0].boxes) == 0:
    print("❓ Nessuna targa rilevata")
    exit()

# 2. ritaglio come nel tuo codice, con pad 15
x1, y1, x2, y2 = map(int, res_t[0].boxes.xyxy[0].tolist())
pad = 15
x1p = max(0, x1 - pad)
y1p = max(0, y1 - pad)
x2p = min(frame.shape[1], x2 + pad)
y2p = min(frame.shape[0], y2 + pad)
plate_crop = frame[y1p:y2p, x1p:x2p]

# 3. salva originale
base_name = f"test_{datetime.now().strftime('%H%M%S')}"
orig_path = f"{base_name}_orig.jpg"
cv2.imwrite(orig_path, plate_crop)
print(f"💾 Salvato originale: {orig_path} ({plate_crop.shape[1]}x{plate_crop.shape[0]})")

# 4. miglioramento qualità (stesso del main)
plate_up = cv2.resize(plate_crop, None, fx=3, fy=3, interpolation=cv2.INTER_LANCZOS4)
gray = cv2.cvtColor(plate_up, cv2.COLOR_BGR2GRAY)
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
enhanced = clahe.apply(gray)
denoised = cv2.bilateralFilter(enhanced, 5, 30, 30)
blur = cv2.GaussianBlur(denoised, (0,0), 1)
sharp = cv2.addWeighted(denoised, 1.5, blur, -0.5, 0)

# 5. salva modificata
proc_path = f"{base_name}_proc.jpg"
cv2.imwrite(proc_path, sharp)
print(f"💾 Salvato migliorato: {proc_path} ({sharp.shape[1]}x{sharp.shape[0]})")

# 6. OCR su entrambe per confronto
print("\n--- OCR su ORIGINALE ---")
res_orig = ocr.run(orig_path)
if res_orig:
    print(f"✅ {res_orig[0].plate.upper()} ({res_orig[0].region})")
else:
    print("❌ niente")

print("\n--- OCR su MIGLIORATO ---")
res_proc = ocr.run(proc_path)
if res_proc:
    print(f"✅ {res_proc[0].plate.upper()} ({res_proc[0].region})")
else:
    print("❌ niente")

print("\nApri i due file e confronta visivamente.")