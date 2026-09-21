"""The workflow files, as a contract (SPEC-phase0 section 11, SPEC-phase1 section 8).

**These exist because a workflow-only change could merge with no checks at all.**
`cfb-ci.yml` triggers on `cfb/**` and `frontend-ci.yml` on `frontend/**`, so a PR
that touched only `.github/workflows/` was reviewed by nothing and found out in
production. That gap cost a week of the market benchmark on 2026-09-14, and the
fix for it merged through the same gap on 2026-09-21.

`actionlint` covers the generic half -- expression syntax, shell, bad `uses`.
What it cannot know is this pipeline's own ordering rules, and those are where the
real failures have been: a step in the wrong place is valid YAML, valid Actions,
and silently wrong for a week.

The rules below are each a thing that has actually broken, or a documented
invariant the workflows state about themselves in prose and nothing enforced.
"""

from fnmatch import fnmatch
from pathlib import Path

import pytest
import yaml

WORKFLOWS = sorted((Path(__file__).parent.parent.parent / ".github" / "workflows").glob("*.yml"))

#: Jobs that reach AWS. Everything else must not be able to.
TOUCHES_AWS = {
    "cfb-predict.yml",
    "cfb-publish.yml",
    "cfb-refresh.yml",
    "cfb-roster.yml",
    "cfb-sagarin.yml",
    "cfb-score.yml",
}


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def triggers(document: dict) -> dict:
    """The `on:` block.

    YAML 1.1 reads a bare ``on`` as the boolean ``True``, which is why this is a
    helper rather than ``document["on"]`` -- a detail that has confused every
    script in this repo that touched a workflow.
    """
    return document[True] if True in document else document["on"]


def steps(document: dict) -> list[dict]:
    (job,) = document["jobs"].values()
    return job["steps"]


def step_names(document: dict) -> list[str]:
    return [s.get("name") or s.get("uses", "") for s in steps(document)]


def commands(document: dict) -> list[str]:
    return [s.get("run", "") for s in steps(document)]


def index_of(document: dict, needle: str) -> int:
    """Position of the first step whose command contains ``needle``."""
    for i, command in enumerate(commands(document)):
        if needle in command:
            return i
    raise AssertionError(f"no step runs {needle!r}; steps are {step_names(document)}")


def named(filename: str) -> dict:
    return load(next(p for p in WORKFLOWS if p.name == filename))


# --- every file ---------------------------------------------------------------


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
class TestEveryWorkflow:
    def test_it_parses(self, path):
        assert isinstance(load(path), dict)

    def test_it_is_named(self, path):
        assert load(path).get("name")

    def test_it_declares_its_permissions(self, path):
        """Never the default token scope.

        An unstated `permissions:` inherits whatever the repository default is,
        which is a setting in a web console rather than a fact in the diff.
        """
        assert load(path).get("permissions")

    def test_only_aws_jobs_can_reach_aws(self, path):
        """`id-token: write` is the capability to assume the publisher role.

        `cfb-ci.yml`'s whole claim is that a test reaching for AWS fails there
        rather than quietly passing on someone's credentials, and that claim is
        this line. Handing the token to a job that has no business with it would
        remove the only thing enforcing it.
        """
        wants_aws = path.name in TOUCHES_AWS
        has_token = load(path).get("permissions", {}).get("id-token") == "write"
        assert has_token is wants_aws

    def test_no_job_names_a_local_aws_profile(self, path):
        """`AWS_PROFILE` and `tp-site` are how a *human* reaches this account.

        A workflow assumes the publisher role by OIDC. One that named a profile
        would be relying on a credential it cannot have, and would fail in a way
        that looks like a permissions problem rather than a wrong idea.

        Checked against the parsed steps rather than the file text: several of
        these workflows explain in a comment that they must not do this, and a
        grep over the raw bytes cannot tell the warning from the offence.
        """
        document = load(path)
        executable = [
            str(document.get("env", {})),
            *(str(step.get("env", "")) for step in steps(document)),
            *(str(step.get("with", "")) for step in steps(document)),
            *commands(document),
        ]
        for fragment in executable:
            assert "AWS_PROFILE" not in fragment
            assert "tp-site" not in fragment

    def test_an_aws_job_installs_boto3(self, path):
        """The gotcha `cfb/CLAUDE.md` opens with.

        A bare `uv sync` prunes boto3, because it is an optional extra so the
        offline suite installs neither it nor botocore. Every S3-backed command
        and the SSM credential read then fail. `cfb-ci.yml` syncs without it *on
        purpose* and is excluded here for that reason.
        """
        if path.name not in TOUCHES_AWS:
            return
        assert any("uv sync --extra s3" in command for command in commands(load(path)))

    def test_a_scheduled_workflow_can_be_run_by_hand(self, path):
        """Every failure in this pipeline is repaired by re-running it.

        A scheduled job with no `workflow_dispatch` can only be retried by
        pushing a commit or waiting a week.
        """
        on = triggers(load(path))
        if "schedule" not in on:
            return
        assert "workflow_dispatch" in on


# --- the orderings that have actually broken ----------------------------------


class TestCfbScoreOrdering:
    """SPEC-phase1 §8, and the 2026-09-14 failure.

    `cfb score` died on a game CFBD had re-issued under a new id. Every step
    below it was skipped -- including the capture of the *opening* week's lines,
    which is the only thing that feeds Thursday's forecast. Week 3 published 119
    games with 0 priced, `predictions/` is write-once, and that week's market
    column is empty for good.
    """

    def test_the_opening_weeks_captures_run_before_the_scoring(self):
        """Capturing next week cannot depend on last week having scored.

        `coming_week` resolves the same partition either side of the scoring
        step, so there is nothing to gain by going second and a week of the
        benchmark to lose.
        """
        document = named("cfb-score.yml")
        scoring = index_of(document, "cfb score")
        assert index_of(document, "--resource games --in-progress") < scoring
        assert index_of(document, "--resource lines --in-progress") < scoring

    def test_the_forecast_runs_after_the_scoring(self):
        """This one genuinely depends on it: a prediction written before
        `cfb score` would be built on ratings that have not seen the week that
        just ended.
        """
        document = named("cfb-score.yml")
        assert index_of(document, "cfb predict") > index_of(document, "cfb score")

    def test_the_replay_check_runs_after_the_scoring(self):
        """SPEC-phase1 §11 step 5: it verifies the state this run just wrote."""
        document = named("cfb-score.yml")
        assert index_of(document, "cfb elo replay") > index_of(document, "cfb score")


class TestCfbPredictOrdering:
    def test_the_lines_are_fetched_before_the_forecast(self):
        """A forecast written before its lines landed has an empty benchmark and
        nothing saying so -- which reads exactly like a week no book priced.
        """
        document = named("cfb-predict.yml")
        assert index_of(document, "--resource lines --in-progress") < index_of(
            document, "cfb predict"
        )

    def test_it_fetches_the_coming_week_not_the_closed_one(self):
        """`--in-progress` resolves `coming_week`. Without it the fetch resolves
        `last_completed_week` and archives the lines of a week already played --
        the shape of the original bug, on the job that reads them.
        """
        document = named("cfb-predict.yml")
        lines = [c for c in commands(document) if "--resource lines" in c]
        assert lines and all("--in-progress" in c for c in lines)


# --- the schedule -------------------------------------------------------------


class TestTheSchedule:
    """SPEC-phase1 §8's table, as crons.

    Pinned because the times encode orderings argued for at length in the files
    themselves, and a cron is the one thing in a workflow that no test, lint or
    review catches when it drifts.
    """

    EXPECTED = {
        "cfb-sagarin.yml": ["0 12 * * 2"],
        "cfb-roster.yml": ["45 11 * * 4"],
        "cfb-predict.yml": ["0 12 * * 4"],
        "cfb-publish.yml": ["30 12 * * 4", "0 12 * * 5"],
        "cfb-score.yml": ["0 12 * * 1"],
        "cfb-refresh.yml": ["0 13 * * 0", "0 14 * * 1"],
    }

    @pytest.mark.parametrize("filename", sorted(EXPECTED))
    def test_the_cron_is_what_the_spec_argued_for(self, filename):
        document = named(filename)
        crons = [entry["cron"] for entry in triggers(document)["schedule"]]
        assert crons == self.EXPECTED[filename]

    def test_the_roster_capture_precedes_the_forecast_it_informs(self):
        """SPEC-phase3 §3.2. An expectation captured *after* the forecast it
        informs is a fact about the past wearing a feature's clothes.

        Both are Thursday jobs and Actions schedules them independently, so this
        pins the intent rather than guaranteeing the outcome -- see the note in
        `cfb-roster.yml`.
        """
        def minutes(filename):
            cron = triggers(named(filename))["schedule"][0]["cron"].split()
            return int(cron[1]) * 60 + int(cron[0])

        assert minutes("cfb-roster.yml") < minutes("cfb-predict.yml")


# --- the gates ----------------------------------------------------------------


class TestEveryPathIsGated:
    """The gap this file exists to close.

    A directory whose changes trigger no workflow is one where a break is found
    in production. That has now happened twice -- `frontend/` in #75, and
    `.github/workflows/` in #82, which merged with no checks at all.
    """

    def paths_of(self, filename: str) -> list[str]:
        return triggers(named(filename))["pull_request"]["paths"]

    @pytest.mark.parametrize(
        ("filename", "guarded"),
        [
            ("cfb-ci.yml", "cfb/**"),
            ("frontend-ci.yml", "frontend/**"),
            ("workflows-ci.yml", ".github/workflows/**"),
        ],
    )
    def test_the_tree_that_matters_is_gated(self, filename, guarded):
        assert guarded in self.paths_of(filename)

    @pytest.mark.parametrize(
        "filename", ["cfb-ci.yml", "frontend-ci.yml", "workflows-ci.yml"]
    )
    def test_a_gate_gates_itself(self, filename):
        """A change to a gate is a change to what the repository checks, and is
        exactly the change that should not land unchecked.

        Matched as a glob, because a gate may cover itself by naming its own file
        (`cfb-ci.yml` does) or by covering the directory it sits in
        (`workflows-ci.yml` does). `fnmatch` is an approximation of GitHub's path
        filters -- it does not stop `*` at a slash -- which is the forgiving
        direction for a check whose job is to catch a file nothing covers.
        """
        own_path = f".github/workflows/{filename}"
        assert any(
            fnmatch(own_path, pattern) for pattern in self.paths_of(filename)
        ), f"{filename} is not matched by its own paths: {self.paths_of(filename)}"
