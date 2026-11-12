# Advanced usage

The Redis and Valkey variants share the same storage options. Use
`redis_expiration_time` and `redis_expiration_time_hash` with Redis, or
`valkey_expiration_time` and `valkey_expiration_time_hash` with Valkey.

## Hash storage

Use a string for a standalone server key and a `(hash_name, field)` tuple
for an entry in a hash. This can save memory when many small entries share
a prefix. Reads preserve input order and duplicate keys. A write batch
raises `ValueError` if it uses the same server key as a standalone string
and a hash name.

```python
from dogpile.cache import make_region

import dogpile_backend_redis_advanced

region = make_region().configure(
    "dogpile_backend_redis_advanced.valkey.hstore",
    arguments={
        "host": "127.0.0.1",
        "port": 6380,
        "valkey_expiration_time": 3600,
        "valkey_expiration_time_hash": None,
    },
)
region.set_multi({
    ("user:42", "name"): "Ada",
    ("user:42", "city"): "London",
    "active-user": 42,
})
assert region.get_multi([("user:42", "city"), "active-user"]) == ["London", 42]
```

The server TTL applies to the entire hash. With a positive server TTL, the hash
policy controls when it is set.

| Policy | Behavior |
| --- | --- |
| `False` | Leave the hash TTL as it is. |
| `None` (default) | Set the TTL when creating a hash and preserve the TTL on updates. |
| `True` | Set or refresh the TTL on every hash write. |

A server TTL of zero disables TTL changes. When the backend sets a hash TTL,
it applies the write and TTL together in a transaction. Dogpile's region-level
`expiration_time` controls freshness when reading cached entries.

## Custom serialization

For a different payload encoding with standard dogpile metadata, pass
`serializer` and `deserializer` to `make_region()`. For example, use
`make_region(serializer=msgpack.packb, deserializer=msgpack.unpackb)` and
configure the resulting region with the standard or hash variant.

Use the `.already_serialized` variant with a proxy when you need to control
the bytes for both the payload and metadata. The integer-time proxy stores the
creation timestamp at whole-second precision.

```python
from dogpile.cache import make_region

import dogpile_backend_redis_advanced
from dogpile_backend_redis_advanced.cache.serializers import (
    Serializer_PickleIntTime_ProxyBackend,
)

region = make_region().configure(
    "dogpile_backend_redis_advanced.already_serialized",
    expiration_time=3600,
    arguments={"host": "127.0.0.1", "port": 6379},
    wrap=[Serializer_PickleIntTime_ProxyBackend],
)
region.set("example", "short payload")
assert region.get("example") == "short payload"
```

`Serializer_PickleNoMeta_ProxyBackend` stores only the payload and
reconstructs metadata when read. Set a positive server TTL if you use that
proxy to enforce entry expiry. `Serializer_Raw_ProxyBackend` also omits
stored metadata and supports a narrower set of payload types. Use separate
key namespaces when comparing or migrating between encodings.

## Distributed locks

Set `distributed_lock=True` to use the server's locks. The advanced backends
use `_lok.` as the default prefix. Set `lock_prefix` explicitly when workers
must coordinate with an existing lock namespace.

Pass `lock_class` to wrap the native lock. The wrapper receives the lock
object and implements `acquire(wait=True)`, `release()`, and `locked()`.
For example, this Redis wrapper allows creation to complete when the lock
lease is already gone. For Valkey, import the same exception from
`valkey.exceptions`.

```python
from redis.exceptions import LockNotOwnedError
from redis.lock import Lock


class IgnoreLostLease:
    def __init__(self, mutex: Lock) -> None:
        self.mutex = mutex

    def acquire(self, wait: bool = True) -> bool:
        return self.mutex.acquire(blocking=wait)

    def release(self) -> None:
        try:
            self.mutex.release()
        except LockNotOwnedError:
            pass

    def locked(self) -> bool:
        return self.mutex.locked()
```

Configure it with
`arguments={"distributed_lock": True, "thread_local_lock": False, "lock_class": IgnoreLostLease}`.
Without a custom wrapper, a lost lease raises the native client exception.

## Related material

- [Redis and Valkey benchmark results](benchmark-results.md)
- [Historical development notes](development-notes.md)
