"""Expert rule results dialog."""

from __future__ import annotations

from nicegui import ui

from amrie.expert_rule import ExpertInterpretationRule
from web.helpers import expert_rule_to_dict

EXPERT_COLUMNS = [
    {'name': 'RULE_CODE', 'label': 'RULE_CODE', 'field': 'RULE_CODE', 'align': 'left'},
    {'name': 'DESCRIPTION', 'label': 'DESCRIPTION', 'field': 'DESCRIPTION', 'align': 'left'},
    {'name': 'ORGANISM_CODE', 'label': 'ORGANISM_CODE', 'field': 'ORGANISM_CODE', 'align': 'left'},
    {'name': 'ORGANISM_CODE_TYPE', 'label': 'ORGANISM_CODE_TYPE', 'field': 'ORGANISM_CODE_TYPE', 'align': 'left'},
    {'name': 'RULE_CRITERIA', 'label': 'RULE_CRITERIA', 'field': 'RULE_CRITERIA', 'align': 'left'},
    {'name': 'AFFECTED_ANTIBIOTICS', 'label': 'AFFECTED_ANTIBIOTICS', 'field': 'AFFECTED_ANTIBIOTICS', 'align': 'left'},
    {'name': 'ANTIBIOTIC_EXCEPTIONS', 'label': 'ANTIBIOTIC_EXCEPTIONS', 'field': 'ANTIBIOTIC_EXCEPTIONS', 'align': 'left'},
]


def open_expert_dialog(rules: list[ExpertInterpretationRule]) -> None:
    rows = [expert_rule_to_dict(rule) for rule in rules]
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-6xl'):
        ui.label(f'Applicable expert rules: {len(rules)}').classes('text-h6')
        ui.table(columns=EXPERT_COLUMNS, rows=rows, row_key='RULE_CODE').classes('w-full').props('flat bordered dense')
        ui.button('Close', on_click=dialog.close)
    dialog.open()
