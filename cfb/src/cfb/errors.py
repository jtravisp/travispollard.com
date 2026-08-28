"""The exception hierarchy (SPEC-phase0 section 9).

Every failure in this package raises. Nothing here is caught to log-and-continue:
a validation failure demoted to a warning is the exact failure mode the project
exists to prevent. Any ``CfbError`` reaching the CLI is exit 1 and a red workflow.
"""


class CfbError(Exception):
    """Base for every error this package raises."""


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
