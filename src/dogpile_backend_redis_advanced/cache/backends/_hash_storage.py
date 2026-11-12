"""Shared hash write semantics for the standalone Redis and Valkey backends."""

from __future__ import annotations

from collections import defaultdict
from typing import cast
from typing import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis import StrictRedis
    from redis.client import Pipeline as RedisPipeline
    from redis.typing import EncodableT
    from valkey import StrictValkey
    from valkey.client import Pipeline as ValkeyPipeline


def write_hash_batch(
    client: StrictRedis | StrictValkey,
    mapping: Mapping[str | tuple[str, str], bytes],
    expiration: int | None,
    hash_policy: bool | None,
) -> None:
    """Write a mixed batch, keeping hash TTL decisions within the transaction."""
    if not mapping:
        return

    strings: dict[str, bytes] = {}
    hashes: dict[str, dict[EncodableT, bytes]] = defaultdict(dict)
    for key, value in mapping.items():
        if isinstance(key, tuple):
            hashes[key[0]][key[1]] = value
        else:
            strings[key] = value

    conflicts = strings.keys() & hashes.keys()
    if conflicts:
        raise ValueError(
            f"Cache keys cannot be both strings and hashes: {sorted(conflicts)}"
        )

    def queue_writes(
        pipe: RedisPipeline | ValkeyPipeline, expiring_hashes: set[str]
    ) -> None:
        for name, fields in hashes.items():
            pipe.hset(name, mapping=fields)
            if expiration and name in expiring_hashes:
                pipe.expire(name, expiration)

        if expiration:
            for key, value in strings.items():
                pipe.setex(key, expiration, value)
        elif strings:
            pipe.mset(strings)

    if hashes and expiration and expiration > 0 and hash_policy is not False:
        def write_watched(pipe: RedisPipeline | ValkeyPipeline) -> None:
            # HLEN returns zero for a missing hash and rejects keys of other types.
            # Read before MULTI so a wrong type cannot expire an unrelated value.
            sizes = {name: cast(int, pipe.hlen(name)) for name in hashes}
            expiring = {name for name, size in sizes.items() if hash_policy or not size}
            pipe.multi()
            queue_writes(pipe, expiring)

        client.transaction(write_watched, *hashes)
    else:
        with client.pipeline() as pipe:
            queue_writes(pipe, set())
            pipe.execute()
