"""NASA FIRMS CSV ingestion with content-addressed raw data and row validation."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import sqlite3
import threading
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

SOURCES = {f"{sensor}_{mode}" for sensor in ("VIIRS_SNPP", "VIIRS_NOAA20", "VIIRS_NOAA21", "MODIS") for mode in ("NRT", "SP")}
_WRITE_LOCK = threading.Lock()
PUBLIC = {
    "noaa20": "https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_Global_24h.csv",
    "noaa21": "https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-21-viirs-c2/csv/J2_VIIRS_C2_Global_24h.csv",
    "viirs": "https://firms.modaps.eosdis.nasa.gov/data/active_fire/viirs-c2/csv/SUOMI_VIIRS_C2_Global_24h.csv",
    "modis": "https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis-c6.1/csv/MODIS_C6_1_Global_24h.csv",
}


def root() -> Path:
    path = Path(os.getenv("FIRETRUST_DATA_DIR", "data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def connect() -> sqlite3.Connection:
    class ClosingConnection(sqlite3.Connection):
        def __exit__(self, *args):
            try:
                return super().__exit__(*args)
            finally:
                self.close()
    db = sqlite3.connect(root() / "firetrust.sqlite3", timeout=30, factory=ClosingConnection, check_same_thread=False)
    db.row_factory = sqlite3.Row
    from .geometry import within_area
    db.create_function('within_area',3,within_area,deterministic=True)
    db.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS areas (id TEXT PRIMARY KEY,geometry TEXT NOT NULL,bbox TEXT NOT NULL,area_km2 REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS batches (
      id TEXT PRIMARY KEY, source TEXT NOT NULL, fetched_at TEXT NOT NULL,
      raw_path TEXT NOT NULL, accepted INTEGER NOT NULL, rejected INTEGER NOT NULL,
      errors TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS detections (
      id TEXT PRIMARY KEY, latitude REAL NOT NULL, longitude REAL NOT NULL,
      acquired_at TEXT NOT NULL, sensor TEXT NOT NULL, satellite TEXT NOT NULL,
      confidence TEXT, confidence_class TEXT, frp REAL, scan REAL, track REAL,
      daynight TEXT, version TEXT, batch_id TEXT NOT NULL REFERENCES batches(id));
    CREATE INDEX IF NOT EXISTS detection_time ON detections(acquired_at);
    CREATE INDEX IF NOT EXISTS detection_location ON detections(latitude,longitude);
    CREATE TABLE IF NOT EXISTS batch_detections (
      batch_id TEXT NOT NULL REFERENCES batches(id), detection_id TEXT NOT NULL REFERENCES detections(id),
      PRIMARY KEY(batch_id,detection_id));
    CREATE INDEX IF NOT EXISTS batch_detection_lookup ON batch_detections(detection_id);
    """)
    columns = {r[1] for r in db.execute("PRAGMA table_info(detections)")}
    if "type_raw" not in columns:
        db.execute("ALTER TABLE detections ADD COLUMN type_raw TEXT DEFAULT ''")
    if "country" not in columns:
        db.execute("ALTER TABLE detections ADD COLUMN country TEXT DEFAULT ''")
    db.execute("CREATE INDEX IF NOT EXISTS detection_country_time ON detections(country,acquired_at DESC,id)")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def number(value: str | None, *, optional: bool = False) -> float | None:
    if optional and (value is None or value.strip() == ""):
        return None
    x = float(value)  # type: ignore[arg-type]
    if not math.isfinite(x):
        raise ValueError("non-finite number")
    return x


def normalize(row: dict[str, str], batch_id: str) -> dict:
    # csv.DictReader stores surplus fields under the None key and pads short rows with None.
    if None in row or any(value is None for value in row.values()):
        raise ValueError("malformed row: field count differs from header")
    lat, lon = number(row.get("latitude")), number(row.get("longitude"))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("coordinates outside WGS84 bounds")
    raw_time = row["acq_time"].strip()
    if not (raw_time.isascii() and raw_time.isdigit()) or len(raw_time) > 4:
        raise ValueError("invalid acquisition time")
    acquired = datetime.strptime(row["acq_date"] + " " + raw_time.zfill(4), "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
    sensor = row.get("instrument", "VIIRS" if "bright_ti4" in row else "MODIS" if "brightness" in row else "").strip().upper()
    if sensor not in {"VIIRS", "MODIS"}:
        raise ValueError("unsupported instrument")
    satellite = row["satellite"].strip()
    satellite = {"Terra":"T", "Aqua":"A", "Suomi-NPP":"N", "S-NPP":"N", "NOAA-20":"N20", "NOAA-21":"N21"}.get(satellite,satellite)
    if not satellite:
        raise ValueError("missing satellite")
    confidence = row.get("confidence", "").strip().lower()
    if sensor == "VIIRS":
        confidence = {"low": "l", "nominal": "n", "high": "h"}.get(confidence, confidence)
        if confidence not in {"l", "n", "h"}:
            raise ValueError("invalid VIIRS confidence")
        quality = {"l": "low", "n": "nominal", "h": "high"}[confidence]
    else:
        score = number(confidence)
        if not 0 <= score <= 100:
            raise ValueError("invalid MODIS confidence")
        quality = "low" if score < 30 else "nominal" if score < 80 else "high"
    frp, scan, track = [number(row.get(k), optional=True) for k in ("frp", "scan", "track")]
    if any(x is not None and x < 0 for x in (frp, scan, track)):
        raise ValueError("negative radiative power or footprint")
    daynight = row.get("daynight", "").upper()
    if daynight not in {"D", "N"}:
        raise ValueError("invalid daynight flag")
    result = dict(latitude=lat, longitude=lon, acquired_at=acquired.isoformat(), sensor=sensor,
                  satellite=satellite, confidence=confidence, confidence_class=quality,
                  frp=frp, scan=scan, track=track, daynight=daynight, version=row.get("version", ""))
    result["id"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    result["type_raw"] = row.get("type", "")
    result["batch_id"] = batch_id
    return result


def ingest_bytes(payload: bytes, source: str) -> dict:
    digest = hashlib.sha256(payload).hexdigest()
    raw_dir = root() / "raw"
    raw_dir.mkdir(exist_ok=True)
    raw_path = raw_dir / f"{digest}.csv"
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    required = {"latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("response is not a supported FIRMS CSV: required columns missing")
    rows, errors = [], []
    for line, row in enumerate(reader, 2):
        try:
            rows.append(normalize(row, digest))
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            errors.append({"line": line, "reason": str(exc)})
    # Exclusive creation preserves the original evidence bytes on retries.
    try:
        with raw_path.open("xb") as file:
            file.write(payload)
    except FileExistsError:
        if hashlib.sha256(raw_path.read_bytes()).hexdigest() != digest:
            raise ValueError("raw evidence checksum mismatch")
    country = ''
    if source.startswith('https://firms.modaps.eosdis.nasa.gov/data/country/'):
        country=source.rsplit('/',1)[-1].split('_',2)[-1].removesuffix('.csv')
    for row in rows:
        row['country']=country
    # Downloads may run in parallel, but SQLite has one writer: serialize batch transactions in-process
    # so large archives cannot exhaust the lock timeout (the cause of earlier OperationalError failures).
    with _WRITE_LOCK, connect() as db:
        prior = db.execute("SELECT * FROM batches WHERE id=?", (digest,)).fetchone()
        if prior:
            return {**dict(prior), "inserted": 0, "replayed": True}
        before = db.execute("SELECT count(*) FROM detections").fetchone()[0]
        db.execute("INSERT INTO batches VALUES (?,?,?,?,?,?,?)", (digest, source, datetime.now(timezone.utc).isoformat(),
                   str(raw_path), len(rows), len(errors), json.dumps(errors[:100])))
        if rows:
            columns = list(rows[0])
            db.executemany(f"INSERT OR IGNORE INTO detections ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                           (tuple(row[c] for c in columns) for row in rows))
            db.executemany("INSERT OR IGNORE INTO batch_detections VALUES (?,?)", ((digest, row["id"]) for row in rows))
            if country:
                db.executemany("UPDATE detections SET country=? WHERE id=? AND country=''", ((country, row['id']) for row in rows))
        inserted = db.execute("SELECT count(*) FROM detections").fetchone()[0] - before
    return dict(id=digest, source=source, accepted=len(rows), rejected=len(errors), inserted=inserted, errors=errors[:100], replayed=False)


def download(url: str, source: str) -> dict:
    # Never persist or print the URL: FIRMS area URLs contain the MAP_KEY.
    request = urllib.request.Request(url, headers={"User-Agent": "FIRETRUST/0.1 scientific prototype"})
    import time
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = response.read(100_000_001)
                declared = response.headers.get("Content-Length")
            if len(payload) > 100_000_000:
                raise ValueError("download exceeds 100 MB safety limit; narrow requested area")
            if declared and declared.isdigit() and int(declared) != len(payload):
                raise RuntimeError("truncated NASA download: received byte count differs from Content-Length")
            break
        except urllib.error.HTTPError as exc:
            if exc.code < 500 or attempt == 2:
                raise RuntimeError(f"NASA download failed with HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 2:
                raise RuntimeError("NASA download failed; check network, source availability and MAP_KEY") from None
        except RuntimeError:
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)
    return ingest_bytes(payload, source)


def fetch_area(source: str, bbox: str, days: int, start: str | None = None) -> dict:
    if source not in SOURCES or not 1 <= days <= 5:
        raise ValueError("supported source and 1-5 days required")
    coords = [float(x) for x in bbox.split(",")]
    if len(coords) != 4 or not all(math.isfinite(x) for x in coords):
        raise ValueError("bbox requires west,south,east,north")
    w, s, e, n = coords
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise ValueError("invalid bbox; split antimeridian requests")
    if start:
        date.fromisoformat(start)
    key = os.environ.get("FIRMS_MAP_KEY", "")
    if not key or not key.isalnum():
        raise ValueError("set a valid FIRMS_MAP_KEY environment variable")
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{bbox}/{days}"
    if start:
        url += f"/{start}"
    return download(url, f"NASA FIRMS {source}; bbox={bbox}; days={days}; start={start or 'latest'}")


