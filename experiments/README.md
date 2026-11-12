# Experiments

## Reproduce the Redis and Valkey benchmark

Install the package with its test and Valkey extras in the project environment.

```sh
python -m pip install -e '.[testing,valkey]'
```

Use disposable Redis and Valkey instances on separate loopback ports, with
persistence disabled. For example, start these in separate terminals.

```sh
redis-server --bind 127.0.0.1 --port 16379 --save "" --appendonly no
valkey-server --bind 127.0.0.1 --port 16380 --save "" --appendonly no
```

Run a smoke check from the repository root.

```sh
python experiments/benchmark.py --redis-port 16379 --valkey-port 16380 \
  --groups 2 --fields 4 --batch-size 4 --repeats 1
```

Generate the [published results](../docs/benchmark-results.md) with the default
workload.

```sh
python experiments/benchmark.py --redis-port 16379 --valkey-port 16380 \
  > docs/benchmark-results.md
```

The script checks each server type, uses a fresh key namespace for every pass,
verifies the returned values, and deletes only the keys it created.

## Compare serializers

The struct experiment asks whether packing date and time values into binary
fields reduces encoded size enough to justify the CPU cost of custom hooks.
The lazy experiment asks whether deferring those conversions pays off when a
caller only reads part of a record. It compares both decoders on identical
MessagePack bytes so the read pattern is the variable.

These experiments run in Python and use the MessagePack dependency from the
testing extra. They need no cache server.

```sh
python experiments/struct_tests.py
python experiments/lazy_serializer.py
```

Both accept `--iterations` and `--repeats`. For a quick check, use
`--iterations 100 --repeats 1`.

- `struct_tests.py` compares MessagePack binary extensions, the same extensions
  with locally bound functions, and pickle's highest protocol. It runs a plain
  record and a record with dates and times. The struct codecs use unsigned
  whole seconds for datetimes and timedeltas, so this workload uses naive
  post-epoch datetimes and nonnegative durations at whole-second precision.
- `lazy_serializer.py` compares eager and lazy decoding of identical MessagePack
  tagged maps, alongside the struct codec and pickle. All four use the same
  temporal record as the first script. The lazy mapping defers only top-level
  temporal conversions and caches them after first access.

Each row verifies the decoded record against the original. The tables report
encoded bytes, median process CPU time to encode or decode and access fields,
and Python bytes retained after a one-field or full read. The retained-memory
measurement uses `tracemalloc` separately from CPU timing and excludes the
encoded buffer. It describes the live Python object, rather than process RSS
or cache server memory.

For example, in one local Python 3.14 run, the temporal record used 143 bytes
with MessagePack struct extensions and 273 bytes with pickle. The struct
codec used more CPU to encode and read it. With the 218-byte tagged-map
encoding, lazy decoding used about 13 µs for one field versus 19 µs for
eager decoding. Reading all fields took about 22 µs lazy versus 19 µs
eager. Lazy decoding also retained more Python memory in both cases. These
figures illustrate how the trade-off depends on the access pattern.

See the [development notes](../docs/development-notes.md) for the original ideas.
