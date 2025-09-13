# stdlib
import pickle
import time
from typing import Any
from typing import Callable
from typing import Dict
from typing import Mapping
from typing import Optional
from typing import Sequence
from typing import Union

# pypi
from dogpile.cache.api import CachedValue
from dogpile.cache.api import KeyType
from dogpile.cache.api import NO_VALUE  # singleton
from dogpile.cache.api import NoValue  # class
from dogpile.cache.proxy import ProxyBackend
from dogpile.cache.region import value_version


# ==============================================================================


def default_dumps_factory() -> Callable:
    """
    optimized for the cpython compiler. shaves a tiny bit off.
    this turns 'pickle_dumps' into a local variable to the dump function.
    original:
              0 LOAD_GLOBAL              0 (pickle)
              3 LOAD_ATTR                1 (dumps)
              6 LOAD_GLOBAL              2 (v)
              9 LOAD_GLOBAL              0 (pickle)
             12 LOAD_ATTR                3 (HIGHEST_PROTOCOL)
             15 CALL_FUNCTION            2
             18 RETURN_VALUE
    optimized:
              0 LOAD_DEREF               0 (_dumps)
              3 LOAD_FAST                0 (v)
              6 LOAD_DEREF               1 (_protocol)
              9 CALL_FUNCTION            2
             12 RETURN_VALUE
    """
    _dumps = pickle.dumps
    _protocol = pickle.HIGHEST_PROTOCOL

    def default_dumps(v: Any) -> bytes:
        return _dumps(v, _protocol)

    return default_dumps


# shortcuts
f_time = time.time
f_pickle_loads = pickle.loads
# f_pickle_dumps = pickle.dumps
f_pickle_dumps = default_dumps_factory()


def faked_meta() -> Dict:
    return {"ct": f_time(), "v": value_version}


class _CustomSerializerProxyBackend(ProxyBackend):
    """
    In order to use a Custom Serializer like this, we do two things:

    1- Include this as a wraps on a Region
    2- Configure the Region to use
      "dogpile_backend_redis_advanced.already_serialized", which does
      the following:
        unsets the Region's serializer/deserializer
        proxies the get/set commands to serialized versions

    Together, that looks like this:

        region = make_region(name="AlreadySerializedRegion")
        region.configure_from_config(
            {"host": REDIS_HOST,
             "port": REDIS_PORT,
             "expiration_time": 3600,
             "wrap": [CustomSerializerProxyBackend],
             "backend": "dogpile_backend_redis_advanced.already_serialized",
             },
            prefix="",
        )

    What does this backend do?

    In the default usage:
        1- The time is truncated from the metadata payload
        2- cache size data can be logged.  Instead of passing in a wrap class
           to the region constructor, pass an instance with
           `DEBUG_CACHE_SIZE = True`::

                wrap = Serializer_Raw_ProxyBackend()
                wrap.DEBUG_CACHE_SIZE = True

    """

    DEBUG_CACHE_SIZE: bool = False

    def get_serialized_multi(
        self,
        key: KeyType,
    ) -> Union[CachedValue, NoValue]:
        raise NotImplementedError(
            "Custom serializers not supported | " "get_serialized_multi"
        )

    def set_serialized_multi(self, key: KeyType, value: Any) -> None:
        raise NotImplementedError(
            "Custom serializers not supported | " "set_serialized_multi"
        )

    def get_serialized(self, key: KeyType) -> Union[CachedValue, NoValue]:
        raise NotImplementedError(
            "Custom serializers not supported | " "get_serialized"
        )

    def set_serialized(self, key: KeyType, value: Any) -> None:
        raise NotImplementedError(
            "Custom serializers not supported | " "set_serialized"
        )

    def get(self, key: KeyType) -> Union[CachedValue, NoValue]:
        serialized = self.proxied.get(key)
        if serialized is NO_VALUE:
            return NO_VALUE
        value = self._deserialize(serialized)
        if self.DEBUG_CACHE_SIZE:
            value[1]["sz"] = len(str(serialized))
        return CachedValue(value[0], value[1])

    def get_multi(
        self,
        keys: Sequence[KeyType],
    ) -> Union[CachedValue, NoValue]:
        backend_values = self.proxied.get_multi(keys)
        for idx, serialized in enumerate(backend_values):
            if serialized is not NO_VALUE:
                value = self._deserialize(serialized)
                if self.DEBUG_CACHE_SIZE:
                    value[1]["sz"] = len(str(serialized))
                backend_values[idx] = CachedValue(value[0], value[1])
        return backend_values

    def set(self, key: KeyType, value: CachedValue) -> None:
        """make the timeout an int"""
        value.metadata["ct"] = int(value.metadata["ct"])
        serialized = self._serialize(value)
        self.proxied.set(key, serialized)

    def set_multi(
        self,
        mapping: Mapping[KeyType, Union[CachedValue, NoValue]],
    ) -> None:
        for k in list(mapping.keys()):
            value = mapping[k]
            value.metadata["ct"] = int(value.metadata["ct"])
            serialized = self._serialize(value)
            mapping[k] = serialized
        self.proxied.set_multi(mapping)


class _CustomSerializerNoMetaProxyBackend(_CustomSerializerProxyBackend):
    """
    This serializer does not cache metadata
    """

    def get(self, key: KeyType) -> Union[CachedValue, NoValue]:
        serialized = self.proxied.get(key)
        if serialized is NO_VALUE:
            return NO_VALUE
        value = self._deserialize(serialized)
        return CachedValue(value, faked_meta())

    def get_multi(
        self,
        keys: Sequence[KeyType],
    ) -> Union[CachedValue, NoValue]:
        backend_values = self.proxied.get_multi(keys)
        for idx, serialized in enumerate(backend_values):
            if serialized is not NO_VALUE:
                value = self._deserialize(serialized)
                backend_values[idx] = CachedValue(value, faked_meta())
        return backend_values

    def set(self, key: KeyType, value: CachedValue) -> None:
        """make the timeout an int"""
        serialized = self._serialize(value.payload)
        self.proxied.set(key, serialized)

    def set_multi(
        self,
        mapping: Mapping[KeyType, Union[CachedValue, NoValue]],
    ) -> None:
        for k in list(mapping.keys()):
            value = mapping[k]
            serialized = self._serialize(value.payload)
            mapping[k] = serialized
        self.proxied.set_multi(mapping)


class Serializer_PickleIntTime_ProxyBackend(_CustomSerializerProxyBackend):
    """
    see docs for `_CustomSerializerProxyBackend`
    """

    _deserialize = f_pickle_loads

    def _serialize(self, serialized: bytes) -> bytes:
        return f_pickle_dumps(serialized)


class Serializer_PickleNoMeta_ProxyBackend(
    _CustomSerializerNoMetaProxyBackend
):  # noqa: E501
    """
    see docs for `_CustomSerializerProxyBackend`
    """

    _deserialize = f_pickle_loads

    def _serialize(self, serialized: bytes) -> bytes:
        return f_pickle_dumps(serialized)


class Serializer_Raw_ProxyBackend(_CustomSerializerProxyBackend):
    """
    see docs for `_CustomSerializerProxyBackend`

    This is a custom serializer designed to make cross-platform cacheable data.

    Strings are encoded to bytes.

    Other types are serialized to bytes and stored with the following mapping:

        TypeIdentifier - 1 character
        \x7f - ascii delete
        Value

    Supported formats

        b\x7f - bytes
        i\x7f - integer
        @\x7f - Special
            @\x7fNone = None
            @\x7fNO_VALUE = dogpile.cache.api.NO_VALUE
    """

    def _deserialize(
        self,
        serialized: bytes,
        *args,
    ) -> Union[str, int, NoValue, None]:
        fmt: Optional[bytes] = None
        value: Any
        if b"\x7f" in serialized:
            fmt, value = serialized.split(b"\x7f")
            if fmt == b"b":
                pass
            elif fmt == b"@":
                if value == b"NO_VALUE":
                    value = NO_VALUE
                elif value == b"None":
                    value = None
            elif fmt == b"i":
                value = int(value)
            else:
                raise ValueError("unknown encoding: %s", serialized)
        else:
            value = serialized.decode()
        return value, faked_meta()

    def _serialize(self, value: CachedValue) -> bytes:
        raw = value.payload
        _raw: str
        if raw is NO_VALUE:
            _raw = "@\x7fNO_VALUE"
        elif raw is None:
            _raw = "@\x7fNone"
        elif isinstance(raw, str):
            if "\x7f" in raw:
                raise ValueError(
                    "cannot encode value containing escape character \\x7f"
                )
            _raw = raw
        elif isinstance(raw, int):
            _raw = "i\x7f%s" % raw
        elif isinstance(raw, bytes):
            # exit early as bytes does not need to be `.encode()`d.
            return b"b\x7f%s" % raw
        else:
            raise ValueError("unsupported payload for raw serialization")
        return _raw.encode()
