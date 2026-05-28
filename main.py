#!/usr/bin/env python3
"""food-jx — Launch the GUI application (double-click to run)."""

import sys
from pathlib import Path

# Ensure src/ is importable from the project root
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# Also handle PyInstaller bundle path
if getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(sys.executable).parent))

from src.main import main

if __name__ == "__main__":
    main()
