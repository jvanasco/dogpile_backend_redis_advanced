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

## Serializer prototypes

`lazy_serializer.py` and `struct_tests.py` are exploratory serializer
prototypes. They are separate from the backend benchmark. See the
[development notes](../docs/development-notes.md) for the original ideas.
