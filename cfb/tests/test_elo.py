"""The Elo update step and the two prediction formulas (SPEC-phase1 3.1, 3.4).

Three cases worked by hand and asserted to exact values. Deriving the expectation
from the same formula the implementation uses would test that the code equals
itself; these constants were computed independently and written down.

## `elo_diff_winner` is signed, from the winner's perspective

§3.4 leaves it ambiguous and the two readings disagree on exactly one kind of
game — an upset — which is the kind that matters most.

    mov_mult = ln(|margin| + 1) * (2.2 / (elo_diff_winner * 0.001 + 2.2))

Read as **signed**, `elo_diff_winner` is the winner's pregame rating advantage:
positive when the favourite won, negative when the underdog did. Read as
**absolute**, it is the size of the gap regardless of who won.

Signed is the confirmed reading (§3.4), and the reason is informational rather
than autocorrelative. An upset is a low-probability event; a low-probability
event carries more information than a likely one; a result the model did not
expect should change it more than one it did. Signed, that is what happens — the
denominator shrinks below 2.2, the multiplier grows, and the upset moves ratings
further.

The autocorrelation argument does not settle this. It explains what the term does
for *favourites*: a strong team running up the score on a weak one must not gain
more than the result warrants. That leaves the underdog direction unspecified
rather than decided, so it cannot be the reason for choosing signed over
absolute.

Absolute damps favourite blowouts and underdog blowouts identically. It would
mean Massachusetts beating Ohio State by 20 teaches the model exactly as much as
Ohio State beating Massachusetts by 20.

`test_an_upset_uses_the_signed_gap` is written to fail under the absolute
reading: 28.373 signed against 20.972 absolute, on the same game.

## What is not here

Clamping. §3.7 is presentational, applied at publish time; the update step and
the stored prediction both use unclamped probabilities. A clamp reaching this far
down would corrupt the Brier scores §5.3 computes.

## Signatures

§3.4 now states both, and they are what these tests call:

    update(ratings, game, *, hfa: float) -> Ratings
    predict(ratings, game, *, hfa: float) -> Prediction   # .predicted_margin, .win_probability

The HFA travels as a keyword rather than on the `Game` because it is a property
of the Sagarin snapshot the run read (§3.3) and not of the fixture. An earlier
draft of this file proposed that shape; §3.4 has since adopted it.
"""

import math

import pytest

from cfb.elo import (
    ELO_PER_POINT,
    MOV_DAMPING,
    MOV_DENOMINATOR_FLOOR,
    Game,
    K,
    mov_denominator,
    predict,
    update,
)
from cfb.errors import EloDomainError

# --- the three hand-worked cases ---------------------------------------------
#
# Each was computed independently of the implementation:
#
#   adj_home = elo_home + hfa * 28          adj_away = elo_away
#   expected = 1 / (1 + 10 ** (-(adj_home - adj_away) / 400))
#   signed   = (adj_home - adj_away) if home won else -(adj_home - adj_away)
#   mult     = ln(|margin| + 1) * (2.2 / (signed * 0.001 + 2.2))
#   delta    = K * mult * (actual - expected)

FAVOURITE = {
    "elo_home": 1700.0, "elo_away": 1500.0, "hfa": 2.5,
    "home_points": 31, "away_points": 21,          # home by 10
    "expected": 0.8255259873611817,
    "mov_mult": 2.1357771660552287,
    "delta": 7.452752245280393,
}

UPSET = {
    "elo_home": 1500.0, "elo_away": 1900.0, "hfa": 2.5,
    "home_points": 24, "away_points": 21,          # home by 3, as a 330-Elo underdog
    "expected": 0.13015005092569085,
    "mov_mult": 1.630934542493989,
    "delta": 28.373366574638556,
    #: What the absolute reading would produce on this same game.
    "delta_if_absolute": 20.971618772558934,
}

BLOWOUT = {
    "elo_home": 2000.0, "elo_away": 1400.0, "hfa": 3.0,
    "home_points": 56, "away_points": 14,          # home by 42
    "expected": 0.9808744720758243,
    "mov_mult": 2.8691540410977243,
    "delta": 1.0974817146355191,
    #: The same matchup decided by 3 instead of 42, to show the multiplier bites.
    "delta_if_margin_3": 0.4045072491844423,
}


def game(case: dict, *, home_points: int | None = None, away_points: int | None = None) -> Game:
    return Game(
        cfbd_game_id=1,
        home="home-team",
        away="away-team",
        home_points=case["home_points"] if home_points is None else home_points,
        away_points=case["away_points"] if away_points is None else away_points,
    )


def ratings_for(case: dict) -> dict[str, float]:
    return {"home-team": case["elo_home"], "away-team": case["elo_away"]}


def run(case: dict, **overrides) -> dict[str, float]:
    return update(ratings_for(case), game(case, **overrides), hfa=case["hfa"])


class TestTheConstants:
    def test_the_scale_is_28_elo_per_point(self):
        """§3.1. The seed, the margin formula and the update all read this."""
        assert ELO_PER_POINT == 28

    def test_k_is_20(self):
        assert K == 20


class TestAFavouriteWinningAsExpected:
    """1700 vs 1500 with 2.5 HFA, home by 10. Nothing surprising happens."""

    def test_the_home_rating_moves_by_the_worked_delta(self):
        after = run(FAVOURITE)
        assert after["home-team"] == pytest.approx(
            FAVOURITE["elo_home"] + FAVOURITE["delta"], abs=1e-9
        )

    def test_the_away_rating_moves_by_the_same_amount_downward(self):
        after = run(FAVOURITE)
        assert after["away-team"] == pytest.approx(
            FAVOURITE["elo_away"] - FAVOURITE["delta"], abs=1e-9
        )

    def test_the_move_is_modest_because_the_result_was_expected(self):
        """82.6% expected, so a win is worth ~7.5 Elo. The number is small on
        purpose: Elo should barely react to what it already predicted.
        """
        after = run(FAVOURITE)
        assert 7 < after["home-team"] - FAVOURITE["elo_home"] < 8


class TestAnUpset:
    """1500 vs 1900 with HFA, home wins by 3 — a 330-Elo underdog winning.

    The case that separates the two readings of `elo_diff_winner`.
    """

    def test_an_upset_uses_the_signed_gap(self):
        """**Fails under the absolute reading.** 28.373 against 20.972.

        Signed, the winner's gap is -330: the denominator falls to 1.87, the
        multiplier rises to 1.631, and the upset moves ratings hard. Absolute
        would use +330, damp the multiplier to 1.205, and treat the most
        informative result of the week like a routine one.
        """
        after = run(UPSET)
        moved = after["home-team"] - UPSET["elo_home"]

        assert moved == pytest.approx(UPSET["delta"], abs=1e-9)
        assert moved != pytest.approx(UPSET["delta_if_absolute"], abs=1e-6)

    def test_the_upset_moves_ratings_further_than_the_expected_win_did(self):
        """The property the signed reading exists to produce.

        A 3-point upset is worth ~28 Elo; a 10-point win by a favourite is worth
        ~7.5. Under the absolute reading the upset would be worth ~21 — still
        more, but for the wrong reason and by the wrong amount.
        """
        upset_move = run(UPSET)["home-team"] - UPSET["elo_home"]
        favourite_move = run(FAVOURITE)["home-team"] - FAVOURITE["elo_home"]
        assert upset_move > favourite_move * 3

    def test_the_loser_gives_up_exactly_what_the_winner_gains(self):
        after = run(UPSET)
        gained = after["home-team"] - UPSET["elo_home"]
        lost = UPSET["elo_away"] - after["away-team"]
        assert gained == pytest.approx(lost, abs=1e-9)


class TestABlowoutWhereTheMultiplierWorks:
    """2084 vs 1400 adjusted, home by 42. Expected 98.1%.

    The damping is doing real work here: a 42-point win by a team that was
    already a 98% favourite is worth about one Elo point.

    This is the favourite case, and the one place the autocorrelation argument
    genuinely applies — it is a claim about what the term does when the expected
    side wins. The module docstring above is about why that argument does not
    reach the upset direction.
    """

    def test_the_blowout_moves_the_worked_delta(self):
        after = run(BLOWOUT)
        assert after["home-team"] == pytest.approx(
            BLOWOUT["elo_home"] + BLOWOUT["delta"], abs=1e-9
        )

    def test_a_42_point_win_is_worth_barely_more_than_one_elo(self):
        """Not a rounding artefact — the point of the correction (§3.4).

        Without it a strong team could farm rating off weak opponents by running
        up scores, and the top of the table would inflate.
        """
        moved = run(BLOWOUT)["home-team"] - BLOWOUT["elo_home"]
        assert 1.0 < moved < 1.2

    def test_margin_still_matters_between_two_blowouts(self):
        """The multiplier damps; it does not flatten.

        Same teams, 42 points against 3: the move is ~2.7x larger. A correction
        that made margin irrelevant would be the opposite failure.
        """
        by_42 = run(BLOWOUT)["home-team"] - BLOWOUT["elo_home"]
        by_3 = run(BLOWOUT, home_points=17, away_points=14)["home-team"] - BLOWOUT["elo_home"]

        assert by_3 == pytest.approx(BLOWOUT["delta_if_margin_3"], abs=1e-9)
        assert by_42 / by_3 == pytest.approx(2.71, abs=0.02)


class TestTheUpdateContract:
    def test_ratings_are_returned_not_mutated(self, ):
        """The project's frozen-evidence idiom: a rating is what the model
        believed at a moment, and a function that edits it in place makes the
        before-state unrecoverable mid-replay.
        """
        before = ratings_for(FAVOURITE)
        snapshot = dict(before)
        update(before, game(FAVOURITE), hfa=FAVOURITE["hfa"])
        assert before == snapshot

    def test_teams_not_in_the_game_are_untouched(self):
        ratings = {**ratings_for(FAVOURITE), "bystander": 1234.5}
        after = update(ratings, game(FAVOURITE), hfa=FAVOURITE["hfa"])
        assert after["bystander"] == 1234.5

    def test_the_total_rating_in_the_system_is_conserved(self):
        """Zero-sum. Elo that leaks or creates rating drifts the whole scale, and
        the drift is invisible in any single game.
        """
        before = ratings_for(BLOWOUT)
        after = run(BLOWOUT)
        assert sum(after.values()) == pytest.approx(sum(before.values()), abs=1e-9)

    def test_an_unrated_team_raises(self):
        """A game naming a team with no rating means the seed missed it or the
        crosswalk resolved to something the ratings do not have. Both are worth a
        red run rather than a default of 1500.
        """
        from cfb.errors import CfbError

        with pytest.raises(CfbError):
            update({"home-team": 1500.0}, game(FAVOURITE), hfa=2.5)


class TestPrediction:
    """§3.1's two formulas, and the PRD's requirement that they cannot disagree."""

    def test_margin_is_the_elo_gap_over_the_scale_plus_hfa(self):
        prediction = predict(
            {"home-team": 1700.0, "away-team": 1500.0}, game(FAVOURITE), hfa=2.5
        )
        assert prediction.predicted_margin == pytest.approx(200 / 28 + 2.5, abs=1e-9)

    @pytest.mark.parametrize(
        ("margin", "probability"),
        [(1, 0.540), (3, 0.619), (7, 0.756), (10, 0.834), (14, 0.905), (21, 0.967)],
    )
    def test_the_spec_3_1_calibration_table(self, margin, probability):
        """The table §3.1 uses to justify choosing 28 over 25.

        It is the closest thing this model has to a claim about the real world,
        so it is pinned: if the scale or the divisor changes, these move and the
        spec's argument has to be rewritten rather than quietly invalidated.
        """
        elo_gap = margin * ELO_PER_POINT
        prediction = predict(
            {"home-team": 1500.0 + elo_gap, "away-team": 1500.0}, game(FAVOURITE), hfa=0.0
        )
        assert prediction.win_probability == pytest.approx(probability, abs=0.001)

    def test_margin_and_probability_cannot_disagree(self):
        """The PRD's requirement, stated as an identity rather than a hope.

        Both derive from one Elo output, so the probability is always the
        logistic of the margin times the scale. A refactor that computed them
        from different quantities would break this and nothing else.
        """
        for elo_home, elo_away, hfa in [
            (1700, 1500, 2.5), (1500, 1900, 2.5), (2486, 605, 0.0), (1500, 1500, 3.0)
        ]:
            prediction = predict(
                {"home-team": float(elo_home), "away-team": float(elo_away)},
                game(FAVOURITE),
                hfa=hfa,
            )
            implied = 1 / (
                1 + 10 ** (-(prediction.predicted_margin * ELO_PER_POINT) / 400)
            )
            assert prediction.win_probability == pytest.approx(implied, abs=1e-12)

    def test_probabilities_are_not_clamped_here(self):
        """§3.7 is presentational and belongs to publish.

        Texas against an FCS median is a 59-point gap and the honest logistic
        answer is 0.99997. Clamping it here would corrupt the Brier scores §5.3
        computes on what the model actually said.
        """
        prediction = predict(
            {"home-team": 2358.0, "away-team": 701.0}, game(FAVOURITE), hfa=0.0
        )
        assert prediction.win_probability > 0.999
        assert prediction.win_probability != 0.999
        assert prediction.win_probability == pytest.approx(
            1 / (1 + 10 ** (-(2358 - 701) / 400)), abs=1e-12
        )


class TestNeutralSites:
    """§3.4: no home-field advantage at a neutral site, in `update` and `predict`.

    §4.2 makes home/away there "whatever CFBD says", so the designation is
    arbitrary — and an edge awarded on it is not a small bias in one direction but
    ~2.4 points of noise in whichever direction the vendor happened to list the
    teams. Both formulas are asserted because a fix applied to one of them would
    leave the prediction and the result scored against different games.
    """

    def test_a_neutral_game_gets_no_home_advantage(self):
        neutral = Game(
            cfbd_game_id=2, home="home-team", away="away-team",
            home_points=24, away_points=21, neutral_site=True,
        )
        with_hfa = update(ratings_for(FAVOURITE), neutral, hfa=2.5)
        without = update(ratings_for(FAVOURITE), neutral, hfa=0.0)
        assert with_hfa == without

    def test_a_neutral_prediction_has_no_home_advantage_in_the_margin(self):
        neutral = Game(
            cfbd_game_id=2, home="home-team", away="away-team",
            home_points=0, away_points=0, neutral_site=True,
        )
        prediction = predict({"home-team": 1700.0, "away-team": 1500.0}, neutral, hfa=2.5)
        assert prediction.predicted_margin == pytest.approx(200 / 28, abs=1e-9)


class TestTheMovDenominatorFloor:
    """§3.4's floor, and the failure it stands in front of.

    The denominator is `elo_diff_winner * 0.001 + 2.2` and the gap is signed, so a
    large enough upset walks it to zero and through. Past zero the multiplier is
    negative and **a bigger win lowers the winner's rating**: the model runs
    backwards on the most informative result of the season, produces ratings that
    are entirely plausible, and nothing anywhere goes red.

    **This is reachable on the current scale.** The 2026 seed spans 211 to 2486,
    so 39 of the top team's possible opponents would cross the floor by beating it
    and 5 would carry the denominator negative. §12's Phase 2 refit of
    `ELO_PER_POINT` widens the window; it does not open it.

    The clamp and the raise answer different questions and are asserted
    separately. The raise is what stops a clamped update from happening quietly,
    and every test below that goes through `update` is testing the raise.

    **The clamp cannot be reached through `update` at all** — the raise stands in
    front of it — so `test_the_clamp_holds_on_its_own` calls `mov_denominator`
    directly. Without that one, deleting the clamp would break nothing, and §3.4's
    defence in depth would be a comment rather than a property.
    """

    @staticmethod
    def game_won_from(disadvantage: float, *, margin: int = 10):
        """A home team `disadvantage` Elo below its opponent, winning by `margin`.

        HFA is zero at the call sites below so the requested gap is the gap the
        formula sees, rather than one offset by whatever the snapshot happens to
        say.
        """
        ratings = {"home-team": 1500.0, "away-team": 1500.0 + disadvantage}
        return ratings, Game(
            cfbd_game_id=9,
            home="home-team",
            away="away-team",
            home_points=14 + margin,
            away_points=14,
        )

    def test_the_floor_is_a_stated_constant(self):
        assert MOV_DENOMINATOR_FLOOR == 0.25

    def test_an_upset_just_inside_the_floor_still_applies(self):
        """1940 Elo of disadvantage: denominator 0.26, and an ordinary update.

        The control. Without it the guard is satisfied by refusing every upset,
        which would drop exactly the games §3.4 says count most.
        """
        ratings, game = self.game_won_from(1940)
        after = update(ratings, game, hfa=0.0)
        assert after["home-team"] > 1500.0

    def test_an_upset_past_the_floor_raises(self):
        """1960 Elo of disadvantage: denominator 0.24, under the floor."""
        ratings, game = self.game_won_from(1960)
        with pytest.raises(EloDomainError):
            update(ratings, game, hfa=0.0)

    def test_the_sign_flip_raises_rather_than_inverting(self):
        """2300 Elo of disadvantage: denominator -0.10 unclamped.

        The case the floor exists for. Unguarded this returns a *lower* rating for
        the winner, and every downstream check — conservation, team coverage, the
        plausibility of the numbers — passes on it.
        """
        ratings, game = self.game_won_from(2300, margin=42)
        with pytest.raises(EloDomainError):
            update(ratings, game, hfa=0.0)

    def test_the_message_names_the_gap_the_floor_and_what_to_look_at(self):
        ratings, game = self.game_won_from(1960)
        with pytest.raises(EloDomainError) as excinfo:
            update(ratings, game, hfa=0.0)
        message = str(excinfo.value)
        assert "1960" in message
        assert "0.25" in message
        assert "refitting" in message

    def test_hfa_counts_toward_the_gap(self):
        """The gap is the HFA-adjusted one, so the floor sits where the formula does.

        A guard that read the raw rating difference would sit ~67 Elo away from
        where the multiplier actually crosses, and would let through the games it
        exists to catch.
        """
        inside, game = self.game_won_from(1940)
        update(inside, game, hfa=0.0)  # 0.26: inside the floor with no HFA

        # Same 1940 gap, but the winner is on the road, so HFA widens what it
        # overcame instead of narrowing it: 0.24, and now under the floor.
        ratings = {"home-team": 1500.0 + 1940, "away-team": 1500.0}
        away_wins = Game(
            cfbd_game_id=10, home="home-team", away="away-team",
            home_points=14, away_points=24,
        )
        with pytest.raises(EloDomainError):
            update(ratings, away_wins, hfa=2.41)

    def test_a_clamped_multiplier_is_never_silently_applied(self):
        """The property the raise adds on top of the clamp.

        With the raise dropped this update would succeed on a clamped multiplier
        and move a rating by hundreds of Elo. Nothing comes back at all, and the
        ratings handed in are untouched.
        """
        ratings, game = self.game_won_from(2300, margin=42)
        with pytest.raises(EloDomainError):
            update(ratings, game, hfa=0.0)
        assert ratings == {"home-team": 1500.0, "away-team": 3800.0}

    @pytest.mark.parametrize("gap", [-1960, -2200, -2300, -10_000])
    def test_the_clamp_holds_on_its_own(self, gap):
        """The half of the guard `update` cannot demonstrate.

        Every one of these gaps drives the raw denominator to or past zero. The
        clamp is what makes the multiplier positive anyway, and this is the only
        test that touches it — going through `update` would hit the raise first
        and pass with the clamp deleted.
        """
        assert mov_denominator(gap) == MOV_DENOMINATOR_FLOOR
        assert MOV_DAMPING / mov_denominator(gap) > 0

    def test_the_clamp_leaves_ordinary_games_alone(self):
        """A floor that moved a normal game would rewrite the whole model."""
        for case in (FAVOURITE, UPSET, BLOWOUT):
            diff = case["elo_home"] + case["hfa"] * ELO_PER_POINT - case["elo_away"]
            signed = diff if case["home_points"] > case["away_points"] else -diff
            assert mov_denominator(signed) == pytest.approx(
                signed * 0.001 + MOV_DAMPING, abs=1e-12
            )


class TestGamesTheModelHasNoAnswerFor:
    """§3.4 defines `actual` for a win and for a loss, and for nothing else."""

    def test_a_tie_raises_rather_than_scoring_as_an_away_win(self):
        """`actual = 1.0 if home won else 0.0` reads a tie as a home loss.

        College football has decided games in overtime since 1996, so a 0-0 final
        is a cancelled game recorded as a score rather than a result. §12 owns the
        cancellation signal this is waiting on.
        """
        tie = Game(
            cfbd_game_id=11, home="home-team", away="away-team",
            home_points=0, away_points=0,
        )
        with pytest.raises(EloDomainError):
            update(ratings_for(FAVOURITE), tie, hfa=2.5)

    def test_an_unplayed_game_raises_rather_than_reading_null_as_zero(self):
        unplayed = Game(cfbd_game_id=12, home="home-team", away="away-team")
        with pytest.raises(EloDomainError):
            update(ratings_for(FAVOURITE), unplayed, hfa=2.5)


def test_the_worked_constants_are_self_consistent():
    """Guards the table at the top of this file rather than the implementation.

    If a constant here were mistyped the tests above would assert a wrong number
    confidently. This re-derives each delta from its own case's inputs, which is
    circular against the formula and not against the arithmetic.
    """
    for case in (FAVOURITE, UPSET, BLOWOUT):
        diff = case["elo_home"] + case["hfa"] * ELO_PER_POINT - case["elo_away"]
        expected = 1 / (1 + 10 ** (-diff / 400))
        margin = case["home_points"] - case["away_points"]
        signed = diff if margin > 0 else -diff
        mult = math.log(abs(margin) + 1) * (2.2 / (signed * 0.001 + 2.2))
        assert expected == pytest.approx(case["expected"], abs=1e-12)
        assert mult == pytest.approx(case["mov_mult"], abs=1e-12)
        assert K * mult * (1.0 - expected) == pytest.approx(case["delta"], abs=1e-12)
