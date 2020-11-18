from __future__ import print_function

"""
This script demonstrates how some caching is done.

It will spin-up a Redis instance, cache to it, and then pull some sample
keys/statistics.

In the code below, hashes are stored with 100 elements; however the sample keys
will only have the first 10 fields.

Then it flushes the db, kills the instance, and repeats with another caching
strategy

The results are printed below.
"""

from dogpile.cache import make_region
import dogpile_backend_redis_advanced

import msgpack
from dogpile.cache.api import CachedValue
from dogpile.cache.region import value_version
import psutil
import redis
import json


import sys
import os
import pdb
import pprint
import subprocess
import time


_demo_process_id = psutil.Process(os.getpid())

# ==============================================================================


REDIS_HOST = "127.0.0.1"
REDIS_PORT = "6379"

REDIS_BIN = "/usr/local/Cellar/redis/3.0.7/bin/redis-server"
REDIS_CONF = "./redis-server--6379.conf"

# ==============================================================================


# we'll update these
REGIONS = {}

# ==============================================================================


class SerializerMsgpackRaw(object):
    """'this is implemented as an object simply for code organization"""

    @classmethod
    def dumps(cls, value):
        """'strip out the payload before packing"""
        if isinstance(value, CachedValue):
            value = value.payload
        value = msgpack.packb(value)
        return value

    @classmethod
    def loads(cls, value):
        """'unpack the value and stash it into a CachedValue"""
        value = msgpack.unpackb(value, use_list=False)
        return CachedValue(value, {"ct": time.time(), "v": value_version})


class SerializerMsgpackInt(object):
    """'this is implemented as an object simply for code organization"""

    @classmethod
    def dumps(cls, value):
        """'
        strip out the payload before packing,
        save the timestamp, but convert it to an int() first

        why?
        Redis has precision on seconds, not microseconds
            1471111902.170488
            1471111902
        """
        if isinstance(value, CachedValue):
            value = (value.payload, int(value.metadata["ct"]))
        value = msgpack.packb(value)
        return value

    @classmethod
    def loads(cls, value):
        value = msgpack.unpackb(value, use_list=False)
        return CachedValue(value[0], {"ct": value[1], "v": value_version})


class SerializerJson(object):
    """'this is implemented as an object simply for code organization"""

    @classmethod
    def dumps(cls, value):
        value = json.dumps(value)
        return value

    @classmethod
    def loads(cls, value):
        """'unpack the value and stash it into a CachedValue"""
        value = json.loads(value)
        return CachedValue(value)


class SerializerJsonRaw(object):
    """'this is implemented as an object simply for code organization"""

    @classmethod
    def dumps(cls, value):
        """'strip out the payload before packing"""
        if isinstance(value, CachedValue):
            value = value.payload
        value = json.dumps(value)
        return value

    @classmethod
    def loads(cls, value):
        """'unpack the value and stash it into a CachedValue"""
        value = json.loads(value)
        return CachedValue(value, {"ct": time.time(), "v": value_version})


class SerializerJsonInt(object):
    """'this is implemented as an object simply for code organization"""

    @classmethod
    def dumps(cls, value):
        """'
        see SerializerMsgpackInt
        """
        if isinstance(value, CachedValue):
            value = (value.payload, int(value.metadata["ct"]))
        value = json.dumps(value)
        return value

    @classmethod
    def loads(cls, value):
        value = json.loads(value)
        return CachedValue(value[0], {"ct": value[1], "v": value_version})


def msgpack_loads(value):
    value = msgpack.unpackb(value, use_list=False)
    if isinstance(value, tuple):
        return CachedValue(*value)
    return value


# ==============================================================================


def initialize_dogpile():

    global REGIONS

    REGIONS["region_redis"] = make_region().configure(
        "dogpile.cache.redis",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "redis_expiration_time": 3600,
        },
    )

    REGIONS["region_redis_local"] = make_region().configure(
        "dogpile.cache.redis",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "redis_expiration_time": None,
        },
    )

    REGIONS["region_msgpack"] = make_region().configure(
        "dogpile_backend_redis_advanced",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "loads": msgpack_loads,
            "dumps": msgpack.packb,
            "redis_expiration_time": 3600,
        },
    )

    REGIONS["region_msgpack_local"] = make_region().configure(
        "dogpile_backend_redis_advanced",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "loads": msgpack_loads,
            "dumps": msgpack.packb,
            "redis_expiration_time": None,
        },
    )

    REGIONS["region_msgpack_local_int"] = make_region().configure(
        "dogpile_backend_redis_advanced",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "loads": SerializerMsgpackInt.loads,
            "dumps": SerializerMsgpackInt.dumps,
            "redis_expiration_time": None,
        },
    )

    REGIONS["region_msgpack_raw"] = make_region().configure(
        "dogpile_backend_redis_advanced",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "loads": SerializerMsgpackRaw.loads,
            "dumps": SerializerMsgpackRaw.dumps,
            "redis_expiration_time": 3600,
        },
    )

    REGIONS["region_msgpack_raw_local"] = make_region().configure(
        "dogpile_backend_redis_advanced",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "loads": SerializerMsgpackRaw.loads,
            "dumps": SerializerMsgpackRaw.dumps,
        },
    )

    REGIONS["region_msgpack_raw_hash"] = make_region().configure(
        "dogpile_backend_redis_advanced_hstore",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "loads": SerializerMsgpackRaw.loads,
            "dumps": SerializerMsgpackRaw.dumps,
            "redis_expiration_time": 3600,
            "redis_expiration_time_hash": None,
        },
    )

    REGIONS["region_json"] = make_region().configure(
        "dogpile_backend_redis_advanced",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "loads": SerializerJson.loads,
            "dumps": SerializerJson.dumps,
            "redis_expiration_time": 3600,
        },
    )

    REGIONS["region_json_local"] = make_region().configure(
        "dogpile_backend_redis_advanced",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "loads": SerializerJson.loads,
            "dumps": SerializerJson.dumps,
            "redis_expiration_time": None,
        },
    )

    REGIONS["region_json_local_int"] = make_region().configure(
        "dogpile_backend_redis_advanced",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "loads": SerializerJsonInt.loads,
            "dumps": SerializerJsonInt.dumps,
            "redis_expiration_time": None,
        },
    )

    REGIONS["region_json_raw"] = make_region().configure(
        "dogpile_backend_redis_advanced",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "loads": SerializerJsonRaw.loads,
            "dumps": SerializerJsonRaw.dumps,
            "redis_expiration_time": 3600,
        },
    )

    REGIONS["region_json_raw_local"] = make_region().configure(
        "dogpile_backend_redis_advanced",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "loads": SerializerJsonRaw.loads,
            "dumps": SerializerJsonRaw.dumps,
            "redis_expiration_time": None,
        },
    )

    REGIONS["region_json_raw_hash"] = make_region().configure(
        "dogpile_backend_redis_advanced_hstore",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "loads": SerializerJsonRaw.loads,
            "dumps": SerializerJsonRaw.dumps,
            "redis_expiration_time": 3600,
            "redis_expiration_time_hash": None,
        },
    )


fake_prefixes = (
    "foo",
    "foobar",
    "foobarbiz",
    "foobarbizbash",
    "foobarbizbashfizzbuzz",
    "fizzbuzz",
)
fake_prefixes2 = (
    "qkknasdkk",
    "kehzipqyfnslhtqnzjsgqolf",
    "7124n9jasdgqbozjayqkdhag",
    "61jkansd89asd",
)

max_a = 1000
max_b = 100
if False:
    max_a = max_a / 100
    max_b = max_a / 10


def prime_region(region_name):
    """
    faster if we use set_multi than not:
        for i in range(0, max_a):
            region.set("%s" % i, i*10)
        for pfx in fake_prefixes:
            for i in range(0, max_b):
                region.set("%s|%s" % (pfx, i), {"one": i*399, "two": pfx,})
        for pfx in fake_prefixes2:
            for i in range(0, max_b):
                region.set("%s|%s" % (pfx, i), pfx)
    """
    region = REGIONS[region_name]
    if "_hash" in region_name:
        for i in range(0, max_a, 100):
            mapping = {}
            for j in range(0, 100):
                x = i + j
                mapping[(i, str(x))] = x * 10
            region.set_multi(mapping)
        for pfx in fake_prefixes:
            for i in range(0, max_b, 100):
                mapping = {}
                for j in range(0, 100):
                    x = i + j
                    mapping[(pfx, x)] = {"one": x * 399, "two": pfx}
                region.set_multi(mapping)
        for pfx in fake_prefixes2:
            for i in range(0, max_b):
                mapping = {}
                for j in range(0, 100):
                    x = i + j
                    mapping[(pfx, i)] = pfx
                region.set_multi(mapping)
    else:
        for i in range(0, max_a, 100):
            mapping = {}
            for j in range(0, 100):
                x = i + j
                mapping[str(x)] = x * 10
            region.set_multi(mapping)
        for pfx in fake_prefixes:
            for i in range(0, max_b, 100):
                mapping = {}
                for j in range(0, 100):
                    x = i + j
                    mapping["%s|%s" % (pfx, x)] = {"one": x * 399, "two": pfx}
                region.set_multi(mapping)
        for pfx in fake_prefixes2:
            for i in range(0, max_b):
                mapping = {}
                for j in range(0, 100):
                    x = i + j
                    mapping["%s|%s" % (pfx, i)] = pfx
                region.set_multi(mapping)


# these statistics will be copied into our payload from the active redis server's info,
info_tracked_keys = (
    "used_memory",
    "used_memory_human",
    "used_memory_rss",
    "used_memory_peak",
    "used_memory_peak_human",
    "used_memory_lua",
)

# these redis keys will be copied into our payload from the active redis server
redis_tracked_keys = [
    "1",
    "100",
    "1000",
    "%s|%s" % ("fizzbuzz", 999),
    "%s|%s" % ("qkknasdkk", 999),
    "fizzbuzz",  # will only appear in hashed store
]
redis_tracked_keys.append(max_a / 2)
redis_tracked_keys.append("%s|%s" % ("fizzbuzz", (max_b / 2)))
redis_tracked_keys.append("%s|%s" % ("qkknasdkk", (max_b / 2)))

if __name__ == "__main__":
    initialize_dogpile()

    redis_connection = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=0)

    def kill_redis():
        try:
            _info = redis_connection.info()
            pid = _info["process_id"]
            print("`redis-server` is open, must kill %s" % pid)
            redis_connection.flushdb()  # just clear it!
            _old_process = psutil.Process(pid)
            _old_process.kill()
        except redis.exceptions.ConnectionError as e:
            pass

    print("initialize test -- killing `redis-server` if open")
    kill_redis()

    regions = (
        "region_redis",
        "region_redis_local",
        "region_msgpack",
        "region_msgpack_local",
        "region_msgpack_local_int",
        "region_msgpack_raw",
        "region_msgpack_raw_local",
        "region_msgpack_raw_hash",
        "region_json",
        "region_json_local",
        "region_json_local_int",
        "region_json_raw",
        "region_json_raw_local",
        "region_json_raw_hash",
    )

    test_results = {}
    redis_server = None

    for _region_name in regions:

        test_results[_region_name] = {}
        if _region_name not in REGIONS:
            raise ValueError("invalid region")

        print("--------------------------------")
        print("testing region: %s" % _region_name)

        print("1. starting redis")
        redis_server = subprocess.Popen([REDIS_BIN, REDIS_CONF], shell=False)
        _info = None
        while _info is None:
            time.sleep(1)
            print(".")
            try:
                _info = redis_connection.info()
            except redis.exceptions.ConnectionError as e:
                pass

        print("2. priming region: %s" % _region_name)
        t_start = time.time()
        prime_region(_region_name)
        t_end = time.time()
        test_results[_region_name]["prime_time"] = t_end - t_start
        print("priming took : %s" % test_results[_region_name]["prime_time"])

        print("3. Checking info")
        _info = redis_connection.info()
        # pdb.set_trace()

        for k in info_tracked_keys:
            test_results[_region_name][k] = _info[k]

        test_results[_region_name]["samples"] = {}

        for k in redis_tracked_keys:
            try:
                test_results[_region_name]["samples"][k] = redis_connection.get(k)
            except redis.exceptions.ResponseError as e:
                mapping = redis_connection.hgetall(k)
                test_results[_region_name]["samples"][k] = {
                    _k: mapping[_k] for _k in sorted(list(mapping.keys()))[:10]
                }

        # clear this out, so it doesn't persist
        redis_connection.flushdb()

        print("4. killing `redis-server`")
        print("killing process %s" % redis_server.pid)
        _old_process = psutil.Process(redis_server.pid)
        _old_process.kill()

    print("demo cleanup.  kill `redis-server`?")
    kill_redis()

    pprint.pprint(test_results)
    open("demo_bench-results-%s.txt" % _demo_process_id, "w").write(
        pprint.pformat(test_results)
    )
