"""
garage_checker/main.py

Main entry point for the Garage Checker application.
"""

import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from garage_checker.core.engine import GarageEngine

def main():
    try:
        engine = GarageEngine()
        engine.run()
    except KeyboardInterrupt:
        print("\n🛑 Stopping Garage Checker...")
    except Exception as e:
        print(f"❌ Fatal Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("✅ Goodbye!")

if __name__ == "__main__":
    main()
