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

__all__ = ["bootstrap", "candidates_path", "canonical_slug", "inherited_ids", "prior_mapping"]

#: How many ranked guesses to offer per undecided name. Enough to usually contain
#: the answer, few enough that the file stays readable at a few hundred lines.
SUGGESTIONS = 4


def candidates_path(season: int, *, data_dir: Path) -> Path:
    return data_dir / f"_candidates-{season}.yaml"


def canonical_slug(name: str) -> str:
    """A project-owned slug: lowercase, ASCII, hyphen-separated.

    **Minted from a vendor's spelling, and only ever once.** An earlier version of
    this docstring called the result "vendor-neutral by construction", which it is
    not: it is a slug of whatever Sagarin happened to call the team that year, and
    on the 2026 roster 31 of 266 ids differ from the CFBD spelling for that reason
    (``southern-california`` for ``USC``).

    Being derived from a vendor is harmless. Being *re-derived* every season is
    not, because Sagarin renaming a team between seasons would mint a different id
    and split that team's history in half exactly where Phase 2's backfill joins
    across seasons. ``inherited_ids`` is what stops that, and ``bootstrap`` calls
    it before minting anything.

    So: a name is a starting point for a human to edit before committing, and
    after it is committed the id is frozen -- for the season by SPEC 6.1, and
    across seasons by inheritance.
    """
    kept = [character.lower() if character.isalnum() else "-" for character in name]
    slug = "".join(kept)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def prior_mapping(season: int, *, data_dir: Path) -> dict[str, dict]:
    """The most recent earlier season's mapping, or ``{}``.

    The most recent earlier season rather than exactly ``season - 1``, so a gap
    year does not silently restart the numbering, and never a *later* one -- a
    backfill season taking ids from the future would make the same run produce
    different files depending on what else had been generated.
    """
    prior = sorted(
        (
            found
            for path in data_dir.glob("teams-*.yaml")
            if (found := _season_of(path)) is not None and found < season
        ),
        reverse=True,
    )
    if not prior:
        return {}
    return yaml.safe_load((data_dir / f"teams-{prior[0]}.yaml").read_bytes()) or {}


def inherited_ids(season: int, *, data_dir: Path) -> dict[int, str]:
    """``{cfbd_id: canonical_id}`` from the most recent earlier season's mapping.

    **Keyed on ``cfbd_id`` because it is the only stable thing in the file.** Both
    name columns are a vendor's current spelling and either can change between
    seasons; SPEC 6.1 already says the id "rides along for direct joins and as a
    cross-check on the name mapping", and this is that cross-check doing work.

    The most recent earlier season rather than exactly ``season - 1``, so a gap
    year does not silently restart the numbering.

    An empty mapping is the ordinary answer for the first season a project has,
    and it means every id is minted fresh.

    An entry with no ``cfbd_id`` is skipped and its canonical id is re-minted next
    season, which is why ``load`` should be the thing that refuses one -- this
    function cannot tell a missing id from a team that did not exist. Two entries
    sharing an id is the worse half and raises: the loser would be silently
    dropped from this dict and re-minted, and the winner would inherit under an id
    that belongs to another team.
    """
    inherited: dict[int, str] = {}
    claimed_by: dict[int, str] = {}
    for canonical, entry in prior_mapping(season, data_dir=data_dir).items():
        cfbd_id = (entry or {}).get("cfbd_id")
        if cfbd_id is None:
            continue
        if cfbd_id in inherited:
            raise ValueError(
                f"cfbd_id {cfbd_id} is claimed by two entries in the season before "
                f"{season}: {claimed_by[cfbd_id]!r} and {canonical!r}. Inheritance is "
                f"keyed on it, so one of the two would be re-minted and the other "
                f"would carry an id that is not its own. Fix the earlier season's file."
            )
        claimed_by[cfbd_id] = canonical
        inherited[cfbd_id] = canonical
    return inherited


def _season_of(path: Path) -> int | None:
    stem = path.stem.removeprefix("teams-")
    return int(stem) if stem.isdigit() else None


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

    # Ids come from the previous season wherever the team existed in it, and are
    # minted only for teams that are genuinely new. See `inherited_ids`.
    prior = prior_mapping(season, data_dir=data_dir)
    inherited = inherited_ids(season, data_dir=data_dir)

    # A Sagarin name the previous season already decided, and the CFBD team it was
    # decided to be. This is what makes a hand decision durable: without it the 32
    # rows in 2026 whose two vendors spell the team differently would return to the
    # candidates pile every year, and the only thing preventing a re-mint would be
    # whether the person re-deciding noticed the `was:` comment. A comment is a
    # convention; this is the guard.
    decided_before = {
        entry["sagarin"]: entry["cfbd_id"]
        for entry in prior.values()
        if entry and entry.get("sagarin") and entry.get("cfbd_id") is not None
    }
    by_cfbd_id = {team["id"]: team for team in cfbd}

    matched: dict[str, dict] = {}
    minted_from: dict[str, str] = {}
    for name in sagarin:
        # Exact name agreement first, then last season's decision for this name.
        # The second resolves a team whose CFBD spelling changed, which name
        # equality cannot see at all.
        team = by_name.get(name) or by_cfbd_id.get(decided_before.get(name, -1))
        if team is None:
            continue
        canonical = inherited.get(team["id"]) or canonical_slug(name)
        if canonical in matched:
            # Two teams claiming one id would silently overwrite each other in
            # this dict and leave the season one team short, with the survivor
            # holding the loser's history.
            raise ValueError(
                f"canonical id {canonical!r} claimed by two teams: "
                f"{minted_from[canonical]!r} and {name!r}. One of them is a rename "
                f"the previous season's mapping does not know about; decide it by hand "
                f"in teams-{season}.yaml rather than letting a slug collision pick."
            )
        minted_from[canonical] = name
        matched[canonical] = {
            "cfbd": team["school"],
            "cfbd_id": team["id"],
            "sagarin": name,
            "division": team["classification"].upper(),
        }

    # Undecided means "this run did not resolve it", not "the two rosters spell
    # it differently". Those were the same set before ids were inherited and are
    # not now: a name resolved by last season's decision never appears in
    # `by_name`, so asking `by_name` lists a team that is already written into
    # teams-YYYY.yaml -- and lists it with no suggestions under it, because the
    # CFBD row it matched is correctly no longer unclaimed. Following this file's
    # own instruction and pasting that block over would duplicate the canonical
    # id, and PyYAML keeps the last of two identical keys without complaining.
    resolved = {entry["sagarin"] for entry in matched.values()}
    decided_ids = {entry["cfbd_id"] for entry in matched.values()}
    undecided = [name for name in sagarin if name not in resolved]
    remaining = [team for team in cfbd if team["id"] not in decided_ids]

    data_dir.mkdir(parents=True, exist_ok=True)
    mapping_file.write_text(_render_mapping(season, matched, inherited), encoding="utf-8")
    candidates_path(season, data_dir=data_dir).write_text(
        _render_candidates(season, undecided, remaining, inherited), encoding="utf-8"
    )
    return len(matched), len(undecided)


def _render_mapping(season: int, matched: dict[str, dict], inherited: dict[int, str]) -> str:
    body = yaml.safe_dump(matched, sort_keys=True, allow_unicode=True, width=100)
    carried = sum(1 for entry in matched.values() if entry["cfbd_id"] in inherited)
    provenance = (
        f"# {carried} of these ids were carried over from the previous season by cfbd_id\n"
        f"# and {len(matched) - carried} were minted here. A vendor renaming a team changes\n"
        f"# the name column below and never the id.\n"
        if inherited
        else "# No earlier season exists, so every id below was minted from the Sagarin\n"
        "# spelling. From next season on they are carried forward by cfbd_id.\n"
    )
    return (
        f"# Crosswalk for the {season} season (SPEC-phase0 6.1).\n"
        f"#\n"
        f"# canonical_id: project-owned slug. Minted once from a vendor spelling -- so it\n"
        f"# is not vendor-neutral -- and frozen thereafter: for this season because a\n"
        f"# played season's mapping never changes, and across seasons because bootstrap\n"
        f"# inherits ids by cfbd_id rather than re-deriving them from names.\n"
        f"#\n"
        f"{provenance}"
        f"#\n"
        f"# The {len(matched)} entries below were written by `cfb crosswalk bootstrap`:\n"
        f"# the two rosters agreed on the name, or the previous season had already\n"
        f"# decided that name and this one only changed the CFBD spelling.\n"
        f"# Everything else is in _candidates-{season}.yaml and is\n"
        f"# a human decision -- similarity scoring orders that list and never decides it.\n"
        f"#\n"
        f"# Conference is deliberately absent: it is time-varying and belongs in each\n"
        f"# snapshot's parsed output, not in a mapping that a played season freezes.\n"
        f"\n" + body
    )


def _render_candidates(
    season: int, undecided: list[str], remaining: list[dict], inherited: dict[int, str]
) -> str:
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
        ranked = sorted(remaining, key=lambda team: _score(name, team["school"]), reverse=True)[
            :SUGGESTIONS
        ]
        lines.append(f"# {name!r}")
        for team in ranked:
            # The previous season's id for this team, if it had one. It is the
            # answer whenever the guess is right, and copying it is what keeps a
            # renamed team's history in one piece.
            carried = inherited.get(team["id"])
            lines.append(
                f"#     {_score(name, team['school']):.2f}  {team['school']!r}"
                f"  id={team['id']}  {team['classification']}"
                + (f"  was: {carried}" if carried else "")
            )
        lines.append(f"{canonical_slug(name)}:")
        lines.append("  cfbd: # one of the above, or a name neither list guessed")
        lines.append("  cfbd_id:")
        lines.append(f"  sagarin: {json.dumps(name)}")
        lines.append("  division: # FBS or FCS")
        lines.append("")
    return "\n".join(lines) + "\n"
