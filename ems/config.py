"""Strict bootstrap configuration, not a Device or Tag domain model."""
from dataclasses import dataclass
import json
from pathlib import Path
import re


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    site_id: str
    timezone: str
    config_version: str
    sampling_interval_ms: int
    poll_timeout_ms: int
    stale_after_ms: int
    offline_after_ms: int
    log_level: str


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError("duplicate configuration key")
        result[key] = value
    return result


def load_config(path: Path) -> Config:
    try:
        with path.open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ConfigError("configuration exceeds 64 KiB")
        data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError("configuration must be a readable UTF-8 JSON file") from exc
    keys = {"siteId", "timezone", "configVersion", "samplingIntervalMs", "pollTimeoutMs",
            "staleAfterMs", "offlineAfterMs", "logLevel"}
    if not isinstance(data, dict) or set(data) != keys:
        raise ConfigError("configuration contains missing or unknown fields")
    if not isinstance(data["siteId"], str) or not re.fullmatch(r"[a-z0-9_-]+", data["siteId"]):
        raise ConfigError("siteId must use lowercase letters, digits, underscore or hyphen")
    # M01 emits UTC only; no dependency on the Windows IANA timezone database.
    if data["timezone"] not in ("Asia/Shanghai", "UTC"):
        raise ConfigError("M01 supports timezone Asia/Shanghai or UTC")
    if not isinstance(data["configVersion"], str) or not data["configVersion"]:
        raise ConfigError("configVersion is required")
    names = ("pollTimeoutMs", "samplingIntervalMs", "staleAfterMs", "offlineAfterMs")
    values = [data[name] for name in names]
    if any(type(value) is not int for value in values):
        raise ConfigError("time intervals must be integers, not bool or float")
    if not (0 < values[0] < values[1] < values[2] < values[3] <= 3600000):
        raise ConfigError("require 0 < poll < sampling < stale < offline <= 3600000 ms")
    if data["logLevel"] not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        raise ConfigError("logLevel must be DEBUG, INFO, WARNING or ERROR")
    return Config(data["siteId"], data["timezone"], data["configVersion"],
                  data["samplingIntervalMs"], data["pollTimeoutMs"],
                  data["staleAfterMs"], data["offlineAfterMs"], data["logLevel"])
