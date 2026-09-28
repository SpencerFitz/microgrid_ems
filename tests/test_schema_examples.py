"""Offline checks for the schema vocabulary emitted in this repository only.

This deliberately is NOT a general JSON Schema validator or meta-schema test.
Unknown keywords fail so a schema extension cannot silently escape this check.
Business invariants are checked by test_contracts and the production parsers.
"""
import json
import math
from pathlib import Path
import re
import unittest
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / 'contracts/jsonschema'
KEYWORDS = {'$schema', '$defs', '$ref', '$comment', 'title', 'type', 'properties', 'required',
            'additionalProperties', 'items', 'anyOf', 'allOf', 'if', 'then', 'not', 'const',
            'enum', 'minimum', 'maximum', 'minLength', 'pattern', 'format'}


def accepts(value, rule, document):
    unknown = rule.keys() - KEYWORDS
    if unknown:
        raise AssertionError(f'Unsupported schema check keywords: {unknown}')
    if '$ref' in rule:
        file, pointer = rule['$ref'].split('#')
        target = json.loads((SCHEMAS/file).read_text(encoding='utf-8')) if file else document
        child = target
        for key in pointer.strip('/').split('/'):
            child = child[key]
        return accepts(value, child, target)
    if 'anyOf' in rule and not any(accepts(value, r, document) for r in rule['anyOf']):
        return False
    if 'allOf' in rule and not all(accepts(value, r, document) for r in rule['allOf']):
        return False
    if 'not' in rule and accepts(value, rule['not'], document):
        return False
    if 'if' in rule and accepts(value, rule['if'], document) and not accepts(value, rule['then'], document):
        return False
    if 'const' in rule and (type(value) is not type(rule['const']) or value != rule['const']):
        return False
    if 'enum' in rule and value not in rule['enum']:
        return False
    kind = rule.get('type')
    checks = {'object':type(value) is dict, 'array':type(value) is list,
              'string':type(value) is str, 'integer':type(value) in (int,float) and math.isfinite(value) and int(value) == value,
              'number':type(value) in (int,float) and math.isfinite(value),
              'boolean':type(value) is bool, 'null':value is None}
    if kind and not checks[kind]:
        return False
    if isinstance(value, dict):
        props = rule.get('properties', {})
        if not set(rule.get('required', [])) <= value.keys():
            return False
        for key, item in value.items():
            child = props.get(key, rule.get('additionalProperties', {}))
            if child is False or not accepts(item, child, document):
                return False
    if isinstance(value, list) and 'items' in rule:
        if not all(accepts(v, rule['items'], document) for v in value):
            return False
    if type(value) in (int, float) and 'minimum' in rule and value < rule['minimum']:
        return False
    if type(value) in (int, float) and 'maximum' in rule and value > rule['maximum']:
        return False
    if isinstance(value, str):
        if len(value) < rule.get('minLength', 0) or ('pattern' in rule and not re.search(rule['pattern'], value)):
            return False
        if rule.get('format') == 'date-time':
            try:
                datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                return False
    return True


class SchemaExampleTests(unittest.TestCase):
    def check(self, name, model, expected=True, change=None):
        obj = json.loads((ROOT/'contracts/examples'/f'{name}.json').read_text(encoding='utf-8'))
        if change:
            change(obj)
        schema = json.loads((SCHEMAS/f'{model}.schema.json').read_text(encoding='utf-8'))
        self.assertEqual(accepts(obj, schema, schema), expected)

    def test_examples_match_structural_schemas(self):
        for name, model in [('site','Site'), ('device','Device'), ('soc_tag','TagDefinition'),
                            ('telemetry_good','TelemetryEnvelope'), ('telemetry_offline','TelemetryEnvelope'), ('snapshot','SystemSnapshot')]:
            with self.subTest(name=name):
                self.check(name, model)

    def test_invalid_envelopes_rejected_by_schema(self):
        changes = [lambda d:d.update(schemaVersion=2), lambda d:d.update(extra=1),
                   lambda d:d['payload'].update(value=None), lambda d:d['payload'].update(quality='UNKNOWN'),
                   lambda d:d['payload'].update(unit='MW'), lambda d:d['payload'].pop('timestamp'),
                   lambda d:d['payload'].update(sequence=True), lambda d:d['payload'].update(value=101)]
        for i, change in enumerate(changes):
            with self.subTest(case=i):
                self.check('telemetry_good','TelemetryEnvelope',False,change)

    def test_control_and_resource_shape_rejected(self):
        self.check('snapshot','SystemSnapshot',False,lambda d:d.update(controlEligible=True))
        self.check('snapshot','SystemSnapshot',False,lambda d:d['ess'].update(soc=60))
