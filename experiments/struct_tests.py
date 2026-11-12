"""Compare struct-based MessagePack codecs with pickle."""

import datetime
import enum
import pickle
import struct
from typing import Any
from typing import TYPE_CHECKING
from typing import Callable
from typing import Union

# pypi
import msgpack

# ==============================================================================

msgpack_packb = msgpack.packb
msgpack_unpackb = msgpack.unpackb
pickle_loads = pickle.loads


"""
TIPS-

If you have a lot of objects per request, this makes a difference:
    msgpack_packb = msgpack.packb
    msgpack_unpackb = msgpack.unpackb
"""


_EPOCH = datetime.datetime(1970, 1, 1)


class MsgpackTypes(enum.IntEnum):
    datetime = 1
    date = 2
    timedelta = 3


def msgpack_alt_default(
    obj: Union[datetime.datetime, datetime.date, datetime.timedelta]
) -> msgpack.ExtType:
    if isinstance(obj, datetime.datetime):
        return msgpack.ExtType(
            MsgpackTypes.datetime.value,
            struct.pack(
                ">I",
                int((obj - _EPOCH).total_seconds()),
            ),
        )
    elif isinstance(obj, datetime.date):
        return msgpack.ExtType(
            MsgpackTypes.date.value,
            struct.pack(">III", obj.year, obj.month, obj.day),
        )
    elif isinstance(obj, datetime.timedelta):
        return msgpack.ExtType(
            MsgpackTypes.timedelta.value,
            struct.pack(">I", int(obj.total_seconds())),
        )
    raise TypeError("Unknown type: %r" % (obj,))


def msgpack_alt_ext_hook(code: int, data: Any) -> Union[
    datetime.date,
    datetime.datetime,
    datetime.timedelta,
    msgpack.ExtType,
]:
    type_ = MsgpackTypes(code)
    if type_ == MsgpackTypes.datetime:
        v = struct.unpack(">I", data)
        return _EPOCH + datetime.timedelta(seconds=v[0])
    elif type_ == MsgpackTypes.date:
        v = struct.unpack(">III", data)
        return datetime.date(v[0], v[1], v[2])
    elif type_ == MsgpackTypes.timedelta:
        v = struct.unpack(">I", data)
        return datetime.timedelta(seconds=v[0])
    return msgpack.ExtType(code, data)


def _msgpack_alt_default_factory() -> Callable:
    """stick some elements in here for cpython"""
    extType = msgpack.ExtType
    mtypes = MsgpackTypes
    pck = struct.pack
    epoch = _EPOCH
    o_datetime = datetime.datetime
    o_date = datetime.date
    o_timedelta = datetime.timedelta

    def _msgpack_alt_default(
        obj: Union[
            datetime.date,
            datetime.datetime,
            datetime.timedelta,
        ]
    ) -> msgpack.ExtType:
        if isinstance(obj, o_datetime):
            return extType(
                mtypes.datetime.value,
                pck(
                    ">I",
                    int((obj - epoch).total_seconds()),
                ),
            )
        elif isinstance(obj, o_date):
            return extType(
                mtypes.date.value,
                pck(">III", obj.year, obj.month, obj.day),
            )
        elif isinstance(obj, o_timedelta):
            return extType(
                mtypes.timedelta.value,
                pck(">I", int(obj.total_seconds())),
            )
        raise TypeError("Unknown type: %r" % (obj,))

    return _msgpack_alt_default


msgpack_alt_default_factory = _msgpack_alt_default_factory()


def _msgpack_alt_ext_hook_factory() -> Callable:
    """stick some elements in here for cpython"""
    o_date = datetime.date
    o_timedelta = datetime.timedelta
    extType = msgpack.ExtType
    mtypes = MsgpackTypes
    unpck = struct.unpack
    epoch = _EPOCH

    def _msgpack_alt_ext_hook(code: int, data: Any) -> Union[
        datetime.date,
        datetime.datetime,
        datetime.timedelta,
        msgpack.ExtType,
    ]:
        type_ = mtypes(code)
        if type_ == mtypes.datetime:
            v = unpck(">I", data)
            return epoch + o_timedelta(seconds=v[0])
        elif type_ == mtypes.date:
            v = unpck(">III", data)
            return o_date(v[0], v[1], v[2])
        elif type_ == mtypes.timedelta:
            v = unpck(">I", data)
            return o_timedelta(seconds=v[0])
        return extType(code, data)

    return _msgpack_alt_ext_hook


msgpack_alt_ext_hook_factory = _msgpack_alt_ext_hook_factory()


# ==============================================================================


class MsgpackSerializer_Types(object):
    @classmethod
    def loads(cls, payload: bytes) -> Any:
        v = msgpack_unpackb(
            payload,
            ext_hook=msgpack_alt_ext_hook,
            use_list=True,
        )
        return v

    @classmethod
    def dumps(cls, payload: Any) -> bytes:
        v = msgpack_packb(
            payload,
            default=msgpack_alt_default,
            use_bin_type=True,
        )
        return v


class MsgpackSerializer_Types_Factory(object):
    @classmethod
    def loads(cls, payload: bytes) -> Any:
        v = msgpack_unpackb(
            payload,
            ext_hook=msgpack_alt_ext_hook_factory,
            use_list=True,
        )
        return v

    @classmethod
    def dumps(cls, payload: Any) -> bytes:
        v = msgpack_packb(
            payload, default=msgpack_alt_default_factory, use_bin_type=True
        )
        return v


class PickleSerializer(object):
    @classmethod
    def loads(cls, payload: bytes) -> Any:
        v = pickle_loads(payload)
        return v

    @classmethod
    def dumps(cls, payload: Any) -> bytes:
        v = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
        return v


if __name__ == "__main__":
    if TYPE_CHECKING or __package__:
        from ._serializer_benchmark import run
        from ._serializer_benchmark import Serializer
    else:
        from _serializer_benchmark import run
        from _serializer_benchmark import Serializer

    run(
        "Struct-based serializers",
        (
            Serializer(
                "MessagePack struct",
                MsgpackSerializer_Types.dumps,
                MsgpackSerializer_Types.loads,
            ),
            Serializer(
                "MessagePack struct (local bindings)",
                MsgpackSerializer_Types_Factory.dumps,
                MsgpackSerializer_Types_Factory.loads,
            ),
            Serializer("Pickle", PickleSerializer.dumps, PickleSerializer.loads),
        ),
        datasets=(False, True),
    )
