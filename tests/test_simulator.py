from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from ems.domain import QualityCode, ValidationError
from ems.simulator import (
    Simulator, SimulatorConfig, Scenario, ManualClock, ClockReading,
    RawMeasurement, SimulatedDriver, ReadFault, DeviceUnavailable,
    SimulatedTimeout, load_scenario,
)

ROOT = Path(__file__).resolve().parents[1]


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.config = load_scenario(ROOT/'configs/scenarios/demo.json')
        self.clock = ManualClock(self.config.start_time)
        self.plant = Simulator(self.config, self.clock)

    def test_power_balance_and_signs(self):
        self.assertEqual(self.plant.inspect_state().pcc_kw, 500)
        for pv, ess, ev, expected in [(300,0,0,200),(350,0,0,150),(350,100,0,50),
                                      (350,-100,0,250),(350,0,50,200),(800,0,0,-300)]:
            with self.subTest(pv=pv, ess=ess, ev=ev):
                self.plant.set_scenario(Scenario(500,pv,ess,ev))
                self.assertAlmostEqual(self.plant.inspect_state().pcc_kw, expected, delta=1e-6)

    def test_soc_discharge_charge_and_no_double_integration(self):
        self.plant.set_scenario(Scenario(500,350,100,0))
        self.clock.advance(3600)
        state = self.plant.inspect_state()
        self.assertAlmostEqual(state.energy_kwh, 500, delta=1e-6)
        self.assertAlmostEqual(state.soc, 50, delta=1e-6)
        self.assertEqual(state, self.plant.inspect_state())
        self.plant.set_scenario(replace(self.plant.scenario, ess_kw=-100))
        self.clock.advance(3600)
        self.assertAlmostEqual(self.plant.inspect_state().soc, 60, delta=1e-6)

    def test_step_partition_independence(self):
        scene = Scenario(500,300,100,0)
        self.plant.set_scenario(scene)
        clock2 = ManualClock(self.config.start_time)
        plant2 = Simulator(self.config, clock2)
        plant2.set_scenario(scene)
        for _ in range(60):
            self.clock.advance(60)
            self.plant.read('ess01')
        clock2.advance(3600)
        self.assertEqual(self.plant.inspect_state(), plant2.inspect_state())

    def test_scenario_change_integrates_old_power_first(self):
        self.plant.set_scenario(Scenario(500,300,100,0))
        self.clock.advance(1800)
        self.plant.set_scenario(Scenario(500,300,-200,0))
        self.assertEqual(self.plant.inspect_state().soc, 55)
        self.clock.advance(900)
        self.assertEqual(self.plant.inspect_state().soc, 60)

    def test_empty_saturation_instant_power_and_recharge(self):
        self.plant.set_scenario(Scenario(500,300,100,0))
        self.clock.advance(7*3600)
        state = self.plant.inspect_state()
        self.assertEqual((state.soc,state.energy_kwh,state.ess_kw,state.pcc_kw),(0,0,0,200))
        self.assertEqual(state.requested_ess_kw,100)
        self.plant.set_scenario(Scenario(500,300,-100,0))
        self.clock.advance(3600)
        self.assertEqual(self.plant.inspect_state().soc,10)

    def test_full_saturation_and_discharge(self):
        self.plant.set_scenario(Scenario(500,300,-100,0))
        self.clock.advance(5*3600)
        state = self.plant.inspect_state()
        self.assertEqual((state.soc,state.energy_kwh,state.ess_kw),(100,1000,0))
        self.plant.set_scenario(Scenario(500,300,100,0))
        self.clock.advance(3600)
        self.assertEqual(self.plant.inspect_state().soc,90)

    def test_disconnect_does_not_stop_physics_and_recovers(self):
        self.plant.set_scenario(Scenario(500,350,100,0))
        driver = SimulatedDriver(self.plant,'ess01')
        driver.connect()
        old = driver.read()[1]
        self.plant.set_connection('ess01',False)
        self.clock.advance(3600)
        with self.assertRaises(DeviceUnavailable):
            driver.read()
        self.assertEqual(self.plant.read('pcc01')[0].value,50)
        self.assertEqual(self.plant.inspect_state().soc,50)
        self.plant.set_connection('ess01',True)
        driver.connect()
        new = driver.read()[1]
        self.assertEqual((new.value,new.quality),(50,QualityCode.GOOD))
        self.assertGreater(new.timestamp,old.timestamp)
        self.assertEqual(old.value,60)
        driver.close()
        with self.assertRaises(DeviceUnavailable):
            driver.read()

    def test_timeout_bad_data_recovery_and_device_isolation(self):
        self.plant.set_fault('ess01',ReadFault.TIMEOUT)
        with self.assertRaises(SimulatedTimeout):
            self.plant.read('ess01')
        self.assertEqual(self.plant.read('pv01')[0].quality,QualityCode.GOOD)
        self.plant.set_fault('ess01',ReadFault.BAD_DATA)
        self.assertTrue(all(p.value is None and p.quality==QualityCode.BAD for p in self.plant.read('ess01')))
        self.plant.set_fault('ess01',ReadFault.NONE)
        self.assertEqual(self.plant.read('ess01')[1].value,60)

    def test_raw_measurements_metadata_and_immutable(self):
        points = [p for d in self.plant.DEVICE_IDS for p in self.plant.read(d)]
        self.assertEqual(len(points),6)
        self.assertEqual(len({(p.device_id,p.property) for p in points}),6)
        for point in points:
            self.assertEqual(point.timestamp,self.config.start_time)
            self.assertEqual(point.quality,QualityCode.GOOD)
            self.assertEqual(point.source,'SIMULATOR')
            self.assertEqual(point.config_version,self.config.config_version)
            self.assertEqual(point,RawMeasurement.from_json(point.to_json()))
        self.assertEqual(self.plant.read('ev01')[0].value,0)
        with self.assertRaises(FrozenInstanceError):
            points[0].value=0

    def test_seeded_variation_reproducible_independent_of_read_order(self):
        scene = Scenario(500,300,100,0,20)
        self.plant.set_scenario(scene)
        clock2=ManualClock(self.config.start_time)
        plant2=Simulator(self.config,clock2)
        plant2.set_scenario(scene)
        random_state=random.getstate()
        observed=[]
        for _ in range(5):
            self.clock.advance(1)
            clock2.advance(1)
            self.plant.read('ess01')
            self.plant.read('pv01')
            a=self.plant.inspect_state()
            b=plant2.inspect_state()
            self.assertEqual(a,b)
            self.assertTrue(280<=a.pv_kw<=320)
            self.assertAlmostEqual(a.pcc_kw,500-a.pv_kw-a.ess_kw,delta=1e-6)
            observed.append(a.pv_kw)
        self.assertGreater(len(set(observed)),1)
        self.assertEqual(random.getstate(),random_state)
        other=Simulator(replace(self.config,seed=43,initial_scenario=scene),ManualClock(self.config.start_time))
        self.assertNotEqual(other.inspect_state().pv_kw,Simulator(replace(self.config,initial_scenario=scene),ManualClock(self.config.start_time)).inspect_state().pv_kw)

    def test_invalid_scenarios_and_atomic_rejection(self):
        before=self.plant.inspect_state()
        for scene in (Scenario(500,300,501,0),Scenario(500,1001,0,0),Scenario(500,10,0,0,20)):
            with self.assertRaises(ValidationError):
                self.plant.set_scenario(scene)
            self.assertEqual(before,self.plant.inspect_state())
        for changes in ({'load_kw':-1},{'pv_kw':True},{'ess_kw':float('nan')},{'ev_kw':float('inf')}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):
                replace(self.plant.scenario,**changes)
        for changes in ({'capacity_kwh':0},{'initial_soc':101},{'seed':True},{'seed':-1},{'schema_version':2}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):
                replace(self.config,**changes)

    def test_config_file_errors_and_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'scenario.json'
            path.write_text(self.config.to_json(),encoding='utf-8-sig')
            self.assertEqual(load_scenario(path),self.config)
            for text in ('{}','{"seed":1,"seed":2}',self.config.to_json().replace('"schemaVersion": 1','"schemaVersion": 2'),' '*65_537):
                path.write_text(text,encoding='utf-8')
                with self.assertRaises(ValidationError):
                    load_scenario(path)

    def test_clock_validation_and_backwards_detection(self):
        before=self.clock.read()
        for seconds in (-1,True,float('inf'),float('nan'),1e-7):
            with self.subTest(seconds=seconds),self.assertRaises(ValidationError):
                self.clock.advance(seconds)
            self.assertEqual(self.clock.read(),before)
        self.clock.advance(0.000001)
        self.assertEqual(self.clock.read().timestamp,before.timestamp+timedelta(microseconds=1))
        class MutableClock:
            def read(inner):
                return inner.value
        clock=MutableClock()
        clock.value=ClockReading(self.config.start_time,10)
        plant=Simulator(self.config,clock)
        clock.value=ClockReading(self.config.start_time,9)
        with self.assertRaisesRegex(ValidationError,'backwards'):
            plant.inspect_state()

    def test_wall_clock_jump_does_not_change_energy_integration(self):
        class MutableClock:
            def read(inner):
                return inner.value
        clock=MutableClock()
        clock.value=ClockReading(self.config.start_time,0)
        plant=Simulator(replace(self.config,initial_scenario=Scenario(500,300,100,0)),clock)
        clock.value=ClockReading(self.config.start_time-timedelta(hours=5),3600)
        self.assertEqual(plant.inspect_state().soc,50)

    def test_bad_adapter_and_raw_inputs(self):
        with self.assertRaises(ValidationError):
            self.plant.read('unknown')
        with self.assertRaises(ValidationError):
            self.plant.set_connection('ess01',1)
        with self.assertRaises(ValidationError):
            self.plant.set_fault('ess01','NONE')
        self.plant.set_connection('ess01',False)
        with self.assertRaises(DeviceUnavailable):
            SimulatedDriver(self.plant,'ess01').connect()
        point=self.plant.read('pv01')[0]
        for changes in ({'value':None},{'unit':'MW'},{'source':'DRIVER'},{'property':'unknown'}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):
                replace(point,**changes)

    def test_cli_demo_and_invalid_scenario(self):
        def run(*args):
            return subprocess.run([sys.executable,str(ROOT/'ems.py'),*args],cwd=ROOT,capture_output=True,
                                  encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'},timeout=10)
        result=run('demo-simulator')
        self.assertEqual(result.returncode,0,result.stderr)
        demo=json.loads(result.stdout)
        self.assertEqual(demo['result'],'PASS')
        self.assertEqual([x['pccKw'] for x in demo['steps'][:4]],[500,200,150,50])
        self.assertTrue(demo['disconnectReadRejected'])
        result=run('simulate','--seconds','3600')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['final']['soc'],60)
        result=run('simulate','--seconds','-1')
        self.assertEqual(result.returncode,1)
        self.assertIn('seconds',json.loads(result.stderr)['error'])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.json'
            path.write_text('{}',encoding='utf-8')
            result=run('simulate','--scenario',str(path))
            self.assertEqual(result.returncode,1)
            self.assertIn('schemaVersion',json.loads(result.stderr)['error'])


if __name__=='__main__':
    unittest.main()
