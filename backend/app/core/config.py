"""Stable paths and environment loading; importing creates no files or connections."""
from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / 'data'
RUNTIME_DIR = BACKEND_DIR / 'var'
PHOTO_MAX_BYTES = 10 * 1024 * 1024

load_dotenv(BACKEND_DIR / '.env', encoding='utf-8-sig')
