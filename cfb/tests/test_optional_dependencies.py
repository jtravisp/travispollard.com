"""A missing optional extra fails like everything else does (SPEC-phase0 9).

`boto3` is an extra, so `uv sync --extra s3` installs it and a bare `uv sync`
prunes it. That is a deliberate trade — the offline suite, which is every test
that runs without `CFB_INTEGRATION=1`, installs neither boto3 nor botocore — and
the cost is that every S3-backed command breaks the moment someone syncs without
the flag.

**The error was the right error and the wrong shape.** A pruned environment raised
`ModuleNotFoundError` from inside `S3SnapshotStore.__init__`, nine frames deep,
naming neither the extra nor the command that fixes it. SPEC 9 says every failure
is exit 1 with a message and no traceback, and it carves out nothing for failures
that are the operator's fault rather than the data's — arguably the opposite,
since this one reaches a human at a terminal, which most `CfbError`s never do.

## How the missing dependency is simulated

`boto3` is installed in this environment, so these tests put `None` into
`sys.modules` for it. That is the documented way an import is made to fail:
CPython raises `ImportError` when it finds `None` cached under a name, which is
the same exception class a genuinely absent package produces. `monkeypatch`
restores the entry afterwards, so nothing leaks into the rest of the suite.

Both call sites are covered because they fail at different moments and only one
of them is obvious. The store fails when the CLI resolves `--store`; `ssm_secret`
fails on the *first CFBD request of a run*, after the calendar has loaded and the
week has resolved, where an unwrapped import error reads as a failure of the
fetch rather than of the environment.
"""

import sys

import pytest

from cfb.cli import main
from cfb.collectors.cfbd import ssm_secret
from cfb.errors import CfbError, MissingDependencyError, optional_import
from cfb.storage import S3SnapshotStore


@pytest.fixture
def no_boto3(monkeypatch):
    """Make `import boto3` raise, the way a bare `uv sync` does."""
    monkeypatch.setitem(sys.modules, "boto3", None)


class TestTheHelper:
    """`errors.optional_import`, the one place the message is written."""

    def test_an_import_error_becomes_a_cfb_error(self):
        with pytest.raises(MissingDependencyError) as excinfo:
            with optional_import("boto3", extra="s3", needed_for="the thing"):
                raise ImportError("No module named 'boto3'")
        assert isinstance(excinfo.value, CfbError)

    def test_the_message_leads_with_the_command_to_run(self):
        """The whole point. A person who has hit this three times in a day needs
        the fix, not a diagnosis they already have.
        """
        with pytest.raises(MissingDependencyError) as excinfo:
            with optional_import("boto3", extra="s3", needed_for="the thing"):
                raise ImportError("No module named 'boto3'")
        assert "uv sync --extra s3" in str(excinfo.value)

    def test_it_says_what_could_not_run(self):
        """Two sites fail at different moments; "boto3 is not installed" alone
        does not say which command was part-way through.
        """
        with pytest.raises(MissingDependencyError, match="the S3 snapshot store"):
            with optional_import(
                "boto3", extra="s3", needed_for="the S3 snapshot store"
            ):
                raise ImportError("nope")

    def test_the_original_error_is_kept_as_the_cause(self):
        """Chained, so `--pdb` and a debugger still reach the real import failure.

        The CLI prints the message and not the traceback, so this costs a reader
        nothing and keeps the evidence for anyone who wants it.
        """
        original = ImportError("No module named 'boto3'")
        with pytest.raises(MissingDependencyError) as excinfo:
            with optional_import("boto3", extra="s3", needed_for="the thing"):
                raise original
        assert excinfo.value.__cause__ is original
        assert "No module named 'boto3'" in str(excinfo.value)

    def test_it_does_not_swallow_anything_else(self):
        """Only `ImportError`. A `KeyError` from inside an imported module is a
        bug in this package, and a bug wearing a clean exit code is a bug nobody
        finds -- the same rule `cli._dispatch` follows.
        """
        with pytest.raises(KeyError):
            with optional_import("boto3", extra="s3", needed_for="the thing"):
                raise KeyError("unrelated")

    def test_a_successful_import_is_transparent(self):
        """The control. Without it the wrapper is satisfied by failing always."""
        with optional_import("boto3", extra="s3", needed_for="the thing"):
            import json  # noqa: F401 - stands in for a present dependency


class TestTheS3Store:
    """Where a pruned environment actually bites (`--store s3://…`)."""

    def test_building_it_raises_a_cfb_error(self, no_boto3):
        with pytest.raises(MissingDependencyError) as excinfo:
            S3SnapshotStore("travispollard-cfb-data", "us-east-1")
        assert "uv sync --extra s3" in str(excinfo.value)

    def test_it_is_not_a_module_not_found_error(self, no_boto3):
        """The regression. `ModuleNotFoundError` is not a `CfbError`, so it misses
        the CLI's exit-1 clause entirely and arrives as a traceback.
        """
        with pytest.raises(CfbError):
            S3SnapshotStore("travispollard-cfb-data", "us-east-1")

    def test_the_other_stores_are_unaffected(self, no_boto3):
        """boto3 is optional *because* the offline path never needs it. If pruning
        it broke the memory or file store, the extra would not be optional.
        """
        from cfb.storage import FileSnapshotStore, MemorySnapshotStore

        assert MemorySnapshotStore().list_keys("") == []
        assert FileSnapshotStore(".").list_manifests("nothing/") == []


class TestTheSsmPath:
    """The site that was never covered, and fails later than the store does."""

    def test_reading_the_key_raises_a_cfb_error(self, no_boto3):
        with pytest.raises(MissingDependencyError) as excinfo:
            ssm_secret()
        assert "uv sync --extra s3" in str(excinfo.value)

    def test_the_message_names_the_credential_read_not_the_store(self, no_boto3):
        """Both sites import boto3 and they fail in different commands. A shared
        message would send whoever reads it to the wrong half of the run.
        """
        with pytest.raises(MissingDependencyError) as excinfo:
            ssm_secret()
        message = str(excinfo.value)
        assert "CFBD key" in message
        assert "snapshot store" not in message


class TestTheCommandContract:
    """SPEC-phase0 9, end to end: exit 1, a message on stderr, no traceback."""

    def test_an_s3_store_exits_1_rather_than_raising(self, no_boto3, capsys):
        """`cfb replay` resolves the store before anything else, so this is the
        shortest path to the failure a person actually hits.
        """
        assert main(["replay", "raw/sagarin/x.txt", "--store", "s3://a-bucket"]) == 1

    def test_the_message_reaches_stderr_with_the_fix(self, no_boto3, capsys):
        main(["replay", "raw/sagarin/x.txt", "--store", "s3://a-bucket"])
        err = capsys.readouterr().err
        assert "MissingDependencyError" in err
        assert "uv sync --extra s3" in err

    def test_no_traceback_reaches_the_terminal(self, no_boto3, capsys):
        """The specific complaint: nine frames of stack and no indication of the
        fix. SPEC 9 says a failure never takes that shape.
        """
        main(["replay", "raw/sagarin/x.txt", "--store", "s3://a-bucket"])
        err = capsys.readouterr().err
        assert "Traceback" not in err
        assert "storage.py" not in err
        assert err.count("\n") < 10

    def test_a_file_store_still_works_with_boto3_pruned(self, no_boto3, tmp_path):
        """The control, and the reason the extra is an extra: local work needs no
        AWS at all, so a pruned environment must not block it.
        """
        assert main(["replay", "missing.txt", "--store", f"file://{tmp_path}"]) == 1
        # exit 1 for SnapshotNotFoundError -- the store was built, which is the point.
