# Garage Checker 🚗🅿️

Sistema di monitoraggio garage con 3 posti auto fissi. Non utilizza OCR; si basa sul rilevamento veicolo all'interno di zone predefinite (ROI) e sui nomi assegnati dall'utente.

## 🚀 Come Avviarlo

L'unico comando necessario è:

```bash
python garage_checker/main.py
```

### Primo Avvio (Configurazione)
Se è la prima volta che lo avvii (o se cancelli il file `rois.json`), si aprirà automaticamente una finestra di anteprima:
1. **Disegna 3 box**: Clicca e trascina con il mouse per disegnare un rettangolo su ognuno dei 3 posti auto.
2. **Salva**: Premi il tasto `s` per salvare la configurazione.
3. **Assegna Nomi**: Ti verrà chiesto di inserire il nome del veicolo o del proprietario per ciascun posto auto (es. "BMW di Mario").
4. **Reset**: Se sbagli durante il disegno, premi `r` per cancellare i box e ricominciare. Se sbagli i nomi, dovrai cancellare `rois.json` e riavviare.

Una volta salvato, il sistema creerà il file `rois.json` e non ti chiederà più la configurazione ai riavvii successivi.

## 📁 Struttura dei File

- **`main.py`**: L'entry point principale. Gestisce il flusso: *Stream -> YOLO -> ROI Check -> Notifiche Telegram*.
- **`config.py`**: Contiene tutte le impostazioni (URL RTSP, soglie di confidenza).
- **`roi_configurator.py`**: Il tool interattivo per disegnare i box e assegnare i nomi. Viene chiamato dal `main` se mancano le ROI.
- **`roi_detector.py`**: Gestisce la logica matematica per capire se un veicolo è dentro un posto auto e disegna l'interfaccia colorata.
- **`telegram_bot.py`**: Gestisce le comunicazioni via Telegram per notifiche di check-in/check-out e il comando `/stato`.
- **`rois.json`**: (Generato automaticamente) Contiene le coordinate dei tuoi 3 posti auto e i nomi assegnati.

## 💡 Come Funziona

1. **Rilevamento Veicolo**: Il sistema cerca veicoli in tutto il frame usando YOLO.
2. **Assegnazione al Posto**: Se un veicolo viene rilevato all'interno di una delle 3 zone ROI, il posto viene marcato come **Occupato**.
3. **Notifiche Telegram**: 
   - **Check-in**: Quando un veicolo occupa un posto, viene inviata una notifica "[Nome Veicolo] è arrivato al posto [ID]" su Telegram.
   - **Check-out**: Quando un veicolo non viene più rilevato in un posto per `TIMEOUT_VEICOLO` secondi, il posto torna **Libero** e viene inviata una notifica "[Nome Veicolo] è uscito dal posto [ID]".
   - **Comando /stato**: Invia un messaggio con la situazione attuale di tutti i posti auto (liberi o occupati con il nome assegnato).

## 🛠 Troubleshooting

- **I box non sono precisi?** Cancella il file `garage_checker/rois.json` e riavvia il `main.py` per ridisegnarli e riassegnare i nomi.
- **Troppi falsi positivi?** Alza la soglia `CONF_VEHICOLI` in `config.py`.
