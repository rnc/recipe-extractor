# SPDX-License-Identifier: Apache-2.0
"""Tests for the command line: --database parsing, --debug and startup logging."""

import logging
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from click.testing import CliRunner
from fastapi import FastAPI

from recipe_extractor import main
from recipe_extractor.main import default_db_path, parse_database, run


def test_default_db_path_is_in_user_data_dir() -> None:
    path = default_db_path()
    assert path.name == "recipes.db"
    assert path.parent.name == "recipe-extractor"
    assert path.is_absolute()


def test_parse_database_words_and_paths(tmp_path: Path) -> None:
    assert parse_database("default") == default_db_path()
    assert parse_database("disabled") is None
    assert parse_database(str(tmp_path / "x.db")) == tmp_path / "x.db"
    assert parse_database("~/x.db") == Path("~/x.db").expanduser()


@pytest.mark.parametrize(
    "value", ["foo", "disable", "Disabled", "DEFAULT", "./x.db", "x/y.db", ""]
)
def test_parse_database_rejects_relative_and_typos(value: str) -> None:
    with pytest.raises(ValueError, match="absolute path"):
        parse_database(value)


class FakeServer:
    """Stands in for uvicorn.run so no server is started."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, app: FastAPI, **kwargs: Any) -> None:
        self.calls.append({"app": app, **kwargs})


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> FakeServer:
    fake = FakeServer()
    monkeypatch.setattr(uvicorn, "run", fake)
    return fake


@pytest.fixture
def isolated_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Make 'default' point inside tmp_path so no test touches a real library."""
    path = tmp_path / "userdata" / "recipes.db"
    monkeypatch.setattr(main, "default_db_path", lambda: path)
    return path


def test_no_flag_enables_persistence_at_default(
    server: FakeServer, isolated_default: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        result = CliRunner().invoke(run, [])
    assert result.exit_code == 0, result.output
    assert isolated_default.exists()
    assert server.calls[0]["app"].state.library is not None
    assert server.calls[0]["host"] == "127.0.0.1"
    assert f"Library: {isolated_default}" in caplog.text
    assert "Listening on http://127.0.0.1:8000" in caplog.text


def test_disabled_turns_persistence_off(
    server: FakeServer, isolated_default: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        result = CliRunner().invoke(run, ["--database=disabled"])
    assert result.exit_code == 0, result.output
    assert server.calls[0]["app"].state.library is None
    assert not isolated_default.exists()
    assert "Library: persistence disabled" in caplog.text


def test_explicit_path(server: FakeServer, tmp_path: Path) -> None:
    target = tmp_path / "custom" / "test-db"
    result = CliRunner().invoke(run, [f"--database={target}"])
    assert result.exit_code == 0, result.output
    assert target.exists()
    assert server.calls[0]["app"].state.library.path == target


@pytest.mark.parametrize("value", ["foo", "disable", "Disabled"])
def test_relative_or_mistyped_value_is_rejected(server: FakeServer, value: str) -> None:
    result = CliRunner().invoke(run, [f"--database={value}"])
    assert result.exit_code == 2
    assert "absolute path" in result.output
    assert server.calls == []


def test_database_flag_requires_a_value(server: FakeServer) -> None:
    result = CliRunner().invoke(run, ["--database"])
    assert result.exit_code == 2
    assert server.calls == []


def test_unopenable_library_is_a_clear_error(
    server: FakeServer, tmp_path: Path
) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    result = CliRunner().invoke(run, [f"--database={blocker / 'db'}"])
    assert result.exit_code == 1
    assert "Cannot open the recipe library" in result.output
    assert "Traceback" not in result.output
    assert server.calls == []


def test_log_level_info_by_default_and_debug_flag(server: FakeServer) -> None:
    CliRunner().invoke(run, ["--database=disabled"])
    assert server.calls[0]["log_level"] == "info"
    assert logging.getLogger().level == logging.INFO

    CliRunner().invoke(run, ["--database=disabled", "--debug"])
    assert server.calls[1]["log_level"] == "debug"
    assert logging.getLogger().level == logging.DEBUG
    logging.getLogger().setLevel(logging.WARNING)  # restore for other tests


def test_help_documents_the_modes() -> None:
    result = CliRunner().invoke(run, ["--help"])
    assert result.exit_code == 0
    for word in ("default", "disabled", "absolute path", "--debug"):
        assert word in result.output
