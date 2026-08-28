"""The exception hierarchy (SPEC-phase0 section 9).

Every failure in this package raises. Nothing here is caught to log-and-continue:
a validation failure demoted to a warning is the exact failure mode the project
exists to prevent. Any ``CfbError`` reaching the CLI is exit 1 and a red workflow.

Almost every error below is a *data* fault -- a page that changed shape, a name
nothing maps, a result the model has no answer for. ``MissingDependencyError`` is
the one environment fault, and it is here for the same reason the others are:
SPEC 9 promises a message and no traceback, and it does not carve out the
failures that are the operator's fault rather than the data's.
"""

from collections.abc import Iterator
from contextlib import contextmanager


class CfbError(Exception):
    """Base for every error this package raises."""


class MissingDependencyError(CfbError):
    """An optional dependency is not installed.

    ``boto3`` is an extra (``uv sync --extra s3``) so the offline test suite --
    which is every test that runs without ``CFB_INTEGRATION=1`` -- installs
    neither it nor botocore. The cost of that choice is this failure, and a bare
    ``uv sync`` prunes the extra and causes it.

    **The traceback was the problem, not the error.** Unwrapped, a missing boto3
    surfaced as a ``ModuleNotFoundError`` nine frames inside
    ``S3SnapshotStore.__init__`` -- technically accurate, and it named neither the
    extra nor the command that fixes it. Both call sites already said "uv sync
    --extra s3" in a docstring, which is exactly the wrong place: the person who
    needs it is at a terminal watching a stack trace, not reading the source.
    """


@contextmanager
def optional_import(module: str, *, extra: str, needed_for: str) -> Iterator[None]:
    """Turn an ``ImportError`` inside this block into a ``MissingDependencyError``.

    The same shape as ``models.validating``, and for the same reason: an exception
    from outside this package is not a ``CfbError``, so it misses the CLI's exit-1
    clause entirely and arrives as a traceback -- the one form SPEC 9 says a
    failure never takes.

    ``needed_for`` is not decoration. The two sites that use this fail at
    different moments -- one when a store is built, one on the first CFBD request
    of a run -- and "boto3 is not installed" alone does not tell anyone which
    command they were part-way through.
    """
    try:
        yield
    except ImportError as exc:
        raise MissingDependencyError(
            f"{module} is not installed, so {needed_for} cannot run.\n\n"
            f"    uv sync --extra {extra}\n\n"
            f"{module} is an optional extra, so the offline test suite installs neither it "
            f"nor its dependencies. A bare `uv sync` prunes it, which is the usual cause of "
            f"this. Original error: {exc}"
        ) from exc


class FetchError(CfbError):
    """Network, timeout, redirect, or non-2xx after retries."""


class EncodingError(CfbError):
    """No candidate encoding decoded the bytes and contained the marker strings."""


class SnapshotExistsError(CfbError):
    """A write targeted a raw key that already holds an object.

    Raw snapshots are write-once (SPEC 2.1). A new capture gets a new timestamped
    key; it never replaces one. Manifests are the documented exception and are
    written through ``put_json``, which does not raise this.
    """


class SnapshotNotFoundError(CfbError):
    """A read targeted a key the store does not hold."""


class ParseError(CfbError):
    """A source page did not match the schema the parser was written against."""


class DuplicateRankError(ParseError):
    """The same published rank appeared twice. Rank is the join key."""


class ValidationError(CfbError):
    """A parsed row failed model validation."""


class UnmappedTeamError(CfbError):
    """A source team name has no crosswalk entry."""


class UnratedTeamError(CfbError):
    """A game named a canonical team the ratings do not hold (SPEC-phase1 3.4).

    Distinct from ``UnmappedTeamError``, which is about a *name*. This one is
    about a name that resolved: the crosswalk knew it and the seed did not
    produce a rating for it, which means the seed missed a team or the two ran
    against different crosswalk versions. Defaulting the team to 1500 would rate
    it as exactly average for the rest of the season with nothing saying so.
    """


class SeedStateError(CfbError):
    """Seeding was asked to run against a snapshot that is not a preseason page.

    SPEC-phase1 3.2 makes seeding a once-per-season operation. A mid-season
    re-seed silently discards every result the ratings have learned from and
    reverts the season to August -- and it looks like a successful run, because
    266 teams come back rated. This refusal is the only thing between that and a
    rerun of the wrong command, which is why it has a name of its own rather than
    sharing ``ParseError`` with a page that failed to parse: nothing was wrong
    with the page.
    """


class EloDomainError(CfbError):
    """The update step was handed a game whose result it defines no behaviour for.

    Three cases, all of them SPEC-phase1 3.4 reaching the edge of what it
    specifies: a game with no result, a tie, and a rating gap past the
    margin-of-victory floor. None of them is a parse failure -- the row is
    well-formed and the model simply has no answer -- and each has a silent wrong
    answer sitting next to it (a null read as zero, a tie scored as an away win, a
    multiplier that inverts) which is the reason this raises instead.
    """


class ReplayError(CfbError):
    """A season could not be rebuilt from ``raw/`` (SPEC-phase1 3.5).

    Every instance is a statement about the snapshots rather than about the
    model: no preseason page to seed from, a game with no kickoff to order by, or
    no Sagarin snapshot preceding a game to take an HFA from.
    """


class StateMismatchError(CfbError):
    """A replay from ``raw/`` did not reproduce the stored Elo state.

    SPEC-phase1 3.5 makes this the difference between a cache and a second source
    of truth, and SPEC-phase1 11 step 5 is the check. It is always a red run: the
    stored object and the snapshots it claims to be derived from disagree, and
    nothing downstream can tell which of them the published numbers came from.
    """


class WeekResolutionError(CfbError):
    """Season/week could not be resolved from the committed calendar."""


class StaleSourceError(CfbError):
    """A source's internal date stamp has not advanced."""


class CallBudgetExceeded(CfbError):
    """A collector tried to exceed its per-run API call budget."""
