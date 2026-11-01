# SPDX-License-Identifier: Apache-2.0
"""FastAPI application and entry point."""

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from recipe_extractor import __version__
from recipe_extractor.api import router

# Never bind to all interfaces (project security policy).
HOST = "127.0.0.1"
PORT = 8000

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="Recipe Extractor", version=__version__)
    app.include_router(router)
    # Mounted last so it cannot shadow the /api routes.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()


def run() -> None:
    uvicorn.run(app, host=HOST, port=PORT)
