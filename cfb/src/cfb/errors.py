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


class WeekResolutionError(CfbError):
    """Season/week could not be resolved from the committed calendar."""


class StaleSourceError(CfbError):
    """A source's internal date stamp has not advanced."""


class CallBudgetExceeded(CfbError):
    """A collector tried to exceed its per-run API call budget."""
