"""The committed game-supersession record (SPEC-phase1 5.2).

This file is about the *artifact*: what it accepts, what it refuses, and what it
answers. `test_scoring.py` covers what the join does with it.

The refusals carry the weight here. A supersession is the one join in this
pipeline a human asserts rather than derives, so the value of the file is exactly
the set of malformed states it will not load -- each of which would otherwise lose
or merge a game in a way nothing downstream could see.

The committed 2026 file is tested too, in `TestTheCommittedRecord`, because a
record that only works in fixtures certifies nothing about the week it was
written to repair.
"""

from datetime import date
from pathlib import Path

import pytest
import yaml

from cfb.crosswalk import load_supersessions, supersessions_path
from cfb.crosswalk.superseded import describe
from cfb.errors import SupersessionError

SEASON = 2026

#: The real one, as `data/crosswalk/games-superseded-2026.yaml` records it.
CAMPBELL_RETIRED = 401866625
CAMPBELL_CURRENT = 401917058


def entry(superseded_by: int, **overrides) -> dict:
    base = {
        "superseded_by": superseded_by,
        "season": SEASON,
        "week": 1,
        "home": "Campbell",
        "away": "Western Carolina",
        "noticed": date(2026, 9, 15),
    }
    return {**base, **overrides}


def write(tmp_path: Path, mapping, *, season: int = SEASON) -> Path:
    path = tmp_path / f"games-superseded-{season}.yaml"
    path.write_text(yaml.safe_dump(mapping), encoding="utf-8")
    return path


# --- what it answers ----------------------------------------------------------


class TestLookup:
    def test_a_recorded_id_resolves_to_its_replacement(self, tmp_path):
        write(tmp_path, {1: entry(2)})
        assert load_supersessions(SEASON, data_dir=tmp_path).current(1) == 2

    def test_an_unrecorded_id_is_its_own_answer(self, tmp_path):
        """Identity, not ``None``.

        This sits in front of every result lookup in `score_week`, so the ordinary
        game -- which is all of them but one a season -- has to pass through
        unchanged and without a branch at the call site.
        """
        write(tmp_path, {1: entry(2)})
        assert load_supersessions(SEASON, data_dir=tmp_path).current(99) == 99

    def test_it_reports_which_ids_are_superseded(self, tmp_path):
        record = load_supersessions(SEASON, data_dir=write(tmp_path, {1: entry(2)}).parent)
        assert record.is_superseded(1)
        assert not record.is_superseded(2)
        assert not record.is_superseded(99)

    def test_it_reads_backwards_so_a_scored_row_can_name_the_retired_id(self, tmp_path):
        """The scored document records both ids; it needs the reverse direction
        to say which forecast it graded.
        """
        record = load_supersessions(SEASON, data_dir=write(tmp_path, {1: entry(2)}).parent)
        assert record.retired_for(2) == 1
        assert record.retired_for(1) is None
        assert record.retired_for(99) is None

    def test_the_entry_carries_its_evidence(self, tmp_path):
        record = load_supersessions(SEASON, data_dir=write(tmp_path, {1: entry(2)}).parent)
        assert record.entry(1)["home"] == "Campbell"
        assert describe(record.entry(1)).startswith("Western Carolina at Campbell")

    def test_asking_for_an_unrecorded_entry_raises(self, tmp_path):
        record = load_supersessions(SEASON, data_dir=write(tmp_path, {1: entry(2)}).parent)
        with pytest.raises(SupersessionError, match="no supersession recorded for game 99"):
            record.entry(99)


# --- absence is ordinary ------------------------------------------------------


class TestAbsence:
    def test_a_missing_file_is_an_empty_mapping(self, tmp_path):
        """Unlike the team crosswalk, where absence is fatal.

        Most seasons need no entries, and an empty mapping relaxes nothing: every
        join it does not cover is the strict join that was already there.
        """
        record = load_supersessions(SEASON, data_dir=tmp_path)
        assert len(record) == 0
        assert record.current(1) == 1

    def test_a_file_holding_only_comments_is_an_empty_mapping(self, tmp_path):
        path = tmp_path / f"games-superseded-{SEASON}.yaml"
        path.write_text("# no supersessions this season\n", encoding="utf-8")
        assert len(load_supersessions(SEASON, data_dir=tmp_path)) == 0

    def test_a_file_that_is_not_a_mapping_raises(self, tmp_path):
        path = tmp_path / f"games-superseded-{SEASON}.yaml"
        path.write_text("- 401866625\n", encoding="utf-8")
        with pytest.raises(SupersessionError, match="not a mapping"):
            load_supersessions(SEASON, data_dir=tmp_path)


# --- the refusals -------------------------------------------------------------


class TestItRefusesAMappingThatWouldLoseAGame:
    """Each of these loads cleanly if the check is removed, and each then drops or
    merges a game somewhere no downstream check can see it.
    """

    def test_a_chain_is_refused_rather_than_followed(self, tmp_path):
        """``a -> b -> c`` where ``b`` is gone too.

        Followed, the answer depends on how far the resolver chose to walk;
        refused, the fix is one edited line and git keeps the intermediate step.
        """
        write(tmp_path, {1: entry(2), 2: entry(3)})
        with pytest.raises(SupersessionError, match="itself superseded by 3"):
            load_supersessions(SEASON, data_dir=tmp_path)

    def test_two_retired_ids_claiming_one_replacement_are_refused(self, tmp_path):
        """Two predicted games collapsing onto one result, which loses one of
        them from the scored set with nothing going red.
        """
        write(tmp_path, {1: entry(3), 2: entry(3)})
        with pytest.raises(SupersessionError, match="both claim to be superseded by 3"):
            load_supersessions(SEASON, data_dir=tmp_path)

    def test_a_self_reference_is_refused(self, tmp_path):
        write(tmp_path, {1: entry(1)})
        with pytest.raises(SupersessionError, match="supersedes itself"):
            load_supersessions(SEASON, data_dir=tmp_path)

    def test_another_seasons_entry_is_refused(self, tmp_path):
        """A played season's joins are frozen. An entry that names 2025 inside
        2026's file is either a typo or an attempt to edit a closed season.
        """
        write(tmp_path, {1: entry(2, season=2025)})
        with pytest.raises(SupersessionError, match="names season 2025"):
            load_supersessions(SEASON, data_dir=tmp_path)


class TestItRefusesARecordAReviewerCannotCheck:
    """The mapping is an assertion, so the evidence is not decoration."""

    @pytest.mark.parametrize(
        "field", ["away", "home", "noticed", "season", "superseded_by", "week"]
    )
    def test_every_required_field_is_required(self, tmp_path, field):
        record = entry(2)
        del record[field]
        write(tmp_path, {1: record})
        with pytest.raises(SupersessionError, match=f"missing.*{field}"):
            load_supersessions(SEASON, data_dir=tmp_path)

    def test_a_quoted_key_is_refused(self, tmp_path):
        """A string key reads as a game id and never matches one."""
        path = tmp_path / f"games-superseded-{SEASON}.yaml"
        path.write_text(
            "'401866625':\n  superseded_by: 401917058\n  season: 2026\n  week: 1\n"
            "  home: Campbell\n  away: Western Carolina\n  noticed: 2026-09-15\n",
            encoding="utf-8",
        )
        with pytest.raises(SupersessionError, match="is not a CFBD game id"):
            load_supersessions(SEASON, data_dir=tmp_path)

    def test_a_non_integer_replacement_is_refused(self, tmp_path):
        write(tmp_path, {1: entry("401917058")})
        with pytest.raises(SupersessionError, match="which is not a CFBD game id"):
            load_supersessions(SEASON, data_dir=tmp_path)

    def test_an_entry_that_is_not_a_mapping_is_refused(self, tmp_path):
        write(tmp_path, {1: 401917058})
        with pytest.raises(SupersessionError, match="not a mapping of fields"):
            load_supersessions(SEASON, data_dir=tmp_path)


# --- the real file ------------------------------------------------------------


class TestTheCommittedRecord:
    """The 2026 file as committed. A record that only works in fixtures certifies
    nothing about the week it was written to repair.
    """

    def test_it_loads(self):
        assert len(load_supersessions(SEASON)) >= 1

    def test_it_holds_the_campbell_re_id(self):
        record = load_supersessions(SEASON)
        assert record.current(CAMPBELL_RETIRED) == CAMPBELL_CURRENT
        assert record.retired_for(CAMPBELL_CURRENT) == CAMPBELL_RETIRED

    def test_the_campbell_entry_names_the_fixture_and_the_week(self):
        found = load_supersessions(SEASON).entry(CAMPBELL_RETIRED)
        assert (found["home"], found["away"]) == ("Campbell", "Western Carolina")
        assert found["week"] == 1
        assert found["season"] == SEASON

    def test_it_lives_where_the_team_crosswalk_lives(self):
        """One `crosswalk_dir` points a backfill or a test at a whole alternative
        set of join artifacts, which only works while both are in one directory.
        """
        assert supersessions_path(SEASON).parent.name == "crosswalk"
        assert supersessions_path(SEASON).is_file()
