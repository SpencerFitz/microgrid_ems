"""M0.1.1 lifecycle, local health, locking and storage-retention demonstration.

No telemetry, event bus, historian, controllers or device commands are implemented.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import msvcrt
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid


COMPONENTS = ("simulator", "device_gateway", "ems_core", "data_service")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class AlreadyRunning(RuntimeError):
    pass


@contextmanager
def instance_lock(data_dir: Path):
    """Windows releases this byte-range lock on process death; no stale PID unlock."""
    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / "instance.lock").open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise AlreadyRunning("another EMS instance is using this data directory") from exc
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


class JSONFormatter(logging.Formatter):
    def __init__(self, site_id):
        super().__init__()
        self.site_id = site_id

    def format(self, record):
        return json.dumps({"time": utc_now(), "level": record.levelname,
                           "service": "ems_runtime", "siteId": self.site_id,
                           "message": record.getMessage()}, ensure_ascii=False)


@contextmanager
def runtime_logger(data_dir, config):
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    logger = logging.Logger("ems_runtime", level=config.log_level)
    formatter = JSONFormatter(config.site_id)
    handlers = [logging.StreamHandler(sys.stdout),
                RotatingFileHandler(data_dir / "logs/ems.log", maxBytes=1000000,
                                    backupCount=3, encoding="utf-8")]
    try:
        for handler in handlers:
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        yield logger
    finally:
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()


def open_state(data_dir):
    """Only bootstrap metadata. No business/history tables before M0.1.7."""
    conn = sqlite3.connect(data_dir / "state.sqlite3", timeout=1.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=1000")
        conn.execute("CREATE TABLE IF NOT EXISTS bootstrap_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT OR IGNORE INTO bootstrap_meta VALUES (?, ?)",
                     ("installation_id", str(uuid.uuid4())))
        conn.commit()
        return conn
    except BaseException:
        conn.close()
        raise


def installation_id(conn):
    return conn.execute("SELECT value FROM bootstrap_meta WHERE key = ?",
                        ("installation_id",)).fetchone()[0]


def write_status(data_dir, state, components, ticks):
    payload = {"stage": "M0.1.1", "state": state, "pid": os.getpid(),
               "updatedAt": utc_now(), "ticks": ticks, "components": components,
               "meaning": "bootstrap health only; no telemetry or control"}
    temp = data_dir / "status.tmp"
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, data_dir / "status.json")


def read_status(data_dir):
    """Report observations honestly: a last heartbeat alone is not live health."""
    path = data_dir / "status.json"
    if not path.exists():
        return {"state": "NOT_STARTED", "recordedState": None, "live": False}
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        updated = datetime.fromisoformat(record["updatedAt"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - updated).total_seconds()
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("invalid status file") from exc
    locked = False
    try:
        with instance_lock(data_dir):
            pass
    except AlreadyRunning:
        locked = True
    live = locked and 0 <= age <= 5 and record.get("state") == "RUNNING"
    # A lock with an old heartbeat means hung/unknown, not a successful health check.
    state = "RUNNING" if live else ("STOPPED" if record.get("state") == "STOPPED" and not locked else "UNAVAILABLE")
    return {"state": state, "recordedState": record.get("state"), "live": live,
            "heartbeatAgeSeconds": round(age, 3), "lastRecord": record}


def run(config, data_dir, *, ticks=0, interval=1.0):
    if ticks < 0 or not 0 < interval <= 2:
        raise ValueError("ticks must be nonnegative; interval must be in (0, 2]")
    with instance_lock(data_dir), runtime_logger(data_dir, config) as logger:
        conn = open_state(data_dir)
        components = {name: "READY" for name in COMPONENTS}
        count = 0
        interrupted = False
        failed = False
        try:
            identity = installation_id(conn)
            logger.info("bootstrap started; four logical modules; no business data")
            while ticks == 0 or count < ticks:
                conn.execute("SELECT 1").fetchone()
                count += 1
                write_status(data_dir, "RUNNING", components, count)
                if ticks == 0 or count < ticks:
                    time.sleep(interval)
        except KeyboardInterrupt:
            interrupted = True
            logger.info("stop requested")
        except Exception:
            failed = True
            logger.error("bootstrap failed")
            raise
        finally:
            conn.close()
            final_state = "FAILED" if failed else "STOPPED"
            write_status(data_dir, final_state, {name: final_state for name in COMPONENTS}, count)
            logger.info("bootstrap stopped; local files retained")
        return {"installationId": identity, "ticks": count, "interrupted": interrupted}


def demo(config, data_dir):
    first = run(config, data_dir, ticks=3, interval=0.01)
    if read_status(data_dir)["state"] != "STOPPED":
        raise RuntimeError("first run did not stop cleanly")
    second = run(config, data_dir, ticks=3, interval=0.01)
    if first["installationId"] != second["installationId"]:
        raise RuntimeError("bootstrap metadata did not survive restart")
    result = {"result": "PASS", "stage": "M0.1.1", "components": list(COMPONENTS),
              "firstTicks": first["ticks"], "secondTicks": second["ticks"],
              "retainedInstallationId": second["installationId"], "finishedAt": utc_now(),
              "scope": "configuration/lifecycle/logs/SQLite metadata; not telemetry"}
    (data_dir / "demo_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
