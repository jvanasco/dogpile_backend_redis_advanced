![Python package](https://github.com/jvanasco/dogpile_backend_redis_advanced/workflows/Python%20package/badge.svg)

# dogpile_backend_redis_advanced

Extensions for dogpile.cache's standalone Redis and Valkey backends. They add
custom distributed lock wrappers, serialization proxies, and tuple keys for
hash storage.

## Install

```sh
pip install dogpile_backend_redis_advanced          # Redis
pip install 'dogpile_backend_redis_advanced[valkey]' # Valkey
```

Requires Python 3.10 or later and dogpile.cache 1.5.0 or later.

## Quick start

```python
from dogpile.cache import make_region

import dogpile_backend_redis_advanced  # Registers the backends.

region = make_region().configure(
    "dogpile_backend_redis_advanced",
    expiration_time=300,
    arguments={"host": "127.0.0.1", "port": 6379},
)

region.set("user:42", {"name": "Ada"})
assert region.get("user:42") == {"name": "Ada"}
```

For Valkey, use `dogpile_backend_redis_advanced.valkey` and the port of your
Valkey server.

| Use case | Redis backend | Valkey backend |
| --- | --- | --- |
| Standard storage with custom lock support | `dogpile_backend_redis_advanced` | `dogpile_backend_redis_advanced.valkey` |
| Group related entries in hashes | `dogpile_backend_redis_advanced.hstore` | `dogpile_backend_redis_advanced.valkey.hstore` |
| Supply encoded bytes through a serialization proxy | `dogpile_backend_redis_advanced.already_serialized` | `dogpile_backend_redis_advanced.valkey.already_serialized` |

See [advanced usage](docs/advanced-usage.md) for hash expiry, serialization, and
distributed locks. See [benchmark results](docs/benchmark-results.md) for the
Redis and Valkey comparison and [experiments](experiments/README.md) for
reproduction commands.

The [custom serializer experiments](experiments/README.md#compare-serializers)
compare struct-based MessagePack, eager and lazy decoding, and pickle on
the same records. They report encoded size, CPU time, and retained Python
memory.


## Testing

Run `tox` with Redis listening on port 6379 or set `DOGPILE_REDIS_PORT` for
another port. Set `DOGPILE_VALKEY_PORT` to include Valkey integration tests.
For a single Python version, run `tox -e py314`. The suites reuse fixtures from
dogpile.cache and produce per-environment HTML coverage reports.

## License

[MIT](LICENSE)
