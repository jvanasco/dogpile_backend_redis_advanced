"""
Redis Backends
------------------

Provides backends for talking to `Redis <http://redis.io>`_.

"""

# stdlib
import re
from typing import Dict
from typing import Iterable
from typing import List
from typing import Mapping
from typing import Optional
from typing import Sequence
from typing import Tuple
from typing import Type
from typing import TYPE_CHECKING
from typing import TypedDict
from typing import Union

# pypi
from dogpile.cache.api import BackendArguments
from dogpile.cache.api import KeyType
from dogpile.cache.api import NoValue
from dogpile.cache.api import SerializedReturnType
from dogpile.cache.backends.redis import _RedisLockWrapper
from dogpile.cache.backends.redis import RedisBackend

# local
from ..serializers import f_pickle_dumps
from ..serializers import f_pickle_loads
from ._hash_storage import write_hash_batch

if TYPE_CHECKING:
    import redis

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


__all__ = (
    "RedisAdvancedBackend",
    "RedisAdvancedHstoreBackend",
    "HashKeyType",
)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

HashKeyType = Tuple[str, str]
"""A hash cache key."""


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


RE_VALID_PREFIX = re.compile(r"^[\w\-\.\:]{2,10}$")


class RedisAdvancedBackendArguments(TypedDict, total=False):
    # todo: this extends forthcoming `dogpile.cache.backends.redis.RedisBackendKwargs`
    lock_class: Type[_RedisLockWrapper]


class RedisAdvancedHstoreBackendArguments(RedisAdvancedBackendArguments):
    redis_expiration_time_hash: Optional[bool]


class RedisAdvancedBackend(RedisBackend):
    """A `Redis <http://redis.io/>`_ backend, using the
    `redis-py <http://pypi.python.org/pypi/redis/>`_ backend.

    This extends the `dogpile.cache` default redis backend

    :param lock_class: class, class to wrap a lock mutex in.  A variety of
     factors can cause the distributed lock to disappear or become invalidated
     after a PUT and before a RELEASE.  By wrapping a mutex in a custom proxy
     class, developers can better track this situation and suppress these errors
     (if wanted) to allow for dogpile's caching decorators to function properly.

            class LockProxy(object):
                '''
                The proxy must accept a ``mutex`` on ``__init__``, and
                support ``acquire`` and ``release`` methods
                '''
                mutex = None

                def __init__(self, mutex):
                    self.mutex = mutex

                def acquire(self, *_args, **_kwargs):
                    '''Acquire the mutex lock'''
                    return self.mutex.acquire(*_args, **_kwargs)

                def release(self):
                    '''Release the mutex lock'''
                    try:
                        self.mutex.release()
                    except redis.exceptions.LockError as e:
                        # handle the error
                        pass
                    except Exception as e:
                        raise

     .. versionadded:: 0.1.0

    Deprecated::

    `lock_prefix`::

        Previous versions, and ``dogpile.cache``, used "_lock" as the prefix.

        This package previously used `_lok.` as the default prefix.

        The custom `lock_prefix` command was ported into `dogpile.cache==1.5.0`

        .. versionchanged:: 0.5.0
    """

    # set in RedisBackend.__init__
    lock_class: Type[_RedisLockWrapper]
    lock_template: str = "_lok.{0}"
    debug_cache_size: bool

    # set in RedisAdvancedBackend.__init__
    writer_client: "redis.StrictRedis"
    reader_client: "redis.StrictRedis"

    serializer = lambda self, x: f_pickle_dumps(x)  # noqa: E731
    deserializer = f_pickle_loads

    def __init__(
        self,
        arguments: BackendArguments,
    ):
        arguments = arguments.copy()
        super(RedisAdvancedBackend, self).__init__(arguments)
        self.lock_class = arguments.get("lock_class", _RedisLockWrapper)

    def get_mutex(self, key: KeyType) -> Optional[_RedisLockWrapper]:
        if self.distributed_lock:
            _mutex = self.writer_client.lock(
                self.lock_template.format(key),
                timeout=self.lock_timeout,
                sleep=self.lock_sleep,
                thread_local=self.thread_local_lock,
                blocking=self.lock_blocking,
                blocking_timeout=self.lock_blocking_timeout,
            )
            return self.lock_class(_mutex)
        return None

    def get_serialized_multi(
        self, keys: Iterable[KeyType]
    ) -> Sequence[SerializedReturnType]:
        """Read keys in order, including empty iterables."""
        return super().get_serialized_multi(tuple(keys))

    def set_serialized_multi(self, mapping: Mapping[KeyType, bytes]) -> None:
        """Treat an empty batch as a no-op."""
        if mapping:
            super().set_serialized_multi(mapping)

    def delete_multi(self, keys: Iterable[KeyType]) -> None:
        """Delete keys without issuing an invalid empty command."""
        keys = tuple(keys)
        if keys:
            super().delete_multi(keys)


class RedisAlreadySerializedBackend(RedisAdvancedBackend):
    """unsets the (de)serializers; pipes get/set to serialized methods"""

    # this purposefully breaks the BytesBackend contract
    serializer = None  # type: ignore[assignment]
    deserializer = None  # type: ignore[assignment]

    def get(self, key: KeyType) -> SerializedReturnType:
        return RedisBackend.get_serialized(self, key)

    def get_multi(self, keys: Iterable[KeyType]) -> Sequence[SerializedReturnType]:
        return self.get_serialized_multi(keys)

    def set(self, key: KeyType, value: bytes) -> None:  # type: ignore[override]
        # override is for purposeful break against super class
        return RedisBackend.set_serialized(self, key, value)

    def set_multi(self, mapping: Mapping[KeyType, bytes]) -> None:  # type: ignore[override]
        # override is for purposeful break against super class
        self.set_serialized_multi(mapping)


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

    A positive ``redis_expiration_time`` enables hash expiry. A TTL of zero
    leaves hashes persistent unless they already have a TTL.

    """

    def __init__(self, arguments: BackendArguments):
        arguments = arguments.copy()
        super(RedisAdvancedHstoreBackend, self).__init__(arguments)
        self.redis_expiration_time_hash = arguments.get(
            "redis_expiration_time_hash", None
        )

    def get_mutex(
        self,
        key: Union[KeyType, HashKeyType],
    ) -> Optional[_RedisLockWrapper]:
        keystr: str
        if isinstance(key, tuple):
            # key can be a tuple
            keystr = ",".join([str(i) for i in key])
        else:
            keystr = key
        return RedisAdvancedBackend.get_mutex(self, keystr)

    def get_serialized(
        self,
        key: Union[KeyType, HashKeyType],
    ) -> SerializedReturnType:
        if isinstance(key, tuple):
            # redis.py command: `hget(hashname, key)`
            value = self.reader_client.hget(key[0], key[1])
        else:
            # redis.py command: `get(name)`
            value = self.reader_client.get(key)
        if value is None:
            return NoValue.NO_VALUE
        return value

    def get_serialized_multi(
        self,
        keys: Iterable[Union[KeyType, HashKeyType]],
    ) -> Sequence[SerializedReturnType]:
        """
        * figure out which are string keys vs hashes, process 2 queues
        * for hashes, bucket into multiple requests
        * reintegrate the values in the right order
        this is sadly complex as we may have duplicate keys - so can't stash
        position in a dict.
        """
        # scoping
        _keys_std: List[KeyType] = []
        _keys_std_idx: List[int] = []
        _keys_hash: List[HashKeyType] = []
        _keys_hash_idx: List[int] = []

        # initialize this list
        values: list[bytes | None] = []

        for _idx, _k in enumerate(keys):
            values.append(None)
            if isinstance(_k, tuple):
                _keys_hash.append(_k)
                _keys_hash_idx.append(_idx)
            else:
                _keys_std.append(_k)
                _keys_std_idx.append(_idx)

        # batch the keys at once
        if _keys_std:
            # redis.py command: `mget(keys, *args)`
            _values = self.reader_client.mget(_keys_std)
            # build this back into the results in the right order
            if _values:
                _values2 = zip(_keys_std_idx, _values)
                for _idx, _v in _values2:
                    values[_idx] = _v

        # group and batch the hashed as needed
        if _keys_hash:
            _hashed: Dict[str, Dict[str, List]] = {}
            for k in _keys_hash:
                # k[0] is our bucket
                if k[0] not in _hashed:
                    _hashed[k[0]] = {"keys": [], "idx": []}
            for idx, k in enumerate(_keys_hash):
                # note that we're using the _keys_hash_idx here
                _hashed[k[0]]["keys"].append(k[1])
                _hashed[k[0]]["idx"].append(_keys_hash_idx[idx])
            for name in _hashed:
                # redis.py command: `hmget(name, keys, *args)`
                _values = self.reader_client.hmget(name, _hashed[name]["keys"])
                # build this back into the results in the right order
                if _values:
                    _values2 = zip(_hashed[name]["idx"], _values)
                    for _idx, _v in _values2:
                        values[_idx] = _v

        return [v if v is not None else NoValue.NO_VALUE for v in values]

    def set_serialized(self, key: Union[KeyType, HashKeyType], value: bytes) -> None:
        """Write a string or one hash field using the configured expiry policy."""
        if not isinstance(key, tuple):
            super().set_serialized(key, value)
        elif self.redis_expiration_time and self.redis_expiration_time_hash is not False:
            self.set_serialized_multi({key: value})
        else:
            name, field = key
            self.writer_client.hset(name, mapping={field: value})

    def set_serialized_multi(
        self, mapping: Mapping[Union[KeyType, HashKeyType], bytes]  # type: ignore[override]
    ) -> None:
        """Write a mixed batch with consistent hash expiry."""
        write_hash_batch(
            self.writer_client,
            mapping,
            self.redis_expiration_time,
            self.redis_expiration_time_hash,
        )

    def delete(
        self,
        key: Union[KeyType, HashKeyType],
    ) -> None:
        if isinstance(key, tuple):
            # redis.py command: hdel(`name, *keys)`
            self.writer_client.hdel(key[0], key[1])
        else:
            # redis.py command: delete(*names)`
            self.writer_client.delete(key)

    def delete_multi(
        self,
        keys: Iterable[Union[KeyType, HashKeyType]],
    ) -> None:
        """
        In order to handle multiple deletes, we need to inspect the keys and
        batch them into the appropriate method.  This has a negligible cost.
        """
        _keys: List = []
        _keys_hash: List = []
        for k in keys:
            if isinstance(k, tuple):
                _keys_hash.append(k)
            else:
                _keys.append(k)
        if _keys:
            # redis.py command: delete(*names)`
            self.writer_client.delete(*_keys)
        if _keys_hash:
            _hashed: Dict[str, List] = {k[0]: [] for k in _keys_hash}
            for k in _keys_hash:
                _hashed[k[0]].append(k[1])
            for name in _hashed:
                # redis.py command: `hdel(name, *keys)`
                self.writer_client.hdel(name, *_hashed[name])
