"""Key construction (SPEC-phase0 2.1).

Every key in the bucket comes from here, and a key is the only thing that says
what a snapshot is. Nothing under ``raw/`` is ever deleted or renamed, so a key
built wrong is wrong permanently -- there is no migration, only a copy that
leaves the mistake in place beside it. That is why this file spends more
assertions on the shape of a string than the string appears to deserve.

``season`` is the partition value ``test_calendar.py`` deliberately does not
cover: SPEC 3.2 lists it for season-level CFBD resources, so it comes from what
is being fetched rather than from when, and no date resolves to it.

**These signatures are proposals.** SPEC 1 assigns "key construction" to
``manifest.py`` and SPEC 2.1 gives the layout, but no function names. Two seemed
to be the minimum: one that builds a snapshot key from the facts of a fetch, and
one that derives the manifest key beside it.
"""

from datetime import UTC, datetime

import pytest

from cfb.errors import WeekResolutionError
from cfb.manifest import manifest_key, snapshot_key

FETCHED = datetime(2026, 9, 16, 11, 3, 2, tzinfo=UTC)


class TestSagarinKeys:
    def test_matches_the_spec_example_exactly(self):
        """SPEC 2.1's first line, reproduced character for character."""
        assert snapshot_key(
            source="sagarin", season=2026, week="04", fetched_at=FETCHED
        ) == "raw/sagarin/season=2026/week=04/2026-09-16T110302Z.txt"

    def test_sagarin_has_no_resource_segment(self):
        """SPEC 2.1: Sagarin has one resource and omits the segment.

        A ``ratings/`` segment here would be harmless-looking and would put every
        Sagarin snapshot at a path the documented layout does not describe.
        """
        key = snapshot_key(source="sagarin", season=2026, week="04", fetched_at=FETCHED)
        assert key.count("/") == 4
        assert "ratings" not in key

    def test_the_timestamp_is_second_resolution_and_colon_free(self):
        """``%Y-%m-%dT%H%M%SZ`` -- ISO 8601 with the time separators dropped.

        Colons in an S3 key are legal and make the object miserable to handle from
        a shell, which SPEC 11's verification commands do.
        """
        key = snapshot_key(source="sagarin", season=2026, week="04", fetched_at=FETCHED)
        assert key.endswith("/2026-09-16T110302Z.txt")
        assert ":" not in key

    def test_two_runs_on_one_day_are_two_objects(self):
        """SPEC 2.1 says so outright, and it is what makes the store write-once.

        If the key were date-only, the second run of a day would collide with the
        first and ``put_bytes`` would refuse the fetch rather than store it.
        """
        second = datetime(2026, 9, 16, 18, 45, 10, tzinfo=UTC)
        assert snapshot_key(
            source="sagarin", season=2026, week="04", fetched_at=FETCHED
        ) != snapshot_key(source="sagarin", season=2026, week="04", fetched_at=second)


class TestCfbdKeys:
    def test_cfbd_carries_a_resource_segment(self):
        assert snapshot_key(
            source="cfbd",
            season=2026,
            week="04",
            fetched_at=datetime(2026, 9, 14, 12, 1, 17, tzinfo=UTC),
            resource="games",
        ) == "raw/cfbd/season=2026/week=04/games/2026-09-14T120117Z.json"

    def test_a_season_level_resource_uses_week_season(self):
        """The ``season`` partition value of SPEC 3.2, which no date produces."""
        assert snapshot_key(
            source="cfbd",
            season=2026,
            week="season",
            fetched_at=datetime(2026, 8, 20, 12, 0, 4, tzinfo=UTC),
            resource="teams",
        ) == "raw/cfbd/season=2026/week=season/teams/2026-08-20T120004Z.json"

    def test_cfbd_without_a_resource_raises(self):
        """SPEC 2.1 requires the segment for CFBD.

        Omitting it silently would put a games pull and a lines pull in the same
        prefix, where the only thing telling them apart is a timestamp.
        """
        with pytest.raises(ValueError):
            snapshot_key(source="cfbd", season=2026, week="04", fetched_at=FETCHED)

    def test_sagarin_with_a_resource_raises(self):
        """The mirror. Accepting and ignoring it would be a silent coercion."""
        with pytest.raises(ValueError):
            snapshot_key(
                source="sagarin", season=2026, week="04", fetched_at=FETCHED, resource="ratings"
            )


#: Every legal ``week=`` value in SPEC 3.2. All fifteen numbered weeks, not a
#: sample: a key builder that drops the leading zero is wrong on ``01``-``09``
#: and right on ``10``-``15``, so a sample decides by luck whether the suite
#: notices. Naming all fifteen takes the luck out.
LEGAL_WEEKS = [f"{n:02d}" for n in range(1, 16)] + [
    "preseason",
    "postseason",
    "offseason",
    "season",
    "unknown",
]


class TestWeekPartitionValues:
    @pytest.mark.parametrize("week", LEGAL_WEEKS)
    def test_every_legal_value_reaches_the_key_intact(self, week):
        """The whole key, not ``f"/week={week}/" in key``.

        The substring form is satisfied by a key that contains the right segment
        somewhere, which is a weaker claim than the one SPEC 2.1 makes -- and the
        assertion it replaces was blind to a builder that emitted ``/week=4/``
        for every week from 10 up, because that builder is correct there.
        """
        assert snapshot_key(source="sagarin", season=2026, week=week, fetched_at=FETCHED) == (
            f"raw/sagarin/season=2026/week={week}/2026-09-16T110302Z.txt"
        )

    @pytest.mark.parametrize("week", ["4", "004", "16", "00", "Week4", "", "04/05", "unknown "])
    def test_anything_else_raises(self, week):
        """The partition value is not a free string.

        ``"4"`` is the dangerous one: it opens a second partition for a week that
        already has one, both halves look plausible in a listing, and every later
        prefix query silently reads half the data.

        This guards the *argument*. What reaches S3 is the return value, and the
        two are separate claims -- see the test below, which is the half of the
        hazard this one cannot see.
        """
        with pytest.raises((WeekResolutionError, ValueError)):
            snapshot_key(source="sagarin", season=2026, week=week, fetched_at=FETCHED)

    @pytest.mark.parametrize(("padded", "bare"), [("01", "1"), ("04", "4"), ("09", "9")])
    def test_the_pad_survives_into_the_emitted_key(self, padded, bare):
        """Accepting ``"04"`` and writing ``/week=4/`` is a state the validator permits.

        ``test_anything_else_raises["4"]`` passes against exactly that builder:
        it rejects the bad input and never looks at the output. Nothing else in
        this class did either, and the emitted key is the only one of the two
        that becomes a permanent S3 prefix.
        """
        key = snapshot_key(source="sagarin", season=2026, week=padded, fetched_at=FETCHED)
        assert f"/week={padded}/" in key
        assert f"/week={bare}/" not in key


class TestManifestKey:
    def test_sits_beside_the_snapshot_it_describes(self):
        snapshot = snapshot_key(source="sagarin", season=2026, week="04", fetched_at=FETCHED)
        assert manifest_key(snapshot) == (
            "raw/sagarin/season=2026/week=04/2026-09-16T110302Z.meta.json"
        )

    def test_replaces_the_cfbd_json_suffix_rather_than_appending(self):
        """``…Z.json`` becomes ``…Z.meta.json``, not ``…Z.json.meta.json``.

        SPEC 2.1 shows the pair; a store listing filters on ``.meta.json``, so an
        appended suffix would still be found and would still be wrong.
        """
        snapshot = snapshot_key(
            source="cfbd",
            season=2026,
            week="04",
            fetched_at=datetime(2026, 9, 14, 12, 1, 17, tzinfo=UTC),
            resource="games",
        )
        assert manifest_key(snapshot) == (
            "raw/cfbd/season=2026/week=04/games/2026-09-14T120117Z.meta.json"
        )

    def test_is_idempotent_on_a_key_that_is_already_a_manifest(self):
        """Guards the double application that produces ``.meta.meta.json``."""
        snapshot = snapshot_key(source="sagarin", season=2026, week="04", fetched_at=FETCHED)
        once = manifest_key(snapshot)
        assert manifest_key(once) == once
