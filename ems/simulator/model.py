"""Ideal aggregate plant, deterministic and single-threaded; no EMS control."""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import hashlib
import random

from ..domain.base import Record, require
from ..domain.models import QualityCode, identity, measurement
from .clock import Clock, ClockReading
from .config import Scenario, SimulatorConfig


class ReadFault(StrEnum):
    NONE = 'NONE'
    TIMEOUT = 'TIMEOUT'
    BAD_DATA = 'BAD_DATA'


class DeviceUnavailable(RuntimeError):
    pass


class SimulatedTimeout(TimeoutError):
    pass


@dataclass(frozen=True)
class RawMeasurement(Record):
    site_id: str
    device_id: str
    property: str
    value: float | None
    unit: str
    timestamp: datetime
    quality: QualityCode
    source: str
    config_version: str

    def validate(self):
        identity(self.site_id, 'siteId')
        identity(self.device_id, 'deviceId')
        require(self.property in ('active_power', 'soc'), 'property', 'unknown simulated property')
        measurement(self.value, self.unit, self.quality)
        require(self.source == 'SIMULATOR', 'source', 'expected SIMULATOR')
        require(self.unit == ('%' if self.property == 'soc' else 'kW'), 'unit', 'property unit mismatch')
        if self.property == 'soc':
            require(self.value is None or 0 <= self.value <= 100, 'value', 'SOC outside [0,100]')


@dataclass(frozen=True)
class PlantState(Record):
    timestamp: datetime
    elapsed_seconds: float
    load_kw: float
    pv_kw: float
    ev_kw: float
    requested_ess_kw: float
    ess_kw: float
    pcc_kw: float
    energy_kwh: float
    soc: float


class Simulator:
    """One aggregate per resource; setters are test/scenario injection only.

    Physics is evaluated analytically from the most recent scenario anchor.
    Repeated reads do not advance time or re-integrate energy. At SOC 0/100,
    the plant's actual ESS power is zero in the blocked direction. This is a
    physical saturation model, not an EMS protection/controller implementation.
    """
    DEVICE_IDS = ('load01', 'pv01', 'ess01', 'pcc01', 'ev01')

    def __init__(self, config: SimulatorConfig, clock: Clock):
        require(isinstance(config, SimulatorConfig), 'config', 'expected SimulatorConfig')
        self._config = config
        self._clock = clock
        self._last_monotonic = -1.0
        initial = self._read_clock()
        self._origin = initial.monotonic_seconds
        self._anchor_time = initial.monotonic_seconds
        self._energy = config.capacity_kwh * config.initial_soc / 100
        self._scenario = config.initial_scenario
        self._connected = dict.fromkeys(self.DEVICE_IDS, True)
        self._faults = dict.fromkeys(self.DEVICE_IDS, ReadFault.NONE)

    @property
    def config(self):
        return self._config

    @property
    def scenario(self):
        return self._scenario

    def _read_clock(self):
        reading = self._clock.read()
        require(isinstance(reading, ClockReading), 'clock', 'expected ClockReading')
        require(reading.monotonic_seconds >= self._last_monotonic, 'clock', 'monotonic clock moved backwards')
        self._last_monotonic = reading.monotonic_seconds
        return reading

    def _state_at(self, reading):
        scenario = self._scenario
        energy = self._energy - scenario.ess_kw * ((reading.monotonic_seconds - self._anchor_time) / 3600)
        energy = max(0.0, min(self.config.capacity_kwh, energy))
        actual_ess = scenario.ess_kw
        if (energy <= 0 and actual_ess > 0) or (energy >= self.config.capacity_kwh and actual_ess < 0):
            actual_ess = 0.0
        elapsed = reading.monotonic_seconds - self._origin
        pv = scenario.pv_kw
        if scenario.pv_variation_kw:
            # One deterministic physical PV perturbation per elapsed second.
            # Local RNG avoids dependence on read order and global random state.
            material = f'{self.config.seed}:{int(elapsed)}'.encode('ascii')
            seed = int.from_bytes(hashlib.sha256(material).digest(), 'big')
            pv += random.Random(seed).uniform(-scenario.pv_variation_kw, scenario.pv_variation_kw)
        return PlantState(reading.timestamp, elapsed, scenario.load_kw, pv, scenario.ev_kw,
                          scenario.ess_kw, actual_ess, scenario.load_kw + scenario.ev_kw - pv - actual_ess,
                          energy, 100 * energy / self.config.capacity_kwh)

    def inspect_state(self) -> PlantState:
        """Test oracle; bypasses communication faults and is not a Gateway API."""
        return self._state_at(self._read_clock())

    def set_scenario(self, scenario: Scenario) -> None:
        # Validate before any mutation; old operating point applies until now.
        self.config.validate_scenario(scenario)
        reading = self._read_clock()
        energy = self._state_at(reading).energy_kwh
        self._energy = energy
        self._anchor_time = reading.monotonic_seconds
        self._scenario = scenario

    def _check_device(self, device_id):
        require(device_id in self.DEVICE_IDS, 'deviceId', 'unknown simulator device')

    def set_connection(self, device_id: str, connected: bool) -> None:
        self._check_device(device_id)
        require(type(connected) is bool, 'connected', 'expected bool')
        self._connected[device_id] = connected

    def set_fault(self, device_id: str, fault: ReadFault) -> None:
        self._check_device(device_id)
        require(isinstance(fault, ReadFault), 'fault', 'expected ReadFault')
        self._faults[device_id] = fault

    def check_connection(self, device_id: str) -> None:
        self._check_device(device_id)
        if not self._connected[device_id]:
            raise DeviceUnavailable(f'{device_id}: simulated communication disconnected')

    def read(self, device_id: str) -> tuple[RawMeasurement, ...]:
        self.check_connection(device_id)
        fault = self._faults[device_id]
        if fault == ReadFault.TIMEOUT:
            raise SimulatedTimeout(f'{device_id}: injected timeout (no real wait)')
        state = self.inspect_state()
        power = {'load01':state.load_kw, 'pv01':state.pv_kw, 'ess01':state.ess_kw,
                 'pcc01':state.pcc_kw, 'ev01':state.ev_kw}[device_id]
        points = [('active_power', power, 'kW')]
        if device_id == 'ess01':
            points.append(('soc', state.soc, '%'))
        return tuple(RawMeasurement(self.config.site_id, device_id, prop,
                                   None if fault == ReadFault.BAD_DATA else value, unit, state.timestamp,
                                   QualityCode.BAD if fault == ReadFault.BAD_DATA else QualityCode.GOOD,
                                   'SIMULATOR', self.config.config_version) for prop, value, unit in points)


class SimulatedDriver:
    """Small device-bound adapter ready for the M0.1.4 Gateway; no retry loop."""
    def __init__(self, simulator: Simulator, device_id: str):
        simulator._check_device(device_id)
        self._simulator = simulator
        self._device_id = device_id
        self._opened = False

    def connect(self) -> None:
        self._simulator.check_connection(self._device_id)
        self._opened = True

    def read(self) -> tuple[RawMeasurement, ...]:
        if not self._opened:
            raise DeviceUnavailable(f'{self._device_id}: driver is closed')
        return self._simulator.read(self._device_id)

    def close(self) -> None:
        self._opened = False
