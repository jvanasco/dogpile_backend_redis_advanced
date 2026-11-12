"""Compare eager and lazy decoding of the same MessagePack tagged maps."""

from collections.abc import Iterator
from collections.abc import Mapping
import datetime
from typing import Any
from typing import TYPE_CHECKING

import msgpack


def _encode_temporal(value: Any) -> dict[str, Any]:
    """Represent supported temporal values with a single reserved tag."""
    if isinstance(value, datetime.datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, datetime.date):
        return {"__date__": value.isoformat()}
    if isinstance(value, datetime.timedelta):
        return {"__timedelta__": [value.days, value.seconds, value.microseconds]}
    raise TypeError(f"Unsupported type {type(value).__name__}")


def _decode_temporal(value: dict[str, Any]) -> Any:
    """Decode a tagged map and pass ordinary maps through unchanged."""
    if len(value) == 1:
        if "__datetime__" in value:
            return datetime.datetime.fromisoformat(value["__datetime__"])
        if "__date__" in value:
            return datetime.date.fromisoformat(value["__date__"])
        if "__timedelta__" in value:
            days, seconds, microseconds = value["__timedelta__"]
            return datetime.timedelta(
                days=days, seconds=seconds, microseconds=microseconds
            )
    return value


class LazyDeserializer(Mapping[str, Any]):
    """Decode and memoize top-level tagged values on first access."""

    def __init__(self, fields: dict[str, Any]) -> None:
        self._fields = fields

    def __getitem__(self, key: str) -> Any:
        value = self._fields[key]
        if isinstance(value, dict):
            value = _decode_temporal(value)
            self._fields[key] = value
        return value

    def __iter__(self) -> Iterator[str]:
        return iter(self._fields)

    def __len__(self) -> int:
        return len(self._fields)


def dumps(record: dict[str, Any]) -> bytes:
    """Use the same tagged-map encoding for both decoders."""
    return msgpack.packb(record, default=_encode_temporal, use_bin_type=True)


def loads_eager(payload: bytes) -> Mapping[str, Any]:
    """Decode tagged values while unpacking the record."""
    return msgpack.unpackb(payload, raw=False, object_hook=_decode_temporal)


def loads_lazy(payload: bytes) -> Mapping[str, Any]:
    """Unpack the record and defer conversions of top-level tagged values."""
    return LazyDeserializer(msgpack.unpackb(payload, raw=False))


if __name__ == "__main__":
    if TYPE_CHECKING or __package__:
        from ._serializer_benchmark import run
        from ._serializer_benchmark import Serializer
        from .struct_tests import MsgpackSerializer_Types
        from .struct_tests import PickleSerializer
    else:
        from _serializer_benchmark import run
        from _serializer_benchmark import Serializer
        from struct_tests import MsgpackSerializer_Types
        from struct_tests import PickleSerializer

    run(
        "Lazy and eager serializers",
        (
            Serializer("MessagePack tagged maps (eager)", dumps, loads_eager),
            Serializer("MessagePack tagged maps (lazy)", dumps, loads_lazy),
            Serializer(
                "MessagePack struct",
                MsgpackSerializer_Types.dumps,
                MsgpackSerializer_Types.loads,
            ),
            Serializer("Pickle", PickleSerializer.dumps, PickleSerializer.loads),
        ),
        datasets=(True,),
    )
