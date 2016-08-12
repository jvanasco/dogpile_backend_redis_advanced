"""
Redis Backends
------------------

Provides backends for talking to `Redis <http://redis.io>`_.

"""
from __future__ import absolute_import
from dogpile.cache.api import CachedValue, NO_VALUE
from dogpile.cache.backends.redis import RedisBackend
from dogpile.util.compat import pickle, u

from collections import defaultdict
import pdb

import redis


__all__ = ('RedisAdvancedBackend',
           'RedisAdvancedHstoreBackend',
           )


class RedisAdvancedBackend(RedisBackend):
    """A `Redis <http://redis.io/>`_ backend, using the
    `redis-py <http://pypi.python.org/pypi/redis/>`_ backend.

    This extends the `dogpile.cache` default redis backend

    :param loads: callable that will be passed a serialized value. by
     default, this is ``pickle.loads``.

    :param dumps: callable that will be passed a serialized value. by
     default, this is ``pickle.dumps(value, pickle.HIGHEST_PROTOCOL)``.

    If you would like to use another serializer, such as msgpack, it may be
    best to use a function or lambda function for finer control:

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

        {
         'loads': my_loads,
         'dumps': msgpack.packb,
         }


    Example configuration::

        from dogpile.cache import make_region

        region = make_region().configure(
            'dogpile_backend_redis_advanced.redis_advanced',
            arguments = {
                'host': 'localhost',
                'port': 6379,
                'db': 0,
                'redis_expiration_time': 60*60*2,   # 2 hours
                'distributed_lock': True
                }
        )
    """

    def __init__(self, arguments):
        arguments = arguments.copy()
        super(RedisAdvancedBackend, self).__init__(arguments)
        self.loads = arguments.pop('loads', pickle.loads)
        self.dumps = arguments.pop('dumps', None)
        if self.dumps is None:
            self.dumps = lambda v: pickle.dumps(v,
                                                pickle.HIGHEST_PROTOCOL)

    def get(self, key):
        value = self.client.get(key)
        if value is None:
            return NO_VALUE
        return self.loads(value)

    def get_multi(self, keys):
        if not keys:
            return []
        values = self.client.mget(keys)
        return [
            self.loads(v) if v is not None else NO_VALUE
            for v in values]

    def set(self, key, value):
        if self.redis_expiration_time:
            self.client.setex(key, self.redis_expiration_time,
                              self.dumps(value))
        else:
            self.client.set(key, self.dumps(value))

    def set_multi(self, mapping):
        mapping = dict(
            (k, self.dumps(v))
            for k, v in mapping.items()
        )

        if not self.redis_expiration_time:
            self.client.mset(mapping)
        else:
            pipe = self.client.pipeline()
            for key, value in mapping.items():
                pipe.setex(key, self.redis_expiration_time, value)
            pipe.execute()


class RedisAdvancedHstoreBackend(RedisAdvancedBackend):
    """A `Redis <http://redis.io/>`_ backend, using the
    `redis-py <http://pypi.python.org/pypi/redis/>`_ backend.

    This extends the `dogpile.cache` default redis backend, and the
    `RedisAdvancedBackend` from this package as well

    Example configuration::

        from dogpile.cache import make_region

        region = make_region().configure(
            'dogpile_backend_redis_advanced.redis_advanced',
            arguments = {
                'host': 'localhost',
                'port': 6379,
                'db': 0,
                'redis_expiration_time': 60*60*2,   # 2 hours
                'redis_expiration_time_hash': True,
                'distributed_lock': True
                }
        )

    :param redis_expiration_time_hash: boolean, default `None`. Manages the
    behavior of hash expiry.  Possible values are:
    * False - ignore hash expiry.
    * None - monitor hash expiry.  set `redis_expiration_time` on new hash
    creation only.
    * True - unconditionally set `redis_expiration_time` on every hash
    key set/update.  
    
    Given `foo` is the redis key/namespace (as in `hmgetall foo` or
    `hmset foo key1 value` or `hmget foo key1`)
    
    If ``redis_expiration_time_hash`` is set to ``True`` or ``False``, dogpile
    will first ask Redis if there is a key named `foo` via `exists foo`.  If 
    no key exists, then `redis_expiration_time` will be unconditionally set. 
    If the key already exists, then `redis_expiration_time` will only be set
    if `redis_expiration_time_hash` is set to `True`.
    
    if `redis_expiration_time_hash` is set to `False`, then dogpile will not set
    expiry times on hashes.    

    """

    def __init__(self, arguments):
        arguments = arguments.copy()
        super(RedisAdvancedHstoreBackend, self).__init__(arguments)
        self.redis_expiration_time_hash = arguments.pop('redis_expiration_time_hash', None)  # noqa

    def get_mutex(self, key):
        if isinstance(key, tuple):
            # key can be a tuple
            key = ",".join(key)
        if self.distributed_lock:
            # redis.py command: `lock(name, timeout=None, sleep=0.1)`
            return self.client.lock(u('_lock{0}').format(key),
                                    self.lock_timeout, self.lock_sleep)
        else:
            return None

    def get(self, key):
        if isinstance(key, tuple):
            # redis.py command: `hget(hashname, key)`
            value = self.client.hget(key[0], key[1])
        else:
            # redis.py command: `get(name)`
            value = self.client.get(key)
        if value is None:
            return NO_VALUE
        return self.loads(value)

    def get_multi(self, keys):
        """
        * figure out which are string keys vs hashes, process 2 queues
        * for hashes, bucket into multiple requests
        * reintegrate the values in the right order
        this is sadly complex as we may have duplicate keys - so can't stash
        position in a dict.
        """
        # scoping
        _keys_str = []
        _keys_str_idx = []
        _keys_hash = []
        _keys_hash_idx = []

        # initialize this list
        values = [None] * len(keys)

        for (_idx, _k) in enumerate(keys):
            if isinstance(_k, tuple):
                _keys_hash.append(_k)
                _keys_hash_idx.append(_idx)
            else:
                _keys_str.append(_k)
                _keys_str_idx.append(_idx)

        # batch the keys at once
        if _keys_str:
            # redis.py command: `mget(keys, *args)`
            _values = self.client.mget(_keys_str)
            # build this back into the results in the right order
            _values = zip(_keys_str_idx, _values)
            for (_idx, _v) in _values:
                values[_idx] = _v

        # group and batch the hashed as needed
        if _keys_hash:
            _hashed = {}
            for k in _keys_hash:
                # k[0] is our bucket
                if k[0] not in _hashed:
                    _hashed[k[0]] = {'keys': [],
                                     'idx': [],
                                     }
            for idx, k in enumerate(_keys_hash):
                # note that we're using the _keys_hash_idx here
                _hashed[k[0]]['keys'].append(k[1])
                _hashed[k[0]]['idx'].append(_keys_hash_idx[idx])
            for name in _hashed:
                # redis.py command: `hmget(name, keys, *args)`
                _values = self.client.hmget(name, _hashed[name]['keys'])
                # build this back into the results in the right order
                _values = zip(_hashed[name]['idx'], _values)
                for (_idx, _v) in _values:
                    values[_idx] = _v

        return [
            self.loads(v) if v is not None else NO_VALUE
            for v in values]

    def set(self, key, value):
        if isinstance(key, tuple):
            _set_expiry = None
            if self.redis_expiration_time_hash is True:
                # unconditionally set
                _set_expiry = True
            elif self.redis_expiration_time_hash is None:
                # conditionally set
                # redis.py command: `exists(key)`
                _hash_exists = self.client.exists(key[0])
                if not _hash_exists:
                    _set_expiry = True
                        
            # redis.py command: `hset(name, key, value)`
            self.client.hset(key[0], key[1],
                             self.dumps(value))
            if _set_expiry:
                # redis.py command: `expire(name, time)`
                self.client.expire(key[0], self.redis_expiration_time)
        else:
            if self.redis_expiration_time:
                # redis.py command: `setex(name, time, value)`
                self.client.setex(key, self.redis_expiration_time,
                                  self.dumps(value))
            else:
                # redis.py command: `set(name, value)`
                self.client.set(key,
                                self.dumps(value))

    def set_multi(self, mapping):
        """
        we'll always use a pipeline for this class
        """
        # encode
        mapping = dict(
            (k, self.dumps(v))
            for k, v in mapping.items()
        )

        # derive key types
        _keys_str = []
        _keys_hash = []
        _hash_bucketed = None
        for _k in mapping.keys():
            if isinstance(_k, tuple):
                _keys_hash.append(_k)
            else:
                _keys_str.append(_k)

        # redis.py command: `pipeline(transaction=True, shard_hint=None)`
        pipe = self.client.pipeline()

        # whether or not we have a redis_expiration_time, we set via hmset
        if _keys_hash:
            _hash_bucketed = defaultdict(dict)
            for k in _keys_hash:
                _hash_bucketed[k[0]][k[1]] = mapping[k]
            for name in _hash_bucketed.keys():
                _set_expiry = None
                if self.redis_expiration_time_hash is True:
                    # unconditionally set
                    _set_expiry = True
                elif self.redis_expiration_time_hash is None:
                    # conditionally set
                    # redis.py command: `exists(key)`
                    _hash_exists = self.client.exists(name)
                    if not _hash_exists:
                        _set_expiry = True

                # redis.py command: `hmset(name, mapping)`
                pipe.hmset(name, _hash_bucketed[name])

                if _set_expiry:
                    # redis.py command: `expire(name, time)`
                    pipe.expire(name, self.redis_expiration_time)

        if not self.redis_expiration_time:
            # redis.py command: `mset(mapping)`
            if _keys_str:
                _mapping_str = {k: mapping[k] for k in _keys_str}
                # redis.py command: `mset(mapping)`
                pipe.mset(_mapping_str)
            # bucketed hash was set above
        else:
            if _keys_str:
                for key in _keys_str:
                    # redis.py command: `setex(name, time, value)`
                    pipe.setex(key, self.redis_expiration_time, mapping[key])
            # bucketed hash was set above

        # run the pipeline
        pipe.execute()

    def delete(self, key):
        if isinstance(key, tuple):
            # redis.py command: hdel(`name, *keys)`
            self.client.hdel(key[0], key[1])
        else:
            # redis.py command: delete(*names)`
            self.client.delete(key)

    def delete_multi(self, keys):
        """
        In order to handle multiple deletes, we need to inspect the keys and
        batch them into the appropriate method.  This has a negligible cost.
        """
        _keys = []
        _keys_hash = []
        for k in keys:
            if isinstance(k, tuple):
                _keys_hash.append(k)
            else:
                _keys.append(k)
        if _keys:
            # redis.py command: delete(*names)`
            self.client.delete(*_keys)
        if _keys_hash:
            _hashed = {k[0]: [] for k in _keys_hash}
            for k in _keys_hash:
                _hashed[k[0]].append(k[1])
            for name in _hashed:
                # redis.py command: `hdel(name, *keys)`
                self.client.hdel(name, *_hashed[name])
