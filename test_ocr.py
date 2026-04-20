from fast_plate_ocr import LicensePlateRecognizer
import os

# Percorso dell'immagine
image_path = "targhe_salvate/2026-04-19/ID_1_014601.jpg"

if not os.path.exists(image_path):
    print(f"❌ Errore: Il file {image_path} non esiste!")
else:
    print("⏳ Caricamento modello OCR (XS)...")
    m = LicensePlateRecognizer('cct-xs-v2-global-model')
    
    print(f"🧐 Analisi immagine: {image_path}")
    results = m.run(image_path)
    
    if results:
        # Estraiamo il primo risultato dalla lista
        pred = results[0]
        print(f"📝 RISULTATO OCR: {pred}")
        
        # Accediamo alle proprietà specifiche dell'oggetto
        targa_letta = pred.plate        # Es: 'EV367EX'
        nazione = pred.region           # Es: 'Italy'
        
        print("-" * 30)
        print(f"✅ TARGA ESTRATTA: {targa_letta}")
        print(f"🌍 NAZIONE:        {nazione}")
        print("-" * 30)
        
        # Simulazione di quello che finirebbe nel CSV
        testo_per_csv = targa_letta.upper().strip()
        print(f"📝 Formato per CSV: {testo_per_csv}")
    else:
        print("❓ Nessun testo rilevato nell'immagine.")