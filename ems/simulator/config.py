"""Strict scenario configuration, separate from bootstrap and EMS commands."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..domain.base import Record, require
from ..domain.models import identity


@dataclass(frozen=True)
class Scenario(Record):
    load_kw: float
    pv_kw: float
    ess_kw: float
    ev_kw: float
    pv_variation_kw: float = 0

    def validate(self):
        for name in ('load_kw', 'pv_kw', 'ev_kw', 'pv_variation_kw'):
            require(0 <= getattr(self, name) <= 1_000_000, name, 'must be within [0,1000000] kW')
        require(abs(self.ess_kw) <= 1_000_000, 'essKw', 'magnitude must not exceed 1000000 kW')


@dataclass(frozen=True)
class SimulatorConfig(Record):
    schema_version: int
    site_id: str
    config_version: str
    start_time: datetime
    seed: int
    capacity_kwh: float
    initial_soc: float
    max_charge_kw: float
    max_discharge_kw: float
    pv_rated_kw: float
    initial_scenario: Scenario

    def validate(self):
        require(self.schema_version == 1, 'schemaVersion', 'expected 1')
        identity(self.site_id, 'siteId')
        require(0 < self.capacity_kwh <= 1_000_000_000, 'capacityKwh', 'must be within (0,1000000000]')
        require(0 <= self.initial_soc <= 100, 'initialSoc', 'must be within [0,100]')
        require(0 <= self.seed <= 2**32-1, 'seed', 'expected unsigned 32-bit seed')
        for name in ('max_charge_kw', 'max_discharge_kw', 'pv_rated_kw'):
            require(0 <= getattr(self, name) <= 1_000_000, name, 'must be within [0,1000000] kW')
        self.validate_scenario(self.initial_scenario)

    def validate_scenario(self, scenario: Scenario) -> None:
        require(isinstance(scenario, Scenario), 'scenario', 'expected Scenario')
        require(-self.max_charge_kw <= scenario.ess_kw <= self.max_discharge_kw,
                'essKw', 'outside charge/discharge rating')
        require(scenario.pv_variation_kw <= scenario.pv_kw
                and scenario.pv_kw + scenario.pv_variation_kw <= self.pv_rated_kw,
                'pvKw/pvVariationKw', 'entire variation range must be within [0,pvRatedKw]')


def load_scenario(path: Path) -> SimulatorConfig:
    with Path(path).open('rb') as stream:
        data = stream.read(65_537)
    require(len(data) <= 65_536, 'scenario', 'file exceeds 64 KiB')
    return SimulatorConfig.from_json(data.decode('utf-8-sig'))
