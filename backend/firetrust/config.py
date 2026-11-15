"""Minimal local configuration loader; process environment always takes precedence."""
import os
from pathlib import Path


def load_local_environment():
    path=Path(__file__).resolve().parents[2]/'.env'
    if not path.exists():return
    allowed={'FIRMS_MAP_KEY','FIRETRUST_DATA_DIR','FIRETRUST_WRITE_TOKEN'}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line=line.strip()
        if not line or line.startswith('#') or '=' not in line:continue
        key,value=line.split('=',1)
        key=key.strip();value=value.strip().strip('"').strip("'")
        if key in allowed:os.environ.setdefault(key,value)
