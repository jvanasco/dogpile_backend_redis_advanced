# stdlib
import datetime
import enum
import pickle
import struct
from typing import Any
from typing import Callable
from typing import Dict
from typing import Generator
from typing import List
from typing import Tuple
from typing import Union

# pypi
import msgpack


# ==============================================================================

msgpack_packb = msgpack.packb
msgpack_unpackb = msgpack.unpackb

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


def msgpack_alt_default(
    obj: Union[datetime.datetime, datetime.date, datetime.timedelta]
) -> msgpack.ExtType:
    if isinstance(obj, datetime.datetime):
        return msgpack.ExtType(
            MsgpackTypes.datetime.value,
            struct.pack(
                ">I",
                int((obj - datetime.datetime(1970, 1, 1)).total_seconds()),
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
        return datetime.datetime.fromtimestamp(v[0])
    elif type_ == MsgpackTypes.date:
        # return datetime.date(int(v[:4]), int(v[4:6]), int(v[6:8]))
        v = struct.unpack(">III", data)
        return datetime.date(v[0], v[1], v[2])
    elif type_ == MsgpackTypes.timedelta:
        v = struct.unpack(">I", data)
        return datetime.timedelta(seconds=v[0])
    return msgpack.ExtType(code, data)


# ==============================================================================


class LazyDeserializer(dict):
    def __getitem__(self, key: str) -> Any:
        if key not in self:
            raise KeyError(key)
        rval = dict.get(self, key)
        if isinstance(rval, dict):
            if "__datetime__" in rval:
                rval = datetime.datetime.fromtimestamp(rval["0"])
                self[key] = rval
            elif "__date__" in rval:
                # is is MUCH faster to use date() than strptime
                # obj = datetime.datetime.strptime(obj['0'], "%Y%m%d").date()
                d = rval["0"]
                rval = datetime.date(int(d[:4]), int(d[4:6]), int(d[6:8]))
                self[key] = rval
            elif "__timedelta__" in rval:
                rval = datetime.timedelta(seconds=rval["0"])
                self[key] = rval
        return rval

    def values(self) -> List[Any]:
        return [self[key] for key in self]

    def itervalues(self) -> Generator[Any, None, None]:
        return (self[key] for key in self)

    def items(self) -> Generator[Tuple[Any, Any], None, None]:
        return ((key, self[key]) for key in self)

    def iteritems(self) -> List[Tuple[str, Any]]:
        return list(self.items())


class LazyDeserializerAlt(LazyDeserializer):
    pass


def override(
    self,
    key: str,
    KeyError=KeyError,
    dict=dict,
    isinstance=isinstance,
    datetime=datetime,
    datetime_datetime_fromtimestamp=datetime.datetime.fromtimestamp,
    datetime_date=datetime.date,
    datetime_timedelta=datetime.timedelta,
    int=int,
) -> Any:
    if key not in self:
        raise KeyError(key)
    rval = dict.get(self, key)
    if isinstance(rval, dict):
        if "__datetime__" in rval:
            rval = datetime_datetime_fromtimestamp(rval["0"])
            self[key] = rval
        elif "__date__" in rval:
            # is is MUCH faster to use date() than strptime
            # obj = datetime.datetime.strptime(obj['0'], "%Y%m%d").date()
            d = rval["0"]
            rval = datetime_date(int(d[:4]), int(d[4:6]), int(d[6:8]))
            self[key] = rval
        elif "__timedelta__" in rval:
            rval = datetime_timedelta(seconds=rval["0"])
            self[key] = rval
    return rval


LazyDeserializerAlt.__getitem__ = override


class MsgpackSerializer(object):
    """unified, self-contained serializer"""

    @classmethod
    def encode_datetime(cls, dt: datetime.datetime) -> Dict:
        """Serialize the given datetime.datetime object to a EPOCH seconds."""
        return {
            "__datetime__": True,
            "0": (dt - datetime.datetime(1970, 1, 1)).total_seconds(),
        }

    @classmethod
    def encode_date(cls, d: datetime.date) -> Dict:
        """Serialize the given datetime.date object to a JSON string."""
        # Default is ISO 8601 compatible (standard notation).
        return {
            "__date__": True,
            "0": "%04d%02d%02d" % (d.year, d.month, d.day),
        }

    @classmethod
    def encode_timedelta(cls, t: datetime.timedelta) -> Dict:
        """Serialize the given datetime.timedelta object to some seconds."""
        return {
            "__timedelta__": True,
            "0": t.total_seconds(),
        }

    @classmethod
    def encoder(cls, o: Any) -> Any:
        if isinstance(o, datetime.datetime):
            return cls.encode_datetime(o)
        elif isinstance(o, datetime.date):
            return cls.encode_date(o)
        elif isinstance(o, datetime.timedelta):
            return cls.encode_timedelta(o)
        elif isinstance(o, set):
            return tuple(o)
        else:
            return o

    @classmethod
    def decode_datedata(
        cls, obj
    ) -> Union[datetime.datetime, datetime.date, datetime.timedelta]:
        if b"__datetime__" in obj:
            obj = datetime.datetime.fromtimestamp(obj["0"])
        elif b"__date__" in obj:
            # is is MUCH faster to use date() than strptime
            # obj = datetime.datetime.strptime(obj['0'], "%Y%m%d").date()
            d = obj["0"]
            obj = datetime.date(int(d[:4]), int(d[4:6]), int(d[6:8]))
        elif b"__timedelta__" in obj:
            obj = datetime.timedelta(seconds=obj["0"])
        return obj

    @classmethod
    def decoder(cls, obj: Any) -> Any:
        obj = cls.decode_datedata(obj)
        return obj

    @classmethod
    def dumps(cls, payload: Any) -> bytes:
        # v = msgpack.packb(payload, default=cls.encoder, use_bin_type=True)
        v = msgpack_packb(payload, default=cls.encoder, use_bin_type=True)
        return v

    @classmethod
    def loads(cls, payload: bytes) -> Any:
        # v = msgpack.unpackb(payload,  encoding="utf-8", use_list=True)
        v = msgpack_unpackb(payload, encoding="utf-8", use_list=True)
        v = LazyDeserializer(v)
        assert "date" in v
        assert "datetime" in v
        assert "timedelta" in v
        return v


def _make_iterencode(
    cls,
    # # HACK: hand-optimized bytecode; turn globals into locals
    ValueError=ValueError,
    dict=dict,
    float=float,
    id=id,
    isinstance=isinstance,
    list=list,
    str=str,
    tuple=tuple,
    iter=iter,
    set=set,
    _datetime=None,
) -> Callable:
    if _datetime is None:
        _datetime = datetime

    @classmethod
    def _iterencode(cls, o: Any) -> Any:
        if isinstance(o, _datetime.datetime):
            """
            Serialize the given datetime.datetime object to a EPOCH seconds.
            """
            yield {
                "__datetime__": True,
                "0": (o - _datetime.datetime(1970, 1, 1)).total_seconds(),
            }
        elif isinstance(o, _datetime.date):
            """Serialize the given datetime.date object to a JSON string."""
            # Default is ISO 8601 compatible (standard notation).
            yield {
                "__date__": True,
                "0": "%04d%02d%02d" % (o.year, o.month, o.day),
            }
        elif isinstance(o, _datetime.timedelta):
            "Serialize the given datetime.timedelta object to some seconds."
            yield {
                "__timedelta__": True,
                "0": o.total_seconds(),
            }
        elif isinstance(o, set):
            yield tuple(o)
        else:
            yield o

    return _iterencode


class MsgpackSerializer_Iterencode(MsgpackSerializer):
    _iterencode = None

    @classmethod
    def encoder(cls, o: Any):
        chunks = cls.iterencode(o)
        if not isinstance(chunks, (list, tuple)):
            chunks = list(chunks)
        return chunks

    @classmethod
    def iterencode(cls, o):
        if cls._iterencode is None:
            cls._iterencode = _make_iterencode(cls, _datetime=datetime)
        return cls._iterencode(o)

    @classmethod
    def loads(cls, payload: bytes) -> Any:
        v = msgpack_unpackb(payload, encoding="utf-8", use_list=True)
        v = LazyDeserializerAlt(v)
        assert "date" in v
        assert "datetime" in v
        assert "timedelta" in v
        return v


class MsgpackSerializer_Alt(object):
    @classmethod
    def loads(cls, payload: bytes) -> Any:
        v = msgpack_unpackb(
            payload,
            ext_hook=msgpack_alt_ext_hook,
            encoding="utf-8",
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


if __name__ == "__main__":
    import pprint
    import timeit

    sample_data = {
        "string": "foo",
        "int": 100,
        "bool": True,
        "list": [1, 2, 3, 4, 5],
        "tuple": [1, 2, 3, 4, 5],
        "dict": {"a": 1, 1: "a"},
        "datetime": datetime.datetime.now(),
        "date": datetime.date.today(),
        "timedelta": datetime.timedelta(seconds=100),
    }
    encoded_msgpack = MsgpackSerializer.dumps(sample_data)
    encoded_msgpack_alt = MsgpackSerializer_Alt.dumps(sample_data)
    loaded_msgpack = MsgpackSerializer.loads(encoded_msgpack)
    loaded_msgpack_alt = MsgpackSerializer_Alt.loads(encoded_msgpack_alt)

    print("==" * 40)
    print("MSGPACK")
    print("- " * 40)
    print("RAW")
    pprint.pprint(sample_data)
    print("- " * 40)
    print("ENCODED")
    pprint.pprint(encoded_msgpack)
    print("- " * 40)
    print("LOADED")
    pprint.pprint(loaded_msgpack)
    print("- " * 40)
    print("ENCODED ALT")
    pprint.pprint(encoded_msgpack_alt)
    print("- " * 40)
    print("LOADED ALT")
    pprint.pprint(loaded_msgpack_alt)
    print("- " * 40)

    # this just checks to make sure we have encoded the items
    if False:
        print("items")
        loaded_msgpack = MsgpackSerializer.loads(encoded_msgpack)
        print(list(loaded_msgpack.items()))
        pprint.pprint(loaded_msgpack)
        print("---")

        print("values")
        loaded_msgpack = MsgpackSerializer.loads(encoded_msgpack)
        print(list(loaded_msgpack.values()))
        pprint.pprint(loaded_msgpack)
        print("---")

        print("iteritems")
        loaded_msgpack = MsgpackSerializer.loads(encoded_msgpack)
        print(list(loaded_msgpack.iteritems()))
        pprint.pprint(loaded_msgpack)
        print("---")

        print("itervalues")
        loaded_msgpack = MsgpackSerializer.loads(encoded_msgpack)
        print(list(loaded_msgpack.itervalues()))
        pprint.pprint(loaded_msgpack)
        print("---")

        print("pprint")
        loaded_msgpack = MsgpackSerializer.loads(encoded_msgpack)
        pprint.pprint(loaded_msgpack)
        print("---")

    iterations = 10000

    time_msgpack_dumps = timeit.timeit(
        "MsgpackSerializer.dumps(sample_data)",
        "from __main__ import MsgpackSerializer, sample_data",
        number=iterations,
    )
    time_msgpack_loads = timeit.timeit(
        "MsgpackSerializer.loads(encoded_msgpack)",
        "from __main__ import MsgpackSerializer, encoded_msgpack",
        number=iterations,
    )
    print("iterations = %s" % iterations)
    print("MsgpackSerializer.dumps : %s" % time_msgpack_dumps)
    print("MsgpackSerializer.loads : %s" % time_msgpack_loads)

    time_msgpack_dumps = timeit.timeit(
        "MsgpackSerializer_Iterencode.dumps(sample_data)",
        "from __main__ import MsgpackSerializer_Iterencode, sample_data",
        number=iterations,
    )
    time_msgpack_loads = timeit.timeit(
        "MsgpackSerializer_Iterencode.loads(encoded_msgpack)",
        "from __main__ import MsgpackSerializer_Iterencode, encoded_msgpack",
        number=iterations,
    )
    print("MsgpackSerializer_Iterencode.dumps : %s" % time_msgpack_dumps)
    print("MsgpackSerializer_Iterencode.loads : %s" % time_msgpack_loads)

    print(MsgpackSerializer_Iterencode.dumps(sample_data))
    print(MsgpackSerializer_Iterencode.loads(encoded_msgpack))

    time_msgpack_dumps = timeit.timeit(
        "MsgpackSerializer_Alt.dumps(sample_data)",
        "from __main__ import MsgpackSerializer_Alt, sample_data",
        number=iterations,
    )
    time_msgpack_loads = timeit.timeit(
        "MsgpackSerializer_Alt.loads(encoded_msgpack_alt)",
        "from __main__ import MsgpackSerializer_Alt, encoded_msgpack_alt",
        number=iterations,
    )
    print("MsgpackSerializer_Alt.dumps : %s" % time_msgpack_dumps)
    print("MsgpackSerializer_Alt.loads : %s" % time_msgpack_loads)

    print(MsgpackSerializer_Alt.dumps(sample_data))
    print(MsgpackSerializer_Alt.loads(encoded_msgpack_alt))

    if True:
        encoded_pickle = pickle.dumps(sample_data)
        loaded_pickle = pickle.loads(encoded_pickle)
        time_pickle_dumps = timeit.timeit(
            "pickle.dumps(sample_data)",
            "from __main__ import pickle, sample_data",
            number=iterations,
        )
        time_pickle_loads = timeit.timeit(
            "pickle.loads(encoded_pickle)",
            "from __main__ import pickle, encoded_pickle",
            number=iterations,
        )
        print("pickle.dumps           : %s" % time_pickle_dumps)
        print("pickle.loads           : %s" % time_pickle_loads)
