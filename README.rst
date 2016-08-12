dogpile_backend_redis_advanced
==============================

This is a plugin for the dogpile cache system that offers some alternatives to
the standard Redis datastore implementation.

Two new backends are offered:

* dogpile_backend_redis_advanced
* dogpile_backend_redis_advanced_hstore

`dogpile_backend_redis_advanced` extends the `dogpile.cache.redis` backend
and allows for custom pickling overrides

`dogpile_backend_redis_advanced_hstore` extends `dogpile_backend_redis_advanced`
and allows for some specific hstore operations

There is a negligible performance hit in `dogpile_backend_redis_advanced_hstore`,
as cache keys must be inspected to determine if they are an hstore or not -- and
there are some operations involved to coordinate values.

usage:
------

myfile.py

    # importing will register the plugins
    import dogpile_backend_redis_advanced

then simply configure dogpile with `dogpile_backend_redis_advanced` or 
`dogpile_backend_redis_advanced_hstore` as the backend.


RedisAdvancedBackend
--------------------

Two new configuration options are offered to specify custom serializers via 
`loads` and `dumps`.  The default selection is to use dogpile's choice of 
`pickle`.

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


One can also abuse/misuse dogpile and defer all cache expiry to Redis using this
serializer hook.

Dogpile doesn't cache your value as-is, but wraps it in a CachedValue object
which contains an API version and a timestamp for the expiry.

This format is necessary for most cache backends, but redis offers the ability
to handle expiry in the cloud.  By using the slim msgpack format and only 
storing the payload, we can drastically cut down the bytes needed to store this
information.

This approach SHOULD NOT BE USED by 99% of users.  However, if you do aggressive
caching, this will allow you to leverage dogpile's excellent locking mechanism 
for handling read-through caching while slimming down your cache size and the
traffic on-the-wire.  

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

This backend extends RedisAdvancedBackend with drop-in support for Hash storage 
under Redis.

* if key names are tuples, they will be treated as hash operations on Redis.
* by setting `redis_expiration_time_hash` to a boolean value, you can control how expiry times work within redis

This backend has a slight, negligible, overhead:

* all key operations (get/get_multi/set/set_multi/delete) require an inspection of keys.
* get_multi requires the order of keys to be tracked, and results from multiple get/hget operations are then correlated
* set_multi requires the mapping to be analyzed and bucketed into different hmsets

redis_expiration_time_hash allows some extended management of expiry in Redis.  by default it is set to `None`

* False - ignore hash expiry. (never set a TTL in redis)
* None - set `redis_expiration_time` on new hash creation only.  this requires a check to the redis key before a set.
* True - unconditionally set `redis_expiration_time` on every hash key set/update.

Please note the following:

* Redis manages the expiry of hashes on the key, making it global for all fields in the hash
* Redis does not support setting a ttl on hashes while doing another operation.  ttl must be set via another request
* if `redis_expiration_time_hash` is set to `True`, there will be 2 calls to the redis API for every key: `hset` or `hmset` then `expires`
* if `redis_expiration_time_hash` is set to `None`, there will be 2-3 calls to the redis API for every key: `exists`, `hset` or `hmset`, and possibly `expires`


Memory Savings and Suggested Usage
--------------------------------------

Redis is an in-memory datastore that offers persistence -- optimizing storage is incredibly important because the entire set must be held in-memory.

The attached `demo.py` (results in `demo.txt`) shows some potential approaches to caching and hashing by priming a Redis datastore with some possible strategies.


| test 				       | memory bytes | memory human | relative | ttl on redis? | ttl in dogpile? | backend                               |
|---	  				   | ---	      |---	         | ---      | ---           | ---             | ---                                   |
| region_redis             | 249399504    | 237.85M      | 0%       | Y             | Y               | dogpile.cache.redis                   |
| region_msgpack   		   | 188472048    | 179.74M      | 75.57%   | Y             | Y               | dogpile_backend_redis_advanced        |
| region_redis_local       | 181501200    | 173.09M      | 72.78%   | -             | Y               | dogpile.cache.redis 			      |
| region_msgpack_raw       | 170765872    | 162.86M      | 68.47%   | Y             | -               | dogpile_backend_redis_advanced        |
| region_msgpack_local     | 128160048    | 122.22M      | 51.39%   | -             | Y               | dogpile_backend_redis_advanced        |
| region_msgpack_raw_local | 110455968    | 105.34M      | 44.29%   | -             | -               | dogpile_backend_redis_advanced        |
| region_msgpack_raw_hash  | 28518864     | 27.20M       | 11.44%   | Y             | -               | dogpile_backend_redis_advanced_hstore |

* the `_local` variants do not set a TTL on Redis
* the `_raw` variants strip out the dogpile CachedValue wrapper and only store the payload
* the `msgpack` variants use msgpack instead of pickle 

Wait WHAT? LOOK AT `region_msgpack_raw_hash` - that's a HUGE savings!

Yes.

The HSTORE has considerable savings due to 2 reasons:

* Redis internally manages a hash much more effectively than keys.
* Redis will only put an expiry on the keys (buckets), not the hash fields

It ends up being a much tighter memory usage

Note that `region_msgpack_raw_local` should not be used.  it has no expiry - it's just shown for reference.

So what should you use?

There are several tradeoffs and concepts to consider:

1. Do you want to access information outside of dogpile (in Python scripts, or even in another language)
2. Do you want the TTL to be handled by Redis or within Python?
3. What are your expiry needs?  what do your keys look like?  there may not be any savings possible.  but if you have a lot of recycled prefixes, there could be.

This is a structured test, and differences are inherent to the types of data and keys. Using the strategies from the `region_msgpack_raw_hash` on our production data has consistently dropped a 300MB Redis imprint to the 60-80MB range.

The redis configuration file is also enclosed.  the above tests are done with redis compression turned on (which is why memory size fluctuates in the full demo report).   


To Do
--------------------------------------
I've been experimenting with handling the TTL within a hash bucket (instead of using the Redis or dogpile methods).
This looks promising.  The rationale is that it is easier for Redis to get/set an extra field from the same hash, than it is to do separate calls to TTL/EXPIRES.  

in code:

	- hset('example', 'foo', 'bar')
	- expires('example', 3600)
	+ hmset('example', {'foo': 'bar',
	                    'expires': time.time() + 3600,
	                    }


Maintenance and Upstream Compatibility
--------------------------------------

Some files in /tests are entirely from dogpile as-is:

	/tests/conftest.py
	/tests/cache/__init__.py
	/tests/cache/_fixtures.py
		
They are versions from dogpile.cache 0.6.2

The core file, dogpile_backend_redis_advanced/cache/backends/redis_advanced.py inherits from dogpile/cache/backends.redis


Testing
-------

This ships with full tests.  

Much of the core package and test fixtures are from dogpile.cache and copyright from that project, which is available under the MIT license.

Tests are handled through tox

Examples:

	tox
	tox -e py27 -- tests/cache/test_redis_backend.py::RedisAdvanced_SerializedRaw_Test
	tox -e py27 -- tests/cache/test_redis_backend.py::HstoreTest
	


License
-------

This project is available under the same MIT license as dogpile.
