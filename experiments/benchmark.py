"""Compare dogpile cache layouts on local Redis and Valkey servers."""

import argparse
from collections.abc import Iterator
from dataclasses import dataclass
from importlib.metadata import version
import platform
from statistics import median
from time import perf_counter
from typing import cast
from uuid import uuid4

from dogpile.cache import make_region
from dogpile.cache.api import KeyType
import msgpack
from redis import Redis
from valkey import Valkey

import dogpile_backend_redis_advanced  # noqa: F401
from dogpile_backend_redis_advanced.cache.serializers import (
    Serializer_PickleNoMeta_ProxyBackend,
)


@dataclass(frozen=True)
class Layout:
    name: str
    backend: str
    hashes: bool = False
    messagepack: bool = False
    no_metadata: bool = False


@dataclass(frozen=True)
class Workload:
    groups: int
    fields: int
    batch_size: int
    repeats: int

    @property
    def entries(self) -> int:
        """Return the number of logical entries in a single pass."""
        return self.groups * self.fields


@dataclass(frozen=True)
class Measurement:
    write_ms: float
    read_ms: float
    bytes_per_entry: float


def batches(values: list[str], batch_size: int) -> Iterator[list[str]]:
    """Yield slices of the keys in their original order."""
    for start in range(0, len(values), batch_size):
        yield values[start:start + batch_size]


def layouts(engine: str) -> tuple[Layout, ...]:
    """Use the same storage and serialization choices on both servers."""
    advanced = "dogpile_backend_redis_advanced"
    if engine == "valkey":
        advanced += ".valkey"
    return (
        Layout("Upstream strings", f"dogpile.cache.{engine}"),
        Layout("Advanced strings", advanced),
        Layout("Advanced hashes", f"{advanced}.hstore", hashes=True),
        Layout(
            "MessagePack hashes", f"{advanced}.hstore", hashes=True, messagepack=True
        ),
        Layout(
            "Payload-only strings", f"{advanced}.already_serialized", no_metadata=True
        ),
    )


def measure(
    client: Redis | Valkey, layout: Layout, workload: Workload
) -> Measurement:
    """Time full writes and verified reads, then measure only the keys written."""
    prefix = f"dogpile-bench:{uuid4().hex}"
    region = (
        make_region(serializer=msgpack.packb, deserializer=msgpack.unpackb)
        if layout.messagepack
        else make_region()
    )
    region.configure(
        layout.backend,
        arguments={"connection_pool": client.connection_pool},
        wrap=[Serializer_PickleNoMeta_ProxyBackend] if layout.no_metadata else (),
    )

    server_keys: list[str] = []
    region_keys: list[str | tuple[str, str]] = []
    for group in range(workload.groups):
        name = f"{prefix}:{group:06d}"
        if layout.hashes:
            server_keys.append(name)
        for field in range(workload.fields):
            field_name = f"{field:04d}"
            if layout.hashes:
                region_keys.append((name, field_name))
            else:
                key = f"{name}:{field_name}"
                server_keys.append(key)
                region_keys.append(key)

    # The advanced hash backend accepts tuple keys at this API boundary.
    keys = cast(list[KeyType], region_keys)
    payloads = {key: f"user-{index:06d}" for index, key in enumerate(keys)}
    pages = list(batches(keys, workload.batch_size))
    writes = [{key: payloads[key] for key in page} for page in pages]
    expected = [[payloads[key] for key in page] for page in pages]

    try:
        started = perf_counter()
        for batch in writes:
            region.set_multi(batch)
        write_ms = (perf_counter() - started) * 1000

        started = perf_counter()
        actual = [region.get_multi(page) for page in pages]
        read_ms = (perf_counter() - started) * 1000
        if actual != expected:
            raise RuntimeError(f"Unexpected cached values for {layout.name}")

        memory_bytes = 0
        with client.pipeline(transaction=False) as pipe:
            for page in batches(server_keys, workload.batch_size):
                for key in page:
                    pipe.execute_command("MEMORY", "USAGE", key, "SAMPLES", 0)
                for size in pipe.execute():
                    if not isinstance(size, int):
                        raise RuntimeError(
                            f"Missing memory measurement for {layout.name}"
                        )
                    memory_bytes += size
        return Measurement(write_ms, read_ms, memory_bytes / workload.entries)
    finally:
        for page in batches(server_keys, workload.batch_size):
            client.delete(*page)


def positive_int(value: str) -> int:
    """Parse a positive workload size or port."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


def main() -> None:
    """Print a Markdown report suitable for the project documentation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redis-port", type=positive_int, required=True)
    parser.add_argument("--valkey-port", type=positive_int, required=True)
    parser.add_argument("--groups", type=positive_int, default=256)
    parser.add_argument("--fields", type=positive_int, default=32)
    parser.add_argument("--batch-size", type=positive_int, default=256)
    parser.add_argument("--repeats", type=positive_int, default=5)
    args = parser.parse_args()
    if args.redis_port == args.valkey_port:
        parser.error("Redis and Valkey need different ports")

    workload = Workload(args.groups, args.fields, args.batch_size, args.repeats)
    print("# Redis and Valkey benchmark\n")
    print(
        f"{workload.entries:,} entries in {workload.groups:,} groups of "
        f"{workload.fields:,}, using batches of up to {workload.batch_size:,}."
    )
    print("Each payload is a short string such as `user-000000`.\n")
    print(
        f"Python {platform.python_version()} on {platform.system()} "
        f"{platform.release()} ({platform.machine()}) with "
        f"dogpile.cache {version('dogpile.cache')} and "
        f"MessagePack {version('msgpack')}."
    )
    print(
        f"Redis client {version('redis')} and Valkey client {version('valkey')}.\n"
    )

    for engine, port in (("redis", args.redis_port), ("valkey", args.valkey_port)):
        client_class = Redis if engine == "redis" else Valkey
        with client_class(host="127.0.0.1", port=port) as client:
            info = cast(dict[str, str], client.info("server"))
            server_version = info.get("valkey_version")
            if (engine == "valkey") != bool(server_version):
                parser.error(f"port {port} does not serve {engine}")
            server_version = server_version or info["redis_version"]
            name = "Redis" if engine == "redis" else "Valkey"
            print(f"## {name} {server_version}\n")
            print("| Layout | Write (ms) | Read (ms) | Bytes per entry |")
            print("| --- | ---: | ---: | ---: |")
            for layout in layouts(engine):
                measure(client, layout, workload)
                results = [
                    measure(client, layout, workload) for _ in range(workload.repeats)
                ]
                print(
                    f"| {layout.name} | {median(r.write_ms for r in results):.2f} | "
                    f"{median(r.read_ms for r in results):.2f} | "
                    f"{median(r.bytes_per_entry for r in results):.1f} |"
                )
            print()

    print(
        f"Each row reports the median of {workload.repeats} measured passes after "
        "one warm-up. Times cover all region batch calls for a complete pass. "
        "Memory sums `MEMORY USAGE` for the workload keys and divides "
        "by the number of logical entries."
    )
    print(
        "\nThe workload disables server TTLs, so these timings exclude TTL updates "
        "and distributed locks. Payload-only strings omit dogpile's stored creation "
        "metadata and need a server TTL when expiry is required. The measurements "
        "describe this workload on these servers. Different key lengths, payloads, "
        "and hash encodings can change the results."
    )
    print("\nSee [reproduction commands](../experiments/README.md).")


if __name__ == "__main__":
    main()
