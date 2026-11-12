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
from ._hash_storage import write_hash_batch


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

    def get_serialized_multi(
        self, keys: Iterable[KeyType]
    ) -> Sequence[SerializedReturnType]:
        """Read keys in order, including empty iterables."""
        return super().get_serialized_multi(tuple(keys))

    def set_serialized_multi(self, mapping: Mapping[KeyType, bytes]) -> None:
        """Treat an empty batch as a no-op."""
        if mapping:
            super().set_serialized_multi(mapping)

    def delete_multi(self, keys: Iterable[KeyType]) -> None:
        """Delete keys without issuing an invalid empty command."""
        keys = tuple(keys)
        if keys:
            super().delete_multi(keys)


class ValkeyAlreadySerializedBackend(ValkeyAdvancedBackend):
    """Accept bytes from a caller or a serialization proxy."""

    serializer = None
    deserializer = None

    def get(self, key: KeyType) -> SerializedReturnType:
        return self.get_serialized(key)

    def get_multi(self, keys: Iterable[KeyType]) -> Sequence[SerializedReturnType]:
        return self.get_serialized_multi(keys)

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
            for (index, _), hash_value in zip(fields, hash_values):
                values[index] = NO_VALUE if hash_value is None else hash_value
        return values

    def set_serialized(self, key: ValkeyKeyType, value: bytes) -> None:
        """Write a string or one hash field using the configured expiry policy."""
        if not isinstance(key, tuple):
            super().set_serialized(key, value)
        elif (
            self.valkey_expiration_time
            and self.valkey_expiration_time_hash is not False
        ):
            self.set_serialized_multi({key: value})
        else:
            name, field = key
            self.writer_client.hset(name, mapping={field: value})

    def set_serialized_multi(
        self, mapping: Mapping[ValkeyKeyType, bytes]  # type: ignore[override]
    ) -> None:
        """Write a mixed batch with consistent hash expiry."""
        write_hash_batch(
            self.writer_client,
            mapping,
            self.valkey_expiration_time,
            self.valkey_expiration_time_hash,
        )

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
