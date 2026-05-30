"""Shared application header with tab navigation."""

from __future__ import annotations

from nicegui import ui


def render_header(active: str = '/') -> None:
    with ui.header().classes('items-center gap-4 px-4'):
        ui.label('AMRIE Web').classes('text-h6')
        ui.link('Single', '/').classes('text-white' if active == '/' else '')
        ui.link('File Mode', '/file').classes('text-white' if active == '/file' else '')
        ui.link('QC', '/qc').classes('text-white' if active == '/qc' else '')
