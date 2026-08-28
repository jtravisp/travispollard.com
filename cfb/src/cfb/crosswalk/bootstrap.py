"""One-off crosswalk candidate generator (SPEC-phase0 6.3).

**Quarantined from the runtime on purpose.** Nothing under ``collectors/`` or
``parsers/`` may import this, and ``tests/test_crosswalk.py`` asserts it two ways
-- by importing each runtime module and checking this one did not come along, and
by grepping the runtime source for the word. The reason is the only thing in here
that would do damage anywhere else: similarity scoring.

**Scoring orders a human's decisions and never makes one.** SPEC 6.3 gives the
example that settles the argument::

    "Southern California"  ~ USC  (0.09)

A threshold low enough to catch that would map half the FCS by accident. So exact
matches are written straight to ``teams-YYYY.yaml``, everything else goes to
``_candidates-YYYY.yaml`` sorted best-first, and a person works down the list. The
score is a sort key, not a verdict -- which is why the candidates file is scratch
and never loaded by anything.

Run it with ``uv run cfb crosswalk bootstrap --season 2026``.
"""

import json
from difflib import SequenceMatcher
from pathlib import Path

import yaml

__all__ = ["bootstrap", "candidates_path", "canonical_slug"]

#: How many ranked guesses to offer per undecided name. Enough to usually contain
#: the answer, few enough that the file stays readable at a few hundred lines.
SUGGESTIONS = 4


def candidates_path(season: int, *, data_dir: Path) -> Path:
    return data_dir / f"_candidates-{season}.yaml"


def canonical_slug(name: str) -> str:
    """A project-owned slug: lowercase, ASCII, hyphen-separated.

    Vendor-neutral by construction (SPEC 6.1) -- it is derived from a name only
    to give a human something readable to start from, and is theirs to change
    before it is committed. Once committed it is stable forever, because
    historical joins are keyed on it.
    """
    kept = [character.lower() if character.isalnum() else "-" for character in name]
    slug = "".join(kept)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _score(left: str, right: str) -> float:
    return round(SequenceMatcher(None, left.lower(), right.lower()).ratio(), 2)


def bootstrap(
    *,
    season: int,
    sagarin_roster: Path,
    cfbd_roster: Path,
    data_dir: Path,
) -> tuple[int, int]:
    """Write the exact matches and the ranked leftovers. Returns ``(matched, undecided)``.

    Refuses to overwrite an existing ``teams-YYYY.yaml``: it holds hand-made
    decisions, and regenerating over them would silently discard the only part of
    this process a machine cannot redo.
    """
    mapping_file = data_dir / f"teams-{season}.yaml"
    if mapping_file.exists():
        raise FileExistsError(
            f"{mapping_file} already exists and holds hand-made decisions. "
            f"Delete it deliberately if you really mean to start over."
        )

    sagarin = [
        line for line in sagarin_roster.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    cfbd = json.loads(cfbd_roster.read_bytes())
    by_name = {team["school"]: team for team in cfbd}

    matched: dict[str, dict] = {}
    for name in sagarin:
        team = by_name.get(name)
        if team is None:
            continue
        matched[canonical_slug(name)] = {
            "cfbd": team["school"],
            "cfbd_id": team["id"],
            "sagarin": name,
            "division": team["classification"].upper(),
        }

    decided_cfbd = {entry["cfbd"] for entry in matched.values()}
    undecided = [name for name in sagarin if name not in by_name]
    remaining = [team for team in cfbd if team["school"] not in decided_cfbd]

    data_dir.mkdir(parents=True, exist_ok=True)
    mapping_file.write_text(_render_mapping(season, matched), encoding="utf-8")
    candidates_path(season, data_dir=data_dir).write_text(
        _render_candidates(season, undecided, remaining), encoding="utf-8"
    )
    return len(matched), len(undecided)


def _render_mapping(season: int, matched: dict[str, dict]) -> str:
    body = yaml.safe_dump(matched, sort_keys=True, allow_unicode=True, width=100)
    return (
        f"# Crosswalk for the {season} season (SPEC-phase0 6.1).\n"
        f"#\n"
        f"# canonical_id: project-owned slug, stable forever, vendor-neutral. A vendor\n"
        f"# renaming a team rewrites one line here rather than every historical row.\n"
        f"#\n"
        f"# The {len(matched)} entries below matched exactly on name and were written by\n"
        f"# `cfb crosswalk bootstrap`. Everything else is in _candidates-{season}.yaml and is\n"
        f"# a human decision -- similarity scoring orders that list and never decides it.\n"
        f"#\n"
        f"# Conference is deliberately absent: it is time-varying and belongs in each\n"
        f"# snapshot's parsed output, not in a mapping that a played season freezes.\n"
        f"\n" + body
    )


def _render_candidates(season: int, undecided: list[str], remaining: list[dict]) -> str:
    lines = [
        f"# SCRATCH -- {season} crosswalk candidates (SPEC-phase0 6.3).",
        "#",
        "# Nothing loads this file. It exists to order decisions, not to make them:",
        "# the scores below are a sort key and the worked example in SPEC 6.3 is why --",
        '#   "Southern California" ~ USC (0.09)',
        "# a threshold low enough to catch that would map half the FCS by accident.",
        "#",
        f"# {len(undecided)} Sagarin names have no exact CFBD match. For each, the closest",
        "# unclaimed CFBD names are listed best-first. Move the decided ones into",
        f"# teams-{season}.yaml in the shape used there, then delete this file.",
        "#",
        "# division comes from the CFBD side: fbs -> FBS, fcs -> FCS.",
        "",
    ]
    for name in undecided:
        ranked = sorted(
            remaining, key=lambda team: _score(name, team["school"]), reverse=True
        )[:SUGGESTIONS]
        lines.append(f"# {name!r}")
        for team in ranked:
            lines.append(
                f"#     {_score(name, team['school']):.2f}  {team['school']!r}"
                f"  id={team['id']}  {team['classification']}"
            )
        lines.append(f"{canonical_slug(name)}:")
        lines.append("  cfbd: # one of the above, or a name neither list guessed")
        lines.append("  cfbd_id:")
        lines.append(f"  sagarin: {json.dumps(name)}")
        lines.append("  division: # FBS or FCS")
        lines.append("")
    return "\n".join(lines) + "\n"
