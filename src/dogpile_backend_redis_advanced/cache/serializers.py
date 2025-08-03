import pickle
from typing import Any
from typing import Callable

# ==============================================================================


def default_dumps_factory() -> Callable:
    """
    optimized for the cpython compiler. shaves a tiny bit off.
    this turns 'pickle_dumps' into a local variable to the dump function.
    original:
              0 LOAD_GLOBAL              0 (pickle)
              3 LOAD_ATTR                1 (dumps)
              6 LOAD_GLOBAL              2 (v)
              9 LOAD_GLOBAL              0 (pickle)
             12 LOAD_ATTR                3 (HIGHEST_PROTOCOL)
             15 CALL_FUNCTION            2
             18 RETURN_VALUE
    optimized:
              0 LOAD_DEREF               0 (_dumps)
              3 LOAD_FAST                0 (v)
              6 LOAD_DEREF               1 (_protocol)
              9 CALL_FUNCTION            2
             12 RETURN_VALUE
    """
    _dumps = pickle.dumps
    _protocol = pickle.HIGHEST_PROTOCOL

    def default_dumps(v: Any) -> bytes:
        return _dumps(v, _protocol)

    return default_dumps


default_dumps = default_dumps_factory()
default_loads: Callable = pickle.loads


"""

    If you would like to use another serializer, such as msgpack, it may be
    best to use a function or lambda function for finer control:

        def my_loads(value):
            ''''
            we need to unpack the value and stash it into a CachedValue
            we support strings in this version, because it's used in unit tests
            that require the ability to set/read raw data
            '''
            value = msgpack.unpackb(value, use_list=False)
            if isinstance(value, tuple):
                return CachedValue(*value)
            return value

        {
         'loads': my_loads,
         'dumps': msgpack.packb,
         }


    Example configuration::

        from dogpile.cache import make_region

        region = make_region().configure(
            'dogpile_backend_redis_advanced.redis_advanced',
            arguments = {
                'host': 'localhost',
                'port': 6379,
                'db': 0,
                'redis_expiration_time': 60*60*2,   # 2 hours
                'distributed_lock': True
                }
        )

"""
