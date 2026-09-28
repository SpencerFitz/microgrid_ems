from contextlib import closing, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from ems.config import ConfigError, load_config
from ems.runtime import AlreadyRunning, demo, instance_lock, read_status, run

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "configs/site/demo.json"


class ConfigTests(unittest.TestCase):
    def test_valid_config(self):
        self.assertEqual(load_config(FIXTURE).site_id, "site01")

    def test_invalid_fields(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cases = {"siteId": ["", "site.*", 123], "timezone": ["Local", "invalid/zone"],
                 "configVersion": ["", None], "pollTimeoutMs": [0, True, 1000],
                 "samplingIntervalMs": [800], "staleAfterMs": [1000],
                 "offlineAfterMs": [3000, 3600001], "logLevel": ["TRACE"]}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            for field, values in cases.items():
                for value in values:
                    with self.subTest(field=field, value=value):
                        path.write_text(json.dumps({**fixture, field: value}), encoding="utf-8")
                        with self.assertRaises(ConfigError):
                            load_config(path)

    def test_bad_json_unknown_missing_and_duplicate(self):
        fixture = FIXTURE.read_text(encoding="utf-8")
        samples = ["{", fixture + " {}", fixture.replace('"siteId"', '"unknown"'),
                   fixture.replace('"siteId": "site01",', ''),
                   fixture.replace('"siteId": "site01",', '"siteId": "a", "siteId": "b",'),
                   " " * 65537]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            for text in samples:
                path.write_text(text, encoding="utf-8")
                with self.subTest(text=text[:40]), self.assertRaises(ConfigError):
                    load_config(path)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "runtime"
        self.config = load_config(FIXTURE)

    def test_demo_and_logs(self):
        with redirect_stdout(io.StringIO()):
            result = demo(self.config, self.data)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(read_status(self.data)["state"], "STOPPED")
        records = [json.loads(line) for line in (self.data / "logs/ems.log").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(records), 4)
        for record in records:
            self.assertEqual(set(record), {"time", "level", "service", "siteId", "message"})
            self.assertTrue(record["time"].endswith("Z"))
        with closing(sqlite3.connect(self.data / "state.sqlite3")) as conn:
            names = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        self.assertEqual(names, [("bootstrap_meta",)])

    def test_exclusive_lock_and_release(self):
        with instance_lock(self.data):
            with self.assertRaises(AlreadyRunning):
                with instance_lock(self.data):
                    pass
        with instance_lock(self.data):
            pass

    def test_keyboard_interrupt_stops_and_keeps_files(self):
        with redirect_stdout(io.StringIO()), patch("ems.runtime.time.sleep", side_effect=KeyboardInterrupt):
            result = run(self.config, self.data)
        self.assertTrue(result["interrupted"])
        self.assertEqual(read_status(self.data)["state"], "STOPPED")
        with instance_lock(self.data):
            pass

    def test_missing_and_stale_status(self):
        self.assertEqual(read_status(self.data)["state"], "NOT_STARTED")
        with redirect_stdout(io.StringIO()):
            run(self.config, self.data, ticks=1)
        status_path = self.data / "status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["state"] = "RUNNING"
        status["updatedAt"] = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        status_path.write_text(json.dumps(status), encoding="utf-8")
        with instance_lock(self.data):
            self.assertEqual(read_status(self.data)["state"], "UNAVAILABLE")
        self.assertFalse(read_status(self.data)["live"])

    def test_unwritable_data_location(self):
        self.data.parent.mkdir(exist_ok=True)
        self.data.write_text("this is a file, not a directory", encoding="utf-8")
        with self.assertRaises(OSError):
            run(self.config, self.data, ticks=1)


class CLITests(unittest.TestCase):
    def invoke(self, args):
        return subprocess.run([sys.executable, str(ROOT / "ems.py"), *args], cwd=ROOT,
                              capture_output=True, text=True, encoding="utf-8", timeout=10,
                              creationflags=subprocess.CREATE_NO_WINDOW)

    def test_doctor_and_validate(self):
        for command in ("doctor", "validate"):
            result = self.invoke([command])
            self.assertEqual(result.returncode, 0, result.stderr)
            json.loads(result.stdout)

    def test_invalid_config_nonzero(self):
        result = self.invoke(["--config", "missing-file.json", "run", "--ticks", "1"])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["type"], "ConfigError")

    def test_live_lock_crash_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "runtime"
            process = subprocess.Popen([sys.executable, str(ROOT / "ems.py"), "--data-dir", str(data), "run"],
                                       cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                deadline = time.monotonic() + 5
                while not (data / "status.json").exists() and time.monotonic() < deadline:
                    if process.poll() is not None:
                        self.fail("runtime exited before first heartbeat")
                    time.sleep(0.02)
                self.assertTrue(read_status(data)["live"])
                duplicate = self.invoke(["--data-dir", str(data), "run", "--ticks", "1"])
                self.assertEqual(duplicate.returncode, 1)
                self.assertEqual(json.loads(duplicate.stderr)["type"], "AlreadyRunning")
            finally:
                process.terminate()
                process.wait(timeout=5)
            self.assertEqual(read_status(data)["state"], "UNAVAILABLE")
            recovery = self.invoke(["--data-dir", str(data), "run", "--ticks", "1"])
            self.assertEqual(recovery.returncode, 0, recovery.stderr)
            self.assertEqual(read_status(data)["state"], "STOPPED")


if __name__ == "__main__":
    unittest.main()
