"""Breakpoint results dialog."""

from __future__ import annotations

from nicegui import ui

from amrie.breakpoint import Breakpoint
from web.helpers import breakpoint_to_dict

BP_COLUMNS = [
    {'name': 'GUIDELINES', 'label': 'GUIDELINES', 'field': 'GUIDELINES', 'align': 'left'},
    {'name': 'YEAR', 'label': 'YEAR', 'field': 'YEAR', 'align': 'left'},
    {'name': 'BREAKPOINT_TYPE', 'label': 'BREAKPOINT_TYPE', 'field': 'BREAKPOINT_TYPE', 'align': 'left'},
    {'name': 'HOST', 'label': 'HOST', 'field': 'HOST', 'align': 'left'},
    {'name': 'SITE_OF_INFECTION', 'label': 'SITE_OF_INFECTION', 'field': 'SITE_OF_INFECTION', 'align': 'left'},
    {'name': 'WHONET_TEST', 'label': 'WHONET_TEST', 'field': 'WHONET_TEST', 'align': 'left'},
    {'name': 'R', 'label': 'R', 'field': 'R', 'align': 'left'},
    {'name': 'I', 'label': 'I', 'field': 'I', 'align': 'left'},
    {'name': 'S', 'label': 'S', 'field': 'S', 'align': 'left'},
    {'name': 'ECV_ECOFF', 'label': 'ECV_ECOFF', 'field': 'ECV_ECOFF', 'align': 'left'},
    {'name': 'ORGANISM_CODE', 'label': 'ORGANISM_CODE', 'field': 'ORGANISM_CODE', 'align': 'left'},
    {'name': 'ORGANISM_CODE_TYPE', 'label': 'ORGANISM_CODE_TYPE', 'field': 'ORGANISM_CODE_TYPE', 'align': 'left'},
    {'name': 'COMMENTS', 'label': 'COMMENTS', 'field': 'COMMENTS', 'align': 'left'},
]


def open_breakpoint_dialog(breakpoints: list[Breakpoint]) -> None:
    rows = [breakpoint_to_dict(bp) for bp in breakpoints]
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-6xl'):
        ui.label(f'Matching breakpoints: {len(breakpoints)}').classes('text-h6')
        ui.table(columns=BP_COLUMNS, rows=rows, row_key='WHONET_TEST').classes('w-full').props('flat bordered dense')
        ui.button('Close', on_click=dialog.close)
    dialog.open()
