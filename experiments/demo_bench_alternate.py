from __future__ import print_function
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


from dogpile.util.compat import pickle


def default_dumps(v):
    return pickle.dumps(v, pickle.HIGHEST_PROTOCOL)


def factory_dumps_a(pickle=pickle):
    def default_dumps(v):
        return pickle.dumps(v, pickle.HIGHEST_PROTOCOL)

    return default_dumps


default_dumps_a = factory_dumps_a()


def factory_dumps_b(pickle=pickle):
    dumps = pickle.dumps

    def default_dumps(v):
        return dumps(v, pickle.HIGHEST_PROTOCOL)

    return default_dumps


default_dumps_b = factory_dumps_b()


def factory_dumps_c():
    dumps = pickle.dumps

    def default_dumps(v):
        return dumps(v, pickle.HIGHEST_PROTOCOL)

    return default_dumps


default_dumps_c = factory_dumps_c()

import dis

print(dis.dis(default_dumps))
print(dis.dis(default_dumps_a))
print(dis.dis(default_dumps_b))
print(dis.dis(default_dumps_c))


# ==============================================================================


def initialize_dogpile():
    global REGIONS

    REGIONS["pickle"] = make_region().configure(
        "dogpile_backend_redis_advanced",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "dumps": default_dumps,
        },
    )
    REGIONS["pickle_a"] = make_region().configure(
        "dogpile_backend_redis_advanced",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "dumps": default_dumps_a,
        },
    )
    REGIONS["pickle_b"] = make_region().configure(
        "dogpile_backend_redis_advanced",
        expiration_time=3600,
        arguments={
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
            "dumps": default_dumps_b,
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
                    mapping[(pfx, x)] = {
                        "one": x * 399,
                        "two": pfx,
                    }
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
                    mapping["%s|%s" % (pfx, x)] = {
                        "one": x * 399,
                        "two": pfx,
                    }
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

    test_results = {}
    redis_server = None

    for _region_name in list(REGIONS.keys()):
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

        t_start = time.time()
        for i in range(0, 1000):
            for k in redis_tracked_keys:
                try:
                    r = redis_connection.get(k)
                except redis.exceptions.ResponseError as e:
                    mapping = redis_connection.hgetall(k)
        t_end = time.time()
        test_results[_region_name]["fetch_time"] = t_end - t_start
        print("fetching took : %s" % test_results[_region_name]["fetch_time"])

        # clear this out, so it doesn't persist
        redis_connection.flushdb()

        print("FIN. killing `redis-server`")
        print("killing process %s" % redis_server.pid)
        _old_process = psutil.Process(redis_server.pid)
        _old_process.kill()

    print("demo cleanup.  kill `redis-server`?")
    kill_redis()
