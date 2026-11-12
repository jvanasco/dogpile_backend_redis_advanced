"""Advanced standalone Valkey backends for dogpile.cache."""

from collections import defaultdict
from typing import cast
from typing import Iterable
from typing import Mapping
from typing import Sequence

from dogpile.cache.api import BackendArguments
from dogpile.cache.api import CacheMutex
from dogpile.cache.api import Deserializer
from dogpile.cache.api import KeyType
from dogpile.cache.api import NO_VALUE
from dogpile.cache.api import SerializedReturnType
from dogpile.cache.api import Serializer
from dogpile.cache.backends.valkey import _ValkeyLockWrapper
from dogpile.cache.backends.valkey import ValkeyBackend

from ..serializers import f_pickle_dumps
from ..serializers import f_pickle_loads


HashKeyType = tuple[str, str]
ValkeyKeyType = KeyType | HashKeyType


class ValkeyAdvancedBackend(ValkeyBackend):
    """Extend dogpile's Valkey backend with a configurable lock wrapper."""

    lock_template = "_lok.{0}"
    serializer: Serializer | None = staticmethod(f_pickle_dumps)
    deserializer: Deserializer | None = staticmethod(f_pickle_loads)

    def __init__(self, arguments: BackendArguments) -> None:
        super().__init__(arguments)
        self.lock_class: type[_ValkeyLockWrapper] = arguments.get(
            "lock_class", _ValkeyLockWrapper
        )

    def get_mutex(self, key: KeyType) -> CacheMutex | None:
        """Wrap the native lock while preserving dogpile's lock options."""
        mutex: _ValkeyLockWrapper | None = super().get_mutex(key)
        if mutex is not None and self.lock_class is not _ValkeyLockWrapper:
            mutex = self.lock_class(mutex.mutex)
        # dogpile's wrapper implements the CacheMutex interface structurally.
        return cast(CacheMutex | None, mutex)


class ValkeyAlreadySerializedBackend(ValkeyAdvancedBackend):
    """Accept bytes from a caller or a serialization proxy."""

    serializer = None
    deserializer = None

    def get(self, key: KeyType) -> SerializedReturnType:
        return self.get_serialized(key)

    def get_multi(self, keys: Iterable[KeyType]) -> Sequence[SerializedReturnType]:
        return self.get_serialized_multi(list(keys))

    def set(self, key: KeyType, value: bytes) -> None:  # type: ignore[override]
        self.set_serialized(key, value)

    def set_multi(  # type: ignore[override]
        self, mapping: Mapping[KeyType, bytes]
    ) -> None:
        self.set_serialized_multi(mapping)


class ValkeyAdvancedHstoreBackend(ValkeyAdvancedBackend):
    """Store string keys directly and (hash, field) keys in Valkey hashes.

    With a positive valkey_expiration_time, valkey_expiration_time_hash
    controls hash expiry. False leaves it alone, None sets it on creation,
    and True refreshes it on every write.
    """

    def __init__(self, arguments: BackendArguments) -> None:
        super().__init__(arguments)
        self.valkey_expiration_time_hash: bool | None = arguments.get(
            "valkey_expiration_time_hash"
        )

    def get_mutex(self, key: ValkeyKeyType) -> CacheMutex | None:
        """Use the same lock naming convention for hash keys as Redis."""
        return super().get_mutex(",".join(key) if isinstance(key, tuple) else key)

    def get_serialized(self, key: ValkeyKeyType) -> SerializedReturnType:
        if isinstance(key, tuple):
            value = cast(bytes | None, self.reader_client.hget(*key))
            return NO_VALUE if value is None else value
        return super().get_serialized(key)

    def get_serialized_multi(
        self, keys: Iterable[ValkeyKeyType]
    ) -> Sequence[SerializedReturnType]:
        """Batch reads by hash and preserve input order and duplicates."""
        strings: list[tuple[int, KeyType]] = []
        hashes: dict[str, list[tuple[int, str]]] = defaultdict(list)
        values: list[SerializedReturnType] = []
        for index, key in enumerate(keys):
            values.append(NO_VALUE)
            if isinstance(key, tuple):
                hashes[key[0]].append((index, key[1]))
            else:
                strings.append((index, key))

        if strings:
            results = super().get_serialized_multi([key for _, key in strings])
            for (index, _), value in zip(strings, results):
                values[index] = value
        for name, fields in hashes.items():
            hash_values = cast(
                list[bytes | None],
                self.reader_client.hmget(name, [field for _, field in fields]),
            )
            for (index, _), value in zip(fields, hash_values):
                values[index] = NO_VALUE if value is None else value
        return values

    def _should_expire_hash(self, name: str) -> bool:
        """Decide before writing whether to set the hash TTL."""
        if not self.valkey_expiration_time:
            return False
        policy = self.valkey_expiration_time_hash
        return policy is True or (
            policy is None and not self.writer_client.exists(name)
        )

    def set_serialized(self, key: ValkeyKeyType, value: bytes) -> None:
        if isinstance(key, tuple):
            name, field = key
            expire = self._should_expire_hash(name)
            self.writer_client.hset(name, mapping={field: value})
            if expire:
                self.writer_client.expire(name, self.valkey_expiration_time)
        else:
            super().set_serialized(key, value)

    def set_serialized_multi(
        self, mapping: Mapping[ValkeyKeyType, bytes]  # type: ignore[override]
    ) -> None:
        """Write mixed string and hash keys in one pipeline."""
        if not mapping:
            return
        strings: dict[KeyType, bytes] = {}
        hashes: dict[str, dict[str, bytes]] = defaultdict(dict)
        for key, value in mapping.items():
            if isinstance(key, tuple):
                hashes[key[0]][key[1]] = value
            else:
                strings[key] = value

        with self.writer_client.pipeline() as pipe:
            for name, fields in hashes.items():
                expire = self._should_expire_hash(name)
                pipe.hset(name, mapping=fields)
                if expire:
                    pipe.expire(name, self.valkey_expiration_time)

            if self.valkey_expiration_time:
                for key, value in strings.items():
                    pipe.setex(key, self.valkey_expiration_time, value)
            elif strings:
                pipe.mset(strings)
            pipe.execute()

    def delete(self, key: ValkeyKeyType) -> None:
        if isinstance(key, tuple):
            self.writer_client.hdel(*key)
        else:
            super().delete(key)

    def delete_multi(self, keys: Iterable[ValkeyKeyType]) -> None:
        """Batch string deletes and group field deletes by hash."""
        strings: list[KeyType] = []
        hashes: dict[str, list[str]] = defaultdict(list)
        for key in keys:
            if isinstance(key, tuple):
                hashes[key[0]].append(key[1])
            else:
                strings.append(key)
        if strings:
            super().delete_multi(strings)
        for name, fields in hashes.items():
            self.writer_client.hdel(name, *fields)
