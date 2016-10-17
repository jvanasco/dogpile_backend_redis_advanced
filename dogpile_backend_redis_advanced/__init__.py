from dogpile.cache.region import register_backend

__version__ = '0.1.4'

# name, modulepath, objname
register_backend(
    "dogpile_backend_redis_advanced", "dogpile_backend_redis_advanced.cache.backends.redis_advanced", "RedisAdvancedBackend")
register_backend(
    "dogpile_backend_redis_advanced_hstore", "dogpile_backend_redis_advanced.cache.backends.redis_advanced", "RedisAdvancedHstoreBackend")
