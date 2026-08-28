"""The storage seam (SPEC-phase0 2.3).

Collectors never construct a boto3 client. They take a ``SnapshotStore`` and call
four methods on it, which is the only reason the test suite can honour
``cfb/CLAUDE.md``'s "no network calls in tests, ever" while still exercising the
write path.

Three implementations, held to one contract by ``tests/test_storage.py``:

* ``MemorySnapshotStore()`` -- tests.
* ``FileSnapshotStore(root)`` -- ``--store file://./local-snapshots`` for local work.
* ``S3SnapshotStore(bucket, region)`` -- production.

**Snapshot bytes are write-once and manifests are not.** ``put_bytes`` refuses a
key that already exists, because SPEC 2.1 makes the raw prefix append-only and the
publisher IAM policy grants no ``s3:DeleteObject`` there -- a snapshot that could
be overwritten is a snapshot that can be lost, and a Sagarin week not captured is
gone permanently. ``put_json`` deliberately allows the rewrite: SPEC 2.2, and steps
3 and 6 of SPEC 4.3, write the same ``.meta.json`` key twice on every successful
run, once after the bytes land and once after the parse succeeds. The manifest is
the one mutable object in the layout, and only in the append-a-field direction.

``list_manifests`` orders by the manifest's ``fetched_at``, not by key. The two
usually agree, but SPEC 3.3 copies ``week=unknown`` objects forward to a corrected
partition, and a re-partitioned object has a key that no longer matches when it was
fetched. ``fetched_at`` is what the freshness check of SPEC 4.6 actually means.

``list_keys`` is the plain listing beside it, and it exists for one prefix that
``list_manifests`` cannot see: ``elo/`` (SPEC-phase1 3.5) holds state documents
with no ``.meta.json`` beside them, so the only way to find the newest is to list
keys. It orders lexicographically rather than by any field, which is the honest
contract -- a key is a string and nothing here has opened the objects. That
happens to be chronological for every prefix this project writes, because
``cfb.manifest`` and ``cfb.elo`` both stamp keys with a fixed-width UTC timestamp,
but that is a property of those key builders and not a promise of this method.
"""

import json
from pathlib import Path
from typing import Protocol

from cfb.errors import SnapshotExistsError, SnapshotNotFoundError
from cfb.models import Manifest, validating

__all__ = [
    "FileSnapshotStore",
    "MemorySnapshotStore",
    "S3SnapshotStore",
    "SnapshotStore",
]

_MANIFEST_SUFFIX = ".meta.json"


class SnapshotStore(Protocol):
    """What a collector is allowed to assume about storage."""

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        """Write verbatim bytes. Raise ``SnapshotExistsError`` if ``key`` exists."""
        ...

    def put_json(self, key: str, obj: dict) -> None:
        """Write a manifest. Overwrites, by design -- see the module docstring."""
        ...

    def get_bytes(self, key: str) -> bytes:
        """Read verbatim bytes. Raise ``SnapshotNotFoundError`` if absent."""
        ...

    def list_manifests(self, prefix: str) -> list[Manifest]:
        """Every manifest under ``prefix``, newest first by ``fetched_at``."""
        ...

    def list_keys(self, prefix: str) -> list[str]:
        """Every object key under ``prefix``, lexicographically ascending."""
        ...


def _encode(obj: dict) -> bytes:
    # indent=2 so `aws s3 cp <key> -` in SPEC 11 is readable without a formatter.
    return json.dumps(obj, indent=2, sort_keys=False).encode("utf-8")


def _newest_first(manifests: list[Manifest]) -> list[Manifest]:
    # snapshot_key breaks ties so the order is total, not merely correct. Two
    # manifests can share a fetched_at when a run captures more than one resource.
    return sorted(manifests, key=lambda m: (m.fetched_at, m.snapshot_key), reverse=True)


def _exists(key: str) -> SnapshotExistsError:
    return SnapshotExistsError(
        f"{key} already exists and raw snapshots are write-once (SPEC 2.1); "
        f"a new capture gets a new timestamped key, it never replaces one"
    )


def _load(key: str, data: bytes) -> Manifest:
    """One manifest, validated, with the key in the error if it does not validate.

    These bytes were written by an earlier run, not by the code reading them, so
    nothing about this path guarantees they still match the schema the reader was
    built against. A bucket holds thousands of them; "a manifest failed" is not
    something anyone can act on.
    """
    with validating(f"manifest at {key}"):
        return Manifest.model_validate_json(data)


def _missing(key: str) -> SnapshotNotFoundError:
    return SnapshotNotFoundError(f"no object at {key}")


class MemorySnapshotStore:
    """A dict. The store the offline test suite runs against."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        if key in self._objects:
            raise _exists(key)
        self._objects[key] = data

    def put_json(self, key: str, obj: dict) -> None:
        self._objects[key] = _encode(obj)

    def get_bytes(self, key: str) -> bytes:
        try:
            return self._objects[key]
        except KeyError:
            raise _missing(key) from None

    def list_manifests(self, prefix: str) -> list[Manifest]:
        return _newest_first(
            [
                _load(key, data)
                for key, data in self._objects.items()
                if key.startswith(prefix) and key.endswith(_MANIFEST_SUFFIX)
            ]
        )

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(key for key in self._objects if key.startswith(prefix))


class FileSnapshotStore:
    """Snapshots on local disk, one file per key, directories mirroring the prefix."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def _path(self, key: str) -> Path:
        # A key is built from a season, a week and a timestamp, never from user
        # input -- but this store writes to a real filesystem, and a key that
        # escaped the root would write somewhere nothing knows to look for it.
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root.resolve()):
            raise ValueError(f"key {key!r} escapes the store root")
        return path

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        if path.exists():
            raise _exists(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def put_json(self, key: str, obj: dict) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_encode(obj))

    def get_bytes(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise _missing(key)
        return path.read_bytes()

    def list_manifests(self, prefix: str) -> list[Manifest]:
        root = self._root.resolve()
        found = [
            _load(path.resolve().relative_to(root).as_posix(), path.read_bytes())
            for path in self._root.rglob(f"*{_MANIFEST_SUFFIX}")
            if path.resolve().relative_to(root).as_posix().startswith(prefix)
        ]
        return _newest_first(found)

    def list_keys(self, prefix: str) -> list[str]:
        root = self._root.resolve()
        return sorted(
            key
            for path in self._root.rglob("*")
            if path.is_file()
            and (key := path.resolve().relative_to(root).as_posix()).startswith(prefix)
        )


class S3SnapshotStore:
    """Production. Region is passed explicitly, never inherited from ambient env.

    boto3 is imported here rather than at module scope so the offline suite can
    import this module -- and the two stores above -- without the dependency
    installed. It is an optional extra: ``uv sync --extra s3``.
    """

    def __init__(self, bucket: str, region: str) -> None:
        import boto3

        self._bucket = bucket
        self._client = boto3.client("s3", region_name=region)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        from botocore.exceptions import ClientError

        try:
            # A conditional write, not a head-then-put: two runs racing on one key
            # would both see it absent and the loser would silently clobber the
            # winner. S3 evaluates IfNoneMatch atomically.
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                IfNoneMatch="*",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("PreconditionFailed", "412"):
                raise _exists(key) from exc
            raise

    def put_json(self, key: str, obj: dict) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=_encode(obj),
            ContentType="application/json",
        )

    def get_bytes(self, key: str) -> bytes:
        from botocore.exceptions import ClientError

        try:
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                raise _missing(key) from exc
            raise

    def list_manifests(self, prefix: str) -> list[Manifest]:
        found = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for entry in page.get("Contents", ()):
                if entry["Key"].endswith(_MANIFEST_SUFFIX):
                    found.append(_load(entry["Key"], self.get_bytes(entry["Key"])))
        return _newest_first(found)

    def list_keys(self, prefix: str) -> list[str]:
        # S3 returns keys in UTF-8 binary order already; sorted() is here so the
        # three stores agree rather than because this one needs it.
        paginator = self._client.get_paginator("list_objects_v2")
        return sorted(
            entry["Key"]
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix)
            for entry in page.get("Contents", ())
        )
