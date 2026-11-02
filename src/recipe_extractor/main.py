# SPDX-License-Identifier: Apache-2.0
"""FastAPI application and entry point."""

import logging
from pathlib import Path
from typing import Any

import click
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from platformdirs import user_data_dir

from recipe_extractor import __version__
from recipe_extractor.api import router
from recipe_extractor.db import RecipeLibrary

# Never bind to all interfaces (project security policy).
HOST = "127.0.0.1"
PORT = 8000

STATIC_DIR = Path(__file__).parent / "static"

APP_NAME = "recipe-extractor"
DB_FILENAME = "recipes.db"

logger = logging.getLogger(__name__)


def default_db_path() -> Path:
    """Library location in the OS user data directory."""
    return Path(user_data_dir(APP_NAME)) / DB_FILENAME


def parse_database(value: str) -> Path | None:
    """Parse a ``--database`` value: ``default``, ``disabled`` or an absolute path.

    Returns the database path, or None when persistence is disabled. Only the exact
    words ``default`` and ``disabled`` are special; anything else must be absolute,
    so a typo such as ``disable`` is rejected instead of creating a stray file.
    """
    if value == "default":
        return default_db_path()
    if value == "disabled":
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("use 'default', 'disabled' or an absolute path")
    return path


class DatabaseParam(click.ParamType[Path | None]):
    name = "default|disabled|ABSOLUTE_PATH"

    def convert(
        self, value: Any, param: click.Parameter | None, ctx: click.Context | None
    ) -> Path | None:
        if value is None or isinstance(value, Path):
            return value
        try:
            return parse_database(str(value))
        except ValueError as e:
            self.fail(f"{e} (got {value!r})", param, ctx)


def create_app(db_path: Path | None = None) -> FastAPI:
    """Build the app. Persistence is off unless ``db_path`` is given.

    Only the command line enables persistence by default, so importing this module
    (as the tests do) can never touch a real library.
    """
    app = FastAPI(title="Recipe Extractor", version=__version__)
    app.state.library = RecipeLibrary(db_path) if db_path is not None else None
    app.include_router(router)
    # Mounted last so it cannot shadow the /api routes.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()


def startup_banner(url: str) -> str:
    """A separator and a colour block telling the user where the server is."""
    text = f"Server running. Click here: {url}"
    width = len(text) + 4
    blank = click.style(" " * width, bg="green")
    line = click.style(f"  {text}  ", fg="black", bg="green", bold=True)
    return "\n".join(["", "─" * width, blank, line, blank, "Press CTRL+C to quit", ""])


class StartupFilter(logging.Filter):
    """Replace uvicorn's start-up chatter with a single banner.

    Attached to ``uvicorn.error``. The "running on" record is the moment the socket
    is listening, so the banner is printed then. With ``--debug`` the original
    records are kept as well.
    """

    NOISE = (
        "Started server process",
        "Waiting for application startup",
        "Application startup complete",
        "Uvicorn running on",
    )

    def __init__(self) -> None:
        super().__init__()
        self.debug = False

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if not message.startswith(self.NOISE):
            return True
        if message.startswith("Uvicorn running on"):
            click.echo(startup_banner(f"http://{HOST}:{PORT}"), err=True)
        return self.debug


_startup_filter = StartupFilter()


def configure_logging(debug: bool) -> int:
    """Log to stderr at INFO, or DEBUG with ``--debug``. Returns the level."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger().setLevel(level)
    _startup_filter.debug = debug
    logging.getLogger("uvicorn.error").addFilter(_startup_filter)
    return level


@click.command()
@click.option(
    "--database",
    type=DatabaseParam(),
    default="default",
    show_default=True,
    help=(
        "Recipe library: 'default' (user data directory), 'disabled' (no "
        "persistence) or an absolute path to the database file."
    ),
)
@click.option("--debug", is_flag=True, help="Log at DEBUG level instead of INFO.")
@click.version_option(__version__)
def run(database: Path | None, debug: bool) -> None:
    """Run Recipe Extractor on http://127.0.0.1:8000."""
    level = configure_logging(debug)
    try:
        server_app = create_app(database)
    except (OSError, RuntimeError) as e:
        raise click.ClickException(f"Cannot open the recipe library: {e}") from e

    if database is None:
        logger.info("Library: persistence disabled")
    else:
        logger.info("Library: %s", database)
    uvicorn.run(
        server_app,
        host=HOST,
        port=PORT,
        log_level=logging.getLevelName(level).lower(),
        log_config=None,
    )
