"""Intrinsic resistance rule results dialog."""

from __future__ import annotations

from nicegui import ui

from amrie.expected_resistance import ExpectedResistancePhenotypeRule
from web.helpers import intrinsic_rule_to_dict

INTRINSIC_COLUMNS = [
    {'name': 'GUIDELINE', 'label': 'GUIDELINE', 'field': 'GUIDELINE', 'align': 'left'},
    {'name': 'REFERENCE_TABLE', 'label': 'REFERENCE_TABLE', 'field': 'REFERENCE_TABLE', 'align': 'left'},
    {'name': 'ORGANISM_CODE', 'label': 'ORGANISM_CODE', 'field': 'ORGANISM_CODE', 'align': 'left'},
    {'name': 'ORGANISM_CODE_TYPE', 'label': 'ORGANISM_CODE_TYPE', 'field': 'ORGANISM_CODE_TYPE', 'align': 'left'},
    {'name': 'ABX_CODE', 'label': 'ABX_CODE', 'field': 'ABX_CODE', 'align': 'left'},
    {'name': 'ABX_CODE_TYPE', 'label': 'ABX_CODE_TYPE', 'field': 'ABX_CODE_TYPE', 'align': 'left'},
    {'name': 'ANTIBIOTIC_EXCEPTIONS', 'label': 'ANTIBIOTIC_EXCEPTIONS', 'field': 'ANTIBIOTIC_EXCEPTIONS', 'align': 'left'},
    {'name': 'COMMENTS', 'label': 'COMMENTS', 'field': 'COMMENTS', 'align': 'left'},
]


def open_intrinsic_dialog(rules: list[ExpectedResistancePhenotypeRule]) -> None:
    rows = [intrinsic_rule_to_dict(rule) for rule in rules]
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-6xl'):
        ui.label(f'Applicable intrinsic rules: {len(rules)}').classes('text-h6')
        ui.table(columns=INTRINSIC_COLUMNS, rows=rows, row_key='ABX_CODE').classes('w-full').props('flat bordered dense')
        ui.button('Close', on_click=dialog.close)
    dialog.open()
