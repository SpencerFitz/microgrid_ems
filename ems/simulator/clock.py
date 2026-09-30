"""Injectable clocks: physical integration uses monotonic time, labels use UTC."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import time
from typing import Protocol

from ..domain.base import Record, convert, require


@dataclass(frozen=True)
class ClockReading(Record):
    timestamp: datetime
    monotonic_seconds: float

    def validate(self):
        require(self.monotonic_seconds >= 0, 'monotonicSeconds', 'must be nonnegative')


class Clock(Protocol):
    def read(self) -> ClockReading: ...


class ManualClock:
    def __init__(self, start: datetime):
        self._start = convert(start, datetime, 'startTime')
        self._microseconds = 0

    def read(self) -> ClockReading:
        return ClockReading(self._start + timedelta(microseconds=self._microseconds), self._microseconds / 1_000_000)

    def advance(self, seconds: float) -> None:
        seconds = convert(seconds, float, 'seconds')
        require(0 <= seconds <= 31_536_000, 'seconds', 'advance must be within [0, 31536000]')
        microseconds = round(seconds * 1_000_000)
        require(abs(microseconds / 1_000_000 - seconds) <= 1e-9, 'seconds', 'microsecond resolution required')
        # Check datetime range before changing state.
        self._start + timedelta(microseconds=self._microseconds + microseconds)
        self._microseconds += microseconds


class SystemClock:
    def read(self) -> ClockReading:
        return ClockReading(datetime.now(timezone.utc), time.monotonic())
