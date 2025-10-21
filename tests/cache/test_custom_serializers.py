from typing import Any
from typing import Callable
from typing import List
from unittest import TestCase

# pypi
from dogpile.cache import make_region
from dogpile.cache.api import NO_VALUE  # singleton
from dogpile.cache.proxy import ProxyBackend
from dogpile.cache.region import CacheRegion

# local
import dogpile_backend_redis_advanced  # noqa: F401
from dogpile_backend_redis_advanced.cache.serializers import f_pickle_loads
from dogpile_backend_redis_advanced.cache.serializers import (
    Serializer_PickleIntTime_ProxyBackend,
)
from dogpile_backend_redis_advanced.cache.serializers import (
    Serializer_PickleNoMeta_ProxyBackend,
)
from dogpile_backend_redis_advanced.cache.serializers import Serializer_Raw_ProxyBackend
from .test_redis_backend import REDIS_HOST
from .test_redis_backend import REDIS_PORT


# ==============================================================================


class _RedisAlreadySerialized:
    assertRaises: Callable
    region: CacheRegion
    wrap: ProxyBackend
    _debug_cache_size: bool = False

    def setUp(self):
        self.region = make_region(name=self.__class__.__name__)
        self.region.configure_from_config(
            {
                "host": REDIS_HOST,
                "port": REDIS_PORT,
                "expiration_time": 3600,
                "wrap": [self.wrap],
                "backend": "dogpile_backend_redis_advanced.already_serialized",
            },
            prefix="",
        )

    def test_set(self):
        value_str = "example value"
        self.region.set("example", value_str)
        cached = self.region.get("example")
        assert value_str == cached

    def test_cached(self):
        value_str = "example value"
        self.region.set("example", value_str)

        # the assembled should look right
        # and have a size if configured
        cached_assembled = self.region.get_value_metadata("example")
        if not self._debug_cache_size:
            assert "sz" not in cached_assembled[1]
        else:
            assert "sz" in cached_assembled[1]

        # the raw value might look identical
        cached_raw = self.region.actual_backend.get_serialized("example")
        if self.wrap == Serializer_PickleNoMeta_ProxyBackend:
            assert f_pickle_loads(cached_raw) == value_str
        elif (self.wrap == Serializer_Raw_ProxyBackend) or (
            isinstance(self.wrap, Serializer_Raw_ProxyBackend)
        ):
            assert cached_raw.decode() == value_str
        else:
            assert f_pickle_loads(cached_raw) != value_str

    def _test_roundtrip(self, name: str, value: Any) -> None:
        cache_key = "%s|%s" % (self.wrap.__class__.__name__, name)
        self.region.set(cache_key, value)
        cached = self.region.get(cache_key)
        assert value == cached

    def test_roundtrip__str(self):
        self._test_roundtrip(name="string", value="STRING")

    def test_roundtrip__int(self):
        self._test_roundtrip(name="int", value=100)

    def test_roundtrip__none(self):
        self._test_roundtrip(name="None", value=None)

    def test_roundtrip__NO_VALUE(self):
        self._test_roundtrip(name="NO_VALUE", value=NO_VALUE)

    def test_roundtrip__float(self):
        if "float" in self._test_roundtrip__expected_fails:
            self.assertRaises(
                ValueError,
                self._test_roundtrip,
                name="float",
                value=1.0,
            )
        else:
            self._test_roundtrip(name="float", value=1.0)

    _test_roundtrip__expected_fails: List[str] = []


class RedisAlreadySerialized__RedisTest__PickleIntTime(
    _RedisAlreadySerialized, TestCase
):
    wrap = Serializer_PickleIntTime_ProxyBackend


class RedisAlreadySerialized__RedisTest__PickleNoMeta(
    _RedisAlreadySerialized, TestCase
):
    wrap = Serializer_PickleNoMeta_ProxyBackend


class RedisAlreadySerialized__RedisTest__Raw(_RedisAlreadySerialized, TestCase):
    wrap = Serializer_Raw_ProxyBackend
    _test_roundtrip__expected_fails = [
        "float",
    ]


class RedisAlreadySerialized__RedisTest__PickleIntTime_Debug(
    _RedisAlreadySerialized, TestCase
):
    _debug_cache_size = True
    wrap = Serializer_PickleIntTime_ProxyBackend()
    wrap.DEBUG_CACHE_SIZE = True


class RedisAlreadySerialized__RedisTest__PickleNoMeta_Debug(
    _RedisAlreadySerialized, TestCase
):
    wrap = Serializer_PickleNoMeta_ProxyBackend


class RedisAlreadySerialized__RedisTest__Raw_debug(_RedisAlreadySerialized, TestCase):
    _debug_cache_size = True
    wrap = Serializer_Raw_ProxyBackend()
    wrap.DEBUG_CACHE_SIZE = True
    _test_roundtrip__expected_fails = [
        "float",
    ]
