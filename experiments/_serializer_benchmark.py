"""Measure equivalent serializer round trips on a fixed record."""

import argparse
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
import datetime
import gc
from importlib.metadata import version
import platform
from statistics import median
from time import process_time_ns
import tracemalloc
from typing import Any


@dataclass(frozen=True)
class Serializer:
    name: str
    dumps: Callable[[dict[str, Any]], bytes]
    loads: Callable[[bytes], Mapping[str, Any]]


def sample_record(*, temporal: bool) -> dict[str, Any]:
    """Return a fixed record with optional top-level date and time fields."""
    record = {
        "id": 42,
        "name": "Ada",
        "active": True,
        "scores": [1, 2, 3, 4, 5],
        "profile": {"city": "London", "role": "engineer"},
    }
    if temporal:
        record.update(
            created_at=datetime.datetime(2024, 1, 2, 3, 4, 5),
            updated_at=datetime.datetime(2024, 2, 3, 4, 5, 6),
            birthday=datetime.date(1990, 3, 4),
            duration=datetime.timedelta(seconds=100),
        )
    return record


def _positive(value: str) -> int:
    """Parse a positive measurement count."""
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return number


def _cpu_us(operation: Callable[[], Any], iterations: int, repeats: int) -> float:
    """Return the median process CPU time per operation in microseconds."""
    operation()
    samples: list[float] = []
    for _ in range(repeats):
        start = process_time_ns()
        for _ in range(iterations):
            operation()
        samples.append((process_time_ns() - start) / iterations / 1_000)
    return median(samples)


def _retained_bytes(operation: Callable[[], Mapping[str, Any]], repeats: int) -> float:
    """Measure traced Python allocations while the decoded record is still alive."""
    samples: list[int] = []
    for _ in range(repeats):
        gc.collect()
        tracemalloc.start()
        try:
            before = tracemalloc.get_traced_memory()[0]
            decoded = operation()
            samples.append(tracemalloc.get_traced_memory()[0] - before)
            del decoded
        finally:
            tracemalloc.stop()
    return median(samples)


def _read(
    serializer: Serializer, encoded: bytes, keys: tuple[str, ...]
) -> Mapping[str, Any]:
    """Decode one record and touch the specified fields."""
    decoded = serializer.loads(encoded)
    for key in keys:
        decoded[key]
    return decoded


def _measure(
    serializer: Serializer,
    record: dict[str, Any],
    first_key: str,
    iterations: int,
    repeats: int,
) -> str:
    """Validate a round trip before reporting CPU, size, and retained memory."""
    encoded = serializer.dumps(record)
    if dict(serializer.loads(encoded)) != record:
        raise ValueError(f"{serializer.name} changed the input record")

    def encode() -> bytes:
        return serializer.dumps(record)

    one_key = (first_key,)
    all_keys = tuple(record)

    def read_one() -> Mapping[str, Any]:
        return _read(serializer, encoded, one_key)

    def read_all() -> Mapping[str, Any]:
        return _read(serializer, encoded, all_keys)

    return (
        f"| {serializer.name} | {len(encoded)} | "
        f"{_cpu_us(encode, iterations, repeats):.2f} | "
        f"{_cpu_us(read_one, iterations, repeats):.2f} | "
        f"{_cpu_us(read_all, iterations, repeats):.2f} | "
        f"{_retained_bytes(read_one, repeats):.0f} | "
        f"{_retained_bytes(read_all, repeats):.0f} |"
    )


def run(
    title: str, serializers: tuple[Serializer, ...], *, datasets: tuple[bool, ...]
) -> None:
    """Run a command-line comparison on each requested dataset."""
    parser = argparse.ArgumentParser(description=title)
    parser.add_argument("--iterations", type=_positive, default=10_000)
    parser.add_argument("--repeats", type=_positive, default=5)
    args = parser.parse_args()

    print(f"# {title}\n")
    print(f"Python {platform.python_version()} · MessagePack {version('msgpack')}.")
    print(
        f"Median of {args.repeats} samples, "
        f"{args.iterations:,} operations per CPU sample."
    )
    for temporal in datasets:
        name = "Record with dates and times" if temporal else "Record with plain values"
        first_key = "created_at" if temporal else "id"
        print(f"\n## {name}\n")
        print(f"One-field reads access `{first_key}`. Full reads access every field.\n")
        print("| Serializer | Encoded B | Encode µs | Read one µs | Read all µs | "
              "Retained after one B | Retained after all B |")
        print("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        record = sample_record(temporal=temporal)
        for serializer in serializers:
            row = _measure(serializer, record, first_key, args.iterations, args.repeats)
            print(row)

    print("\nRetained bytes are traced Python allocations for the live decoded record.")
    print("Encoded buffers are measured separately. CPU timings run without tracing.")
