"""Regression checks for Redis and Valkey write and lock edge cases."""

from dataclasses import dataclass
from importlib import import_module
import os
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from dogpile.cache import make_region
from dogpile.cache.api import NO_VALUE

from dogpile_backend_redis_advanced.cache.backends.redis_advanced import (
    RedisAdvancedHstoreBackend,
)
from dogpile_backend_redis_advanced.cache.backends.valkey_advanced import (
    ValkeyAdvancedHstoreBackend,
)
from .test_redis_backend import REDIS_HOST
from .test_redis_backend import REDIS_PORT
from .test_valkey_backend import VALKEY_ARGUMENTS
from .test_valkey_backend import VALKEY_BACKEND
from .test_valkey_backend import VALKEY_PORT


@dataclass(frozen=True)
class _Service:
    name: str
    backend: str
    arguments: dict[str, Any]
    response_error: type[Exception]
    lock_error: type[Exception]

    def hstore(self, **options: Any) -> RedisAdvancedHstoreBackend | ValkeyAdvancedHstoreBackend:
        """Configure the registered hash backend for this service."""
        arguments = self.arguments | options
        region = make_region().configure(f"{self.backend}.hstore", arguments=arguments)
        backend = region.backend
        assert isinstance(backend, (RedisAdvancedHstoreBackend, ValkeyAdvancedHstoreBackend))
        return backend


@pytest.fixture(params=["redis", "valkey"])
def service(request: pytest.FixtureRequest) -> _Service:
    """Use the configured test service and its native exception classes."""
    name = request.param
    if name == "valkey":
        if VALKEY_PORT is None:
            pytest.skip("Set DOGPILE_VALKEY_PORT to run Valkey integration tests")
        backend = VALKEY_BACKEND
        arguments = VALKEY_ARGUMENTS
    else:
        backend = "dogpile_backend_redis_advanced"
        arguments = {"host": REDIS_HOST, "port": REDIS_PORT}

    errors = import_module(f"{name}.exceptions")
    result = _Service(name, backend, arguments, errors.ResponseError, errors.LockNotOwnedError)
    try:
        result.hstore().reader_client.ping()
    except errors.ConnectionError:
        if name == "redis" and os.getenv("DOGPILE_REDIS_PORT") is None:
            pytest.skip("Redis is unavailable")
        raise
    return result


class BackendHardeningTest:
    @pytest.mark.parametrize("policy", [None, True])
    def test_hash_without_ttl(self, service: _Service, policy: bool | None) -> None:
        """Zero TTL keeps new hashes and preserves any pre-existing expiry."""
        backend = service.hstore(**{f"{service.name}_expiration_time_hash": policy})
        name = uuid4().hex
        first = (name, "first")
        second = (name, "second")
        try:
            backend.set_serialized(first, b"")
            assert backend.get_serialized(first) == b""
            assert backend.reader_client.ttl(name) == -1
            backend.writer_client.expire(name, 300)
            backend.set_serialized_multi({second: b"two"})
            assert backend.get_serialized_multi(iter([first, second, first])) == [
                b"", b"two", b"",
            ]
            assert backend.reader_client.ttl(name) != -1
        finally:
            backend.delete_multi([first, second])

    @pytest.mark.parametrize("suffix", ["", ".already_serialized", ".hstore"])
    def test_empty_batch(self, service: _Service, suffix: str) -> None:
        """Every variant accepts empty writes, reads, and deletes."""
        backend = make_region().configure(
            service.backend + suffix, arguments=service.arguments
        ).backend
        backend.set_serialized_multi({})
        assert list(backend.get_serialized_multi(iter(()))) == []
        backend.delete_multi(iter(()))
        if suffix == ".already_serialized":
            backend.set_multi({})
            assert list(backend.get_multi(iter(()))) == []

    def test_mixed_type_batch_conflict(self, service: _Service) -> None:
        """A key cannot address both a string and a hash within one write."""
        backend = service.hstore()
        name = uuid4().hex
        field = (name, "field")
        try:
            backend.set_serialized(field, b"original")
            with pytest.raises(ValueError, match="both strings and hashes"):
                backend.set_serialized_multi({name: b"string", field: b"replacement"})
            assert backend.get_serialized(field) == b"original"
        finally:
            backend.delete(field)

    def test_hash_type_error_preserves_ttl(self, service: _Service) -> None:
        """A failed hash write cannot set an expiry on an existing string."""
        backend = service.hstore(
            **{
                f"{service.name}_expiration_time": 300,
                f"{service.name}_expiration_time_hash": True,
            }
        )
        name = uuid4().hex
        other = uuid4().hex
        try:
            backend.writer_client.set(name, b"original")
            with pytest.raises(service.response_error):
                backend.set_serialized_multi({(name, "field"): b"value", other: b"other"})
            assert backend.get_serialized(name) == b"original"
            assert backend.reader_client.ttl(name) == -1
            assert backend.get_serialized(other) is NO_VALUE
        finally:
            backend.delete_multi([name, other])

    def test_concurrent_hash_creation(self, service: _Service) -> None:
        """Retry the TTL decision when another writer creates the watched hash."""
        backend = service.hstore(**{f"{service.name}_expiration_time": 300})
        client = backend.writer_client
        name = uuid4().hex
        pipeline_type = type(client.pipeline())
        original_hlen = pipeline_type.hlen

        def create_after_read(pipe: Any, key: str) -> Any:
            result = original_hlen(pipe, key)
            if result == 0:
                client.hset(key, mapping={"concurrent": b"first"})
            return result

        try:
            with patch.object(pipeline_type, "hlen", create_after_read):
                backend.set_serialized((name, "ours"), b"second")
            assert backend.get_serialized_multi([(name, "concurrent"), (name, "ours")]) == [
                b"first", b"second",
            ]
            assert backend.reader_client.ttl(name) == -1
        finally:
            backend.delete(name)

    def test_lock_release_preserves_replacement(self, service: _Service) -> None:
        """Losing a lock reports the error and leaves its replacement owned."""
        backend = service.hstore(distributed_lock=True, thread_local_lock=False)
        key = uuid4().hex
        lock_key = backend.lock_template.format(key)
        original = backend.get_mutex(key)
        replacement = backend.get_mutex(key)
        assert original is not None and replacement is not None
        assert original.acquire(wait=False)
        try:
            backend.writer_client.delete(lock_key)
            assert replacement.acquire(wait=False)
            try:
                with pytest.raises(service.lock_error):
                    original.release()
                assert replacement.locked()
            finally:
                replacement.release()
        finally:
            backend.writer_client.delete(lock_key)
