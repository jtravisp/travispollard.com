"""`/games` returns every division, and the model rates two of them.

**Written after the first real capture, which is the only reason it exists.**
Every fixture in this suite before it was three or four FBS/FCS games, so nothing
could have caught what the vendor actually sends: week 1 of 2026 came back with
455 games — 110 D-III, 109 D-II, 72 FCS-FCS, 51 FBS-FBS, 48 FBS-FCS, 28
FCS-vs-D-II, and 37 against schools CFBD does not classify at all. Only 171 have
both teams in the crosswalk. `cfb predict` failed on the first D-II team name.

The rule under test has three parts and the third is the subtle one:

    both sides fbs/fcs        in
    either side ii/iii        out
    one classified, one not   out  -- an NCAA team's unclassified opponent is
                                     an NAIA school, and there are nine on the
                                     week 1 slate
    neither classified        ASK THE CAPTURE

That last line is what keeps this a *selection* rather than a filter over
failures, and it is answered by the file the row came out of rather than by the
row. A capture where the vendor classified nobody is one this project has no
division evidence about, so every row stays in, the crosswalk remains the
authority and an unmapped name still raises — which `cfb/CLAUDE.md` requires and
which a filter would have quietly turned into a drop. It is also why the ~50
fixtures written before this rule existed still work: none of them set a
classification.

**A capture that classifies almost everybody is the opposite case, and reading it
per row inverted the answer.** CFBD carried Oklahoma Panhandle (NAIA) at
Schreiner (D-III) in 2026 week 2 as `homeClassification: "ii"`, then dropped the
field to null between the 09-14 and 09-15 captures with nothing else in the file
changing — 303 rows, 302 of them still classified. Per row that promoted an
NAIA-vs-D-III game into the modelled set and stopped the season's scoring on an
unmapped team name. Per capture, the 302 rows beside it say what the blank means.
"""

from datetime import UTC, datetime

import pytest

from cfb.sources import MODELLED_DIVISIONS, RawGame, week_slate
from cfb.storage import MemorySnapshotStore
from test_replay import SEASON, cfbd_game, put_games

KICKOFF = datetime(2026, 9, 5, 19, 0, tzinfo=UTC)
PULLED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def game(*, home_division: str | None, away_division: str | None, game_id: int = 1) -> RawGame:
    row = cfbd_game(
        game_id=game_id,
        week=1,
        kickoff=KICKOFF,
        home="Texas",
        away="Ohio State",
        home_points=None,
        away_points=None,
    )
    # The vendor omits the key entirely for a school in no NCAA division rather
    # than sending null, so absence is modelled as absence.
    if home_division is not None:
        row["homeClassification"] = home_division
    if away_division is not None:
        row["awayClassification"] = away_division
    return RawGame.model_validate(row)


class TestWhatTheModelRates:
    def test_the_two_divisions_sagarin_covers(self):
        """138 FBS and 128 FCS is the whole rated universe."""
        assert MODELLED_DIVISIONS == {"fbs", "fcs"}

    @pytest.mark.parametrize(
        ("home", "away"),
        [("fbs", "fbs"), ("fcs", "fcs"), ("fbs", "fcs"), ("fcs", "fbs")],
    )
    def test_two_division_one_teams_are_in(self, home, away):
        assert game(home_division=home, away_division=away).is_modelled(capture_classifies=True)

    @pytest.mark.parametrize(
        ("home", "away"),
        [("ii", "ii"), ("iii", "iii"), ("fcs", "ii"), ("ii", "fcs"), ("fbs", "iii")],
    )
    def test_anything_below_fcs_is_out(self, home, away):
        assert not game(home_division=home, away_division=away).is_modelled(
            capture_classifies=True
        )

    def test_case_is_not_load_bearing(self):
        """CFBD sends lowercase today. A vendor that starts sending "FBS" should
        not silently empty the slate."""
        assert game(home_division="FBS", away_division="Fcs").is_modelled(
            capture_classifies=True
        )


class TestTheAsymmetryThatMakesItASelection:
    def test_neither_classified_is_in_when_the_capture_classifies_nobody(self):
        """**The rule that keeps the crosswalk the authority.**

        No division evidence means this project does not get to decide on
        division grounds, so the game stays in and an unmapped name raises the
        way `cfb/CLAUDE.md` says it must. Excluding here would convert that hard
        rule into a silent drop.
        """
        assert game(home_division=None, away_division=None).is_modelled(
            capture_classifies=False
        )

    def test_neither_classified_is_out_when_the_capture_classifies_others(self):
        """The same row, the opposite answer, decided by the file it came from.

        A capture that classifies almost every row and leaves one blank is not
        evidence-free; it is evidence with a hole, and the rows around the hole
        say what it means. Read per row instead, one dropped vendor field
        promotes an NAIA game into the slate -- which is what stopped 2026 week 2.
        """
        assert not game(home_division=None, away_division=None).is_modelled(
            capture_classifies=True
        )

    def test_a_row_reports_whether_it_carries_any_classification(self):
        assert not game(home_division=None, away_division=None).has_classification
        assert game(home_division="fbs", away_division=None).has_classification
        assert game(home_division=None, away_division="fcs").has_classification

    @pytest.mark.parametrize("classified", ["fbs", "fcs"])
    def test_one_classified_and_one_not_is_out(self, classified):
        """An NCAA team's unclassified opponent is an NAIA school.

        Nine of these are on week 1's real slate — Northwestern (IA), Louisiana
        Christian, Kentucky Christian, Webber International and the rest. They
        have no rating and never will.
        """
        assert not game(home_division=classified, away_division=None).is_modelled(
            capture_classifies=True
        )
        assert not game(home_division=None, away_division=classified).is_modelled(
            capture_classifies=True
        )

    def test_the_committed_fixtures_are_the_neither_case(self):
        """Why ~50 pre-existing fixtures were unaffected by this rule landing."""
        row = cfbd_game(
            game_id=9, week=1, kickoff=KICKOFF, home="Texas", away="Ohio State",
            home_points=None, away_points=None,
        )
        assert "homeClassification" not in row
        assert RawGame.model_validate(row).is_modelled(capture_classifies=False)


class TestWeekSlateAppliesIt:
    def test_out_of_scope_games_never_reach_the_caller(self):
        store = MemorySnapshotStore()
        put_games(
            store,
            week="01",
            fetched_at=PULLED_AT,
            games=[
                {**cfbd_game(game_id=1, week=1, kickoff=KICKOFF, home="Texas",
                             away="Ohio State", home_points=None, away_points=None),
                 "homeClassification": "fbs", "awayClassification": "fbs"},
                {**cfbd_game(game_id=2, week=1, kickoff=KICKOFF, home="Delta State",
                             away="Northeastern State", home_points=None, away_points=None),
                 "homeClassification": "ii", "awayClassification": "ii"},
            ],
        )
        found, _ = week_slate(store, SEASON, lambda raw: True)
        assert [raw.id for raw, _ in found] == [1]

    def test_a_blank_row_is_dropped_when_the_capture_classifies_everything_else(self):
        """**2026 week 2, exactly as it arrived.**

        The vendor dropped one `homeClassification` and changed nothing else. Per
        row that reads as "no division evidence" and lets an NAIA game through;
        per capture, the rows beside it are the evidence.
        """
        store = MemorySnapshotStore()
        put_games(
            store,
            week="01",
            fetched_at=PULLED_AT,
            games=[
                {**cfbd_game(game_id=1, week=1, kickoff=KICKOFF, home="Texas",
                             away="Ohio State", home_points=None, away_points=None),
                 "homeClassification": "fbs", "awayClassification": "fbs"},
                # Oklahoma Panhandle (NAIA) at Schreiner (D-III), as the 09-15
                # capture holds it: both sides blank.
                cfbd_game(game_id=2, week=1, kickoff=KICKOFF, home="Oklahoma Panhandle",
                          away="Schreiner", home_points=47, away_points=29),
            ],
        )
        found, _ = week_slate(store, SEASON, lambda raw: True)
        assert [raw.id for raw, _ in found] == [1]

    def test_a_blank_row_is_kept_when_the_capture_classifies_nobody(self):
        """The evidence-free capture, unchanged. Every fixture older than the
        division rule is this case, and the crosswalk stays the authority.
        """
        store = MemorySnapshotStore()
        put_games(
            store,
            week="01",
            fetched_at=PULLED_AT,
            games=[
                cfbd_game(game_id=1, week=1, kickoff=KICKOFF, home="Texas",
                          away="Ohio State", home_points=None, away_points=None),
                cfbd_game(game_id=2, week=1, kickoff=KICKOFF, home="Alabama",
                          away="Georgia", home_points=None, away_points=None),
            ],
        )
        found, _ = week_slate(store, SEASON, lambda raw: True)
        assert [raw.id for raw, _ in found] == [1, 2]

    def test_each_capture_is_judged_by_its_own_evidence(self):
        """Scoped to the capture, not the run.

        An old classification-free capture must not make a complete one speak for
        it, nor the reverse: two files are two separate pieces of evidence.
        """
        store = MemorySnapshotStore()
        put_games(
            store,
            week="01",
            fetched_at=PULLED_AT,
            games=[
                cfbd_game(game_id=1, week=1, kickoff=KICKOFF, home="Texas",
                          away="Ohio State", home_points=None, away_points=None),
            ],
        )
        put_games(
            store,
            week="02",
            fetched_at=PULLED_AT,
            games=[
                {**cfbd_game(game_id=2, week=2, kickoff=KICKOFF, home="Alabama",
                             away="Georgia", home_points=None, away_points=None),
                 "homeClassification": "fbs", "awayClassification": "fbs"},
                cfbd_game(game_id=3, week=2, kickoff=KICKOFF, home="Oklahoma Panhandle",
                          away="Schreiner", home_points=None, away_points=None),
            ],
        )
        found, _ = week_slate(store, SEASON, lambda raw: True)
        # 1 survives its evidence-free capture; 3 does not survive one that
        # classifies its neighbour.
        assert sorted(raw.id for raw, _ in found) == [1, 2]

    def test_a_malformed_row_out_of_scope_does_not_redden_the_run(self):
        """**The exact shape that stopped the first production run.**

        `Delta State at Northeastern State` came back with `home=52` and
        `away=None` on a D-II game that had not kicked off. `is_partially_scored`
        is right to call that malformed, but policing a vendor's bookkeeping in a
        division this project never models would have failed a Friday over
        nothing. So the division filter runs first.
        """
        store = MemorySnapshotStore()
        put_games(
            store,
            week="01",
            fetched_at=PULLED_AT,
            games=[
                {**cfbd_game(game_id=1, week=1, kickoff=KICKOFF, home="Texas",
                             away="Ohio State", home_points=None, away_points=None),
                 "homeClassification": "fbs", "awayClassification": "fbs"},
                {**cfbd_game(game_id=2, week=1, kickoff=KICKOFF, home="Delta State",
                             away="Northeastern State", home_points=52, away_points=None),
                 "homeClassification": "ii", "awayClassification": "ii"},
            ],
        )
        found, _ = week_slate(store, SEASON, lambda raw: True)
        assert [raw.id for raw, _ in found] == [1]

    def test_a_malformed_row_in_scope_still_raises(self):
        """The filter narrows what is watched; it does not stop watching."""
        from cfb.errors import ReplayError

        store = MemorySnapshotStore()
        put_games(
            store,
            week="01",
            fetched_at=PULLED_AT,
            games=[
                {**cfbd_game(game_id=3, week=1, kickoff=KICKOFF, home="Texas",
                             away="Ohio State", home_points=52, away_points=None),
                 "homeClassification": "fbs", "awayClassification": "fbs"},
            ],
        )
        with pytest.raises(ReplayError, match="one score and not the other"):
            week_slate(store, SEASON, lambda raw: True)
