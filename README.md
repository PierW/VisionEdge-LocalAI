# VisionEdge-LocalAI

## Overview

Sistema di monitoraggio video locale con AI per il rilevamento di persone e veicoli, tracciamento con ID persistenti, riconoscimento targhe OCR e gestione whitelist via Telegram.

### Caratteristiche Principali

- **Rilevamento Persone:** Detection in tempo reale con registrazione video e notifiche Telegram
- **Conteggio Persone:** Conteggio attraverso linea virtuale con log dettagliati
- **Tracciamento Veicoli:** BoT-SORT tracking con ID persistenti, timeout automatico (6s)
- **Riconoscimento Targhe:** OCR adattivo giorno/notte con ensemble voting
- **Gestione Whitelist:** Database JSON con autorizzazioni e storico accessi
- **Telegram Bot:** Interazione per autorizzare/negare veicoli sconosciuti
- **Privacy-First:** Tutto offline, nessun dato cloud
- **Hardware Optimized:** Apple Metal (MPS) acceleration per Mac

---

## Struttura del Progetto

Il sistema è composto da **4 script principali** indipendenti:

### 1. targhe_auto/main.py - Rilevamento Veicoli con OCR
Monitora veicoli in transito con riconoscimento targhe automatico.

**Caratteristiche:**
- Rilevamento veicoli (car, moto, bus, truck) con YOLOv8
- Tracking con BoT-SORT (ID persistenti)
- OCR targhe con preprocessing adattivo giorno/notte
- Ensemble voting (2 varianti per massima accuratezza)
- Whitelist con autorizzazioni
- **Se un veicolo autorizzato entra, esegue uno script Python personalizzato**
- Notifiche Telegram con bottoni per autorizzare/negare/skippare

**Configurazione:** [targhe_auto/config.py](targhe_auto/config.py)

---

### 2. garage_checker/main.py - Monitoraggio Posti Auto (ROI)
Monitora posti auto specifici nel garage senza OCR.

**Caratteristiche:**
- Rilevamento veicoli con YOLOv8
- Zone ROI (Region of Interest) configurabili
- Check-in/check-out basato su timeout
- Nessun OCR, solo rilevamento presenza
- Notifiche Telegram

**Configurazione:** [garage_checker/config.py](garage_checker/config.py)

---

### 3. camera_persone.py - Rilevamento Persone
Rileva persone nella scena video con registrazione.

**Caratteristiche:**
- Rilevamento YOLOv8 classe "person"
- Registrazione video automatica quando persona rilevata
- Snapshot inviato su Telegram
- Chiusura registrazione dopo 2s di assenza
- Indicatori REC/LIVE

---

### 4. camera_conteggio_persone.py - Conteggio Persone
Conta persone che attraversano una linea virtuale.

**Caratteristicä:**
- Linea virtuale configurabile (default 50% altezza)
- Validazione crossing con storico posizione
- Check-in (entrata) e Check-out (uscita)
- Log dettagliati in CSV
- Riepilogo Telegram ogni 60 secondi

---

### File di Supporto

| File/Directory | Descrizione |
|----------------|-------------|
| `targhe_auto/config.py` | Configurazione (RTSP, soglie, timeout) |
| `targhe_auto/plate_processor.py` | Preprocessing adattivo + ensemble OCR |
| `targhe_auto/telegram_bot.py` | Bot Telegram per autorizzazione |
| `targhe_auto/whitelist_manager.py` | Gestione database veicoli |
| `garage_checker/roi_detector.py` | Rilevamento ROI |
| `garage_checker/roi_configurator.py` | Configuratore interattivo ROI |
| `test_onvif.py` | Utility per scoprire RTSP URL |
| `test_ocr.py` | Test OCR su immagini singole |
| `botsort_custom.yaml` | Configurazione BoT-SORT tracker |

---

## Configurazione

### Variabili d'ambiente (.env)

```env
TELEGRAM_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
RTSP_URL_TARGHE=rtsp://your_camera_ip:port/stream
```

### targhe_auto/config.py

```python
DEVICE = "mps" or "cpu"
TIMEOUT_VEICOLO = 6  # secondi per check-out
MAX_TENTATIVI_OCR = 10
MAX_CANDIDATI = 4
CONF_VEICOLI = 0.4
CONF_TARGA = 0.4
ORA_GIORNO = (7, 20)  # giorno/notte
```

### botsort_custom.yaml

```yaml
tracker_type: botsort
track_high_thresh: 0.45
track_low_thresh: 0.1
new_track_thresh: 0.5
track_buffer: 90
match_thresh: 0.7
fuse_score: True
with_reid: True
proximity_thresh: 0.5
appearance_thresh: 0.4
```

---

## Uso

### 1. Setup

```bash
# Clona e crea ambiente virtuale
git clone https://github.com/PierW/VisionEdge-LocalAI.git
cd VisionEdge-LocalAI
python3 -m venv video-ai-env
source video-ai-env/bin/activate
pip install -r requirements.txt

# Configura .env con TELEGRAM_TOKEN e TELEGRAM_CHAT_ID
```

### 2. Rilevamento Veicoli con OCR

```bash
python targhe_auto/main.py
```

**Flusso:**
1. Veicolo rilevato → Check-in
2. OCR targhe con ensemble voting
3. Controllo whitelist:
   - ✅ Autorizzato → esegue script Python + notifica
   - ❌ Non autorizzato → alert Telegram
   - ❓ Sconosciuto → alert con bottoni (Autorizza/Nega/Skippa/Modifica)
4. Timeout 6s → Check-out

**Telegram Bot:**
- `/stato` → veicoli nel garage
- Alert sconosciuta → 4 bottoni interattivi

---

### 3. Monitoraggio Posti Auto (ROI)

```bash
python garage_checker/main.py
```

**Primo avvio:** Configurazione interattiva delle ROI
**Funzionalità:**
- Zone ROI predefinite
- Check-in/check-out automatico
- Notifiche Telegram

---

### 4. Rilevamento Persone

```bash
python camera_persone.py
```

**Funzionalità:**
- Detection YOLOv8 person class
- Registrazione video quando persona rilevata
- Chiusura automatica dopo 2s di assenza
- Snapshot inviato su Telegram
- Indicatori REC/LIVE

---

### 5. Conteggio Persone

```bash
python camera_conteggio_persone.py
```

**Funzionalità:**
- Linea virtuale al 50% dell'altezza frame
- Validazione crossing con storico posizione
- Log dettagliati in `conteggio_log/passaggi.csv`
- Riepilogo Telegram ogni 60 secondi

1. **Check-in:** Veicolo rilevato → log ENTRATA
2. **OCR:** Max 4 candidati per veicolo → ensemble voting
3. **Whitelist check:**
   - Autorizzato → accesso + notifica
   - Non autorizzato → alert Telegram con bottoni
   - Sconosciuto → alert Telegram
4. **Check-out:** Timeout 6s → log USCITA

**Telegram Bot:**
- `/stato` → mostra veicoli nel garage
- Alert sconosciuta → 4 bottoni:
  - ✅ Autorizza → chiedi nome → salva whitelist
  - ❌ Nega → chiedi nome → salva whitelist
  - ⏭ Skippa → ignora sessione
  - ✏️ Modifica targa → chiedi targa corretta → nuovi bottoni

---

## Whitelist JSON

Struttura file `targhe_auto/whitelist.json`:

```json
{
  "AB123CD": {
    "targa": "AB123CD",
    "nome": "Mario Rossi",
    "autorizzato": true,
    "prima_vista": "2026-01-15 10:30:00",
    "ultimo_accesso": "2026-01-20 08:00:00",
    "ultima_uscita": "2026-01-20 18:00:00"
  }
}
```

---

## OCR Adattivo

### Rilevamento Giorno/Notte

Criterio triplo (basta uno scatta):
- `brightness < 80` → immagine scura
- `noise > 14` → alto rumore (ISO alto)
- `contrast < 30` → basso contrasto

### Preprocessing Variants

**Giorno:**
- `day_a`: Originale a colori
- `day_b`: CLAHE + sharpening

**Notte:**
- `night_a`: Denoising + CLAHE + gamma + sharpening
- `night_b`: Denoising aggressivo + CLAHE (no gamma)

### Ensemble OCR

- OCR su entrambe le varianti
- Vince la variante con confidence più alta
- Confidence = mean(char_probs)
- File temporanei puliti automaticamente

---

## Logging CSV

### targhe_auto/accessi_veicoli.csv

| Colonna | Descrizione |
|---------|-------------|
| Timestamp | Data/ora |
| ID_Veicolo | BoT-SORT object ID |
| Evento | ENTRATA/USCITA/TARGA_RILEVATA/TARGA_SCONOSCIUTA |
| File_Targa | Nome file immagine |
| Testo_Targa | Targa letta |
| Nazione | Regione/nazione |
| Proprietario | Nome dal whitelist |
| Modalita_OCR | diurna/notturna |
| Confidence | Score OCR |

### conteggio_log/passaggi.csv

| Colonna | Descrizione |
|---------|-------------|
| Timestamp | Data/ora |
| Evento | CHECK-IN/CHECK-OUT |
| ID | Object ID |
| Totale_IN | Totali ingressi |
| Totale_OUT | Totali uscite |
| Presenti | Attualmente presenti |

---

## API Whitelist

```python
from whitelist_manager import (
    is_known,      # targa presente?
    is_authorized, # targa autorizzata?
    get_entry,     # ottieni entry
    add_or_update, # aggiungi/aggiorna
    update_ultimo_accesso,
    update_ultima_uscita,
    list_all
)
```

---

## Roadmap

- [ ] **LLM Integration:** Analisi contestuale eventi
- [ ] **Web Dashboard:** Monitoraggio live
- [ ] **Deduplicazione:** Evita salvataggi multipli
- [ ] **Regole business:** Validazione targhe DB
- [ ] **Notifiche:** Email/SMS/Telegram alert

---

## File Esclusi da Git

- `video-ai-env/` (ambiente virtuale)
- `targhe_auto/targhe_salvate/` (immagini catturate)
- `targhe_auto/accessi_veicoli.csv` (log)
- `conteggio_log/` (log conteggio)
- `__pycache__`

---

## Licenza

Uso personale / Sperimentale
