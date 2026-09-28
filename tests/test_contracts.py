import copy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import subprocess
import sys
import unittest

from ems.domain import (
    Site, Device, TagDefinition, TelemetryEnvelope, TelemetrySample,
    SystemSnapshot, SnapshotValue, QualityCode, ValidationError,
)

ROOT = Path(__file__).resolve().parents[1]


def fixture(name):
    return json.loads((ROOT / 'contracts/examples' / f'{name}.json').read_text(encoding='utf-8'))


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tag = TagDefinition.from_dict(fixture('soc_tag'))
        self.sample = TelemetryEnvelope.from_dict(fixture('telemetry_good')).payload

    def test_all_examples_roundtrip(self):
        for cls, name in [(Site, 'site'), (Device, 'device'), (TagDefinition, 'soc_tag'),
                          (TelemetryEnvelope, 'telemetry_good'), (TelemetryEnvelope, 'telemetry_offline'),
                          (SystemSnapshot, 'snapshot')]:
            with self.subTest(name=name):
                obj = cls.from_dict(fixture(name))
                self.assertEqual(cls.from_json(obj.to_json()), obj)

    def test_reject_missing_unknown_duplicate_keys(self):
        for key, value in [('unexpected', 1), ('schemaVersion', 2), ('schemaVersion', True)]:
            event = fixture('telemetry_good')
            event[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValidationError):
                TelemetryEnvelope.from_dict(event)
        event = fixture('telemetry_good')
        del event['payload']['timestamp']
        with self.assertRaisesRegex(ValidationError, 'payload.timestamp'):
            TelemetryEnvelope.from_dict(event)
        with self.assertRaisesRegex(ValidationError, 'duplicate'):
            Site.from_json('{"id":"site01","id":"site02"}')

    def test_good_null_and_nonfinite(self):
        for value in (None, float('nan'), float('inf'), -float('inf'), 10**400):
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValidationError):
                replace(self.sample, value=value)
        for literal in ('NaN', 'Infinity', '-Infinity', '1e400'):
            text = self.sample.to_json().replace('"value": 60', '"value": ' + literal)
            with self.subTest(literal=literal), self.assertRaises(ValidationError):
                TelemetrySample.from_json(text)

    def test_soc_limits_and_types(self):
        for value in (-1, 101, True, '60'):
            with self.subTest(value=value), self.assertRaisesRegex(ValidationError, 'value'):
                replace(self.sample, value=value)
        for value in (0, 100, 60.5):
            replace(self.sample, value=value).validate_against(self.tag)
        with self.assertRaisesRegex(ValidationError, 'unit'):
            replace(self.sample, unit='kW')
        with self.assertRaisesRegex(ValidationError, 'minValue/maxValue'):
            replace(self.tag, max_value=101)

    def test_point_identity_and_definition(self):
        for updates in ({'site_id':'other'}, {'device_id':'ESS01'}, {'tag_id':'site01.ess01.a.b'},
                        {'sequence':True}, {'sequence':-1}, {'unit':'MW'}):
            with self.subTest(updates=updates), self.assertRaises(ValidationError):
                replace(self.sample, **updates)
        with self.assertRaisesRegex(ValidationError, 'configVersion'):
            replace(self.sample, config_version='other').validate_against(self.tag)
        event = fixture('telemetry_good')
        event['siteId'] = 'other'
        with self.assertRaisesRegex(ValidationError, 'siteId'):
            TelemetryEnvelope.from_dict(event)

    def test_definition_timing_bounds(self):
        for updates in ({'sampling_interval_ms':0}, {'stale_after_ms':1000},
                        {'offline_after_ms':3000}, {'min_value':80,'max_value':70}, {'deadband':-1}):
            with self.subTest(updates=updates), self.assertRaises(ValidationError):
                replace(self.tag, **updates)

    def test_int_bool_string_and_numeric_bounds(self):
        for dtype, valid, invalid in [('INT64', 1, True), ('BOOL', True, 1), ('STRING','closed',False)]:
            data = fixture('soc_tag')
            data.update(id='site01.ess01.state', dataType=dtype, unit='1', minValue=None, maxValue=None)
            tag = TagDefinition.from_dict(data)
            sample = replace(self.sample, tag_id=tag.id, unit='1', value=valid)
            sample.validate_against(tag)
            with self.subTest(dtype=dtype), self.assertRaises(ValidationError):
                replace(sample, value=invalid).validate_against(tag)
        tag = replace(self.tag, id='site01.ess01.power', unit='kW', min_value=-100, max_value=100)
        sample = replace(self.sample, tag_id=tag.id, unit='kW', value=-100)
        sample.validate_against(tag)
        for value in (-101, 101):
            with self.assertRaisesRegex(ValidationError, 'value'):
                replace(sample, value=value).validate_against(tag)
        with self.assertRaisesRegex(ValidationError, 'INT64'):
            replace(sample, value=2**63)

    def test_utc_only_and_real_dates(self):
        for value in ('2026-09-28T00:00:00', '2026-09-28T08:00:00+08:00', '2026-02-30T00:00:00Z'):
            data = self.sample.to_dict()
            data['timestamp'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValidationError, 'timestamp'):
                TelemetrySample.from_dict(data)
        for value in (datetime(2026, 9, 28), datetime(2026, 9, 28, tzinfo=timezone(timedelta(hours=8)))):
            with self.assertRaises(ValidationError):
                replace(self.sample, timestamp=value)

    def test_offline_preserves_measurement_time(self):
        offline = TelemetryEnvelope.from_dict(fixture('telemetry_offline')).payload
        offline.validate_against(self.tag)
        self.assertEqual(offline.timestamp, self.sample.timestamp)
        self.assertEqual(offline.value, self.sample.value)
        self.assertGreater(offline.quality_timestamp, self.sample.quality_timestamp)
        self.assertEqual(replace(offline, value=None).quality, QualityCode.OFFLINE)

    def test_deep_immutability_and_detached_serialization(self):
        data = fixture('snapshot')
        snapshot = SystemSnapshot.from_dict(data)
        data['tags']['site01.ess01.soc']['value'] = 0
        self.assertEqual(snapshot.tags['site01.ess01.soc'].value, 60)
        with self.assertRaises(TypeError):
            snapshot.tags['x'] = self.sample
        with self.assertRaises(TypeError):
            snapshot.ess['soc'] = 'other'
        with self.assertRaises(FrozenInstanceError):
            snapshot.tags['site01.ess01.soc'].value = 0
        source = dict(snapshot.tags)
        copied = replace(snapshot, tags=source)
        source.clear()
        self.assertEqual(len(copied.tags), 1)
        encoded = snapshot.to_dict()
        encoded['ess']['soc'] = 'other'
        self.assertEqual(snapshot.ess['soc'], 'site01.ess01.soc')
        self.assertIsInstance(snapshot.missing_tag_ids, tuple)

    def test_snapshot_references_and_no_control(self):
        snapshot = SystemSnapshot.from_dict(fixture('snapshot'))
        for changes in ({'control_eligible':True}, {'cutoff_time':snapshot.timestamp + timedelta(seconds=1)},
                        {'ess':{'soc':'site01.ess01.missing'}}, {'grid':{'activePowerKw':'site01.ess01.soc'}},
                        {'invalid_tag_ids':('site01.ess01.missing',)}, {'cycle':-1}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                replace(snapshot, **changes)

    def test_site_and_device_validation(self):
        site = Site.from_dict(fixture('site'))
        for changes in ({'rated_power_kw':-1}, {'grid_import_limit_kw':True}, {'timezone':'Mars'}, {'id':'has.dot'}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                replace(site, **changes)
        data = fixture('device')
        data['type'] = 'DIESEL'
        with self.assertRaisesRegex(ValidationError, 'type'):
            Device.from_dict(data)

    def test_demo_cli(self):
        result = subprocess.run([sys.executable, str(ROOT/'ems.py'), 'demo-contracts'], cwd=ROOT,
                                capture_output=True, encoding='utf-8', env={**__import__('os').environ, 'PYTHONIOENCODING':'utf-8'}, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['result'], 'PASS')
        self.assertTrue(data['sampleTimestampPreserved'])
        self.assertFalse(data['snapshotControlEligible'])


if __name__ == '__main__':
    unittest.main()
