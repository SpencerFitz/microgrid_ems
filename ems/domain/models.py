"""M0.1.2 data contracts; no acquisition, scheduling or control execution."""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import re

from .base import Record, require


class QualityCode(StrEnum):
    GOOD = 'GOOD'
    BAD = 'BAD'
    STALE = 'STALE'
    OFFLINE = 'OFFLINE'
    MANUAL = 'MANUAL'
    UNCERTAIN = 'UNCERTAIN'


class DataType(StrEnum):
    FLOAT64 = 'FLOAT64'
    INT64 = 'INT64'
    BOOL = 'BOOL'
    STRING = 'STRING'


class DeviceType(StrEnum):
    GRID_METER = 'GRID_METER'
    METER = 'METER'
    PV_INVERTER = 'PV_INVERTER'
    ESS_PCS = 'ESS_PCS'
    BMS = 'BMS'
    EVSE = 'EVSE'
    MGCC = 'MGCC'
    PLC = 'PLC'
    BREAKER = 'BREAKER'
    WEATHER = 'WEATHER'


class DeviceStatus(StrEnum):
    DISABLED = 'DISABLED'
    DISCONNECTED = 'DISCONNECTED'
    CONNECTING = 'CONNECTING'
    ONLINE = 'ONLINE'
    DEGRADED = 'DEGRADED'


class TagSource(StrEnum):
    DRIVER = 'DRIVER'
    CALCULATED = 'CALCULATED'
    MANUAL = 'MANUAL'


class OperatingMode(StrEnum):
    STOPPED = 'STOPPED'
    GRID_CONNECTED = 'GRID_CONNECTED'
    ISLAND_TRANSITION = 'ISLAND_TRANSITION'
    ISLAND = 'ISLAND'
    BLACK_START = 'BLACK_START'
    FAULT = 'FAULT'
    MAINTENANCE = 'MAINTENANCE'


class Completeness(StrEnum):
    COMPLETE = 'COMPLETE'
    INCOMPLETE = 'INCOMPLETE'


UNITS = ('kW', 'kvar', 'kWh', 'V', 'A', 'Hz', '%', '°C', '1')
Value = float | int | bool | str | None


def identity(value, path):
    require(re.fullmatch(r'[a-z0-9_-]+', value), path, 'use lowercase letters/digits/_/-')


def tag_identity(value, path='tagId'):
    require(re.fullmatch(r'[a-z0-9_-]+\.[a-z0-9_-]+\.[a-z][a-z0-9_]*', value), path, 'expected site.device.property')


def linked_ids(site_id, device_id, tag_id):
    identity(site_id, 'siteId')
    identity(device_id, 'deviceId')
    tag_identity(tag_id)
    require(tag_id.startswith(f'{site_id}.{device_id}.'), 'tagId', 'site/device mismatch')


def measurement(value, unit, quality, path='value'):
    require(unit in UNITS, 'unit', 'unsupported unit')
    require(quality != QualityCode.GOOD or value is not None, path, 'GOOD cannot be null')
    if type(value) is int:
        require(-(2**63) <= value < 2**63, path, 'integer outside INT64')


@dataclass(frozen=True)
class Site(Record):
    id: str
    name: str
    timezone: str
    pcc_device_id: str
    rated_power_kw: float
    grid_import_limit_kw: float
    grid_export_limit_kw: float
    config_version: str

    def validate(self):
        identity(self.id, 'id')
        identity(self.pcc_device_id, 'pccDeviceId')
        require(self.timezone in ('Asia/Shanghai', 'UTC'), 'timezone', 'unsupported M01 timezone')
        for field in ('rated_power_kw', 'grid_import_limit_kw', 'grid_export_limit_kw'):
            require(getattr(self, field) >= 0, field, 'must be nonnegative')


@dataclass(frozen=True)
class Device(Record):
    id: str
    site_id: str
    name: str
    type: DeviceType
    vendor: str
    model: str
    driver: str
    protocol: str
    enabled: bool
    status: DeviceStatus
    config_version: str

    def validate(self):
        identity(self.id, 'id')
        identity(self.site_id, 'siteId')


@dataclass(frozen=True)
class TagDefinition(Record):
    id: str
    site_id: str
    device_id: str
    name: str
    data_type: DataType
    unit: str
    writable: bool
    deadband: float
    sampling_interval_ms: int
    stale_after_ms: int
    offline_after_ms: int
    source: TagSource
    config_version: str
    min_value: float | None = None
    max_value: float | None = None

    def validate(self):
        linked_ids(self.site_id, self.device_id, self.id)
        require(self.unit in UNITS, 'unit', 'unsupported unit')
        require(0 < self.sampling_interval_ms < self.stale_after_ms < self.offline_after_ms,
                'samplingIntervalMs', 'require 0 < sampling < stale < offline')
        require(self.deadband >= 0, 'deadband', 'must be nonnegative')
        require(self.min_value is None or self.max_value is None or self.min_value <= self.max_value,
                'minValue', 'must not exceed maxValue')
        if self.data_type in (DataType.BOOL, DataType.STRING):
            require(self.unit == '1' and self.min_value is None and self.max_value is None and self.deadband == 0,
                    'dataType', 'BOOL/STRING require unit 1, no numeric bounds and zero deadband')
        if self.id.endswith('.soc'):
            require(self.unit == '%' and self.data_type in (DataType.FLOAT64, DataType.INT64)
                    and self.min_value is not None and self.max_value is not None
                    and 0 <= self.min_value <= self.max_value <= 100, 'minValue/maxValue', 'SOC requires numeric % bounds within [0,100]')


@dataclass(frozen=True)
class TelemetrySample(Record):
    sample_id: str
    site_id: str
    device_id: str
    tag_id: str
    value: Value
    timestamp: datetime
    received_at: datetime
    quality: QualityCode
    quality_timestamp: datetime
    unit: str
    source: str
    producer_epoch: str
    sequence: int
    config_version: str
    reason: str | None = None

    def validate(self):
        linked_ids(self.site_id, self.device_id, self.tag_id)
        measurement(self.value, self.unit, self.quality)
        require(self.sequence >= 0, 'sequence', 'must be nonnegative')
        if self.tag_id.endswith('.soc'):
            require(self.unit == '%', 'unit', 'SOC requires %')
            require(self.value is None or (type(self.value) in (float, int) and 0 <= self.value <= 100), 'value', 'SOC must be [0,100] or null with non-GOOD quality')

    def validate_against(self, tag: TagDefinition):
        require(isinstance(tag, TagDefinition), 'tag', 'expected TagDefinition')
        require((self.site_id, self.device_id, self.tag_id) == (tag.site_id, tag.device_id, tag.id), 'tagId', 'definition identity mismatch')
        require(self.unit == tag.unit, 'unit', 'definition unit mismatch')
        require(self.config_version == tag.config_version, 'configVersion', 'definition version mismatch')
        if self.value is None:
            return self
        expected = {DataType.FLOAT64: (float, int), DataType.INT64: (int,), DataType.BOOL: (bool,), DataType.STRING: (str,)}
        require(type(self.value) in expected[tag.data_type], 'value', f'expected {tag.data_type}')
        if tag.data_type in (DataType.FLOAT64, DataType.INT64):
            require(tag.min_value is None or self.value >= tag.min_value, 'value', 'below minValue')
            require(tag.max_value is None or self.value <= tag.max_value, 'value', 'above maxValue')
        return self


@dataclass(frozen=True)
class TelemetryEnvelope(Record):
    schema_version: int
    message_id: str
    event_type: str
    site_id: str
    producer: str
    published_at: datetime
    correlation_id: str
    payload: TelemetrySample

    def validate(self):
        require(self.schema_version == 1, 'schemaVersion', 'unsupported version; expected 1')
        require(self.event_type == 'telemetry.updated', 'eventType', 'expected telemetry.updated')
        require(self.site_id == self.payload.site_id, 'siteId', 'payload site mismatch')


@dataclass(frozen=True)
class SnapshotValue(Record):
    value: Value
    unit: str
    sample_timestamp: datetime
    received_at: datetime
    effective_quality: QualityCode
    quality_timestamp: datetime
    age_ms: int
    sample_id: str
    source: str

    def validate(self):
        measurement(self.value, self.unit, self.effective_quality)
        require(self.age_ms >= 0, 'ageMs', 'must be nonnegative; future timestamp needs explicit handling in M0.1.6')


@dataclass(frozen=True)
class SystemSnapshot(Record):
    id: str
    site_id: str
    cycle: int
    core_epoch: str
    timestamp: datetime
    cutoff_time: datetime
    config_version: str
    operating_mode: OperatingMode
    tags: Mapping[str, SnapshotValue]
    grid: Mapping[str, str]
    load: Mapping[str, str]
    pv: Mapping[str, str]
    ess: Mapping[str, str]
    ev: Mapping[str, str]
    completeness: Completeness
    control_eligible: bool
    missing_tag_ids: tuple[str, ...]
    invalid_tag_ids: tuple[str, ...]
    calculated_pcc: SnapshotValue | None = None
    balance_residual: SnapshotValue | None = None

    def validate(self):
        identity(self.site_id, 'siteId')
        require(self.cycle >= 0, 'cycle', 'must be nonnegative')
        require(self.cutoff_time <= self.timestamp, 'cutoffTime', 'must not exceed timestamp')
        require(not self.control_eligible, 'controlEligible', 'M01 always false')
        require((self.completeness == Completeness.COMPLETE) == (not self.missing_tag_ids), 'completeness', 'must agree with missingTagIds')
        for tag_id in (*self.tags, *self.missing_tag_ids, *self.invalid_tag_ids):
            tag_identity(tag_id)
            require(tag_id.startswith(self.site_id + '.'), 'tags', 'site mismatch')
        require(not set(self.missing_tag_ids) & self.tags.keys(), 'missingTagIds', 'missing tags cannot be present')
        require(set(self.invalid_tag_ids) <= self.tags.keys(), 'invalidTagIds', 'must reference present tags')
        for group, allowed in RESOURCE_FIELDS.items():
            view = getattr(self, group)
            require(view.keys() <= allowed.keys(), group, 'unknown resource property')
            for key, tag_id in view.items():
                require(tag_id in self.tags, f'{group}.{key}', 'reference must exist in tags')
                require(self.tags[tag_id].unit == allowed[key], f'{group}.{key}', 'reference unit mismatch')
        for name in ('calculated_pcc', 'balance_residual'):
            value = getattr(self, name)
            require(value is None or value.unit == 'kW', name, 'expected kW')


# Resource views are explicit references into the authoritative tags map.
RESOURCE_FIELDS = {
    'grid': {'activePowerKw': 'kW', 'reactivePowerKvar': 'kvar', 'voltageV': 'V', 'frequencyHz': 'Hz', 'gridPresent': '1', 'breakerState': '1'},
    'load': {'activePowerKw': 'kW'}, 'pv': {'activePowerKw': 'kW'}, 'ev': {'activePowerKw': 'kW'},
    'ess': {'activePowerKw': 'kW', 'soc': '%', 'maxChargePowerKw': 'kW', 'maxDischargePowerKw': 'kW', 'online': '1'},
}
