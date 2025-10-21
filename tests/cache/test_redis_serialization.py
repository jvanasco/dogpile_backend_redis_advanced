import pickle
import time
from typing import Any
from typing import List
from typing import Optional
from typing import Sequence
from typing import Tuple
from typing import Union
from unittest import TestCase

# pypi
from dogpile.cache.api import CachedValue
from dogpile.cache.api import NO_VALUE
from dogpile.testing import eq_
from dogpile.testing.fixtures import _GenericBackendFixture
from dogpile.testing.fixtures import _GenericBackendTestSuite
from dogpile.testing.fixtures import _GenericMutexTestSuite
import msgpack
import redis

# local
import dogpile_backend_redis_advanced  # noqa: F401
from .test_redis_backend import _TestRedisConn
from .test_redis_backend import ConfigDict
from .test_redis_backend import REDIS_HOST
from .test_redis_backend import REDIS_PORT

# ==============================================================================


def my_loads(value):
    """'
    we need to unpack the value and stash it into a CachedValue
    we support strings in this version, because it's used in unit tests
    that require the ability to set/read raw data.
    we could disable that test, but this workaround supports it.
    """
    # this is True for backward compatibility
    value = msgpack.unpackb(value, use_list=False, raw=False)
    if isinstance(value, tuple):
        return CachedValue(*value)
    return value


class _SerializedAlternate(
    _TestRedisConn,
    _GenericBackendTestSuite,
):
    config_args: ConfigDict = {
        "arguments": {  # type: ignore[typeddict-unknown-key]
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "foo": "barf",
            "loads": my_loads,
            # "dumps": msgpack.packb,
        }
    }


class RedisAdvanced_SerializedAlternate_Test(_SerializedAlternate):
    backend = "dogpile_backend_redis_advanced"


class RedisAdvancedHstore_SerializedAlternate_Test(_SerializedAlternate):
    backend = "dogpile_backend_redis_advanced.hstore"


# make this simple
KEY_STRING = "some_key"
KEY_HASH = ("some_key", "h1")
CLOUD_VALUE__BYTES = b"some value"

_keys_mixed: List[Union[int, Tuple[str, int]]] = [
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    ("a", 10),
    ("a", 30),
    ("a", 20),
    ("b", 9),
    ("c", 8),
    ("d", 7),
    ("e", 6),
    ("f", 5),
    ("g", 4),
    ("h", 3),
    ("i", 2),
    ("j", 1),
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    20,
]


def _keys_to_value(x: Any) -> str:
    "this just"
    return str(x * 2)


KEYS_2_RAW__PAIRS: List[Tuple[Union[str, Tuple[str, ...]], str]] = []
KEYS_2_ENCODED__PAIRS: List[Tuple[Sequence[str], bytes]] = []


for k in _keys_mixed:
    _value: str
    _value_encoded: bytes
    _key: Union[str, Tuple[str, ...]]
    if isinstance(k, tuple):
        _key = tuple(str(i) for i in k)
        _value = _keys_to_value(_key[1])
    else:
        _key = str(k)
        _value = _keys_to_value(_key)

    _value_encoded = pickle.dumps(_value)

    KEYS_2_RAW__PAIRS.append((_key, _value))
    KEYS_2_ENCODED__PAIRS.append((_key, _value_encoded))


class RedisAdvancedHstore_HstoreTest(_TestRedisConn, _GenericBackendFixture, TestCase):
    backend = "dogpile_backend_redis_advanced.hstore"
    config_args: ConfigDict = {
        "arguments": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "redis_expiration_time": 3,
        }
    }

    def test_backend_set_get_delete(self):
        """
        this tests
            * get
            * set
            * delete
        """

        backend = self._backend()
        # strings
        backend.set_serialized(KEY_STRING, CLOUD_VALUE__BYTES)
        eq_(backend.get_serialized(KEY_STRING), CLOUD_VALUE__BYTES)
        backend.delete(KEY_STRING)
        eq_(backend.get_serialized(KEY_STRING), NO_VALUE)

        # make sure we delete above. otherwise the test will fail by trying to
        # use a hmset on a normal key

        # hstore
        backend.set_serialized(KEY_HASH, CLOUD_VALUE__BYTES)
        eq_(backend.get_serialized(KEY_HASH), CLOUD_VALUE__BYTES)
        backend.delete(KEY_HASH)
        eq_(backend.get_serialized(KEY_HASH), NO_VALUE)

    def test_mixed_keys(self):
        """
        this tests
            * get_multi
            * set_multi
            * delete_multi
        """
        backend = self._backend()

        # set up the mapping of original items
        # upload the mapping
        keys2encoded = dict(KEYS_2_ENCODED__PAIRS)
        keys_ = list(keys2encoded.keys())
        backend.set_serialized_multi(keys2encoded)

        # grab the results
        # purposefully not grabbing via string key as in mixed_mapping
        results = backend.get_serialized_multi(keys_)

        # enumerate the results, match their order to the ordered array
        for idx, result in enumerate(results):
            # the key supplied is: keys_mixed[idx]
            # this equates to: KEYS_2_RAW__PAIRS[idx][0]
            result_key = keys_[idx]
            eq_(result, keys2encoded[result_key])

        # delete them all
        backend.delete_multi(keys_)

        # grab the results
        results = backend.get_serialized_multi(keys_)

        # ensure they're all misses
        for _result in results:
            eq_(_result, NO_VALUE)


class RedisAdvancedHstore_HstoreTest_Expires_Hash(RedisAdvancedHstore_HstoreTest):
    redis_expiration_time_hash: Optional[bool] = None
    config_args: ConfigDict = {
        "arguments": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "redis_expiration_time": 3,
            "redis_expiration_time_hash": redis_expiration_time_hash,
        }
    }

    def test_expires(self):
        """
        this tests
            * get_multi
            * set_multi
            * delete_multi
        """
        backend = self._backend()

        # hstore
        backend.set_serialized(KEY_HASH, CLOUD_VALUE__BYTES)
        eq_(backend.get_serialized(KEY_HASH), CLOUD_VALUE__BYTES)

        # we don't set ttl on `redis_expiration_time_hash = False`
        if self.redis_expiration_time_hash is not False:
            ttl = backend.reader_client.ttl(KEY_HASH[0])
            assert ttl >= 1, "ttl should be larger"

            ttl = backend.writer_client.ttl(KEY_HASH[0])
            assert ttl >= 1, "ttl should be larger"

        backend.delete(KEY_HASH)
        eq_(backend.get_serialized(KEY_HASH), NO_VALUE)

    def test_expires_multi(self):
        """
        this tests
            * get_multi
            * set_multi
            * delete_multi
        """
        backend = self._backend()

        # hstore
        keys2encoded = dict(KEYS_2_ENCODED__PAIRS)
        keys_ = list(keys2encoded.keys())
        backend.set_serialized_multi(keys2encoded)

        # grab the results
        results = backend.get_serialized_multi(keys_)

        # enumerate the results, match their order to the ordered array
        for idx, result in enumerate(results):
            result_key = keys_[idx]
            eq_(result, keys2encoded[result_key])

        # we don't set ttl on `redis_expiration_time_hash = False`
        if self.redis_expiration_time_hash is not False:
            # make sure every key has an expiry!
            for k in keys_:
                if isinstance(k, tuple):
                    k = k[0]
                ttl = backend.reader_client.ttl(k)
                assert ttl >= 0, "ttl should be larger"

                ttl = backend.writer_client.ttl(k)
                assert ttl >= 0, "ttl should be larger"

        # delete them all
        backend.delete_multi(keys_)


class RedisAdvancedHstore_HstoreTest_Expires_Hash_True(
    RedisAdvancedHstore_HstoreTest_Expires_Hash
):
    redis_expiration_time_hash = True
    config_args: ConfigDict = {
        "arguments": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "redis_expiration_time": 10,
            "redis_expiration_time_hash": redis_expiration_time_hash,
        }
    }

    def test_expires_tracked(self):
        """
        When redis_expiration_time_hash is True, we should be setting the
        expiry on every hash set.

        to test this, we're just going to loop this a few times

        the loop should reset the expiry to 10 seconds, then sleep 1s, so it will
        always be >= 9.
        """
        backend = self._backend()

        for i in range(0, 3):
            backend.set_serialized(KEY_HASH, CLOUD_VALUE__BYTES)
            eq_(backend.get_serialized(KEY_HASH), CLOUD_VALUE__BYTES)

            ttl = backend.reader_client.ttl(KEY_HASH[0])
            assert ttl >= 9, "ttl should be larger"

            ttl = backend.writer_client.ttl(KEY_HASH[0])
            assert ttl >= 9, "ttl should be larger"

            time.sleep(1)

        backend.delete(KEY_HASH)
        eq_(backend.get_serialized(KEY_HASH), NO_VALUE)

    def test_expires_tracked_multi(self):
        backend = self._backend()

        # set up the mapping
        keys2encoded = dict(KEYS_2_ENCODED__PAIRS)
        keys_ = list(keys2encoded.keys())

        for i in range(0, 3):
            # upload the mapping
            backend.set_serialized_multi(keys2encoded)

            # grab the results
            results = backend.get_serialized_multi(keys_)

            # enumerate the results, match their order to the ordered array
            for idx, result in enumerate(results):
                result_key = keys_[idx]
                eq_(result, keys2encoded[result_key])

                if isinstance(result_key, tuple):
                    key = result_key[0]
                    ttl = backend.reader_client.ttl(key)
                    assert ttl >= 9, "ttl should be larger"

                    ttl = backend.writer_client.ttl(key)
                    assert ttl >= 9, "ttl should be larger"

            time.sleep(1)

        backend.delete_multi(keys_)


class RedisAdvancedHstore_HstoreTest_Expires_Hash_None(
    RedisAdvancedHstore_HstoreTest_Expires_Hash
):
    redis_expiration_time_hash = None
    config_args: ConfigDict = {
        "arguments": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "redis_expiration_time": 10,
            "redis_expiration_time_hash": redis_expiration_time_hash,
        }
    }

    def test_expires_tracked(self):
        """
        When redis_expiration_time_hash is None, we should be setting the
        expiry only if the key doesn't exist

        to test this, we're just going to loop this a few times

        the loop should reset the expiry to 3 seconds, then sleep 1s, so it will
        always be about 5
        """
        backend = self._backend()

        for i in range(0, 5):
            backend.set_serialized(KEY_HASH, CLOUD_VALUE__BYTES)
            eq_(backend.get_serialized(KEY_HASH), CLOUD_VALUE__BYTES)
            time.sleep(1)

        ttl = backend.reader_client.ttl(KEY_HASH[0])
        assert ttl <= 6, "ttl should be <= 6"
        assert ttl >= 4, "ttl should be <= 4"

        ttl = backend.writer_client.ttl(KEY_HASH[0])
        assert ttl <= 6, "ttl should be <= 6"
        assert ttl >= 4, "ttl should be <= 4"

        backend.delete(KEY_HASH)
        eq_(backend.get_serialized(KEY_HASH), NO_VALUE)

    def test_expires_tracked_multi(self):
        backend = self._backend()

        # set up the mapping
        keys2encoded = dict(KEYS_2_ENCODED__PAIRS)
        keys_ = list(keys2encoded.keys())

        # loop over this a bit setting and sleeping
        for i in range(0, 5):
            # upload the mapping
            backend.set_serialized_multi(keys2encoded)

            # grab the results
            results = backend.get_serialized_multi(keys_)

            # enumerate the results, match their order to the ordered array
            for idx, result in enumerate(results):
                result_key = keys_[idx]
                eq_(result, keys2encoded[result_key])

            time.sleep(1)

        # check the ttls.  we should not have set them on the subsequent loops
        for key in keys_:
            if isinstance(key, tuple):
                key = key[0]
                ttl = backend.reader_client.ttl(key)
                assert ttl <= 6, "ttl should be <= 6"
                assert ttl >= 4, "ttl should be <= 4"

                ttl = backend.writer_client.ttl(key)
                assert ttl <= 6, "ttl should be <= 6"
                assert ttl >= 4, "ttl should be <= 4"

        backend.delete_multi(keys_)


class RedisAdvancedHstore_HstoreTest_Expires_Hash_False(
    RedisAdvancedHstore_HstoreTest_Expires_Hash
):
    redis_expiration_time_hash = False
    config_args: ConfigDict = {
        "arguments": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "redis_expiration_time": 2,
            "redis_expiration_time_hash": False,
        }
    }

    def test_expires_tracked(self):
        """
        When redis_expiration_time_hash is False, we should be ignoring hash
        expiry so it should always be -1.
        """
        backend = self._backend()

        for i in range(0, 3):
            backend.set_serialized(KEY_HASH, CLOUD_VALUE__BYTES)
            eq_(backend.get_serialized(KEY_HASH), CLOUD_VALUE__BYTES)

            ttl = backend.reader_client.ttl(KEY_HASH[0])
            assert ttl == -1, "ttl should be -1"

            ttl = backend.writer_client.ttl(KEY_HASH[0])
            assert ttl == -1, "ttl should be -1"

        backend.delete(KEY_HASH)
        eq_(backend.get_serialized(KEY_HASH), NO_VALUE)

    def test_expires_tracked_multi(self):
        backend = self._backend()

        # set up the mapping
        keys2encoded = dict(KEYS_2_ENCODED__PAIRS)
        keys_ = list(keys2encoded.keys())

        # loop over this a bit setting and sleeping
        for i in range(0, 3):
            # upload the mapping
            backend.set_serialized_multi(keys2encoded)

            # grab the results
            results = backend.get_serialized_multi(keys_)

            # enumerate the results, match their order to the ordered array
            for idx, result in enumerate(results):
                result_key = keys_[idx]
                eq_(result, keys2encoded[result_key])

            # and make sure we did not set the ttl
            for key in keys_:
                if isinstance(key, tuple):
                    key = key[0]
                    ttl = backend.reader_client.ttl(key)
                    assert ttl == -1, "ttl should be -1"

                    ttl = backend.writer_client.ttl(key)
                    assert ttl == -1, "ttl should be -1"

            time.sleep(1)

        backend.delete_multi(keys_)


class RedisAdvancedHstore_DistributedMutex_CustomPrefixTest(
    _TestRedisConn, _GenericMutexTestSuite
):
    backend = "dogpile_backend_redis_advanced.hstore"
    config_args: ConfigDict = {
        "arguments": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "distributed_lock": True,
            "thread_local_lock": False,
            "lock_prefix": "_lk-",
        }
    }

    def test_prefix(self):
        """
        test the lock being set to the desired prefix by querying for a
        value of the prefix.  since the value is not managed as a normal key,
        the test is performed using the backend client
        """
        reg = self._region()
        key = "creator"
        value = "creator value"

        def creator():
            lock_key = self.config_args["arguments"]["lock_prefix"] + key
            locked = reg.backend.writer_client.get(lock_key)
            assert locked and locked is not NO_VALUE
            return value

        assert reg.get_or_create(key, creator) == value

        # reset the region...
        reg.delete(key)


class _RedisDistributedLockProxy:
    """base lock wrapper for testing"""

    mutex: Any
    _locked: bool = False

    def __init__(self, mutex: Any):
        self._locked = False
        self.mutex = mutex

    def acquire(self, *_args, **_kwargs):
        if self._locked:
            return False
        self._locked = True
        return self.mutex.acquire(*_args, **_kwargs)

    def release(self):
        self._locked = False
        self.mutex.release()

    def locked(self):
        return self._locked


class RedisDistributedLockProxy_Silent(_RedisDistributedLockProxy):
    """example lock wrapper
    this will silently pass if a LockError is encountered
    """

    def release(self):
        # defer imports until backend is used
        try:
            self.mutex.release()
        except redis.exceptions.LockError as e:
            # log.debug("safe lock timeout")
            pass
        except Exception as e:
            raise
        finally:
            self._locked = False


class RedisDistributedLockProxy_Fatal(_RedisDistributedLockProxy):
    """example lock wrapper
    this will re-raise LockErrors but give a hook to log or retry
    """

    def release(self):
        # defer imports until backend is used
        try:
            self.mutex.release()
        except redis.exceptions.LockError as e:
            raise
        except Exception as e:
            raise
        finally:
            self._locked = False


class RedisAdvancedHstore_RedisDistributedLockProxy_Silent_LockTest(
    _TestRedisConn, _GenericMutexTestSuite
):
    backend = "dogpile_backend_redis_advanced.hstore"
    config_args: ConfigDict = {
        "arguments": {
            "host": "127.0.0.1",
            "port": 6379,
            "db": 0,
            "distributed_lock": True,
            "thread_local_lock": False,
            "lock_class": RedisDistributedLockProxy_Silent,
            "lock_timeout": 1,
            "redis_expiration_time": 1,
        }
    }

    def test_pass_lock_timeout__single(self):
        reg = self._region()

        # ensure this works instantly.
        def creator():
            return "creator value"

        assert reg.get_or_create("creator", creator) == "creator value"

        # reset the region...
        reg.delete("creator")

        # can this work on a timeout?
        # sleep for 1 second longer than the timeout, so redis must expire
        def creator_sleep():
            time.sleep(self.config_args["arguments"]["lock_timeout"] + 1)
            return "creator_sleep value"

        assert (
            reg.get_or_create("creator_sleep", creator_sleep) == "creator_sleep value"
        )

        # no need reset, the `creator_sleep` is timed out

    def test_pass_lock_timeout__multi(self):
        reg = self._region()

        def _creator_multi(*_creator_keys):
            time.sleep(self.config_args["arguments"]["lock_timeout"] + 1)
            # rval is an ordered list
            return [int(_k[-1]) for _k in _creator_keys]

        _values_expected = [1, 2, 3]
        _keys = [str("creator_sleep_multi-%s" % i) for i in _values_expected]
        _values = reg.get_or_create_multi(_keys, _creator_multi)
        assert _values == _values_expected

        # reset the region...
        for _k in _keys:
            reg.delete(_k)


class RedisAdvancedHstore_RedisDistributedLockProxy_Fatal_LockTest(
    _TestRedisConn, _GenericMutexTestSuite
):
    backend = "dogpile_backend_redis_advanced.hstore"
    config_args: ConfigDict = {
        "arguments": {
            "host": "127.0.0.1",
            "port": 6379,
            "db": 0,
            "distributed_lock": True,
            "thread_local_lock": False,
            "lock_class": RedisDistributedLockProxy_Fatal,
            "lock_timeout": 1,
            "redis_expiration_time": 1,
        }
    }

    def test_pass_lock_timeout__single(self):
        reg = self._region()

        # ensure this works instantly.
        def creator():
            return "creator value"

        assert reg.get_or_create("creator", creator) == "creator value"

        # can this work on a timeout?
        # sleep for 1 second longer than the timeout, so redis must expire
        def creator_sleep():
            time.sleep(self.config_args["arguments"]["lock_timeout"] + 1)
            return "creator_sleep value"

        try:
            result = reg.get_or_create("creator_sleep", creator_sleep)
            raise ValueError("expected an error!")
        except redis.exceptions.LockError as e:
            pass

    def test_pass_lock_timeout__multi(self):
        reg = self._region()

        def _creator_multi(*_creator_keys):
            time.sleep(self.config_args["arguments"]["lock_timeout"] + 1)
            # rval is an ordered list
            return [int(_k[-1]) for _k in _creator_keys]

        _values_expected = [1, 2, 3]
        _keys = [str("creator_sleep_multi-%s" % i) for i in _values_expected]
        try:
            _values = reg.get_or_create_multi(_keys, _creator_multi)
            raise ValueError("expected an error!")
        except redis.exceptions.LockError as e:
            pass
