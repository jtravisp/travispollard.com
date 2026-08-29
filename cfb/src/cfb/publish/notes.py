"""The weekly note scaffold (SPEC-phase1 7).

**The one human step in this phase, by design.** The pipeline writes the numbers
and a person writes the prose; the PRD's fifteen-minute target is what the
scaffold exists to protect, and it protects it by making sure the fifteen minutes
are spent on the commentary rather than on looking figures up.

Everything here is read out of one ``ScoredWeek``. Nothing is recomputed --
§5.3 already decided what a week's figures are, and a note that arrived at its
own numbers would be a second opinion published under the same name.

**Where the finished note goes is not here.** §7 puts it in the repo as MDX under
``frontend/app/cfb/notes/``, because it is prose that ships with the site rather
than data the pipeline owns. So this module's output is a starting point that
leaves the bucket and never comes back: the scaffold is written to ``notes/``,
a person edits it into MDX, and the site build is what publishes it. That
asymmetry is why §6.1's ``notes/index.json`` and ``notes/<slug>.json`` were
dropped -- see PHASE-1.
"""

from datetime import datetime
from pathlib import Path

from cfb.crosswalk import Crosswalk
from cfb.crosswalk import load as load_crosswalk
from cfb.elo.scoring import TEXAS, ScoredGame, ScoredWeek
from cfb.sources import week_position
from cfb.storage import SnapshotStore

__all__ = ["biggest_miss", "note_key", "scaffold", "write_scaffold"]

#: Second resolution and no colons, matching every other key this project builds.
_STAMP_FORMAT = "%Y-%m-%dT%H%M%SZ"


def note_key(*, season: int, week: str, generated_at: datetime) -> str:
    """``notes/season=2026/week=04/2026-09-21T123000Z.md`` (§7).

    **Timestamped, where §7 named a fixed ``scaffold.md``.** A fixed name cannot
    be written twice: ``put_bytes`` refuses an existing key, and the publisher
    role has no ``s3:DeleteObject``, so the second run of a week -- after a
    rescore, or after the first scaffold was edited badly -- would fail on the
    write rather than produce a scaffold.

    The alternative was to make this the one mutable non-JSON object in the
    layout, which buys nothing: a scaffold is derived entirely from ``scored/``
    and a person takes the newest one. So it follows the same discipline as every
    other generated document instead, and SPEC-phase1 7 records the change.
    """
    week_position(week)  # rejects a partition value that would open a second prefix
    return f"notes/season={season}/week={week}/{generated_at.strftime(_STAMP_FORMAT)}.md"


def biggest_miss(week: ScoredWeek) -> ScoredGame | None:
    """The game the model got most wrong, by absolute error (§7).

    ``None`` on a week with no scored games, which is not the same as a week the
    model got right. Ties break on the game id so the same ``ScoredWeek`` always
    produces the same scaffold -- a note that changed between two runs over
    nothing would undermine the one property the prediction log exists to have.
    """
    if not week.games:
        return None
    return max(week.games, key=lambda game: (game.abs_error, -game.cfbd_game_id))


def scaffold(
    week: ScoredWeek,
    *,
    generated_at: datetime,
    crosswalk: Crosswalk | None = None,
    crosswalk_dir: Path | None = None,
) -> str:
    """The markdown a person edits into the week's note.

    Written as prose with the numbers already in it rather than as a table to be
    read off, because the fifteen minutes are supposed to go on what the numbers
    *mean*. The `TODO` markers are deliberate and deliberately unmissable: an
    unedited scaffold that shipped would read as a finished note.

    **Team names are rendered, never canonical ids.** The first scaffold this
    produced said "Texas hosted ohio-state" and "north-carolina at tcu", which is
    §6.3's rule broken in the most visible possible place -- a document whose
    entire purpose is to be read by a person and then published as prose. The
    crosswalk's job ends at this boundary exactly as it does at `publish`.
    """
    resolver = crosswalk or load_crosswalk(week.season, data_dir=crosswalk_dir)
    texas = next((game for game in week.games if TEXAS in (game.home, game.away)), None)
    miss = biggest_miss(week)

    lines = [
        f"# Week {week.week}, {week.season}",
        "",
        f"<!-- Scaffold generated {generated_at.isoformat()} from the scored week.",
        "     Every figure below came from the pipeline. Replace each TODO with",
        "     commentary, then commit the finished note as MDX under",
        "     frontend/app/cfb/notes/. Delete this comment. -->",
        "",
        "## Texas",
        "",
    ]

    if texas is None:
        lines += [
            "No Texas game was scored this week — a bye, or a game that had not been",
            "played when the results were captured.",
            "",
            "TODO: a sentence on what that means for next week, or cut this section.",
            "",
        ]
    else:
        lines += _texas_lines(texas, resolver)

    lines += [
        "## The full slate",
        "",
        f"- **{week.full_slate.games} games scored**"
        + (f", {week.unplayed} not yet played" if week.unplayed else ""),
        f"- Mean absolute error: {_number(week.full_slate.mae)}"
        f" (market {_number(week.full_slate.market_mae)} over"
        f" {week.full_slate.market_games} priced games,"
        f" Sagarin {_number(week.full_slate.sagarin_mae)} over"
        f" {week.full_slate.sagarin_games})",
        f"- Brier score: {_number(week.full_slate.brier, 3)}",
        f"- Against the spread: {week.full_slate.ats.record}"
        f" ({week.full_slate.ats.scored} of {week.full_slate.ats.games} games priced with an"
        f" edge; {week.full_slate.ats.excluded_no_line} had no line,"
        f" {week.full_slate.ats.excluded_no_edge} no edge)",
        f"- Correlation with Sagarin's predictions: {_number(week.sagarin_r, 3)}",
        "",
        "TODO: is the model beating the market, and over how many games?",
        "",
        "## Biggest miss",
        "",
    ]

    if miss is None:
        lines += ["No games were scored this week.", ""]
    else:
        lines += [
            f"**{resolver.display_name(miss.away)} at"
            f" {resolver.display_name(miss.home)}** — predicted"
            f" {_signed(miss.predicted_margin)} for the home team, actual"
            f" {_signed(float(miss.actual_margin))}, off by"
            f" {miss.abs_error:.1f} points.",
            "",
            "TODO: why. A team the ratings have wrong, or a game nobody could have called?",
            "",
        ]

    lines += [
        "---",
        "",
        f"<!-- Scored from {week.results_fetched_at.isoformat()}, against predictions",
        f"     generated {week.predictions_generated_at.isoformat()}. -->",
        "",
    ]
    return "\n".join(lines)


def write_scaffold(
    store: SnapshotStore,
    week: ScoredWeek,
    *,
    generated_at: datetime,
    crosswalk: Crosswalk | None = None,
    crosswalk_dir: Path | None = None,
) -> str:
    """Write one week's scaffold. Returns the key.

    ``put_bytes`` like everything else the pipeline generates, so a regenerated
    scaffold lands beside its predecessor rather than replacing it. A person who
    has already started editing one does not lose it to a rerun.
    """
    key = note_key(season=week.season, week=week.week, generated_at=generated_at)
    markdown = scaffold(
        week, generated_at=generated_at, crosswalk=crosswalk, crosswalk_dir=crosswalk_dir
    )
    store.put_bytes(key, markdown.encode("utf-8"), "text/markdown")
    return key


def _texas_lines(game: ScoredGame, resolver: Crosswalk) -> list[str]:
    """Texas's own game, in §7's order: prediction, result, error, line, verdict."""
    at_home = game.home == TEXAS
    team = resolver.display_name(TEXAS)
    opponent = resolver.display_name(game.away if at_home else game.home)
    # Re-signed to Texas, matching what `/cfb` published. A note stating the
    # margin from the home team's view for an away game would contradict the page
    # it is written to accompany.
    predicted = game.predicted_margin if at_home else -game.predicted_margin
    actual = game.actual_margin if at_home else -game.actual_margin
    won = (game.home_won and at_home) or (not game.home_won and not at_home)

    lines = [
        f"{team} {'hosted' if at_home else 'travelled to'} {opponent} and"
        f" {'won' if won else 'lost'} by {abs(actual)}.",
        "",
        f"- Predicted: {_signed(predicted)} for {team}",
        f"- Actual: {_signed(float(actual))}",
        f"- Error: {game.abs_error:.1f} points",
    ]

    if game.market_line is None:
        lines.append("- No book priced this game, so it is outside the ATS record")
    elif game.beat_market is None:
        lines.append(
            f"- The line was {game.market_line:+g}"
            f" ({game.market_line_source}) and the model had no edge on it"
        )
    else:
        lines.append(
            f"- The line was {game.market_line:+g} ({game.market_line_source});"
            f" the model took {game.market_pick} and"
            f" **{'beat it' if game.beat_market else 'lost to it'}**"
        )

    if game.sagarin_predictor_margin is not None:
        sagarin = (
            game.sagarin_predictor_margin if at_home else -game.sagarin_predictor_margin
        )
        lines.append(f"- Sagarin predicted {_signed(sagarin)} for {team}")

    lines += ["", "TODO: what happened. One paragraph.", ""]
    return lines


def _number(value: float | None, digits: int = 2) -> str:
    """A mean, or the word. **Never a zero** -- §5.3's rule, in prose form."""
    return "not available" if value is None else f"{value:.{digits}f}"


def _signed(margin: float) -> str:
    return f"{margin:+.1f}"
