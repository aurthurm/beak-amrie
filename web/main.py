"""AMRIE NiceGUI web application entry point."""

from __future__ import annotations

import os

from nicegui import ui

import web.api.breakpoints  # noqa: F401
import web.api.interpret  # noqa: F401
import web.api.qc  # noqa: F401
import web.api.reference  # noqa: F401
import web.api.rules  # noqa: F401
import web.pages.file_mode  # noqa: F401
import web.pages.qc  # noqa: F401
import web.pages.single  # noqa: F401


def start() -> None:
    ui.run(
        host='0.0.0.0',
        port=8080,
        title='AMRIE Web',
        storage_secret=os.environ.get('STORAGE_SECRET', 'amrie-dev-secret'),
        fastapi_docs=True,
        show=False,
        reload=False,
    )


if __name__ == '__main__':
    start()
