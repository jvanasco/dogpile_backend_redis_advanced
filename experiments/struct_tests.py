from __future__ import print_function

# stdlib
import datetime
import pprint
import timeit
import pdb
import enum
import struct

# pypi
import msgpack
from dogpile.util.compat import pickle

# ==============================================================================

msgpack_packb = msgpack.packb
msgpack_unpackb = msgpack.unpackb
pickle_loads = pickle.loads
pickle_dumps = pickle.dumps

"""
TIPS-

If you have a lot of objects per request, this makes a difference:
    msgpack_packb = msgpack.packb
    msgpack_unpackb = msgpack.unpackb
"""


class MsgpackTypes(enum.IntEnum):
    datetime = 1
    date = 2
    timedelta = 3


def msgpack_alt_default(obj):
    if isinstance(obj, datetime.datetime):
        return msgpack.ExtType(
            MsgpackTypes.datetime.value,
            struct.pack(">I", (obj - datetime.datetime(1970, 1, 1)).total_seconds()),
        )
    elif isinstance(obj, datetime.date):
        return msgpack.ExtType(
            MsgpackTypes.date.value, struct.pack(">III", obj.year, obj.month, obj.day)
        )
    elif isinstance(obj, datetime.timedelta):
        return msgpack.ExtType(
            MsgpackTypes.timedelta.value, struct.pack(">I", obj.total_seconds())
        )
    raise TypeError("Unknown type: %r" % (obj,))


def msgpack_alt_ext_hook(code, data):
    type_ = MsgpackTypes(code)
    if type_ == MsgpackTypes.datetime:
        v = struct.unpack(">I", data)
        return datetime.datetime.fromtimestamp(v[0])
    elif type_ == MsgpackTypes.date:
        v = struct.unpack(">III", data)
        return datetime.date(v[0], v[1], v[2])
    elif type_ == MsgpackTypes.timedelta:
        v = struct.unpack(">I", data)
        return datetime.timedelta(seconds=v[0])
    return msgpack.ExtType(code, data)


def _msgpack_alt_default_factory():
    """stick some elements in here for cpython"""
    extType = msgpack.ExtType
    mtypes = MsgpackTypes
    pck = struct.pack
    o_datetime = datetime.datetime
    o_date = datetime.date
    o_timedelta = datetime.timedelta

    def _msgpack_alt_default(obj):
        if isinstance(obj, o_datetime):
            return extType(
                mtypes.datetime.value,
                pck(">I", (obj - o_datetime(1970, 1, 1)).total_seconds()),
            )
        elif isinstance(obj, o_date):
            return extType(mtypes.date.value, pck(">III", obj.year, obj.month, obj.day))
        elif isinstance(obj, o_timedelta):
            return extType(mtypes.timedelta.value, pck(">I", obj.total_seconds()))
        raise TypeError("Unknown type: %r" % (obj,))

    return _msgpack_alt_default


msgpack_alt_default_factory = _msgpack_alt_default_factory()


def _msgpack_alt_ext_hook_factory():
    """stick some elements in here for cpython"""
    o_datetime = datetime.datetime
    o_date = datetime.date
    o_timedelta = datetime.timedelta
    extType = msgpack.ExtType
    mtypes = MsgpackTypes
    unpck = struct.unpack

    def _msgpack_alt_ext_hook(code, data):
        type_ = mtypes(code)
        if type_ == mtypes.datetime:
            v = unpck(">I", data)
            return o_datetime.fromtimestamp(v[0])
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
    def loads(cls, payload):
        v = msgpack_unpackb(
            payload, ext_hook=msgpack_alt_ext_hook, encoding="utf-8", use_list=True
        )
        return v

    @classmethod
    def dumps(cls, payload):
        v = msgpack_packb(payload, default=msgpack_alt_default, use_bin_type=True)
        return v


class MsgpackSerializer_Types_Factory(object):
    @classmethod
    def loads(cls, payload):
        v = msgpack_unpackb(
            payload,
            ext_hook=msgpack_alt_ext_hook_factory,
            encoding="utf-8",
            use_list=True,
        )
        return v

    @classmethod
    def dumps(cls, payload):
        v = msgpack_packb(
            payload, default=msgpack_alt_default_factory, use_bin_type=True
        )
        return v


class PickleSerializer(object):
    @classmethod
    def loads(cls, payload):
        v = pickle_loads(payload)
        return v

    @classmethod
    def dumps(cls, payload):
        v = pickle_dumps(payload)
        return v


if __name__ == "__main__":

    results = {}
    for test in ("datetime", "no_datetime"):
        results[test] = {}

        sample_data = {
            "string": "foo",
            "int": 100,
            "bool": True,
            "list": [1, 2, 3, 4, 5],
            "tuple": [1, 2, 3, 4, 5],
            "dict": {"a": 1, 1: "a"},
        }
        if test == "datetime":
            sample_data["datetime"] = datetime.datetime.now()
            sample_data["date"] = datetime.date.today()
            sample_data["timedelta"] = datetime.timedelta(seconds=100)

        encoded_msgpack = MsgpackSerializer_Types.dumps(sample_data)
        encoded_msgpack_factory = MsgpackSerializer_Types_Factory.dumps(sample_data)
        encoded_pickle = PickleSerializer.dumps(sample_data)

        loaded_msgpack = MsgpackSerializer_Types.loads(encoded_msgpack)
        loaded_msgpack_factory = MsgpackSerializer_Types_Factory.loads(
            encoded_msgpack_factory
        )
        loaded_pickle = PickleSerializer.loads(encoded_pickle)

        print(loaded_msgpack)
        print(loaded_msgpack_factory)
        print(loaded_pickle)

        iterations = 10000

        harness = (
            ("MsgpackSerializer_Types", "encoded_msgpack", "loaded_msgpack"),
            (
                "MsgpackSerializer_Types_Factory",
                "encoded_msgpack_factory",
                "loaded_msgpack_factory",
            ),
            ("PickleSerializer", "encoded_pickle", "loaded_pickle"),
        )

        for suite in harness:
            t_loads = timeit.timeit(
                "%s.dumps(sample_data)" % suite[0],
                "from __main__ import %s, sample_data" % suite[0],
                number=iterations,
            )
            t_dumps = timeit.timeit(
                "%s.loads(%s)" % (suite[0], suite[1]),
                "from __main__ import %s, %s" % (suite[0], suite[1]),
                number=iterations,
            )
            results[test][suite[0]] = {
                "iterations": iterations,
                "loads": t_loads,
                "dumps": t_dumps,
            }

    pprint.pprint(results)
