dogpile_backend_redis_advanced
==============================

This is a plugin for the dogpile cache system that implements an alternative to
the standard redis caching backing.

Two new backends are offered:

	dogpile.cache.redis_advanced
	dogpile.cache.redredis_advanced_hstore


RedisAdvancedBackend extends the dogile RedisBackend and allows for custom pickling.
RedisAdvancedHstoreBackend extends RedisAdvancedBackend and allows for some specific hstore operations

There is a negligible performance hit in RedisAdvancedHstoreBackend, as cache keys must be inspected to determine if they are an hstore or not

usage:

	# importing will register the plugins
	import dogpile_backend_redis_advanced
	
then configure dogpile with `dogpile.cache.redis_advanced` or `dogpile.cache.redis_advanced_hstore` as the backend


RedisAdvancedBackend

new hooks are to specify custom serializes via `loads` and `dumps`

* loads
* dumps


RedisAdvancedHstoreBackend

same as above

ALSO

1. if key names are tuples, they will be treated as hash operations on Redis.
2. by setting `redis_expiration_time_hash` to a boolean value, you can control how expiry times work within redis
