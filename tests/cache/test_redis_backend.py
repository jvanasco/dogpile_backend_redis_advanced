from concurrent.futures import ThreadPoolExecutor
import os
from threading import Event
import time
from typing import Any
from typing import Optional

# pypi
from dogpile.cache.region import _backend_loader
from dogpile.testing import eq_
from dogpile.testing.fixtures import _GenericBackendFixture
from dogpile.testing.fixtures import _GenericBackendTestSuite
from dogpile.testing.fixtures import _GenericMutexTestSuite
from dogpile.testing.fixtures import _GenericSerializerTestSuite
from mock import Mock
from mock import patch
import pytest
from typing_extensions import NotRequired
from typing_extensions import TypedDict

# local
import dogpile_backend_redis_advanced  # noqa: F401

# ==============================================================================

REDIS_HOST = "127.0.0.1"
REDIS_PORT = int(os.getenv("DOGPILE_REDIS_PORT", "6379"))
expect_redis_running = os.getenv("DOGPILE_REDIS_PORT") is not None

# import to register the plugin

"""
ABOUT THESE TESTS

Compatibility Tests
===

Tests that have `_Compatibility_` in the name are pegged to upstream tests. They
ensure compatibility with the core dogpile cache routines

* RedisAdvanced_Compatibility_Test
* RedisAdvanced_Compatibility_DistributedMutexTest
* RedisAdvanced_Compatibility_ConnectionTest
* RedisAdvancedHstore_Compatibility_Test
* RedisAdvancedHstore_Compatibility_DistributedMutexTest
* RedisAdvancedHstore_Compatibility_ConnectionTest

SerializedAlternate_Test
===

these tests use msgpack to test different serializers

HstoreTests
===

These test advanced support for hstore

tox -e py27 -- tests/cache/test_redis_backend.py::RedisAdvanced_SerializedAlternate_Test

"""


class ArugumentsDict(TypedDict):
    host: str
    port: int
    db: int
    distributed_lock: NotRequired[bool]
    thread_local_lock: NotRequired[bool]
    lock_timeout: NotRequired[int]
    redis_expiration_time: NotRequired[int]
    blocking_timeout: NotRequired[int]
    lock_class: NotRequired[Any]
    lock_prefix: NotRequired[str]
    redis_expiration_time_hash: NotRequired[Optional[bool]]


class ConfigDict(TypedDict):
    arguments: ArugumentsDict


class _TestRedisConn:
    @classmethod
    def _check_backend_available(cls, backend):
        try:
            # backend._create_client()
            backend.set_serialized("x", b"y")
            assert backend.get_serialized("x") == b"y"
            backend.delete("x")
        except Exception as exc:
            if not expect_redis_running:
                pytest.skip(
                    str(exc.args[0]) + "redis is not running or "
                    "otherwise not functioning correctly"
                )
            else:
                raise


# ==============================================================================


class RedisAdvanced__RedisTest(_TestRedisConn, _GenericBackendTestSuite):
    # implements: dogpile_cache/tests/cache/test_redis_backend.py::RedisTest
    backend = "dogpile_backend_redis_advanced"
    config_args: ConfigDict = {
        "arguments": {  # type: ignore[typeddict-unknown-key]
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "foo": "barf",
        }
    }


class RedisAdvancedHstore__RedisTest(RedisAdvanced__RedisTest):
    # implements: dogpile_cache/tests/cache/test_redis_backend.py::RedisTest
    backend = "dogpile_backend_redis_advanced.hstore"


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


class RedisAdvanced__RedisSerializerTest(
    _GenericSerializerTestSuite,
    RedisAdvanced__RedisTest,
):
    pass


class RedisAdvancedHstore__RedisSerializerTest(RedisAdvanced__RedisSerializerTest):
    pass


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


class RedisAdvanced__RedisDistributedMutexTest(_TestRedisConn, _GenericMutexTestSuite):
    backend = "dogpile_backend_redis_advanced"
    config_args: ConfigDict = {
        "arguments": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "distributed_lock": True,
        }
    }


class RedisAdvancedHStore__RedisDistributedMutexTest(
    RedisAdvanced__RedisDistributedMutexTest
):
    backend = "dogpile_backend_redis_advanced.hstore"


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


class RedisAdvanced__RedisAsyncCreationTest(_TestRedisConn, _GenericBackendFixture):
    backend = "dogpile_backend_redis_advanced"
    config_args: ConfigDict = {
        "arguments": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "distributed_lock": True,
            # This is the important bit:
            "thread_local_lock": False,
            "blocking_timeout": 3,
        }
    }

    def test_distributed_async_locks(self):
        pool = ThreadPoolExecutor(max_workers=1)
        ev = Event()

        # A simple example of how people may implement an async runner -
        # plugged into a thread pool executor.
        def asyncer(cache, key, creator, mutex):
            print("asyncer")
            print("cache", cache)
            print("key", key)
            print("creator", creator)
            print("mutex", mutex)

            def _call():
                print(4)
                try:
                    value = creator()
                    cache.set(key, value)
                finally:
                    # If a thread-local lock is used here, this will fail
                    # because generally the async calls run in a different
                    # thread (that's the point of async creators).
                    try:
                        mutex.release()
                    except Exception:
                        pass
                    else:
                        ev.set()

            return pool.submit(_call)

        print(1)
        reg = self._region(
            region_args={"async_creation_runner": asyncer},
            config_args={"expiration_time": 0.1},
        )

        print(2)

        @reg.cache_on_arguments()
        def blah(k):
            print(21)
            return k * 2

        print(3)
        # First call adds to the cache without calling the async creator.
        eq_(blah("asd"), "asdasd")

        # Wait long enough to cause the cached value to get stale.
        time.sleep(0.3)

        # This will trigger the async runner and return the stale value.
        eq_(blah("asd"), "asdasd")

        # Wait for the the async runner to finish or timeout. If the mutex
        # release errored, then the event won't be set and we'll timeout.
        # On <= Python 3.1, wait returned nothing. So check is_set after.
        ev.wait(timeout=1.0)
        eq_(ev.is_set(), True)


class RedisAdvancedHstore__RedisAsyncCreationTest(
    RedisAdvanced__RedisAsyncCreationTest
):
    backend = "dogpile_backend_redis_advanced.hstore"


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


@patch("redis.StrictRedis", autospec=True)
class RedisAdvanced__RedisConnectionTest:
    # reimplements `RedisConnectionTest`
    backend = "dogpile_backend_redis_advanced"
    backend_cls: Any

    @classmethod
    def setup_class(cls):
        print("RedisAdvanced__RedisConnectionTest", cls)
        cls.backend_cls = _backend_loader.load(cls.backend)
        try:
            cls.backend_cls({})
        except ImportError:
            print("Backend %s not installed" % cls.backend)
            pytest.skip("Backend %s not installed" % cls.backend)

    def _test_helper(self, mock_obj, expected_args, connection_args=None):
        if connection_args is None:
            connection_args = expected_args

        self.backend_cls(connection_args)
        mock_obj.assert_called_once_with(**expected_args)

    def test_connect_with_defaults(self, MockStrictRedis):
        # The defaults, used if keys are missing from the arguments dict.
        arguments = {
            "host": "localhost",
            "port": 6379,
            "db": 0,
        }
        expected = arguments.copy()
        expected.update({"username": None, "password": None})
        self._test_helper(MockStrictRedis, expected, arguments)

    def test_connect_with_basics(self, MockStrictRedis):
        arguments = {
            "host": "127.0.0.1",
            "port": 6379,
            "db": 0,
        }
        expected = arguments.copy()
        expected.update({"username": None, "password": None})
        self._test_helper(MockStrictRedis, expected, arguments)

    def test_connect_with_password(self, MockStrictRedis):
        arguments = {
            "host": "127.0.0.1",
            "password": "some password",
            "port": 6379,
            "db": 0,
        }
        expected = arguments.copy()
        expected.update({"username": None})
        self._test_helper(MockStrictRedis, expected, arguments)

    def test_connect_with_username_and_password(self, MockStrictRedis):
        arguments = {
            "host": "127.0.0.1",
            "username": "redis",
            "password": "some password",
            "port": 6379,
            "db": 0,
        }
        self._test_helper(MockStrictRedis, arguments)

    def test_connect_with_socket_timeout(self, MockStrictRedis):
        arguments = {
            "socket_timeout": 0.5,
            "host": "127.0.0.1",
            "port": 6379,
            "db": 0,
        }
        expected = arguments.copy()
        expected.update({"username": None, "password": None})
        self._test_helper(MockStrictRedis, expected, arguments)

    def test_connect_with_socket_connect_timeout(self, MockStrictRedis):
        arguments = {
            "host": "127.0.0.1",
            "port": 6379,
            "socket_timeout": 1.0,
            "db": 0,
        }
        expected = arguments.copy()
        expected.update({"username": None, "password": None})
        self._test_helper(MockStrictRedis, expected, arguments)

    def test_connect_with_socket_keepalive(self, MockStrictRedis):
        arguments = {
            "host": "127.0.0.1",
            "port": 6379,
            "socket_keepalive": True,
            "db": 0,
        }
        expected = arguments.copy()
        expected.update({"username": None, "password": None})
        self._test_helper(MockStrictRedis, expected, arguments)

    def test_connect_with_socket_keepalive_options(self, MockStrictRedis):
        arguments = {
            "host": "127.0.0.1",
            "port": 6379,
            "socket_keepalive": True,
            # 4 = socket.TCP_KEEPIDLE
            "socket_keepalive_options": {4, 10.0},
            "db": 0,
        }
        expected = arguments.copy()
        expected.update({"username": None, "password": None})
        self._test_helper(MockStrictRedis, expected, arguments)

    def test_connect_with_connection_pool(self, MockStrictRedis):
        pool = Mock()
        arguments = {"connection_pool": pool, "socket_timeout": 0.5}
        expected_args = {"connection_pool": pool}
        self._test_helper(MockStrictRedis, expected_args, connection_args=arguments)

    def test_connect_with_url(self, MockStrictRedis):
        arguments = {"url": "redis://redis:password@127.0.0.1:6379/0"}
        self._test_helper(MockStrictRedis.from_url, arguments)

    def test_extra_arbitrary_args(self, MockStrictRedis):
        arguments = {
            "url": "redis://redis:password@127.0.0.1:6379/0",
            "connection_kwargs": {
                "ssl": True,
                "encoding": "utf-8",
                "new_redis_arg": 50,
            },
        }
        self._test_helper(
            MockStrictRedis.from_url,
            {
                "url": "redis://redis:password@127.0.0.1:6379/0",
                "ssl": True,
                "encoding": "utf-8",
                "new_redis_arg": 50,
            },
            arguments,
        )


class RedisAdvancedHstore__RedisConnectionTest(RedisAdvanced__RedisConnectionTest):
    # reimplements `RedisConnectionTest`
    backend = "dogpile_backend_redis_advanced.hstore"
