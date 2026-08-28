"""Pydantic failures leave as ``cfb.errors.ValidationError`` (SPEC-phase0 section 9).

SPEC 9 declares ``ValidationError(CfbError)`` and describes it as the one that
"wraps pydantic". Nothing wrapped anything: every model boundary in the package
let ``pydantic_core.ValidationError`` propagate untouched, and that class is not a
``CfbError``.

**The CLI is what makes this matter.** SPEC 9's contract is that any ``CfbError``
becomes exit 1 with a message on stderr. A pydantic error escaping a model
boundary is not a ``CfbError``, so it misses that clause entirely and surfaces as
a traceback -- the one shape SPEC 9 says a failure never takes. The behaviour was
identical before the CLI existed only because nothing was catching anything yet.

Two things this deliberately does **not** do:

* It does not convert our own validators' errors. ``ranks_are_unique`` raises
  ``DuplicateRankError`` and ``preseason_degeneracy_is_flagged`` raises
  ``ParseError``; both are already ``CfbError`` and both say something far more
  specific than "a model failed to validate". Relabelling them would trade a
  precise diagnosis for a generic one.
* It does not convert anything else. A ``KeyError`` at a model boundary is a bug
  in this package, and dressing a bug as a validation failure hides it behind a
  clean exit code.

**The signature is a proposal.** SPEC 9 names the exception and not the mechanism::

    with validating("line 42: team rank 7"):
        TeamRating(...)

A context manager rather than a wrapper function, because the boundaries are
model constructions inside loops that already know their own context -- a line
number, a key, a resource -- and that context is the difference between a usable
error and "1 validation error for TeamRating".
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from cfb.errors import CfbError, DuplicateRankError, ParseError, ValidationError
from cfb.models import Manifest, SagarinSnapshot, TeamRating, validating
from cfb.parsers.sagarin_ratings import parse_ratings
from cfb.storage import FileSnapshotStore, MemorySnapshotStore

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "sagarin_2026_preseason.txt"

FETCHED = datetime(2026, 9, 16, 11, 3, 2, tzinfo=UTC)

#: A manifest that is structurally complete and violates one field constraint.
#: ``bytes`` is ``ge=0``; this is what a truncated or hand-edited object in the
#: bucket looks like to ``list_manifests``.
BAD_MANIFEST = {
    "schema_version": 1,
    "source": "sagarin",
    "resource": "ratings",
    "source_url": "http://sagarin.com/sports/cfsend.htm",
    "http_status": 200,
    "sha256": "0" * 64,
    "bytes": -1,
    "encoding": "utf-8",
    "fetched_at": "2026-09-16T11:03:02Z",
    "season": 2026,
    "week": "04",
    "week_resolution": "calendar",
    "snapshot_key": "raw/sagarin/season=2026/week=04/2026-09-16T110302Z.txt",
}

MANIFEST_KEY = "raw/sagarin/season=2026/week=04/2026-09-16T110302Z.meta.json"


@pytest.fixture(scope="module")
def page() -> str:
    return GOLDEN.read_bytes().decode("utf-8")


class TestTheWrapperItself:
    def test_a_pydantic_failure_becomes_a_cfb_validation_error(self):
        with pytest.raises(ValidationError):
            with validating("line 42"):
                TeamRating(
                    rank=0,
                    name="Ohio State",
                    rating=1.0,
                    predictor=1.0,
                    golden_mean=1.0,
                    recent=1.0,
                    division="A",
                    conference="BIG TEN",
                    wins=0,
                    losses=0,
                )

    def test_the_context_survives_into_the_message(self):
        """"1 validation error for TeamRating" does not say which row.

        The boundaries are constructions inside loops over hundreds of rows. An
        error that names the model and not the line sends whoever reads the red
        run back to the page to find it by hand.
        """
        with pytest.raises(ValidationError) as excinfo:
            with validating("line 42: team rank 0"):
                TeamRating(
                    rank=0,
                    name="Ohio State",
                    rating=1.0,
                    predictor=1.0,
                    golden_mean=1.0,
                    recent=1.0,
                    division="A",
                    conference="BIG TEN",
                    wins=0,
                    losses=0,
                )

        message = str(excinfo.value)
        assert "line 42" in message
        assert "rank" in message, "the failing field should survive the wrap"

    def test_the_pydantic_error_is_kept_as_the_cause(self):
        """``raise ... from exc``. The detail is in the chained exception."""
        with pytest.raises(ValidationError) as excinfo:
            with validating("somewhere"):
                Manifest.model_validate_json(json.dumps(BAD_MANIFEST))

        assert isinstance(excinfo.value.__cause__, PydanticValidationError)

    def test_a_cfb_error_passes_through_unchanged(self):
        """Our own validators already raise something more specific.

        ``DuplicateRankError`` names the rank and both lines it appeared on.
        ``ValidationError`` would say a model failed, which is true and useless.
        """
        with pytest.raises(DuplicateRankError):
            with validating("somewhere"):
                raise DuplicateRankError("rank 43 appears twice")

    def test_an_unrelated_exception_passes_through_unchanged(self):
        """A ``KeyError`` here is a bug in this package, not bad input.

        Converting it would give a bug a clean ``CfbError`` exit and bury the
        traceback that identifies it.
        """
        with pytest.raises(KeyError):
            with validating("somewhere"):
                raise KeyError("predictor")

    def test_nothing_is_raised_when_the_model_is_fine(self, page):
        with validating("the golden capture"):
            team = TeamRating(
                rank=1,
                name="Ohio State",
                rating=103.07,
                predictor=103.07,
                golden_mean=103.07,
                recent=103.07,
                division="A",
                conference="BIG TEN",
                wins=0,
                losses=0,
            )
        assert team.rank == 1


class TestValidationErrorIsCatchableByTheCli:
    def test_it_is_a_cfb_error(self):
        """The whole point. SPEC 9: any ``CfbError`` is exit 1 with a message.

        A pydantic error is not one, which is why an unwrapped model failure
        reaches the CLI as a traceback instead.
        """
        assert issubclass(ValidationError, CfbError)

    def test_it_is_not_pydantics_class(self):
        """Two different exceptions share a name; only one of them exits cleanly."""
        assert ValidationError is not PydanticValidationError
        assert not issubclass(PydanticValidationError, CfbError)


class TestTheParserBoundary:
    def test_a_row_that_violates_a_field_constraint_raises_cfb_validation_error(self, page):
        """Rank 0 passes the row regex and fails ``rank: int = Field(ge=1)``.

        Before the wrap this came out of ``parse_ratings`` as a raw pydantic
        error: a page shape the parser accepted and the model rejected, escaping
        as the one exception class the CLI has no clause for.
        """
        row = "   1  Ohio State           A  = 103.07"
        assert row in page, "the golden capture's rank-1 row changed; this test is stale"
        broken = page.replace(row, "   0  Ohio State           A  = 103.07", 1)

        with pytest.raises(ValidationError):
            parse_ratings(broken)

    def test_a_duplicate_rank_still_raises_duplicate_rank_error(self, page):
        """The regression guard for the wrap.

        A wrapper placed too widely catches our own validators and relabels every
        precise error as a generic one. This is the assertion that fails if that
        happens.
        """
        broken = page.replace(
            "  43  Northwestern         A  =  77.49",
            "  42  Northwestern         A  =  77.49",
            1,
        )

        with pytest.raises(DuplicateRankError):
            parse_ratings(broken)


class TestTheStorageBoundary:
    """``list_manifests`` validates bytes that came out of the bucket.

    This is the boundary most likely to fire in production and the least likely
    to be reachable in a test otherwise: the objects are written by an earlier
    run, not by the code doing the reading, so nothing about the read path
    guarantees they still match the schema the reader was built against.
    """

    def test_memory_store(self):
        store = MemorySnapshotStore()
        store.put_json(MANIFEST_KEY, BAD_MANIFEST)

        with pytest.raises(ValidationError):
            store.list_manifests("raw/sagarin/")

    def test_file_store(self, tmp_path):
        store = FileSnapshotStore(tmp_path)
        store.put_json(MANIFEST_KEY, BAD_MANIFEST)

        with pytest.raises(ValidationError):
            store.list_manifests("raw/sagarin/")

    def test_the_key_is_named_so_the_bad_object_can_be_found(self, tmp_path):
        """A bucket holds thousands of these. "a manifest failed" is not actionable."""
        store = FileSnapshotStore(tmp_path)
        store.put_json(MANIFEST_KEY, BAD_MANIFEST)

        with pytest.raises(ValidationError) as excinfo:
            store.list_manifests("raw/sagarin/")

        assert MANIFEST_KEY in str(excinfo.value)

    def test_a_manifest_that_is_not_json_at_all_also_raises_a_cfb_error(self, tmp_path):
        """Truncation is the other way an object goes bad, and it is not a
        constraint violation -- ``model_validate_json`` fails at the parse.
        """
        store = FileSnapshotStore(tmp_path)
        store.put_bytes(MANIFEST_KEY, b"{not json", "application/json")

        with pytest.raises(CfbError):
            store.list_manifests("raw/sagarin/")

    def test_a_good_manifest_still_round_trips(self, tmp_path):
        """The control, so none of the above is satisfied by a store that always raises."""
        store = FileSnapshotStore(tmp_path)
        store.put_json(MANIFEST_KEY, {**BAD_MANIFEST, "bytes": 148793})

        [manifest] = store.list_manifests("raw/sagarin/")
        assert manifest.bytes == 148793


class TestTheSnapshotBoundary:
    def test_a_bad_field_on_the_snapshot_raises_cfb_validation_error(self):
        with pytest.raises(ValidationError):
            with validating("the 2026 page"):
                SagarinSnapshot(
                    fetched_at=FETCHED,
                    page_date_stamp=None,
                    page_state="mid-season",  # not in the Literal
                    hfa={"rating": 2.41},
                    teams=[],
                    predictions=[],
                )

    def test_our_own_snapshot_validators_still_raise_their_own_types(self):
        """``hfa_is_present`` raises ``ParseError``, and must keep doing so."""
        with pytest.raises(ParseError):
            with validating("the 2026 page"):
                SagarinSnapshot(
                    fetched_at=FETCHED,
                    page_date_stamp=None,
                    page_state="preseason",
                    hfa={},
                    teams=[],
                    predictions=[],
                )


class TestTheManifestBoundary:
    """Built through ``model_validate_json``, which is how a manifest is really read.

    ``Manifest`` is ``strict=True``, so ``Manifest(**a_dict_from_json)`` fails on
    the ISO ``fetched_at`` string before reaching any field worth testing. JSON
    mode is the boundary the storage layer actually crosses.
    """

    def _manifest(self, **overrides) -> Manifest:
        return Manifest.model_validate_json(json.dumps({**BAD_MANIFEST, **overrides}))

    def test_a_bad_field_raises_cfb_validation_error(self):
        with pytest.raises(ValidationError):
            with validating("building the manifest"):
                self._manifest(bytes=1, sha256="not-a-hash")

    def test_the_week_validator_still_raises_parse_error(self):
        """``_week_is_a_known_partition`` is ours and stays ``ParseError``."""
        with pytest.raises(ParseError):
            with validating("building the manifest"):
                self._manifest(bytes=1, week="4")

    def test_json_round_trip_of_a_valid_manifest_is_untouched(self):
        with validating("reading it back"):
            manifest = self._manifest(bytes=148793)
        assert manifest.week == "04"
