"""
action_autorizzato.py
Script eseguito ogni volta che viene rilevata una targa AUTORIZZATA.

Riceve la targa e il nome del proprietario come argomenti CLI:
    python action_autorizzato.py AB123CD "Mario Rossi"

Sostituisci il contenuto con la tua logica reale (apri cancello, log esterno, ecc.)
"""

import sys
from datetime import datetime

def main():
    targa = sys.argv[1] if len(sys.argv) > 1 else "???"
    nome  = sys.argv[2] if len(sys.argv) > 2 else "Sconosciuto"

    print(f"👋 Hello World!")
    print(f"   Targa autorizzata: {targa}")
    print(f"   Proprietario: {nome}")
    print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()