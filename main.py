import cv2
import time
from ultralytics import YOLO

# =========================
# INIT
# =========================

model = YOLO("yolov8n.pt")

rtsp_url = "rtsp://192.168.1.203:554/realmonitor?channel=0&stream=1.sdp"

cap = cv2.VideoCapture(rtsp_url)

if not cap.isOpened():
    print("❌ Stream non aperto")
    exit()

print("✅ Stream connesso. Avvio detection...")

# =========================
# STATE VARIABLES
# =========================

frame_id = 0
last_snapshot_time = 0

# =========================
# MAIN LOOP
# =========================

try:
    while True:
        ret, frame = cap.read()

        # =========================
        # FIX 1: reconnect RTSP
        # =========================
        if not ret or frame is None:
            print("⚠️ Frame perso - riconnessione...")
            cap.release()
            time.sleep(1)
            cap = cv2.VideoCapture(rtsp_url)

            # 👇 messaggio di successo
            if cap.isOpened():
                print("✅ Riconnessione riuscita!")
            else:
                print("❌ Riconnessione fallita")

            continue

        # =========================
        # FIX 3: resize frame
        # =========================
        frame = cv2.resize(frame, (640, 360))

        # =========================
        # FIX 2: frame skip
        # =========================
        frame_id += 1
        if frame_id % 3 != 0:
            # preview anche senza YOLO
            cv2.imshow("AI Camera", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            continue

        # =========================
        # YOLO inference
        # =========================
        results = model(frame, verbose=False)

        person_detected = False

        for r in results:
            for box in r.boxes:
                cls = int(box.cls[0])
                label = model.names[cls]

                if label == "person":
                    person_detected = True

        # =========================
        # PREVIEW LIVE (always)
        # =========================
        cv2.imshow("AI Camera", frame)

        # =========================
        # SNAPSHOT (cooldown 5s)
        # =========================
        if person_detected:
            print("👤 PERSON DETECTED!")

            now = time.time()

            if now - last_snapshot_time > 5:
                filename = f"person_{int(now)}.jpg"
                cv2.imwrite(filename, frame)
                print(f"📸 Snapshot salvato: {filename}")
                last_snapshot_time = now

        # =========================
        # EXIT
        # =========================
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except KeyboardInterrupt:
    print("\n🛑 Stop manuale (CTRL+C)")

finally:
    cap.release()
    cv2.destroyAllWindows()
    print("🧹 Pulizia completata")