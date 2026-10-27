"""Render selected icon A (parcel/export arrow), without the firefly accent."""
import subprocess
import sys
from pathlib import Path
subprocess.run([sys.executable,str(Path(__file__).with_name('options.py')),'--selected'],check=True)
