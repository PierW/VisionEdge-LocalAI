# 👁️ VisionEdge-LocalAI

## 📌 Overview
Questo repository nasce come framework per trasformare comuni telecamere domestiche economiche in sistemi di monitoraggio intelligenti, operando interamente **offline e in locale**.

L'obiettivo è il pieno controllo tecnico sulla pipeline video, ottimizzando le risorse per hardware come MacBook (M-series) o Raspberry Pi, evitando il transito di dati su server cloud esterni.

### ✨ Caratteristiche Tecniche
- **Efficienza:** Analisi a 10fps (su stream a 30fps) per ridurre il carico CPU/GPU.
- **Hardware Agnostic:** Supporto Apple Metal (MPS) per accelerazione GPU su Mac.
- **Resilienza:** Gestione automatica delle riconnessioni agli stream RTSP con thread dedicato.
- **Privacy-First:** Nessun dato lascia la rete locale.
- **Tracking Multi-Oggetto:** Tracciamento persistente dei veicoli con ID univoci.
- **Gestione Stato OCR:** Controllo tentativi massimi per evitare loop infiniti.
- **Logging CSV:** Registrazione completa di tutti gli eventi (ENTRATA/USCITA/TARGA_RILEVATA).

---

## 📂 Struttura del Progetto

Il repository include diversi script specializzati per diverse fasi di implementazione:

- `camera_persone.py`: Script di base per la detection di persone in tempo reale (YOLOv8n).
- `camera_targhe.py`: Pipeline avanzata per il tracking di veicoli e rilevamento targhe con OCR.
- `test_onvif.py`: Utility per scoprire gli indirizzi RTSP delle telecamere via protocollo ONVIF.
- `test_ocr.py`: Utility per testare il modello OCR su immagini singole.
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
python test_onvif.py
```

### Avvio Rilevamento Persone (Standard)
```bash
python camera_persone.py
```

### Avvio Rilevamento e Tracking Targhe
```bash
python camera_targhe.py
```

---

## 🎯 Funzionalità camera_targhe.py

### Tracking Veicoli
- Rilevamento veicoli (classe: auto, moto, furgone, bus)
- Tracciamento persistente con ID univoci per ogni frame
- Timeout automatico per check-out (configurabile: 30 secondi default)

### Rilevamento Targhe con OCR
- Crop intelligente della regione di interesse (ROI) dalla targa
- Salvataggio immagini delle targhe per data
- OCR con modello `cct-xs-v2-global-model` per estrazione testo
- Rilevamento nazione/regione

### Gestione Errori OCR
- Tentativi massimi configurabili (`MAX_TENTATIVI_OCR = 10`)
- Conteggio fallimenti per evitare loop infiniti
- Pulizia automatica file immagine se tentativi esauriti
- Logging eventi nel CSV con stato di ogni tentativo

### Logging Eventi
File: `accessi_veicoli.csv`

Colonne:
- Timestamp
- ID_Veicolo
- Evento (ENTRATA/USCITA/TARGA_RILEVATA)
- File_Targa
- Testo_Targa
- Nazione

---

## 🧪 Roadmap e Sviluppi Prossimi

- [ ] **LLM Integration:** Analisi contestuale degli eventi tramite modelli linguistici locali
- [ ] **Web Dashboard:** Interfaccia leggera per il monitoraggio live
- [ ] **Deduplicazione:** Logica per evitare salvataggi multipli della stessa targa/persona
- [ ] **Regole business:** Integrazione con database per validazione targhe
- [ ] **Notifiche:** Alert via email/SMS/Telegram per eventi importanti

---

## 🧹 File esclusi da Git
- `video-ai-env/` (ambiente virtuale)
- `targhe_salvate/` (output delle immagini catturate)
- `accessi_veicoli.csv` (log eventi)
- `__pycache__`

---

## 📜 Licenza
Uso personale / Sperimentale
