"""Integration coverage for the standalone Valkey backend variants."""

import os
from typing import cast
from uuid import uuid4

import pytest

from dogpile.cache import make_region
from dogpile.cache.api import NO_VALUE
from dogpile.cache.backends.valkey import _ValkeyLockWrapper
from dogpile.testing.fixtures import _GenericBackendTestSuite
from dogpile.testing.fixtures import _GenericMutexTestSuite
from dogpile.testing.fixtures import _GenericSerializerTestSuite

import dogpile_backend_redis_advanced  # noqa: F401
from dogpile_backend_redis_advanced.cache.backends.valkey_advanced import (
    ValkeyAdvancedBackend,
)
from dogpile_backend_redis_advanced.cache.backends.valkey_advanced import (
    ValkeyAdvancedHstoreBackend,
    ValkeyKeyType,
)
from dogpile_backend_redis_advanced.cache.serializers import (
    Serializer_PickleIntTime_ProxyBackend,
)


VALKEY_BACKEND = "dogpile_backend_redis_advanced.valkey"
VALKEY_PORT = os.getenv("DOGPILE_VALKEY_PORT")
VALKEY_ARGUMENTS = {"host": "127.0.0.1", "port": int(VALKEY_PORT or "6380")}
pytestmark = pytest.mark.skipif(
    VALKEY_PORT is None, reason="Set DOGPILE_VALKEY_PORT to run Valkey integration tests"
)


class _ValkeyConnection:
    @classmethod
    def _check_backend_available(cls, backend: ValkeyAdvancedBackend) -> None:
        """Fail if the explicitly configured Valkey service is unavailable."""
        assert backend.reader_client.ping()


class ValkeyAdvancedTest(_ValkeyConnection, _GenericBackendTestSuite):
    backend = VALKEY_BACKEND
    config_args = {"arguments": VALKEY_ARGUMENTS}


class ValkeyAdvancedSerializerTest(_GenericSerializerTestSuite, ValkeyAdvancedTest):
    """Run dogpile's standard serializer tests against the advanced backend."""


class ValkeyHstoreTest(ValkeyAdvancedTest):
    backend = f"{VALKEY_BACKEND}.hstore"


class _TestLockWrapper(_ValkeyLockWrapper):
    """Identify locks created through the custom wrapper hook."""


class ValkeyAdvancedMutexTest(_ValkeyConnection, _GenericMutexTestSuite):
    backend = f"{VALKEY_BACKEND}.hstore"
    config_args = {
        "arguments": {
            **VALKEY_ARGUMENTS,
            "distributed_lock": True,
            "thread_local_lock": False,
            "lock_class": _TestLockWrapper,
            "lock_prefix": "valkey.",
        }
    }

    def test_hash_key_lock(self) -> None:
        """A tuple key uses the custom wrapper and the configured prefix."""
        backend = self._backend()
        name = uuid4().hex
        mutex = backend.get_mutex((name, "field"))
        assert isinstance(mutex, _TestLockWrapper)
        assert mutex.acquire()
        try:
            assert backend.reader_client.exists(f"valkey.{name},field")
        finally:
            mutex.release()


class ValkeyAdvancedVariantsTest:
    def test_already_serialized_region(self) -> None:
        """The raw backend works with dogpile regions through a serializer proxy."""
        region = make_region().configure(
            f"{VALKEY_BACKEND}.already_serialized",
            arguments=VALKEY_ARGUMENTS,
            wrap=[Serializer_PickleIntTime_ProxyBackend],
        )
        key = uuid4().hex
        other = uuid4().hex
        try:
            region.set(key, b"raw")
            region.set_multi({other: b"\x00\xff"})
            assert region.get(key) == b"raw"
            assert region.get_multi([other, key]) == [b"\x00\xff", b"raw"]
        finally:
            region.delete_multi([key, other])

    def test_hash_mixed_multi(self) -> None:
        """Batch operations preserve duplicate positions, misses and hash grouping."""
        backend = ValkeyAdvancedHstoreBackend(VALKEY_ARGUMENTS)
        name = uuid4().hex
        scalar = f"{name}.string"
        field = (name, "first")
        other = (f"{name}.other", "second")
        missing = (name, "missing")
        try:
            backend.set_serialized_multi({field: b"", scalar: b"plain", other: b"two"})
            keys: list[ValkeyKeyType] = [field, scalar, other, missing, field]
            assert backend.get_serialized_multi(iter(keys)) == [b"", b"plain", b"two", NO_VALUE, b""]
            backend.delete(field)
            backend.delete_multi([scalar, other])
            assert backend.get_serialized_multi([field, scalar, other]) == [NO_VALUE] * 3
        finally:
            backend.delete_multi([field, scalar, other])

    @pytest.mark.parametrize("policy", [False, None, True])
    def test_hash_expiry(self, policy: bool | None) -> None:
        """Check creation and refresh policies without sleeping for expiration."""
        backend = ValkeyAdvancedHstoreBackend(
            {
                **VALKEY_ARGUMENTS,
                "valkey_expiration_time": 300,
                "valkey_expiration_time_hash": policy,
            }
        )
        name = uuid4().hex
        key = (name, "field")
        scalar = f"{name}.string"
        try:
            backend.set_serialized(key, b"first")
            ttl = cast(int, backend.reader_client.ttl(name))
            if policy is False:
                assert ttl == -1
            else:
                assert ttl > 60
                backend.writer_client.expire(name, 60)

            backend.set_serialized_multi({key: b"second", scalar: b"value"})
            assert backend.get_serialized(key) == b"second"
            assert cast(int, backend.reader_client.ttl(scalar)) > 60
            ttl = cast(int, backend.reader_client.ttl(name))
            if policy is True:
                assert ttl > 60
            elif policy is None:
                assert 0 < ttl <= 60
            else:
                assert ttl == -1
        finally:
            backend.delete_multi([key, scalar])
