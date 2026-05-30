"""QC reference strain evaluation tab."""

from __future__ import annotations

from nicegui import ui

from amrie.qc import get_quality_control_interpretation
from web.components.header import render_header


@ui.page('/qc')
def qc_page() -> None:
    render_header('/qc')

    with ui.column().classes('w-full max-w-xl gap-4 p-4'):
        ui.label('Quality Control').classes('text-h5')
        strain_input = ui.input('Reference strain', placeholder='e.g. atcc25922').classes('w-full')
        antibiotic_input = ui.input(
            'Antibiotic (full WHONET code)',
            placeholder='e.g. SAM_ND10',
        ).classes('w-full')
        measurement_input = ui.input('Measurement').classes('w-full')
        result_label = ui.label('Result: —').classes('text-h6')

        def evaluate() -> None:
            strain = (strain_input.value or '').strip()
            antibiotic = (antibiotic_input.value or '').strip()
            measurement = (measurement_input.value or '').strip()
            if not strain or not antibiotic or not measurement:
                ui.notify('Strain, antibiotic, and measurement are required.', type='negative')
                return
            result = get_quality_control_interpretation(strain, antibiotic, measurement)
            display = result or '(none)'
            result_label.set_text(f'Result: {display}')
            badge_type = 'positive' if result == 'IN' else 'negative' if result == 'OUT' else 'warning'
            ui.notify(f'QC result: {display}', type=badge_type)

        ui.button('Evaluate', on_click=evaluate).classes('w-full')
