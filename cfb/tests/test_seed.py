"""Seeding Elo from the Sagarin preseason page (SPEC-phase1 3.2).

Against the **real golden capture**, not a synthetic fixture. The numbers §3.2
publishes — Ohio State 2486, Texas 2358, Massachusetts 605 — were computed from
that page, and a synthetic fixture would only assert that the formula is the
formula. The whole reason the seed is defensible is what the real page contains
(a 67.2-point FBS spread, a 25.8-point division gap), so the real page is what
these tests read.

**The centring is the part that can silently be wrong.** `1500 + (rating - mean)
* 28` looks correct under any `mean`, and picking the all-266 mean instead of the
FBS mean shifts every rating by **367 Elo** — Ohio State becomes 2853 — while
leaving every relative gap intact and every internal-consistency check passing.
Only an absolute assertion catches it, which is why the three published numbers
are hardcoded here rather than derived.

**Signatures are proposals; the exception is not.** §3.2 gives `seed(snapshot,
crosswalk) -> Ratings`, and §9 now names `SeedStateError` for the in-season
refusal, so that is what the tests below assert. Asserting `CfbError` would have
passed on any failure at all -- including the `UnmappedTeamError` a broken
crosswalk raises three lines earlier -- which is the one thing a test of a
refusal must not do. `Ratings` is exercised only as a mapping of canonical id to
float.
"""

import statistics
from datetime import UTC, date, datetime
from itertools import combinations
from pathlib import Path

import pytest

from cfb.crosswalk import load as load_crosswalk
from cfb.elo import ELO_PER_POINT
from cfb.elo.seed import seed
from cfb.errors import SeedStateError
from cfb.models import SagarinSnapshot
from cfb.parsers.sagarin_predictions import parse_predictions
from cfb.parsers.sagarin_ratings import (
    parse_hfa,
    parse_page_date_stamp,
    parse_page_state,
    parse_ratings,
)

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "sagarin_2026_preseason.txt"

#: The three §3.2 publishes, and the FCS median it names alongside them.
#:
#: **These move every time ``ELO_PER_POINT`` does**, because a seed is
#: ``1500 + (rating - mean) * ELO_PER_POINT`` and the scale is the whole of it.
#: Across the three scales this project has shipped:
#:
#: =============  ====  ====  ====
#: at             28    20    16
#: =============  ====  ====  ====
#: Ohio State     2486  2204  2063
#: Texas          2358  2113  1990
#: Massachusetts  605   861   989
#: FCS median     701   929   1043
#: =============  ====  ====  ====
#:
#: Every *gap* scales with the constant and every *predicted margin* is unchanged,
#: which is the identity `test_the_seed_identity_survives_any_scale` pins and the
#: reason SPEC-phase1 3.2 calls an in-season rescale safe to make.
OHIO_STATE = 2063
TEXAS = 1990
MASSACHUSETTS = 989
FCS_MEDIAN = 1043

#: What centring on the all-266 mean would produce instead. Present so the test
#: that rules it out names the number it is ruling out.
OHIO_STATE_IF_ALL_266_CENTRED = 2273


@pytest.fixture(scope="module")
def page() -> str:
    return GOLDEN.read_bytes().decode("utf-8")


@pytest.fixture(scope="module")
def snapshot(page) -> SagarinSnapshot:
    return SagarinSnapshot(
        fetched_at=datetime(2026, 8, 28, 17, 20, 6, tzinfo=UTC),
        page_date_stamp=parse_page_date_stamp(page),
        page_state=parse_page_state(page),
        hfa=parse_hfa(page),
        teams=parse_ratings(page),
        predictions=parse_predictions(page),
    )


@pytest.fixture(scope="module")
def crosswalk():
    return load_crosswalk(2026)


@pytest.fixture(scope="module")
def ratings(snapshot, crosswalk):
    return seed(snapshot, crosswalk)


@pytest.fixture(scope="module")
def by_canonical(snapshot, crosswalk) -> dict[str, float]:
    """Sagarin RATING keyed the same way the seed is, for the pair checks."""
    return {crosswalk.from_sagarin(t.name): t.rating for t in snapshot.teams}


class TestThePublishedNumbers:
    """§3.2's three values, absolute. These are what catch a wrong centring."""

    @pytest.mark.parametrize(
        ("canonical", "expected"),
        [("ohio-state", OHIO_STATE), ("texas", TEXAS), ("massachusetts", MASSACHUSETTS)],
    )
    def test_the_named_teams_seed_to_the_published_values(self, ratings, canonical, expected):
        assert round(ratings[canonical]) == expected

    def test_the_fcs_median_lands_where_the_spec_says(self, ratings, crosswalk, snapshot):
        fcs = [
            ratings[crosswalk.from_sagarin(t.name)]
            for t in snapshot.teams
            if t.division == "AA"
        ]
        assert round(statistics.median(fcs)) == FCS_MEDIAN


class TestTheCentring:
    """The failure this file exists for: a plausible mean that is the wrong one."""

    def test_it_is_the_fbs_mean_not_the_all_266_mean(self, ratings):
        """Centring on all 266 shifts every rating up by 262 Elo.

        Every gap survives that shift, so the internal-consistency property below
        passes either way and so does anything relative. Only an absolute value
        distinguishes them.
        """
        assert round(ratings["ohio-state"]) != OHIO_STATE_IF_ALL_266_CENTRED
        assert round(ratings["ohio-state"]) == OHIO_STATE

    def test_the_fbs_field_straddles_1500(self, ratings, crosswalk, snapshot):
        """What centring on the FBS mean is *for* (§3.2).

        FBS either side of 1500, FCS falling where the ratings put it rather than
        being placed there by hand.
        """
        fbs = [
            ratings[crosswalk.from_sagarin(t.name)]
            for t in snapshot.teams
            if t.division == "A"
        ]
        assert statistics.mean(fbs) == pytest.approx(1500, abs=0.5)
        assert min(fbs) < 1500 < max(fbs)

    def test_it_is_this_snapshot_s_mean_not_a_stored_constant(self, snapshot, crosswalk):
        """Shift every rating on the page by a constant; nothing should move.

        A hardcoded 67.85 would look identical on the golden capture and be wrong
        on every other page Sagarin ever publishes. Re-centring on the shifted
        mean is the behaviour that survives next Tuesday.
        """
        shifted = snapshot.model_copy(
            update={
                "teams": [t.model_copy(update={"rating": t.rating + 10.0}) for t in snapshot.teams]
            }
        )

        before = seed(snapshot, crosswalk)
        after = seed(shifted, crosswalk)

        assert after["ohio-state"] == pytest.approx(before["ohio-state"], abs=1e-6)
        assert after["massachusetts"] == pytest.approx(before["massachusetts"], abs=1e-6)


class TestInternalConsistency:
    """The strongest property available, and it holds for every pair.

    An Elo gap divided by ELO_PER_POINT must reproduce Sagarin's own rating
    difference. It is true by construction, which is exactly why it is worth
    asserting: it fails the moment someone introduces a per-team adjustment, a
    division bonus, or a clamp into the seed, all of which look reasonable in
    isolation and all of which break the one guarantee the seed offers.
    """

    def test_every_pair_reproduces_the_sagarin_difference(self, ratings, by_canonical):
        # 266 teams, 35,245 pairs. Exhaustive because "for every pair" is the claim.
        worst = 0.0
        for a, b in combinations(sorted(by_canonical), 2):
            elo_points = (ratings[a] - ratings[b]) / ELO_PER_POINT
            sagarin_points = by_canonical[a] - by_canonical[b]
            worst = max(worst, abs(elo_points - sagarin_points))
        # 2/28 covers integer rounding on both ends if seed() rounds; if it does
        # not, this is exact.
        assert worst <= 2 / ELO_PER_POINT, f"worst pair disagrees by {worst:.4f} points"

    def test_the_offset_from_the_sagarin_scale_is_one_constant(self, ratings, by_canonical):
        """The O(n) form of the same claim, and the one that localises a break.

        If `elo/28 - rating` is not a single constant across all 266 teams, some
        team got a different transform from the rest — and this names which.
        """
        offsets = {
            canonical: ratings[canonical] / ELO_PER_POINT - rating
            for canonical, rating in by_canonical.items()
        }
        spread = max(offsets.values()) - min(offsets.values())
        assert spread <= 2 / ELO_PER_POINT, (
            f"transform is not uniform; spread {spread:.4f}, "
            f"outliers {sorted(offsets, key=offsets.get)[:3]}"
        )


class TestWhatIsSeeded:
    def test_every_rated_team_is_present(self, ratings, snapshot):
        assert len(ratings) == len(snapshot.teams) == 266

    def test_it_is_keyed_by_canonical_id_not_vendor_name(self, ratings):
        assert "ohio-state" in ratings
        assert "Ohio State" not in ratings

    def test_fbs_and_fcs_are_both_seeded(self, ratings, crosswalk, snapshot):
        """FCS games count (§3.4), so FCS teams need ratings."""
        divisions = {crosswalk.division(canonical) for canonical in ratings}
        assert divisions == {"FBS", "FCS"}

    def test_the_division_gap_survives_the_transform(self, ratings, crosswalk, snapshot):
        """25.8 points of separation is what stops Texas-vs-cupcake reading as a
        coin flip, which is the entire argument for seeding at all (§1.2).
        """
        fbs = [ratings[c] for c in ratings if crosswalk.division(c) == "FBS"]
        fcs = [ratings[c] for c in ratings if crosswalk.division(c) == "FCS"]
        gap_points = (statistics.median(fbs) - statistics.median(fcs)) / ELO_PER_POINT
        assert gap_points == pytest.approx(25.8, abs=0.2)


class TestSeedingIsPreseasonOnly:
    """§3.2: a mid-season re-seed silently discards every result learned so far.

    The refusal is the only thing standing between a rerun of the wrong command
    and a season's ratings quietly reverting to August.
    """

    @pytest.fixture(scope="module")
    def in_season(self, snapshot) -> SagarinSnapshot:
        return snapshot.model_copy(
            update={"page_state": "in-season", "page_date_stamp": date(2026, 9, 15)}
        )

    def test_an_in_season_snapshot_is_refused(self, in_season, crosswalk):
        with pytest.raises(SeedStateError):
            seed(in_season, crosswalk)

    def test_the_refusal_says_why(self, in_season, crosswalk):
        with pytest.raises(SeedStateError) as excinfo:
            seed(in_season, crosswalk)
        message = str(excinfo.value).lower()
        assert "preseason" in message or "in-season" in message

    def test_a_preseason_snapshot_is_accepted(self, snapshot, crosswalk):
        """The control. Without it the refusal is satisfied by refusing everything."""
        assert len(seed(snapshot, crosswalk)) == 266


class TestUnmappedNamesStillRaise:
    def test_a_name_the_crosswalk_cannot_resolve_raises(self, snapshot, tmp_path):
        """Seeding is a second place vendor names cross into canonical space.

        It gets the same treatment as the collector (Phase 0 §6.4): the run fails
        rather than seeding 265 teams and silently omitting one, which would
        leave that team unrated for the season with nothing saying so.
        """
        import yaml

        from cfb.crosswalk import load

        entries = yaml.safe_load(
            (Path(__file__).parent.parent / "data" / "crosswalk" / "teams-2026.yaml").read_text(
                encoding="utf-8"
            )
        )
        for canonical in [c for c, e in entries.items() if e["sagarin"] == "Ohio State"]:
            del entries[canonical]
        root = tmp_path / "crosswalk"
        root.mkdir()
        (root / "teams-2026.yaml").write_text(
            yaml.safe_dump(entries, allow_unicode=True), encoding="utf-8"
        )

        from cfb.errors import UnmappedTeamError

        with pytest.raises(UnmappedTeamError):
            seed(snapshot, load(2026, data_dir=root))


class TestTheScaleCancels:
    """**The seed identity survives any ``ELO_PER_POINT``, and that is why the
    rescale was safe to make mid-season.**

    ``seed`` multiplies a Sagarin rating difference by the scale and ``predict``
    divides an Elo gap by it, so the constant cancels and a week 1 predicted
    margin is bit-identical at 20, at 28, or at anything else. Only the Elo
    numbers themselves move.

    This matters for more than tidiness. §3.6's contamination series opens at a
    correlation of exactly 1.0 because a week 1 forecast reproduces Sagarin's
    PREDICTOR to the floating-point bit; if the scale disturbed that, changing it
    would silently retire the seed disclosure. It does not.

    The invariance holds **at the seed only.** Once `update` has run, ratings
    carry K-scaled deltas that do not rescale with the constant, so margins from
    week 2 onward genuinely differ -- which is the responsiveness change
    `test_k_moves_one_point_of_margin_per_unit` records.
    """

    def scaled_seed(self, snapshot, crosswalk, scale):
        """Seed at an arbitrary scale, using §3.2's formula directly.

        Written out rather than monkeypatching the module constant: the point is
        to compare the implementation against the formula, and patching would
        compare the implementation against itself.
        """
        fbs = [team.rating for team in snapshot.teams if team.division == "A"]
        mean = statistics.mean(fbs)
        return {
            crosswalk.from_sagarin(team.name): 1500 + (team.rating - mean) * scale
            for team in snapshot.teams
        }

    def margin(self, ratings, home, away, scale, hfa=2.41):
        return (ratings[home] - ratings[away]) / scale + hfa

    @pytest.mark.parametrize("scale", [14, 20, 25, 28, 40])
    def test_the_seed_identity_survives_any_scale(self, snapshot, crosswalk, scale):
        """Predicted margins are identical at every scale; only Elo moves."""
        here = self.scaled_seed(snapshot, crosswalk, scale)
        reference = self.scaled_seed(snapshot, crosswalk, 28)

        for home, away in [
            ("texas", "ohio-state"),
            ("ohio-state", "massachusetts"),
            ("texas", "texas-state"),
        ]:
            assert self.margin(here, home, away, scale) == pytest.approx(
                self.margin(reference, home, away, 28), abs=1e-9
            )

    def test_the_elo_values_do_move(self, snapshot, crosswalk):
        """The control. Without this the test above would pass on a no-op."""
        at_20 = self.scaled_seed(snapshot, crosswalk, 20)
        at_28 = self.scaled_seed(snapshot, crosswalk, 28)
        assert round(at_28["ohio-state"]) == 2486
        assert round(at_20["ohio-state"]) == 2204

    def test_the_shipped_seed_matches_the_formula_at_the_shipped_scale(
        self, ratings, snapshot, crosswalk
    ):
        """And the implementation is the formula, not merely consistent with it."""
        expected = self.scaled_seed(snapshot, crosswalk, ELO_PER_POINT)
        assert ratings == pytest.approx(expected, abs=1e-9)
