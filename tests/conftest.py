"""Make the checkout's stage modules available to tests without package aliases."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for directory in sorted((ROOT / 'code').iterdir()):
    if directory.is_dir():
        sys.path.insert(0, str(directory))
