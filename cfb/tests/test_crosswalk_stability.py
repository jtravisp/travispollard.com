"""Canonical ids survive a vendor rename between seasons (SPEC-phase0 6.1).

§6.1 says a canonical id is "stable forever, because historical joins are keyed on
it", and one file per season so "a 2027 realignment cannot retroactively break a
2026 join". Both were true of the *file* and neither was true of the *generator*.

`bootstrap` minted ids with `canonical_slug(sagarin_name)` — on both of its paths.
An exact name match writes the slug straight into `teams-YYYY.yaml`, and a name
that needs a human writes the same slug into `_candidates-YYYY.yaml` as a
pre-filled key. `southern-california` came from the second: `"Southern California"`
and `"USC"` are not an exact match, so a person decided that row and accepted the
slug the template offered.

Minting from a vendor spelling is fine once — an id has to come from somewhere.
Re-deriving it every season is not. A team Sagarin respells between seasons gets a
different id in each, and on the 2026 roster that is not hypothetical: 31 of 266
ids are the Sagarin spelling rather than the CFBD one, `southern-california` among
them, so Sagarin switching to `USC` is exactly the shape that would fire.

**What that failure looks like is the reason it is worth a test.** Nothing raises.
Both seasons load, both validate, every name resolves. The team simply has two
identities and Phase 2's backfill — the one thing that joins across seasons —
averages half a history against the other half. `_index` already refuses two names
mapping to one id *within* a season; nothing watched across them.

The fix is to inherit ids by `cfbd_id`, which SPEC 6.1 already keeps for exactly
this purpose ("rides along for direct joins and as a cross-check on the name
mapping"). `TestARenameBetweenSeasons` is the discriminating case: it renames a
team the way Sagarin would and asserts the id does not move.

These build tiny rosters rather than using the committed 266, because the property
is about two seasons and only one season exists.
"""

import json
from pathlib import Path

import pytest
import yaml

from cfb.crosswalk import load
from cfb.crosswalk.bootstrap import bootstrap, canonical_slug, inherited_ids

#: Anchored on this file, not the working directory. SPEC 6.4's fix loop ends
#: with "uv run pytest cfb/tests/test_crosswalk.py", which runs from the repo
#: root, where a relative path resolves to nothing.
CROSSWALK_FILE = Path(__file__).parent.parent / "data" / "crosswalk" / "teams-2026.yaml"

#: Enough teams to have a rename, a survivor and a newcomer, and no more.
USC = {"id": 30, "school": "USC", "classification": "fbs"}
TEXAS = {"id": 251, "school": "Texas", "classification": "fbs"}
NEWCOMER = {"id": 9999, "school": "Delaware", "classification": "fbs"}


def rosters(tmp_path: Path, *, sagarin: list[str], cfbd: list[dict]) -> tuple[Path, Path]:
    sagarin_file = tmp_path / "sagarin.txt"
    cfbd_file = tmp_path / "cfbd.json"
    sagarin_file.write_text("\n".join(sagarin), encoding="utf-8")
    cfbd_file.write_bytes(json.dumps(cfbd).encode("utf-8"))
    return sagarin_file, cfbd_file


def run(tmp_path: Path, season: int, *, sagarin: list[str], cfbd: list[dict]) -> dict:
    data_dir = tmp_path / "crosswalk"
    sagarin_file, cfbd_file = rosters(tmp_path, sagarin=sagarin, cfbd=cfbd)
    bootstrap(
        season=season,
        sagarin_roster=sagarin_file,
        cfbd_roster=cfbd_file,
        data_dir=data_dir,
    )
    return yaml.safe_load((data_dir / f"teams-{season}.yaml").read_bytes())


def candidates(tmp_path: Path, season: int) -> str:
    return (tmp_path / "crosswalk" / f"_candidates-{season}.yaml").read_text(encoding="utf-8")


def seed_prior(tmp_path: Path, season: int, entries: dict) -> Path:
    """Write a season's mapping the way a human leaves it.

    Used instead of running `bootstrap` for the earlier season, because the rows
    that matter here are exactly the ones bootstrap cannot produce: a canonical id
    whose two vendor names disagree is a hand decision by definition.
    """
    data_dir = tmp_path / "crosswalk"
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"teams-{season}.yaml"
    path.write_bytes(yaml.safe_dump(entries, allow_unicode=True).encode("utf-8"))
    return path


#: The committed 2026 row for USC, which no exact-match run could have written.
USC_2026 = {
    "southern-california": {
        "cfbd": "USC",
        "cfbd_id": 30,
        "sagarin": "Southern California",
        "division": "FBS",
    },
    "texas": {"cfbd": "Texas", "cfbd_id": 251, "sagarin": "Texas", "division": "FBS"},
}


# --- the first season ---------------------------------------------------------


class TestTheFirstSeason:
    """Nothing to inherit from, so every id is minted. Unchanged behaviour."""

    def test_an_exact_match_is_written_with_a_minted_id(self, tmp_path):
        entries = run(tmp_path, 2026, sagarin=["Texas"], cfbd=[TEXAS, USC])
        assert set(entries) == {"texas"}

    def test_a_name_the_vendors_spell_differently_is_left_to_a_human(self, tmp_path):
        """`"Southern California"` and `"USC"` are not an exact match, and SPEC 6.3
        forbids the similarity score from deciding it — the worked example is that
        this exact pair scores 0.09.
        """
        entries = run(tmp_path, 2026, sagarin=["Southern California"], cfbd=[USC])
        assert entries is None or "southern-california" not in (entries or {})
        assert "'Southern California'" in candidates(tmp_path, 2026)

    def test_which_is_where_the_usc_id_actually_came_from(self, tmp_path):
        """**The provenance of `southern-california`.**

        Not an auto-match — bootstrap never matched that row. The candidates file
        offers a pre-filled key built from the Sagarin spelling, and whoever
        decided the row accepted it. Same minting rule, the other code path.
        """
        run(tmp_path, 2026, sagarin=["Southern California"], cfbd=[USC])
        assert "southern-california:" in candidates(tmp_path, 2026)
        assert canonical_slug("Southern California") == "southern-california"

    def test_no_earlier_season_means_nothing_to_inherit(self, tmp_path):
        assert inherited_ids(2026, data_dir=tmp_path / "nowhere") == {}


# --- the season after ---------------------------------------------------------


class TestARenameBetweenSeasons:
    """**The discriminating case.** Sagarin respells a team; the id must not move.

    Without inheritance every assertion here still produces a valid, loadable,
    fully-resolving crosswalk — with the team under a second identity.
    """

    @pytest.fixture
    def after_2026(self, tmp_path):
        """2026 as it is actually committed: USC under `southern-california`."""
        seed_prior(tmp_path, 2026, USC_2026)
        return tmp_path

    def test_the_id_is_carried_over_not_re_derived(self, after_2026):
        """Sagarin switches to `USC`. Re-deriving would mint `usc`; inheriting
        keeps `southern-california`, and the team keeps one history.
        """
        entries = run(after_2026, 2027, sagarin=["USC", "Texas"], cfbd=[USC, TEXAS])
        assert "southern-california" in entries
        assert "usc" not in entries

    def test_the_name_column_records_the_rename(self, after_2026):
        """The id is frozen; the spelling is not. That is the split SPEC 6.1 wants
        — "a vendor renaming a team rewrites one line here rather than every
        historical row".
        """
        entries = run(after_2026, 2027, sagarin=["USC", "Texas"], cfbd=[USC, TEXAS])
        assert entries["southern-california"]["sagarin"] == "USC"
        assert entries["southern-california"]["cfbd_id"] == 30

    def test_a_cfbd_rename_alone_is_resolved_by_last_seasons_decision(self, after_2026):
        """**What makes a hand decision durable.**

        CFBD respells the team and Sagarin does not. Name equality between the two
        rosters cannot see the pair at all — that is what put this row in front of
        a human in 2026. But 2026 recorded that `"Southern California"` *is*
        cfbd_id 30, so 2027 resolves it without asking again, under the same id.

        Without this pass all 32 rows whose vendors disagree return to the
        candidates pile every season, and the only thing preventing a re-mint is
        whether whoever re-decides them reads a comment.
        """
        renamed = {"id": 30, "school": "Southern Cal", "classification": "fbs"}
        entries = run(
            after_2026,
            2027,
            sagarin=["Southern California", "Texas"],
            cfbd=[renamed, TEXAS],
        )
        assert entries["southern-california"]["cfbd"] == "Southern Cal"
        assert entries["southern-california"]["cfbd_id"] == 30

    def test_both_vendors_renaming_at_once_goes_back_to_a_human(self, after_2026):
        """The honest limit. Sagarin says `USC`, CFBD says `Southern Cal`, and
        2026 recorded `Southern California` — so nothing links the two rows and
        no rule could without guessing, which SPEC 6.3 forbids.

        What the tooling owes the person is the id the team already holds, and the
        candidates file carries it.
        """
        renamed = {"id": 30, "school": "Southern Cal", "classification": "fbs"}
        entries = run(after_2026, 2027, sagarin=["USC", "Texas"], cfbd=[renamed, TEXAS])
        assert "southern-california" not in entries
        assert "was: southern-california" in candidates(after_2026, 2027)

    def test_a_resolved_name_is_not_also_listed_as_undecided(self, after_2026):
        """**A row cannot be both decided and pending.**

        CFBD respells the team, so `"Southern California"` never appears in this
        season's CFBD roster and name equality cannot see it -- but the previous
        season's decision resolves it, and it is written into teams-2027.yaml.
        The candidates file asked the wrong question ("is this name in the CFBD
        roster?") instead of the right one ("did this run resolve it?"), so it
        listed the row a second time.

        Two things made that worse than a stray line. The block came with no
        suggestions under it, because the CFBD row it matched is correctly no
        longer unclaimed -- so it read as a team with no possible partner. And
        the file says to move decided rows into teams-2027.yaml, which would
        duplicate a canonical id that is already there; PyYAML keeps the last of
        two identical keys and would silently drop the inherited row for a
        hand-filled one.
        """
        renamed = {"id": 30, "school": "Southern Cal", "classification": "fbs"}
        entries = run(
            after_2026,
            2027,
            sagarin=["Southern California", "Texas"],
            cfbd=[renamed, TEXAS],
        )
        assert "southern-california" in entries
        # The bare name appears in the header's SPEC 6.3 example, so match the two
        # shapes an *undecided* row actually takes: the quoted heading and the key.
        pending = candidates(after_2026, 2027)
        assert "# 'Southern California'" not in pending
        assert "southern-california:" not in pending

    def test_the_two_returned_counts_partition_the_roster(self, after_2026):
        """`(matched, undecided)` is what the CLI prints. They must not overlap:
        a run reporting 2 decided and 1 pending on a two-team roster is telling
        whoever reads it there is work left that does not exist.
        """
        renamed = {"id": 30, "school": "Southern Cal", "classification": "fbs"}
        data_dir = after_2026 / "crosswalk"
        sagarin_file, cfbd_file = rosters(
            after_2026, sagarin=["Southern California", "Texas"], cfbd=[renamed, TEXAS]
        )
        matched, undecided = bootstrap(
            season=2027,
            sagarin_roster=sagarin_file,
            cfbd_roster=cfbd_file,
            data_dir=data_dir,
        )
        assert matched + undecided == 2

    def test_a_team_that_did_not_change_is_unaffected(self, after_2026):
        """The control. Inheritance must not disturb the 234 that already agree."""
        entries = run(after_2026, 2027, sagarin=["USC", "Texas"], cfbd=[USC, TEXAS])
        assert entries["texas"]["cfbd_id"] == 251

    def test_a_genuinely_new_team_still_gets_a_fresh_id(self, after_2026):
        """Inheritance covers teams that existed. Promotion and expansion are real,
        and a season that could only reuse ids would refuse to grow.
        """
        entries = run(
            after_2026,
            2027,
            sagarin=["USC", "Texas", "Delaware"],
            cfbd=[USC, TEXAS, NEWCOMER],
        )
        assert entries["delaware"]["cfbd_id"] == 9999
        assert "southern-california" in entries

    def test_a_team_that_left_simply_does_not_appear(self, after_2026):
        entries = run(after_2026, 2027, sagarin=["USC"], cfbd=[USC, TEXAS])
        assert set(entries) == {"southern-california"}


class TestInheritedIds:
    def test_it_maps_cfbd_id_to_canonical_id(self, tmp_path):
        seed_prior(tmp_path, 2026, USC_2026)
        assert inherited_ids(2027, data_dir=tmp_path / "crosswalk") == {
            30: "southern-california",
            251: "texas",
        }

    def test_it_reads_the_most_recent_earlier_season(self, tmp_path):
        """Not `season - 1`. A gap year must not silently restart the numbering."""
        seed_prior(tmp_path, 2026, USC_2026)
        assert inherited_ids(2030, data_dir=tmp_path / "crosswalk")[30] == ("southern-california")

    def test_a_later_season_is_not_inherited_from(self, tmp_path):
        """Bootstrapping a backfill season must not take ids from the future,
        which would make the same run produce different files depending on what
        else had been generated.
        """
        seed_prior(tmp_path, 2026, USC_2026)
        assert inherited_ids(2025, data_dir=tmp_path / "crosswalk") == {}

    def test_two_entries_sharing_a_cfbd_id_raises(self, tmp_path):
        """The anchor has to be unique or it anchors nothing.

        Inheritance is a ``{cfbd_id: canonical_id}`` dict, so a duplicated id
        silently keeps one entry and drops the other: the dropped team is
        re-minted next season under whatever the vendor calls it, and the kept one
        inherits an id belonging to its twin. `load` validates neither the
        presence nor the uniqueness of `cfbd_id`, so nothing upstream catches it.
        """
        seed_prior(
            tmp_path,
            2026,
            {
                "southern-california": {
                    "cfbd": "USC",
                    "cfbd_id": 30,
                    "sagarin": "Southern California",
                    "division": "FBS",
                },
                "usc": {
                    "cfbd": "USC",
                    "cfbd_id": 30,
                    "sagarin": "USC",
                    "division": "FBS",
                },
            },
        )
        with pytest.raises(ValueError, match="claimed by two entries"):
            inherited_ids(2027, data_dir=tmp_path / "crosswalk")


class TestCollisions:
    def test_two_teams_claiming_one_id_raises(self, tmp_path):
        """Reachable when a rename makes a *new* team slug into an *old* team's id.

        Left alone the two would overwrite each other in a dict, leaving the
        season one team short and the survivor holding the loser's history — the
        same failure `_index` refuses within a season, arriving from the other
        direction.
        """
        seed_prior(tmp_path, 2026, USC_2026)
        impostor = {"id": 4242, "school": "Southern California", "classification": "fbs"}

        with pytest.raises(ValueError, match="southern-california"):
            run(
                tmp_path,
                2027,
                sagarin=["USC", "Southern California"],
                cfbd=[USC, impostor],
            )

    def test_the_message_names_both_claimants(self, tmp_path):
        seed_prior(tmp_path, 2026, USC_2026)
        impostor = {"id": 4242, "school": "Southern California", "classification": "fbs"}

        with pytest.raises(ValueError) as excinfo:
            run(
                tmp_path,
                2027,
                sagarin=["USC", "Southern California"],
                cfbd=[USC, impostor],
            )
        assert "USC" in str(excinfo.value)


class TestTheGeneratedFileSaysWhereIdsCameFrom:
    """The header the generator writes is read by whoever edits the file by hand,
    and it used to claim the ids were vendor-neutral. They are not.
    """

    def test_a_first_season_says_the_ids_were_minted(self, tmp_path):
        run(tmp_path, 2026, sagarin=["Texas"], cfbd=[TEXAS])
        header = (tmp_path / "crosswalk" / "teams-2026.yaml").read_text(encoding="utf-8")
        assert "minted" in header
        assert "not vendor-neutral" in header

    def test_a_later_season_counts_what_it_carried_over(self, tmp_path):
        seed_prior(tmp_path, 2026, USC_2026)
        run(
            tmp_path,
            2027,
            sagarin=["USC", "Texas", "Delaware"],
            cfbd=[USC, TEXAS, NEWCOMER],
        )
        header = (tmp_path / "crosswalk" / "teams-2027.yaml").read_text(encoding="utf-8")
        assert "2 of these ids were carried over" in header

    def test_the_candidates_file_shows_the_id_a_team_already_had(self, tmp_path):
        """The other half of the fix, and the one a human acts on.

        `southern-california` was accepted from a pre-filled candidate key. If a
        later season sends that team back through the candidates path, the file has
        to say which id it already holds — otherwise the person re-deciding the row
        mints a second one with no way of knowing.
        """
        seed_prior(tmp_path, 2026, USC_2026)
        run(tmp_path, 2027, sagarin=["Southern Cal"], cfbd=[USC])
        assert "was: southern-california" in candidates(tmp_path, 2027)


# --- the committed file -------------------------------------------------------


class TestTheCommittedSeason:
    """2026 is the first season, so there is nothing for it to have inherited.
    What matters is that it is internally consistent enough to be inherited *from*.
    """

    def test_every_entry_carries_a_cfbd_id(self):
        """Inheritance is keyed on it. An entry without one could never be carried
        forward, and would be re-minted under whatever the vendor called it next.
        """
        entries = yaml.safe_load(CROSSWALK_FILE.read_bytes())
        missing = [c for c, e in entries.items() if e.get("cfbd_id") is None]
        assert missing == []

    def test_no_two_teams_share_a_cfbd_id(self):
        """Two teams under one id would make inheritance ambiguous, and the loser
        would be re-minted next season."""
        entries = yaml.safe_load(CROSSWALK_FILE.read_bytes())
        ids = [e["cfbd_id"] for e in entries.values()]
        assert len(ids) == len(set(ids))

    def test_the_ids_that_differ_from_the_cfbd_spelling_are_the_ones_at_risk(self):
        """Documents the exposure rather than asserting a preference.

        These are the entries where the two vendors disagree on a name, so they
        are the ones a rename could move. The count is pinned so that it changing
        is a deliberate edit rather than a surprise.
        """
        entries = yaml.safe_load(CROSSWALK_FILE.read_bytes())
        divergent = [
            canonical
            for canonical, entry in entries.items()
            if canonical != canonical_slug(entry["cfbd"])
        ]
        assert len(divergent) == 31
        assert "southern-california" in divergent

    def test_the_committed_file_still_loads(self):
        assert len(load(2026).entries) == 266
