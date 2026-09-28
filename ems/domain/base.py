"""Strict wire conversion shared by immutable domain records (stdlib only)."""
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import math
import re
from types import MappingProxyType, UnionType
from typing import get_args, get_origin, get_type_hints


class ValidationError(ValueError):
    pass


def require(condition, path, message):
    if not condition:
        raise ValidationError(f"{path}: {message}")


def camel(name):
    first, *rest = name.split('_')
    return first + ''.join(part.title() for part in rest)


def convert(value, kind, path, wire=False):
    origin, args = get_origin(kind), get_args(kind)
    if origin is UnionType:
        for option in args:
            try:
                return convert(value, option, path, wire)
            except ValidationError:
                pass
        raise ValidationError(f"{path}: invalid value/type for {kind}")
    if kind is type(None):
        require(value is None, path, 'must be null')
    elif kind is datetime:
        if wire:
            require(isinstance(value, str) and re.fullmatch(
                r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', value), path, 'expected UTC RFC3339 ending Z')
            try:
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError as exc:
                raise ValidationError(f'{path}: invalid calendar time') from exc
        require(isinstance(value, datetime) and value.utcoffset() is not None
                and value.utcoffset().total_seconds() == 0, path, 'expected aware UTC datetime')
        value = value.astimezone(timezone.utc)
    elif isinstance(kind, type) and issubclass(kind, Enum):
        if wire:
            try:
                value = kind(value)
            except (ValueError, TypeError) as exc:
                raise ValidationError(f'{path}: unknown {kind.__name__}') from exc
        require(isinstance(value, kind), path, f'expected {kind.__name__}')
    elif is_dataclass(kind):
        if wire:
            value = kind.from_dict(value, path)
        require(isinstance(value, kind), path, f'expected {kind.__name__}')
    elif origin is Mapping:
        require(isinstance(value, Mapping), path, 'expected mapping')
        value = MappingProxyType({convert(k, args[0], path, wire):
                                  convert(v, args[1], f'{path}.{k}', wire) for k, v in value.items()})
    elif origin is tuple:
        require(isinstance(value, (list, tuple)) if wire else isinstance(value, tuple), path, 'expected array/tuple')
        value = tuple(convert(v, args[0], f'{path}[{i}]', wire) for i, v in enumerate(value))
    elif kind is float:
        require(type(value) in (int, float), path, 'expected finite number, not bool')
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        require(finite, path, 'expected finite number')
    else:
        require(type(value) is kind, path, f'expected {kind.__name__}')
        if kind is str:
            require(bool(value.strip()), path, 'must not be empty')
    return value


def encode(value):
    if isinstance(value, datetime):
        return value.isoformat().replace('+00:00', 'Z')
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {camel(f.name): encode(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [encode(v) for v in value]
    return value


class Record:
    def __post_init__(self):
        hints = get_type_hints(type(self))
        for field in fields(self):
            object.__setattr__(self, field.name, convert(getattr(self, field.name), hints[field.name], camel(field.name)))
        self.validate()

    def validate(self):
        pass

    @classmethod
    def from_dict(cls, data, path='$'):
        require(type(data) is dict, path, 'expected object')
        from dataclasses import MISSING
        allowed = {camel(f.name): f for f in fields(cls)}
        require(not data.keys() - allowed.keys(), path, f'unknown fields: {sorted(data.keys() - allowed.keys())}')
        for key, field in allowed.items():
            require(key in data or field.default is not MISSING, f'{path}.{key}', 'required field')
        hints = get_type_hints(cls)
        values = {allowed[k].name: convert(v, hints[allowed[k].name], f'{path}.{k}', True) for k, v in data.items()}
        try:
            return cls(**values)
        except ValidationError as exc:
            raise ValidationError(f'{path}.{exc}') from exc

    def to_dict(self):
        return encode(self)

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False, indent=2)

    @classmethod
    def from_json(cls, text):
        def pairs(items):
            result = {}
            for key, value in items:
                require(key not in result, key, 'duplicate JSON key')
                result[key] = value
            return result
        def invalid(value):
            raise ValidationError(f'$: nonfinite JSON number {value}')
        try:
            return cls.from_dict(json.loads(text, object_pairs_hook=pairs, parse_constant=invalid))
        except (json.JSONDecodeError, RecursionError) as exc:
            raise ValidationError('$: invalid JSON') from exc
