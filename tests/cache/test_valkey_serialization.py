"""Run the shared serialization and hash-storage cases against Valkey."""

from importlib import import_module

import pytest

from . import test_redis_serialization as shared
from .test_valkey_backend import _ValkeyConnection
from .test_valkey_backend import VALKEY_ARGUMENTS
from .test_valkey_backend import VALKEY_BACKEND
from .test_valkey_backend import VALKEY_PORT


if VALKEY_PORT is None:
    pytest.skip("Set DOGPILE_VALKEY_PORT to run Valkey tests", allow_module_level=True)

_LOCK_ERROR: type[Exception] = import_module("valkey.exceptions").LockError
_HSTORE_BACKEND = f"{VALKEY_BACKEND}.hstore"


def _valkey_config(
    config: shared.SerializationConfig,
    *,
    lock_class: type[shared._RedisDistributedLockProxy] | None = None,
) -> shared.SerializationConfig:
    """Translate the Redis suite's connection and expiry options for Valkey."""
    arguments = dict(config["arguments"])
    arguments.update(VALKEY_ARGUMENTS)
    for option in ("expiration_time", "expiration_time_hash"):
        redis_option = f"redis_{option}"
        if redis_option in arguments:
            arguments[f"valkey_{option}"] = arguments.pop(redis_option)
    if lock_class is not None:
        arguments["lock_class"] = lock_class
    return {"arguments": arguments}


class ValkeySerializedAlternateTest(
    _ValkeyConnection, shared.RedisAdvanced_SerializedAlternate_Test
):
    backend = VALKEY_BACKEND
    config_args = _valkey_config(shared.RedisAdvanced_SerializedAlternate_Test.config_args)


class ValkeyHstoreSerializedAlternateTest(ValkeySerializedAlternateTest):
    backend = _HSTORE_BACKEND


class ValkeyHstoreTest(_ValkeyConnection, shared.RedisAdvancedHstore_HstoreTest):
    backend = _HSTORE_BACKEND
    config_args = _valkey_config(shared.RedisAdvancedHstore_HstoreTest.config_args)


class ValkeyHstoreExpiresHashTest(
    _ValkeyConnection, shared.RedisAdvancedHstore_HstoreTest_Expires_Hash
):
    backend = _HSTORE_BACKEND
    config_args = _valkey_config(shared.RedisAdvancedHstore_HstoreTest_Expires_Hash.config_args)


class ValkeyHstoreExpiresHashTrueTest(
    _ValkeyConnection, shared.RedisAdvancedHstore_HstoreTest_Expires_Hash_True
):
    backend = _HSTORE_BACKEND
    config_args = _valkey_config(
        shared.RedisAdvancedHstore_HstoreTest_Expires_Hash_True.config_args
    )


class ValkeyHstoreExpiresHashNoneTest(
    _ValkeyConnection, shared.RedisAdvancedHstore_HstoreTest_Expires_Hash_None
):
    backend = _HSTORE_BACKEND
    config_args = _valkey_config(
        shared.RedisAdvancedHstore_HstoreTest_Expires_Hash_None.config_args
    )


class ValkeyHstoreExpiresHashFalseTest(
    _ValkeyConnection, shared.RedisAdvancedHstore_HstoreTest_Expires_Hash_False
):
    backend = _HSTORE_BACKEND
    config_args = _valkey_config(
        shared.RedisAdvancedHstore_HstoreTest_Expires_Hash_False.config_args
    )


class ValkeyHstoreCustomPrefixTest(
    _ValkeyConnection, shared.RedisAdvancedHstore_DistributedMutex_CustomPrefixTest
):
    backend = _HSTORE_BACKEND
    config_args = _valkey_config(
        shared.RedisAdvancedHstore_DistributedMutex_CustomPrefixTest.config_args
    )


class _ValkeySilentLock(shared.RedisDistributedLockProxy_Silent):
    lock_error = _LOCK_ERROR


class _ValkeyFatalLock(shared.RedisDistributedLockProxy_Fatal):
    lock_error = _LOCK_ERROR


class ValkeyHstoreSilentLockTest(
    _ValkeyConnection, shared.RedisAdvancedHstore_RedisDistributedLockProxy_Silent_LockTest
):
    backend = _HSTORE_BACKEND
    config_args = _valkey_config(
        shared.RedisAdvancedHstore_RedisDistributedLockProxy_Silent_LockTest.config_args,
        lock_class=_ValkeySilentLock,
    )


class ValkeyHstoreFatalLockTest(
    _ValkeyConnection, shared.RedisAdvancedHstore_RedisDistributedLockProxy_Fatal_LockTest
):
    backend = _HSTORE_BACKEND
    lock_error = _LOCK_ERROR
    config_args = _valkey_config(
        shared.RedisAdvancedHstore_RedisDistributedLockProxy_Fatal_LockTest.config_args,
        lock_class=_ValkeyFatalLock,
    )
