# 👁️ VisionEdge-LocalAI

## 📌 Overview
Questo repository nasce come framework per trasformare comuni telecamere domestiche economiche in sistemi di monitoraggio intelligenti, operando interamente **offline e in locale**. 

L'obiettivo è il pieno controllo tecnico sulla pipeline video, ottimizzando le risorse per hardware come MacBook (M-series) o Raspberry Pi, evitando il transito di dati su server cloud esterni.

### ✨ Caratteristiche Tecniche
- **Efficienza:** Analisi a 10fps (su stream a 30fps) per ridurre il carico CPU/GPU.
- **Hardware Agnostic:** Supporto per Apple Metal (MPS) e predisposizione per hardware rudimentali.
- **Resilienza:** Gestione automatica delle riconnessioni agli stream RTSP.
- **Privacy-First:** Nessun dato lascia la rete locale.

---

## 📂 Struttura del Progetto

Il repository include diversi script specializzati per diverse fasi di implementazione:

- `main.py`: Script di base per la detection di persone in tempo reale (YOLOv8n).
- `camera_targhe.py`: Pipeline avanzata per il tracking di veicoli e rilevamento targhe.
- `onvif_test.py`: Utility per scoprire gli indirizzi RTSP delle telecamere via protocollo ONVIF.
- `yolov8n_plate.pt`: Modello custom ottimizzato per il rilevamento delle targhe.

---

## 🧠 Modelli e Riconoscimenti

Il rilevamento delle targhe utilizza un modello custom basato su YOLOv8n.
- **Modello Attuale:** Basato sull'addestramento di [PierW/plate-detection-yolov8](https://github.com/PierW/plate-detection-yolov8).
- **Nota Storica:** Nelle fasi iniziali è stato testato il modello `yolov8n_plate_BAK` derivato dal repository di [mendez-luisjose](https://github.com/mendez-luisjose/License-Plate-Detection-with-YoloV8-and-EasyOCR).

---

## ⚙️ Setup e Installazione

### 1. Clona il repository
```bash
git clone https://github.com/PierW/VisionEdge-LocalAI.git
cd VisionEdge-LocalAI
```

### 2. Crea ambiente virtuale
```bash
python3 -m venv video-ai-env
source video-ai-env/bin/activate
```

### 3. Installa dipendenze
```bash
pip install -r requirements.txt
```

### 4. Gestione Ambiente
Al termine della sessione, disattivare l'ambiente:
```bash
deactivate
```

---

## 🚀 Utilizzo

### Configurazione Camera
Usa il test ONVIF per trovare l'URL corretto della tua camera:
```bash
python onvif_test.py
```

### Avvio Rilevamento Persone (Standard)
```bash
python main.py
```

### Avvio Rilevamento e Tracking Targhe
```bash
python camera_targhe.py
```

---

## 🧪 Roadmap e Sviluppi Prossimi

- [ ] **Integrazione OCR:** Scelta del motore (EasyOCR vs PaddleOCR) per la lettura testuale.
- [ ] **LLM Integration:** Analisi contestuale degli eventi tramite modelli linguistici locali.
- [ ] **Web Dashboard:** Interfaccia leggera per il monitoraggio live.
- [ ] **Deduplicazione:** Logica per evitare salvataggi multipli della stessa targa/persona.

---

## 🧹 File esclusi da Git
- `video-ai-env/` (ambiente virtuale)
- `targhe_salvate/` (output delle immagini catturate)
- `__pycache__`

---

## 📜 Licenza
Uso personale / Sperimentale