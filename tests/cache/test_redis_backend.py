from dogpile.cache.api import CachedValue, NO_VALUE
from dogpile.cache.region import _backend_loader
from ._fixtures import _GenericBackendTest, _GenericMutexTest, _GenericBackendFixture
from . import eq_, assert_raises_message
from unittest import TestCase
from mock import patch, Mock
import pytest
import os
import msgpack
import pdb
import time

REDIS_HOST = '127.0.0.1'
REDIS_PORT = int(os.getenv('DOGPILE_REDIS_PORT', '6379'))


# import to register the plugin
import dogpile_backend_redis_advanced

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

class _TestRedisConn(object):

    @classmethod
    def _check_backend_available(cls, backend):
        try:
            client = backend._create_client()
            client.set("x", "y")
            # on py3k it appears to return b"y"
            assert client.get("x").decode("ascii") == "y"
            client.delete("x")
        except:
            pytest.skip(
                "redis is not running or "
                "otherwise not functioning correctly")


# ==============================================================================


class _Compatibility_Test(_TestRedisConn, _GenericBackendTest):
    config_args = {
        "arguments": {
            'host': REDIS_HOST,
            'port': REDIS_PORT,
            'db': 0,
            "foo": "barf"
        }
    }


class RedisAdvanced_Compatibility_Test(_Compatibility_Test):
    backend = 'dogpile.cache.redis_advanced'


class RedisAdvancedHstore_Compatibility_Test(_Compatibility_Test):
    backend = 'dogpile.cache.redis_advanced_hstore'


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


class _Compatibility_DistributedMutexTest(_TestRedisConn, _GenericMutexTest):
    config_args = {
        "arguments": {
            'host': REDIS_HOST,
            'port': REDIS_PORT,
            'db': 0,
            'distributed_lock': True,
        }
    }


class RedisAdvanced_Compatibility_DistributedMutexTest(_Compatibility_DistributedMutexTest):
    backend = 'dogpile.cache.redis_advanced'


class RedisAdvancedHstore_Compatibility_DistributedMutexTest(_Compatibility_DistributedMutexTest):
    backend = 'dogpile.cache.redis_advanced_hstore'


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


@patch('redis.StrictRedis', autospec=True)
class _Compatibility_ConnectionTest(TestCase):

    @classmethod
    def setup_class(cls):
        cls.backend_cls = _backend_loader.load(cls.backend)
        try:
            cls.backend_cls({})
        except ImportError:
            pytest.skip("Backend %s not installed" % cls.backend)

    def _test_helper(self, mock_obj, expected_args, connection_args=None):
        if connection_args is None:
            connection_args = expected_args

        self.backend_cls(connection_args)
        mock_obj.assert_called_once_with(**expected_args)

    def test_connect_with_defaults(self, MockStrictRedis):
        # The defaults, used if keys are missing from the arguments dict.
        arguments = {
            'host': 'localhost',
            'password': None,
            'port': 6379,
            'db': 0,
        }
        self._test_helper(MockStrictRedis, arguments, {})

    def test_connect_with_basics(self, MockStrictRedis):
        arguments = {
            'host': '127.0.0.1',
            'password': None,
            'port': 6379,
            'db': 0,
        }
        self._test_helper(MockStrictRedis, arguments)

    def test_connect_with_password(self, MockStrictRedis):
        arguments = {
            'host': '127.0.0.1',
            'password': 'some password',
            'port': 6379,
            'db': 0,
        }
        self._test_helper(MockStrictRedis, arguments)

    def test_connect_with_socket_timeout(self, MockStrictRedis):
        arguments = {
            'host': '127.0.0.1',
            'port': 6379,
            'socket_timeout': 0.5,
            'password': None,
            'db': 0,
        }
        self._test_helper(MockStrictRedis, arguments)

    def test_connect_with_connection_pool(self, MockStrictRedis):
        pool = Mock()
        arguments = {
            'connection_pool': pool,
            'socket_timeout': 0.5
        }
        expected_args = {'connection_pool': pool}
        self._test_helper(MockStrictRedis, expected_args,
                          connection_args=arguments)

    def test_connect_with_url(self, MockStrictRedis):
        arguments = {
            'url': 'redis://redis:password@127.0.0.1:6379/0'
        }
        self._test_helper(MockStrictRedis.from_url, arguments)


class RedisAdvanced_Compatibility_ConnectionTest(_Compatibility_ConnectionTest):
    backend = 'dogpile.cache.redis_advanced'


class RedisAdvancedHstore_Compatibility_ConnectionTest(_Compatibility_ConnectionTest):
    backend = 'dogpile.cache.redis_advanced_hstore'


# ==============================================================================


def my_loads(value):
    ''''
    we need to unpack the value and stash it into a CachedValue
    we support strings in this version, because it's used in unit tests
    that require the ability to set/read raw data
    '''
    value = msgpack.unpackb(value, use_list=False)
    if isinstance(value, tuple):
        return CachedValue(*value)
    return value
    


class _SerializedAlternate_Test(_TestRedisConn, _GenericBackendTest):
    config_args = {
        "arguments": {
            'host': REDIS_HOST,
            'port': REDIS_PORT,
            'db': 0,
            "foo": "barf",
            'loads': my_loads,
            'dumps': msgpack.packb,
        }
    }


class RedisAdvanced_SerializedAlternate_Test(_SerializedAlternate_Test):
    backend = 'dogpile.cache.redis_advanced'


class RedisAdvancedHstore_SerializedAlternate_Test(_SerializedAlternate_Test):
    backend = 'dogpile.cache.redis_advanced_hstore'


# ==============================================================================

# make this simple
key_string = "some_key"
key_hash = ("some_key", "h1")
cloud_value = "some value"

keys_mixed = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
              ('a', 10), ('a', 30), ('a', 20),
              ('b', 9), ('c', 8), ('d', 7), ('e', 6), ('f', 5), ('g', 4), ('h', 3), ('i', 2), ('j', 1),
              11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
              ]

def keys_multiplier(x):
    return x * 2

mixed_generated = []
for k in keys_mixed:
    if isinstance(k, tuple):
        mixed_generated.append((k, keys_multiplier(k[1])))
    else:
        mixed_generated.append((k, keys_multiplier(k)))



class HstoreTest(_TestRedisConn, _GenericBackendFixture, TestCase):
    # tox -e py27 -- tests/cache/test_redis_backend.py::HstoreTest
    backend = 'dogpile.cache.redis_advanced_hstore'
    config_args = {
        "arguments": {
            'host': REDIS_HOST,
            'port': REDIS_PORT,
            'db': 0,
            'redis_expiration_time': 10,
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
        backend.set(key_string, cloud_value)
        eq_(backend.get(key_string), cloud_value)
        backend.delete(key_string)
        eq_(backend.get(key_string), NO_VALUE)
        
        # make sure we delete above. otherwise the test will fail by trying to
        # use a hmset on a normal key

        # hstore
        backend.set(key_hash, cloud_value)
        eq_(backend.get(key_hash), cloud_value)
        backend.delete(key_hash)
        eq_(backend.get(key_hash), NO_VALUE)

    def test_mixed_keys(self):
        """
        this tests
            * get_multi
            * set_multi
            * delete_multi
        """
        backend = self._backend()

        # set up the mapping
        mixed_mapping = dict(mixed_generated)
        
        # upload the mapping
        backend.set_multi(mixed_mapping)

        # grab the results
        results = backend.get_multi(keys_mixed)
        
        # enumerate the results, match their order to the ordered array
        for idx, result in enumerate(results):
            eq_(result, mixed_generated[idx][1])

        # delete them all
        backend.delete_multi(keys_mixed)

        # grab the results
        results = backend.get_multi(keys_mixed)
        
        # ensure they're all misses
        for _result in results:
            eq_(_result, NO_VALUE)


class HstoreTest_Expires_Hash(HstoreTest):
    redis_expiration_time_hash = None
    config_args = {
        "arguments": {
            'host': REDIS_HOST,
            'port': REDIS_PORT,
            'db': 0,
            'redis_expiration_time': 3,
            'redis_expiration_time_hash': redis_expiration_time_hash,
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
        backend.set(key_hash, cloud_value)
        eq_(backend.get(key_hash), cloud_value)

        # we don't set ttl on `redis_expiration_time_hash = False`
        if self.redis_expiration_time_hash is not False:
            ttl = backend.client.ttl(key_hash[0])
            assert ttl >= 1, "ttl should be larger"

        backend.delete(key_hash)
        eq_(backend.get(key_hash), NO_VALUE)

    def test_expires_multi(self):
        """
        this tests
            * get_multi
            * set_multi
            * delete_multi
        """
        backend = self._backend()

        # hstore
        mixed_mapping = dict(mixed_generated)
        backend.set_multi(mixed_mapping)

        # grab the results
        results = backend.get_multi(keys_mixed)
        
        # enumerate the results, match their order to the ordered array
        for idx, result in enumerate(results):
            eq_(result, mixed_generated[idx][1])
    
        # we don't set ttl on `redis_expiration_time_hash = False`
        if self.redis_expiration_time_hash is not False:
            # make sure every key has an expiry!
            for k in keys_mixed:
                if isinstance(k, tuple):
                    k = k[0]
                ttl = backend.client.ttl(k)
                assert ttl >= 0, "ttl should be larger"

        # delete them all
        backend.delete_multi(keys_mixed)


class HstoreTest_Expires_HashTrue(HstoreTest_Expires_Hash):
    redis_expiration_time_hash = True
    config_args = {
        "arguments": {
            'host': REDIS_HOST,
            'port': REDIS_PORT,
            'db': 0,
            'redis_expiration_time': 10,
            'redis_expiration_time_hash': redis_expiration_time_hash,
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
            backend.set(key_hash, cloud_value)
            eq_(backend.get(key_hash), cloud_value)

            ttl = backend.client.ttl(key_hash[0])
            assert ttl >= 9, "ttl should be larger"

            time.sleep(1)

        backend.delete(key_hash)
        eq_(backend.get(key_hash), NO_VALUE)

    def test_expires_tracked_multi(self):
        backend = self._backend()

        # set up the mapping
        mixed_mapping = dict(mixed_generated)

        for i in range(0, 3):
            # upload the mapping
            backend.set_multi(mixed_mapping)

            # grab the results
            results = backend.get_multi(keys_mixed)
        
            # enumerate the results, match their order to the ordered array
            for idx, result in enumerate(results):
                eq_(result, mixed_generated[idx][1])
                
                key = keys_mixed[idx]
                if isinstance(key, tuple):
                    key = key[0]
                    ttl = backend.client.ttl(key)
                    assert ttl >= 9, "ttl should be larger"

            time.sleep(1)

        backend.delete_multi(keys_mixed)



class HstoreTest_Expires_HashNone(HstoreTest_Expires_Hash):
    redis_expiration_time_hash = None
    config_args = {
        "arguments": {
            'host': REDIS_HOST,
            'port': REDIS_PORT,
            'db': 0,
            'redis_expiration_time': 10,
            'redis_expiration_time_hash': redis_expiration_time_hash,
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
            backend.set(key_hash, cloud_value)
            eq_(backend.get(key_hash), cloud_value)
            time.sleep(1)

        ttl = backend.client.ttl(key_hash[0])
        assert ttl <= 6, "ttl should be <= 6"
        assert ttl >= 4, "ttl should be <= 4"

        backend.delete(key_hash)
        eq_(backend.get(key_hash), NO_VALUE)


    def test_expires_tracked_multi(self):
        backend = self._backend()

        # set up the mapping
        mixed_mapping = dict(mixed_generated)

        # loop over this a bit setting and sleeping
        for i in range(0, 5):
            # upload the mapping
            backend.set_multi(mixed_mapping)

            # grab the results
            results = backend.get_multi(keys_mixed)
            # enumerate the results, match their order to the ordered array
            for idx, result in enumerate(results):
                eq_(result, mixed_generated[idx][1])
        
            time.sleep(1)

        # check the ttls.  we should not have set them on the subsequent loops
        for key in keys_mixed:   
            if isinstance(key, tuple):
                key = key[0]
                ttl = backend.client.ttl(key)
                assert ttl <= 6, "ttl should be <= 6"
                assert ttl >= 4, "ttl should be <= 4"

        backend.delete_multi(keys_mixed)


class HstoreTest_Expires_HashFalse(HstoreTest_Expires_Hash):
    redis_expiration_time_hash = False
    config_args = {
        "arguments": {
            'host': REDIS_HOST,
            'port': REDIS_PORT,
            'db': 0,
            'redis_expiration_time': 2,
            'redis_expiration_time_hash': False,
        }
    }

    def test_expires_tracked(self):
        """
        When redis_expiration_time_hash is False, we should be ignoring hash
        expiry so it should always be -1.
        """
        backend = self._backend()

        for i in range(0, 3):
            backend.set(key_hash, cloud_value)
            eq_(backend.get(key_hash), cloud_value)

            ttl = backend.client.ttl(key_hash[0])
            assert ttl == -1, "ttl should be -1"

        backend.delete(key_hash)
        eq_(backend.get(key_hash), NO_VALUE)

    def test_expires_tracked_multi(self):
        backend = self._backend()

        # set up the mapping
        mixed_mapping = dict(mixed_generated)

        # loop over this a bit setting and sleeping
        for i in range(0, 3):
            # upload the mapping
            backend.set_multi(mixed_mapping)

            # grab the results
            results = backend.get_multi(keys_mixed)
        
            # enumerate the results, match their order to the ordered array
            for idx, result in enumerate(results):
                eq_(result, mixed_generated[idx][1])

            # and make sure we did not set the ttl                
            for key in keys_mixed:   
                if isinstance(key, tuple):
                    key = key[0]
                    ttl = backend.client.ttl(key)
                    assert ttl == -1, "ttl should be -1"

            time.sleep(1)

        backend.delete_multi(keys_mixed)