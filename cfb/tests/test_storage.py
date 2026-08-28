"""The ``SnapshotStore`` contract (SPEC-phase0 2.3), as one suite over every store.

``MemorySnapshotStore``, ``FileSnapshotStore`` and ``S3SnapshotStore`` are three
implementations of one protocol, and the collectors are written against the
protocol rather than against any of them. A contract that only the in-memory
store is held to is not a contract -- it is a description of the in-memory store.
So every assertion below runs against all three, parametrized on the ``store``
fixture, and a store that passes here is substitutable for the others.

The S3 parametrization is skipped unless ``CFB_INTEGRATION=1`` and
``CFB_TEST_BUCKET`` names a bucket, so a bare ``uv run pytest`` stays entirely
offline, as ``cfb/CLAUDE.md`` requires. That gate is the only reason this file
can exercise the real write path at all without breaking the no-network rule.

Two points where this suite follows the spec rather than the obvious reading:

* Immutability is a property of ``put_bytes``, not of the store. Snapshot bytes
  are write-once (SPEC 2.1: nothing under ``raw/`` is ever overwritten, enforced
  by an IAM policy granting no ``s3:DeleteObject``). The manifest is the
  documented exception -- SPEC 2.2, and the step 3 / step 6 pair in SPEC 4.3,
  write the same ``.meta.json`` key twice on every successful run: once after the
  bytes land, once after the parse. A store that refused the second write would
  make the normal path impossible, so ``put_json`` must permit it.
* ``list_manifests`` returns newest first by ``fetched_at`` (SPEC 2.3), which is
  not the same as key order. Keys sort by capture timestamp; ``fetched_at`` is
  the field the ordering contract actually names, and a re-partitioned object
  (SPEC 3.3, ``week=unknown`` copied forward) has a key that no longer matches it.
"""

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cfb.errors import SnapshotExistsError, SnapshotNotFoundError
from cfb.models import Manifest
from cfb.storage import FileSnapshotStore, MemorySnapshotStore, S3SnapshotStore

FIXTURES = Path(__file__).parent / "fixtures"

# Bytes chosen to break a store that round-trips through str: CRLF that a text
# mode would translate, a cp1252 high byte that is not valid UTF-8, an embedded
# NUL, and no trailing newline. SPEC 2.1 stores snapshots verbatim -- the manifest
# sha256 is a hash of what the server sent, so any normalization makes it a lie.
ADVERSARIAL = b"rank\tname\r\n1\tOhio State\x92s\r\n\x00 no trailing newline"

_INTEGRATION = pytest.mark.skipif(
    os.environ.get("CFB_INTEGRATION") != "1" or not os.environ.get("CFB_TEST_BUCKET"),
    reason="set CFB_INTEGRATION=1 and CFB_TEST_BUCKET to run the S3 contract",
)


@pytest.fixture(scope="session")
def run_token() -> str:
    """Isolates one test run's keys from every other run's.

    The integration store cannot clean up after itself: the publisher role is
    denied ``s3:DeleteObject``, which is the point of SPEC 2.1. So keys have to be
    unique per run rather than reused, and the objects are expected to accumulate
    under a ``test/`` prefix that a lifecycle rule can expire.
    """
    return uuid.uuid4().hex[:12]


@pytest.fixture(
    params=[
        pytest.param("memory", id="memory"),
        pytest.param("file", id="file"),
        pytest.param("s3", id="s3", marks=_INTEGRATION),
    ]
)
def store(request, tmp_path):
    if request.param == "memory":
        return MemorySnapshotStore()
    if request.param == "file":
        return FileSnapshotStore(tmp_path)
    return S3SnapshotStore(
        bucket=os.environ["CFB_TEST_BUCKET"],
        region=os.environ.get("CFB_TEST_REGION", "us-east-1"),
    )


@pytest.fixture
def prefix(run_token, request) -> str:
    """A per-test prefix under ``test/``, never under ``raw/``.

    Writing this suite's objects under ``raw/`` would put unreachable garbage in
    the immutable prefix permanently -- nothing there can be deleted.
    """
    return f"test/{run_token}/{request.node.name}"


def snapshot_key(prefix: str, stamp: str = "2026-09-16T110302Z") -> str:
    """A key in the SPEC 2.1 shape, under the test prefix."""
    return f"{prefix}/sagarin/season=2026/week=04/{stamp}.txt"


def manifest_key(snapshot_key: str) -> str:
    return snapshot_key.removesuffix(".txt") + ".meta.json"


def manifest_dict(snapshot_key: str, fetched_at: datetime, **overrides) -> dict:
    """A fetch-only manifest: the SPEC 4.3 step 3 write.

    ``parse_ok`` and the counts are absent on purpose. Steps 4-7 have not run, and
    SPEC 4.3 calls that honest partial state detectable and replayable.
    """
    manifest = {
        "schema_version": 1,
        "source": "sagarin",
        "resource": "ratings",
        "source_url": "http://sagarin.com/sports/cfsend.htm",
        "http_status": 200,
        "sha256": "ba40d83651ea42b961c8042c82831724c4d2c278b187930370f75115897090a2",
        "bytes": 148793,
        "encoding": "cp1252",
        "fetched_at": fetched_at.isoformat().replace("+00:00", "Z"),
        "season": 2026,
        "week": "04",
        "week_resolution": "calendar",
        "snapshot_key": snapshot_key,
    }
    return manifest | overrides


class TestRoundTrip:
    def test_bytes_read_back_identical(self, store, prefix):
        """Verbatim means verbatim: the bytes out are the bytes in."""
        key = snapshot_key(prefix)
        store.put_bytes(key, ADVERSARIAL, "text/plain")
        assert store.get_bytes(key) == ADVERSARIAL

    def test_the_real_capture_survives(self, store, prefix):
        """The golden capture is the artifact this store exists to protect.

        148,793 bytes of CRLF-terminated cp1252 with the HTML wrapper intact. If a
        store round-trips the adversarial constant but not this, the constant was
        not adversarial enough.
        """
        original = (FIXTURES / "sagarin_2026_preseason.txt").read_bytes()
        key = snapshot_key(prefix)
        store.put_bytes(key, original, "text/plain")
        assert store.get_bytes(key) == original

    def test_empty_payload_round_trips(self, store, prefix):
        """A zero-byte snapshot is a real fetch result, not a missing object.

        It has to stay distinguishable from an absent key, which is why this is
        not the same test as the missing-key one below.
        """
        key = snapshot_key(prefix)
        store.put_bytes(key, b"", "text/plain")
        assert store.get_bytes(key) == b""

    def test_json_round_trips_through_get_bytes(self, store, prefix):
        """A manifest is an object in the store like any other."""
        snap = snapshot_key(prefix)
        key = manifest_key(snap)
        payload = manifest_dict(snap, datetime(2026, 9, 16, 11, 3, 2, tzinfo=UTC))
        store.put_json(key, payload)
        assert json.loads(store.get_bytes(key)) == payload


class TestImmutability:
    def test_rewriting_a_snapshot_key_raises(self, store, prefix):
        key = snapshot_key(prefix)
        store.put_bytes(key, ADVERSARIAL, "text/plain")
        with pytest.raises(SnapshotExistsError) as excinfo:
            store.put_bytes(key, b"different bytes entirely", "text/plain")
        assert key in str(excinfo.value)

    def test_the_original_survives_a_refused_rewrite(self, store, prefix):
        """The raise is not the guarantee. The surviving bytes are.

        A store that raises *after* clobbering the object has still lost the
        irreplaceable artifact, and a test asserting only ``pytest.raises`` passes.
        """
        key = snapshot_key(prefix)
        store.put_bytes(key, ADVERSARIAL, "text/plain")
        with pytest.raises(SnapshotExistsError):
            store.put_bytes(key, b"different bytes entirely", "text/plain")
        assert store.get_bytes(key) == ADVERSARIAL

    def test_same_bytes_rewritten_still_raises(self, store, prefix):
        """Write-once is about the key, not about whether the content differs.

        Letting an identical rewrite through makes the store's behaviour depend on
        a comparison the IAM policy behind it cannot make.
        """
        key = snapshot_key(prefix)
        store.put_bytes(key, ADVERSARIAL, "text/plain")
        with pytest.raises(SnapshotExistsError):
            store.put_bytes(key, ADVERSARIAL, "text/plain")

    def test_manifest_rewrite_is_permitted(self, store, prefix):
        """The documented exception: SPEC 2.2, and steps 3 and 6 of SPEC 4.3.

        Every successful run writes this key twice; the second write adds the
        post-parse fields. A store that refused it would make the normal path
        impossible. This is the one mutable object in the layout, and only in the
        append-a-field direction.
        """
        snap = snapshot_key(prefix)
        key = manifest_key(snap)
        fetched_at = datetime(2026, 9, 16, 11, 3, 2, tzinfo=UTC)

        store.put_json(key, manifest_dict(snap, fetched_at))
        full = manifest_dict(
            snap, fetched_at, parse_ok=True, team_count=266, page_state="in-season"
        )
        store.put_json(key, full)

        assert json.loads(store.get_bytes(key)) == full


class TestMissing:
    def test_reading_a_missing_key_raises(self, store, prefix):
        key = snapshot_key(prefix)
        with pytest.raises(SnapshotNotFoundError) as excinfo:
            store.get_bytes(key)
        assert key in str(excinfo.value)

    def test_a_written_sibling_does_not_satisfy_a_missing_key(self, store, prefix):
        """Guards a store that resolves by prefix scan and returns the near miss."""
        store.put_bytes(snapshot_key(prefix, "2026-09-16T110302Z"), ADVERSARIAL, "text/plain")
        with pytest.raises(SnapshotNotFoundError):
            store.get_bytes(snapshot_key(prefix, "2026-09-23T110302Z"))

    def test_listing_an_empty_prefix_returns_empty(self, store, prefix):
        """No manifests is an ordinary answer, not an error.

        The freshness check of SPEC 4.6 calls this on the first ever run.
        """
        assert store.list_manifests(f"{prefix}/sagarin/") == []


class TestListing:
    @staticmethod
    def write_three(store, prefix) -> list[str]:
        """Three snapshots whose ``fetched_at`` order reverses their key order.

        If key order and ``fetched_at`` order agreed, a store that sorted by key
        would pass the ordering assertion without implementing it.
        """
        stamps = ["2026-09-02T110000Z", "2026-09-09T110000Z", "2026-09-16T110000Z"]
        fetched = [
            datetime(2026, 9, 16, 11, 0, tzinfo=UTC),
            datetime(2026, 9, 9, 11, 0, tzinfo=UTC),
            datetime(2026, 9, 2, 11, 0, tzinfo=UTC),
        ]
        for stamp, when in zip(stamps, fetched, strict=True):
            snap = snapshot_key(prefix, stamp)
            store.put_bytes(snap, ADVERSARIAL, "text/plain")
            store.put_json(manifest_key(snap), manifest_dict(snap, when))
        return stamps

    def test_returns_manifests_newest_first(self, store, prefix):
        self.write_three(store, prefix)
        found = store.list_manifests(f"{prefix}/sagarin/")
        stamps = [m.fetched_at for m in found]
        assert stamps == sorted(stamps, reverse=True)
        assert stamps[0] == datetime(2026, 9, 16, 11, 0, tzinfo=UTC)

    def test_ordering_is_by_fetched_at_not_by_key(self, store, prefix):
        """The distinction the fixture above was built to expose."""
        self.write_three(store, prefix)
        found = store.list_manifests(f"{prefix}/sagarin/")
        assert [m.snapshot_key for m in found] == [
            snapshot_key(prefix, "2026-09-02T110000Z"),
            snapshot_key(prefix, "2026-09-09T110000Z"),
            snapshot_key(prefix, "2026-09-16T110000Z"),
        ]

    def test_returns_manifests_not_snapshots(self, store, prefix):
        """The prefix holds both ``.txt`` and ``.meta.json``; only the latter parse."""
        stamps = self.write_three(store, prefix)
        assert len(store.list_manifests(f"{prefix}/sagarin/")) == len(stamps)

    def test_the_prefix_is_respected(self, store, prefix):
        """A caller asking for week 04 must not be handed week 05.

        The freshness check compares against the previous snapshot of the same
        source; leaking a neighbouring prefix compares the wrong pair.
        """
        self.write_three(store, prefix)
        other = snapshot_key(prefix, "2026-09-23T110000Z").replace("week=04", "week=05")
        store.put_bytes(other, ADVERSARIAL, "text/plain")
        store.put_json(
            manifest_key(other),
            manifest_dict(other, datetime(2026, 9, 23, tzinfo=UTC), week="05"),
        )

        found = store.list_manifests(f"{prefix}/sagarin/season=2026/week=04/")
        assert all(m.snapshot_key != other for m in found)
        assert len(found) == 3

    def test_listing_keys_on_an_empty_prefix_returns_empty(self, store, prefix):
        """The `elo/` prefix before the first scored week (SPEC-phase1 3.5)."""
        assert store.list_keys(f"{prefix}/elo/") == []

    def test_list_keys_returns_every_object_not_only_manifests(self, store, prefix):
        """The distinction that made this method necessary.

        `elo/` state documents (SPEC-phase1 3.5) have no `.meta.json` beside them,
        so `list_manifests` cannot see them at all and a replay would have nothing
        to check itself against.
        """
        self.write_three(store, prefix)
        found = store.list_keys(f"{prefix}/sagarin/")
        assert len(found) == 6
        assert sum(1 for key in found if key.endswith(".meta.json")) == 3
        assert sum(1 for key in found if key.endswith(".txt")) == 3

    def test_list_keys_is_lexicographic(self, store, prefix):
        """Not `fetched_at`: this method has not opened the objects.

        The two disagree by construction in `write_three`, whose capture stamps
        run opposite to its `fetched_at` values -- so a store that reused the
        `list_manifests` ordering here would fail rather than coincide.
        """
        self.write_three(store, prefix)
        found = store.list_keys(f"{prefix}/sagarin/")
        assert found == sorted(found)
        # The last key, not the newest manifest: `.txt` sorts after `.meta.json`.
        assert found[-1] == snapshot_key(prefix, "2026-09-16T110000Z")

    def test_list_keys_respects_the_prefix(self, store, prefix):
        self.write_three(store, prefix)
        other = snapshot_key(prefix, "2026-09-23T110000Z").replace("week=04", "week=05")
        store.put_bytes(other, ADVERSARIAL, "text/plain")

        found = store.list_keys(f"{prefix}/sagarin/season=2026/week=04/")
        assert other not in found
        assert len(found) == 6

    def test_manifests_come_back_as_models(self, store, prefix):
        """``list_manifests`` returns ``list[Manifest]``, not raw dicts (SPEC 2.3).

        Parsing at the boundary is what makes a malformed manifest in the bucket an
        error here rather than an AttributeError three call frames away.
        """
        self.write_three(store, prefix)
        found = store.list_manifests(f"{prefix}/sagarin/")
        assert all(isinstance(m, Manifest) for m in found)
        assert found[0].source == "sagarin"
        assert found[0].season == 2026
        assert found[0].week == "04"
