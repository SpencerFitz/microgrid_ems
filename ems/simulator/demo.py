from dataclasses import replace
from math import isclose

from ..domain.base import require
from .clock import ManualClock
from .config import load_scenario
from .model import Simulator, SimulatedDriver, DeviceUnavailable


def demo_simulator(root):
    config = load_scenario(root / 'configs/scenarios/demo.json')
    clock = ManualClock(config.start_time)
    plant = Simulator(config, clock)
    rows = []

    def capture(label, pcc, soc):
        state = plant.inspect_state()
        require(isclose(state.pcc_kw, pcc, abs_tol=1e-6, rel_tol=0), label, 'PCC verification failed')
        require(isclose(state.soc, soc, abs_tol=1e-6, rel_tol=0), label, 'SOC verification failed')
        rows.append({'step':label, **state.to_dict()})

    capture('initial', 500, 60)
    plant.set_scenario(replace(plant.scenario, pv_kw=300))
    capture('pv_300', 200, 60)
    plant.set_scenario(replace(plant.scenario, pv_kw=350))
    capture('pv_350', 150, 60)
    plant.set_scenario(replace(plant.scenario, ess_kw=100))
    capture('ess_discharge_100', 50, 60)
    clock.advance(3600)
    capture('discharge_one_hour', 50, 50)
    plant.set_scenario(replace(plant.scenario, ess_kw=-100))
    capture('ess_charge_100', 250, 50)
    clock.advance(3600)
    capture('charge_one_hour', 250, 60)

    plant.set_scenario(replace(plant.scenario, ess_kw=100))
    driver = SimulatedDriver(plant, 'ess01')
    driver.connect()
    before = driver.read()
    plant.set_connection('ess01', False)
    clock.advance(3600)
    try:
        driver.read()
    except DeviceUnavailable:
        unavailable = True
    else:
        raise RuntimeError('disconnect demonstration did not reject reading')
    capture('communication_lost_physics_continues', 50, 50)
    plant.set_connection('ess01', True)
    driver.connect()
    after = driver.read()
    driver.close()
    require(after[1].value == 50 and after[1].timestamp > before[1].timestamp,
            'recovery', 'expected new successful SOC measurement')
    return {'result':'PASS', 'stage':'M0.1.3', 'clock':'virtual; no real waiting',
            'powerBalance':'P_PCC = P_Load + P_EV - P_PV - P_ESS', 'steps':rows,
            'disconnectReadRejected':unavailable,
            'recoveredMeasurements':[point.to_dict() for point in after],
            'explanation':'ESS 正值放电、负值充电。1000kWh 储能以100kW放电1小时，SOC下降10个百分点。断线只影响读取；模型继续运行。'}


def simulate_scenario(path, seconds):
    config = load_scenario(path)
    clock = ManualClock(config.start_time)
    plant = Simulator(config, clock)
    initial = plant.inspect_state()
    clock.advance(seconds)
    state = plant.inspect_state()
    points = [point.to_dict() for device in plant.DEVICE_IDS for point in plant.read(device)]
    return {'result':'PASS', 'stage':'M0.1.3', 'clock':'virtual',
            'initial':initial.to_dict(), 'final':state.to_dict(), 'measurements':points}
