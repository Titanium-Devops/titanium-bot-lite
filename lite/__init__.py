"""Titanium Tiiny Bot, a small local console."""
import time

# Start before the remaining package and server imports for CLI readiness timing.
IMPORT_STARTED = time.monotonic()

from pathlib import Path

__version__ = Path(__file__).with_name("VERSION").read_text(encoding="utf-8").strip()
