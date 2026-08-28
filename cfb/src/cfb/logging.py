"""Structured logging (SPEC-phase0 section 9).

One event per line, ``key=value`` separated by spaces, to stdout::

    event=snapshot_written source=sagarin season=2026 week=04 key=raw/... bytes=184320
    event=freshness source=sagarin result=skip reason=no_page_date_stamp

The point is a greppable Actions log. A run that fails is read by whoever gets the
email, and the two questions they have -- what happened, and to which snapshot --
should both be answerable with ``grep`` rather than by opening the bucket.

**The vocabulary is here, not at each call site.** A skip that logs
``reason=no_stamp`` in one place and ``reason=missing_date`` in another is not a
vocabulary, and the freshness check (SPEC 4.6) is the case that makes this matter:
its skips are correct behaviour and are indistinguishable from a healthy run
except by this line. Something has to be greppable and stable, so the strings are
constants and the tests import these rather than restating them.

Deliberately not the stdlib ``logging`` module. There is no configuration to get
wrong, no handler to be missing in CI, no level that can be raised until the
skips stop being recorded, and the output is identical locally and in Actions.
"""

import sys
from typing import Any

__all__ = [
    "EVENT_FRESHNESS",
    "EVENT_SNAPSHOT_WRITTEN",
    "REASON_NOT_IN_SEASON",
    "REASON_NO_PAGE_DATE_STAMP",
    "REASON_NO_PRIOR_MANIFEST",
    "RESULT_OK",
    "RESULT_SKIP",
    "log",
]

# --- events -------------------------------------------------------------------
EVENT_SNAPSHOT_WRITTEN = "snapshot_written"
EVENT_FRESHNESS = "freshness"

# --- outcomes -----------------------------------------------------------------
RESULT_OK = "ok"
RESULT_SKIP = "skip"

# --- why a freshness comparison was skipped (SPEC 4.6) ------------------------
#: Nothing precedes today's snapshot -- the first ever run, or an empty store.
REASON_NO_PRIOR_MANIFEST = "no_prior_manifest"
#: Either side carries no ``page_date_stamp``. The preseason page has none at all
#: (SPEC 4.7), so there is nothing to compare until the first in-season page lands.
REASON_NO_PAGE_DATE_STAMP = "no_page_date_stamp"
#: Out of season. Sagarin does not update from roughly February through August.
REASON_NOT_IN_SEASON = "not_in_season"


def log(event: str, **fields: Any) -> None:
    """Write one ``key=value`` line to stdout.

    Fields whose value is ``None`` are omitted rather than logged as ``key=None``:
    a key with no value is noise in a grep, and its absence says the same thing.
    """
    rendered = [f"event={event}"]
    rendered += [f"{key}={_value(value)}" for key, value in fields.items() if value is not None]
    print(" ".join(rendered), file=sys.stdout, flush=True)


def _value(value: Any) -> str:
    """Render one value, quoting only if it would otherwise split into two fields.

    A space inside an unquoted value silently turns one field into two and a
    parser reading the line back gets a key it has never heard of. Nothing in this
    project logs a value with whitespace today; this is here so that the first
    thing that does is still readable.
    """
    text = str(value)
    return f'"{text}"' if any(character.isspace() for character in text) else text
