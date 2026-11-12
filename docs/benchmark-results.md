# Redis and Valkey benchmark

8,192 entries in 256 groups of 32, using batches of up to 256.
Each payload is a short string such as `user-000000`.

Python 3.14.6 on Darwin 22.6.0 (x86_64) with dogpile.cache 1.5.0 and MessagePack 1.2.4.
Redis client 8.1.0 and Valkey client 6.2.0.

## Redis 8.8.0

| Layout | Write (ms) | Read (ms) | Bytes per entry |
| --- | ---: | ---: | ---: |
| Upstream strings | 325.76 | 319.79 | 148.5 |
| Advanced strings | 428.62 | 340.31 | 148.5 |
| Advanced hashes | 399.82 | 391.33 | 70.9 |
| MessagePack hashes | 296.44 | 350.75 | 56.9 |
| Payload-only strings | 299.50 | 125.92 | 108.0 |

## Valkey 9.1.2

| Layout | Write (ms) | Read (ms) | Bytes per entry |
| --- | ---: | ---: | ---: |
| Upstream strings | 352.23 | 264.65 | 148.5 |
| Advanced strings | 300.88 | 290.05 | 150.0 |
| Advanced hashes | 297.53 | 339.60 | 82.5 |
| MessagePack hashes | 371.48 | 418.32 | 66.5 |
| Payload-only strings | 237.86 | 150.72 | 112.0 |

Each row reports the median of 5 measured passes after one warm-up. Times cover all region batch calls for a complete pass. Memory sums `MEMORY USAGE` for the workload keys and divides by the number of logical entries.

The workload disables server TTLs, so these timings exclude TTL updates and distributed locks. Payload-only strings omit dogpile's stored creation metadata and need a server TTL when expiry is required. The measurements describe this workload on these servers. Different key lengths, payloads, and hash encodings can change the results.

See [reproduction commands](../experiments/README.md).
