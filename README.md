![Python package](https://github.com/jvanasco/dogpile_backend_redis_advanced/workflows/Python%20package/badge.svg)

This package supports Python2 and Python3

This package DOES NOT support `dogpile.cache>=1.0`. Support is planned, but there have been several major API changes that are incompatible.

dogpile_backend_redis_advanced
==============================

This is a plugin for the **dogpile.cache** system that offers some alternatives
to the standard **Redis** datastore implementation.

Two new backends are offered:

| backend | description |
| --- | --- |
| `dogpile_backend_redis_advanced` | extends the `dogpile.cache.redis` backend and allows for custom pickling overrides |
| `dogpile_backend_redis_advanced_hstore` | extends `dogpile_backend_redis_advanced` and allows for some specific hstore operations |

There is a negligible performance hit in `dogpile_backend_redis_advanced_hstore`,
as cache keys must be inspected to determine if they are an hstore or not -- and
there are some operations involved to coordinate values.

Additionally, some behavior is changed:

* The constructor now accepts a ``lock_class`` argument, which can be used to
  wrap a mutex and alter how releases are handled.  This can be necessary if you
  have a distributed lock and timeout or flush issues (via LRU or otherwise).
  A lock disappearing in Redis will raise a fatal exception under the standard
  Redis backend.
* The constructor now accepts a ``lock_prefix`` argument, which can be used to
  alter the prefix used for locks.  The standard Redis backend uses `_lock` as
  the prefix -- which can be hard to read or isolate for tests.  One might want
  to use "\_" as the lock prefix (so that `keys "\_*"` will show all locks).

Purpose:
--------

Mike Bayer's **dogpile.cache** is an excellent package for general purpose
development.

The system offers 3 key features:

1. Elegant read-through caching functionality.
2. A locking mechanism that ensures only the first request of a cache-miss will
   create the resource (turning the rest into consumers of the first-requestor's
   creation).
3. Integrated cache expiry against time and library versions.


Unfortunately, the integrated cache expiry feature comes at a cost -- objects
are wrapped into a tuple with some metadata and pickled before hitting the
datastore.

The additional metadata or pickle format may not be needed or wanted.  Look how
the size of "a" grows by the time it becomes something passed off to Redis:


| type  | example |
| ----- | ------- |
| string                        | a                                                                                                               |
| pickle(string)                | S'a'\np0\n.                                                                                                     |
| CachedValue(string)           | ('a', {'ct': 1471113698.76127, 'v': 1})                                                                         |
| pickle(CachedValue(string) )  | cdogpile.cache.api\nCachedValue\np0\n(S'a'\np1\n(dp2\nS'ct'\np3\nF1471113698.76127\nsS'v'\np4\nI1\nstp5\nRp6\n. |

By adding in hooks for custom serializers, this backend lets developers choose
better ways to cache data.  

You may want a serializer that doesn't care about the expiry of cached data, so
just uses simpler strings.:

| type  | example 1 | example 2 |
| ----- | --------- | --------- |
| string                                | a                         | mellifluous                         |
| json.dumps(string)                    | "a"                       | "mellifluous"                       |
| msgpack.packb(string)                 | \xa1a                     | \xabmellifluous                     |

Or, you may want to fool **dogpile.cache** by manipulating what the cached is. 
Instead of using a Python dict, of time and API version, you might just track
the time but only to the second. 

| type | example 1 | example 2 |
| ---- | --------- | --------- |
| AltCachedValue(string)                | ('a', 1471113698)         | ('mellifluous', 1471113698)         |
| json.dumps(AltCachedValue(string))    | '["a", 1471113698]'       | '["mellifluous", 1471113698]'       |
| msgpack.packb(AltCachedValue(string)) | '\x92\xa1a\xceW\xafi\xe2' | '\x92\xabmellifluous\xceW\xafi\xe2' |


This is how **dogpile.cache** stores "a":

	cdogpile.cache.api\nCachedValue\np0\n(S'a'\np1\n(dp2\nS'ct'\np3\nF1471113698.76127\nsS'v'\np4\nI1\nstp5\nRp6\n.

This package lets us cache a raw string and trick **dogpile.cache** into
thinking our data parcel is "timely":

	a

Or, we include a simpler version of the time, along with a different serializer.

This packet of data and time:

	["a", 1471113698]

Is then serialized to:

	\x92\xa1a\xceW\xafi\xe2
	
If you cache lots of big objects, **dogpile.cache**'s overhead is minimal -- but
if you have a cache that works for mapping short bits of text, like ids to
usernames (and vice-versa) you will see considerable savings.

Another way to make **Redis** more efficient is to use hash storage.

Let's say you have a lot of keys that look like this:

	region.set("user-15|posts", x)
	region.set("user-15|friends", y)
	region.set("user-15|profile", z)
	region.set("user-15|username", z1)

You could make **Redis** a bit more efficient by using hash storage, in which
you have 1 key with multiple fields:

	region.hset("user-15", {'posts': x,
							'friends', y,
							'profile', z,
							'username', z1,
							})

Redis tends to operate much more efficiently in this situation (more below),
but you can also save some bytes by not repeating the key prefix. Instagram's
engineering team has a great article on this
[Instagram Engineering](http://instagram-engineering.tumblr.com/post/12202313862/storing-hundreds-of-millions-of-simple-key-value).

90% of **dogpile.cache** users who choose **Redis** will never need this
package.  A decent number of other users with large datasets have been trying to
squeeze every last bit of memory and performance out of their machines -- and
this package is designed to facilitate that.


Usage:
------

myfile.py

    # importing will register the plugins
    import dogpile_backend_redis_advanced

then simply configure **dogpile.cache** with `dogpile_backend_redis_advanced` or 
`dogpile_backend_redis_advanced_hstore` as the backend.


RedisAdvancedBackend
--------------------

Two new configuration options are offered to specify custom serializers via 
`loads` and `dumps`.  The default selection is to use **dogpile.cache**'s choice
of  `pickle`.

This option was designed to support `msgpack` as the serializer:

    import msgpack
    from dogpile.cache.api import CachedValue

    def msgpack_loads(value):
        """pickle maintained the `CachedValue` wrapper of the tuple
           msgpack does not, so it must be added back in.
           """
        value = msgpack.unpackb(value, use_list=False)
        return CachedValue(*value)

    region = make_region().configure(
        arguments= {'loads': msgpack_loads,
                    'dumps': msgpack.packb,
                    }
        )


One can also abuse/misuse **dogpile.cache** and defer all cache expiry to
**Redis** using this serializer hook.

**dogpile.cache** doesn't cache your value as-is, but wraps it in a CachedValue
object which contains an API version and a timestamp for the expiry.

This format is necessary for most cache backends, but **Redis** offers the
ability to handle expiry in the cloud.  By using the slim msgpack format and
only storing the payload, you can drastically cut down the bytes needed to store
this information.

This approach SHOULD NOT BE USED by 99% of users.  However, if you do aggressive
caching, this will allow you to leverage **dogpile.cache**'s excellent locking
mechanism for handling read-through caching while slimming down your cache size
and the traffic on-the-wire.  

    import time
    from dogpile.cache.api import CachedValue
    from dogpile.cache.region import value_version
    import msgpack

    def raw_dumps(value):
        ''''pull the payload out of the CachedValue and serialize that
        '''
        value = value.payload
        value = msgpack.packb(value)
        return value

    def raw_loads(value):
        ''''unpack the value and return a CachedValue with the current time
        '''
        value = msgpack.unpackb(value, use_list=False)
        return CachedValue(
            value,
            {
                "ct": time.time(),
                "v": value_version
            })

    region = make_region().configure(
        arguments= {'loads': msgpack_loads,
                    'dumps': msgpack.packb,
                    'redis_expiration_time': 1,
                    }
        )


RedisAdvancedHstoreBackend
--------------------------

This backend extends **RedisAdvancedBackend** with drop-in support for Hash
storage under Redis.

* If key names are tuples, they will be treated as hash operations on Redis.
* By setting `redis_expiration_time_hash` to a boolean value, you can control
  how expiry times work within Redis

This backend has a slight, negligible, overhead:

* All key operations (`get`/`get_multi`/`set`/`set_multi`/`delete`) require an
  inspection of keys.
* `get_multi` requires the order of keys to be tracked, and results from
  multiple `get`/`hget` operations are then correlated.
* `set_multi` requires the mapping to be analyzed and bucketed into different
  hmsets

`redis_expiration_time_hash` allows some extended management of expiry in Redis.
By default it is set to `None`.

* `False` - ignore hash expiry. (never set a TTL in Redis)
* `None` - set `redis_expiration_time` on new hash creation only. This requires
  a check to the **Redis** key before a set.
* `True` - unconditionally set `redis_expiration_time` on every hash key
  set/update.

Please note the following:

* **Redis** manages the expiry of hashes on the key, making it global for all
  fields in the hash.
* **Redis** does not support setting a TTL on hashes while doing another
  operation.  TTL must be set via another request.
* If `redis_expiration_time_hash` is set to `True`, there will be 2 calls to
  the **Redis** API for every key: `hset` or `hmset` then `expires`.
* If `redis_expiration_time_hash` is set to `None`, there will be 2-3 calls to
  the **Redis** API for every key: `exists`, `hset` or `hmset`, and possibly
  `expires`.


Memory Savings and Suggested Usage
--------------------------------------

Redis is an in-memory datastore that offers persistence -- optimizing storage is
incredibly important because the entire set must be held in-memory.

### Example Demo

The attached `demo.py` (results in `demo.txt`) shows some potential approaches
to caching and hashing by priming a **Redis** datastore with some possible
strategies of a single dataset.

It's worth looking at `demo.txt` to see how the different serializesr encode the
data -- sample keys are pulled for each format.

| test                     | memory bytes | memory human | relative | ttl on Redis? | ttl in dogpile? | backend                                 | encoder |
| ------------------------ | ------------ | ------------ | -------- | ------------- | --------------- | --------------------------------------- | ------- |
| region_redis             | 249399504    | 237.85M      | 0%       | Y             | Y               | `dogpile.cache.redis`                   | pickle  |
| region_json              | 222924496    | 212.60M      | 89.38%   | Y             | Y               | `dogpile_backend_redis_advanced`        | json    |
| region_msgpack           | 188472048    | 179.74M      | 75.57%   | Y             | Y               | `dogpile_backend_redis_advanced`        | msgpack |
| region_redis_local       | 181501200    | 173.09M      | 72.78%   | -             | Y               | `dogpile.cache.redis`                   | pickle  |
| region_json_raw          | 171554880    | 163.61M      | 68.79%   | Y             | -               | `dogpile_backend_redis_advanced`        | json    |
| region_msgpack_raw       | 170765872    | 162.86M      | 68.47%   | Y             | -               | `dogpile_backend_redis_advanced`        | msgpack |
| region_json_local        | 162612752    | 155.08M      | 65.20%   | -             | Y               | `dogpile_backend_redis_advanced`        | json    |
| region_json_local_int    | 128648576    | 122.69M      | 57.71%   | -             | Y, `int(time)`  | `dogpile_backend_redis_advanced`        | json    |
| region_msgpack_local     | 128160048    | 122.22M      | 51.39%   | -             | Y               | `dogpile_backend_redis_advanced`        | msgpack |
| region_msgpack_local_int | 126938576    | 121.06M      | 50.89%   | -             | Y, `int(time)`  | `dogpile_backend_redis_advanced`        | msgpack |
| region_json_raw_local    | 111241280    | 106.09M      | 44.60%   | -             | -               | `dogpile_backend_redis_advanced`        | json    |
| region_msgpack_raw_local | 110455968    | 105.34M      | 44.29%   | -             | -               | `dogpile_backend_redis_advanced`        | msgpack |
| region_msgpack_raw_hash  | 28518864     | 27.20M       | 11.44%   | Y, only keys  | -               | `dogpile_backend_redis_advanced_hstore` | msgpack |
| region_json_raw_hash     | 24836160     | 23.69M       |  9.96%   | Y, only keys  | -               | `dogpile_backend_redis_advanced_hstore` | json    |

Notes:

* the `_local` variants do not set a TTL on Redis
* the `_raw` variants strip out the dogpile CachedValue wrapper and only store
  the payload
* the `_msgpack` variants use msgpack instead of pickle 
* the `_json` variants use json instead of pickle 
* the `_int` variant applies int() to the dogpile timestamp, dropping a few
  bytes per entry

Wait WHAT? LOOK AT `region_msgpack_raw_hash` and `region_json_raw_hash` - that's
a HUGE savings!

Yes.

The HSTORE has considerable savings due to 2 reasons:

* **Redis** internally manages a hash much more effectively than keys.
* **Redis** will only put an expiry on the keys (buckets), not the hash fields

HSTORE ends up being a much tighter memory usage for this example set, as we're
setting 100 fields in each key.  The savings would not be so severe if you were
setting 5-10 fields per key

Note that `region_msgpack_raw_local` and `region_json_raw_local` should not be
used unless you're running a LRU -- they have no expiry.

### Assumptions

This demo is assuming a few things that are not tested here (but there are
plenty of benchmarks on the internet showing this):

* msgpack is the fastest encoder for serializing and deserializing data.
* json outperforms cpickle on serializing; cpickle outperforms json on
  deserializing data.

Here are some benchmarks and links:

* https://gist.github.com/justinfx/3174062
* https://gist.github.com/cactus/4073643
* http://www.benfrederickson.com/dont-pickle-your-data/

#### Caveats

In the examples above, we deal with (de)serializing simple, native, datatypes:
`string`, `int`, `bool`, `list`, `dict`, `tuple`.  For these datatypes, msgpack
is both the smallest datastore and the fastest performer.

If you need to store more complex types, you will need to provide a custom
encoder/decoder and will likely suffer a performance hit on the speed of
(de)serialization.  Unfortunately, the more complex data types that require
custom encoding/decoding include standard `datetime` objects, which can be
annoying.

The file `custom_serializer.py` shows an example class for handling
(de)serialization -- `MsgpackSerializer`.  Some common `datetime` formats are
supported; they are encoded as a specially formatted dict, and decoded
correspondingly.  A few tricks are used to shave off time and make it roughly
comparable to the speed of pickle.


### Key Takeaways

* this was surprising - while the differences are negligible on small datasets,
  using **Redis** to track expiry on long data-sets is generally not a good
  idea(!). **dogpile.cache** tracks this data much more efficiently.  you can
  enable an LRU policy in **Redis** to aid in expiry.
* msgpack and json are usually fairly comparable in size [remember the
  assumption that msgpack is better for speed].
* reformatting the **dogpile.cache** metadata (replacing a `dict` an `int()` of
  the expiry) saves a lot of space under JSON when you have small payloads. the
  strings are a fraction of the size.
* msgpack is really good with nested data structures 

The following payloads for `1` are strings:

    region_json_local =        '[10, {"v": 1, "ct": 1471113698.76127}]'
    region_json_local_int =    '[10, 1471113753]'
    region_msgpack_local =     '\x92\n\x82\xa1v\x01\xa2ct\xcbA\xd5\xeb\x92\x83\xe9\x97\x9a'
    region_msgpack_local_int = '\x92\n\xceW\xafct'


### So what should you use?

There are several tradeoffs and concepts to consider:

1. Do you want to access information outside of **dogpile.cache** (in Python
   scripts, or even in another language)
2. Are you worried about the time to serialize/deserialize?  are you write-heavy
   or read-heavy?
3. Do you want the TTL to be handled by **Redis** or within Python?
4. What are your expiry needs?  what do your keys look like?  there may not be
   any savings possible.  but if you have a lot of recycled prefixes, there
   could be.
5. What do your values look like?  How many are there?

This test uses a particular dataset, and differences are inherent to the types
of data and keys. Using the strategies from the `region_msgpack_raw_hash` on
our production data has consistently dropped a 300MB **Redis** imprint to the
60-80MB range.

The **Redis** configuration file is also enclosed. The above tests are done with
**Redis** compression turned on (which is why memory size fluctuates in the full
demo reporting).   


Custom Lock Classes
-------------------

If your Redis db gets flushed the lock will disappear. This will cause the Redis
backend to raise an exception EVEN THOUGH you have succeeded in generating your
data.

By using a ``lock_class``, you can catch the exception and decide what to do --
log it?, continue on, raise an error?  It's up to you!

	import redis.exceptions

	class RedisDistributedLockProxy(object):
		"""example lock wrapper
		this will silently pass if a LockError is encountered
		"""
		mutex = None

		def __init__(self, mutex):
			self.mutex = mutex

		def acquire(self, *_args, **_kwargs):
			return self.mutex.acquire(*_args, **_kwargs)

		def release(self):
			# defer imports until backend is used
			global redis
			import redis  # noqa
			try:
				self.mutex.release()
			except redis.exceptions.LockError, e:
				# log.debug("safe lock timeout")
				pass
			except Exception as e:
				raise



To Do
--------------------------------------

I've been experimenting with handling the TTL within a hash bucket (instead of
using the **Redis** or **dogpile.cache** methods). This looks promising.  The
rationale is that it is easier for **Redis** to get/set an extra field from the
same hash, than it is to do separate calls to TTL/EXPIRES.  

in code:

	- hset('example', 'foo', 'bar')
	- expires('example', 3600)
	+ hmset('example', {'foo': 'bar',
						'expires': time.time() + 3600,
						}

I've also been experimenting with blessing the result into a subclass of `dict`
that would do the object pair decoding lazily as-needed.
That would speed up most use cases.


Maturity
--------------------------------------

This package is pre-release.  I've been using these strategies in production
via a custom fork of **dogpile.cache** for several years, but am currently
migrating it to a plugin.


Maintenance and Upstream Compatibility
--------------------------------------

Some files in /tests are entirely from **dogpile.cache** as-is:

*   /tests/conftest.py
*   /tests/cache/\__init__.py
*   /tests/cache/\_fixtures.py
        
They are versions from **dogpile.cache** 0.6.2

The core file, `/cache/backends/redis_advanced.py` inherits from
**dogpile.cache**'s `/cache/backends/redis.py`


Testing
-------

This ships with full tests.  

Much of the core package and test fixtures are from **dogpile.cache** and
copyright from that project, which is available under the MIT license.

Tests are handled through tox

Examples:

```
tox
tox -e py27 -- tests/cache/test_redis_backend.py
tox -e py27 -- tests/cache/test_redis_backend.py::RedisAdvanced_SerializedRaw_Test
tox -e py27 -- tests/cache/test_redis_backend.py::HstoreTest
``` 

Tests pass on the enclosed `redis.conf` file:

```/usr/local/Cellar/redis/3.0.7/redis-server ./redis-server--6379.conf```



License
-------

This project is available under the same MIT license as **dogpile.cache**.
