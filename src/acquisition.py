"""Shared artifact provenance. Files are append-only snapshots, not vendor originals."""
import hashlib
import json
from pathlib import Path
import uuid
import pandas as pd


class AcquisitionError(ValueError):
    pass


def utc_now():
    return pd.Timestamp.now(tz="UTC")


def run_name(source, symbol, interval):
    import re
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", symbol)
    return f"{source}_{safe}_{interval}_{utc_now().strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False, default=str)


def write_csv(path, frame):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        frame.to_csv(stream, index=False)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
