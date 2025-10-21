from dogpile.cache.region import register_backend

__version__ = "0.5.0"

# name, modulepath, objname
register_backend(
    "dogpile_backend_redis_advanced",
    "dogpile_backend_redis_advanced.cache.backends.redis_advanced",
    "RedisAdvancedBackend",
)
register_backend(
    "dogpile_backend_redis_advanced.already_serialized",
    "dogpile_backend_redis_advanced.cache.backends.redis_advanced",
    "RedisAlreadySerializedBackend",
)
register_backend(
    "dogpile_backend_redis_advanced.hstore",
    "dogpile_backend_redis_advanced.cache.backends.redis_advanced",
    "RedisAdvancedHstoreBackend",
)
