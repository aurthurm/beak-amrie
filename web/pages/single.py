"""Single-drug interpretation tab."""

from __future__ import annotations

from nicegui import ui

from amrie import interpret_single
from amrie.breakpoint import get_applicable_breakpoints
from amrie.expert_rule import RuleCodes, get_applicable_expert_rules
from amrie.expected_resistance import get_applicable_expected_resistance_rules
from web.components.breakpoint_dialog import open_breakpoint_dialog
from web.components.expert_dialog import open_expert_dialog
from web.components.filters import FilterState, filters_panel
from web.components.header import render_header
from web.components.intrinsic_dialog import open_intrinsic_dialog
from web.helpers import (
    build_full_test_codes,
    get_potency_options,
    make_single_tab_config,
    split_full_test_codes,
)
from web.state import (
    ANTIBIOTIC_OPTIONS,
    ORGANISM_OPTIONS,
    SELECT_PLACEHOLDER,
)


def _valid_selection(organism: str, antibiotic: str, guidelines: list[str], measurement: str) -> bool:
    if not organism or organism == SELECT_PLACEHOLDER:
        return False
    if not antibiotic or antibiotic == SELECT_PLACEHOLDER:
        return False
    if not guidelines:
        return False
    return bool(measurement.strip())


@ui.page('/')
def single_page() -> None:
    render_header('/')
    filter_state = FilterState()
    test_method = 'disk'

    with ui.row().classes('w-full gap-4 p-4'):
        with ui.column().classes('w-1/3'):
            ui.label('Organism / Antibiotic').classes('text-h6')
            organism_select = ui.select(
                ORGANISM_OPTIONS,
                value=SELECT_PLACEHOLDER,
                with_input=True,
                label='Organism',
            ).classes('w-full')
            antibiotic_select = ui.select(
                ANTIBIOTIC_OPTIONS,
                value=SELECT_PLACEHOLDER,
                with_input=True,
                label='Antibiotic',
            ).classes('w-full')

            potency_select = ui.select([], label='Potency').classes('w-full')
            measurement_input = ui.input('Measurement').classes('w-full')

            def update_potency() -> None:
                abx = antibiotic_select.value
                if not abx or abx == SELECT_PLACEHOLDER:
                    potency_select.set_options([], value='')
                    return
                options = get_potency_options(abx, filter_state.guidelines)
                potency_select.set_options(options, value=options[0] if options else '')

            antibiotic_select.on('update:model-value', lambda _: update_potency())

            test_method_radio = ui.radio({'disk': 'Disk', 'mic': 'MIC / Etest'}, value='disk')

            def on_test_method_change() -> None:
                nonlocal test_method
                test_method = test_method_radio.value
                potency_select.set_enabled(test_method == 'disk')

            test_method_radio.on('update:model-value', lambda _: on_test_method_change())
            on_test_method_change()

        with ui.column().classes('w-1/3'):
            ui.label('Filters').classes('text-h6')
            filters_panel(filter_state)
            restrict_guidelines_cb = ui.checkbox('Restrict guidelines (breakpoints)', value=False)
            restrict_years_cb = ui.checkbox('Restrict year (breakpoints)', value=False)
            restrict_drugs_cb = ui.checkbox('Filter by selected antibiotic (breakpoints)', value=True)

        with ui.column().classes('w-1/3'):
            ui.label('Actions').classes('text-h6')
            include_comments_cb = ui.checkbox('Include interpretation comments', value=False)
            results_area = ui.column().classes('w-full gap-1')

            def build_full_codes() -> list[str]:
                abx = antibiotic_select.value
                if not abx or abx == SELECT_PLACEHOLDER:
                    return []
                potency = potency_select.value or ''
                return build_full_test_codes(
                    filter_state.guidelines,
                    abx,
                    test_method,
                    potency if test_method == 'disk' else '',
                )

            def validate_common() -> bool:
                return _valid_selection(
                    organism_select.value,
                    antibiotic_select.value,
                    filter_state.guidelines,
                    measurement_input.value or '',
                )

            def run_interpretations() -> None:
                if not validate_common():
                    ui.notify('One or more selections is invalid.', type='negative')
                    return
                config = make_single_tab_config(
                    guideline_year=filter_state.guideline_year,
                    include_comments=include_comments_cb.value,
                    restrict_breakpoint_types=filter_state.restrict_breakpoint_types,
                    breakpoint_types=filter_state.breakpoint_types,
                    restrict_sites=filter_state.restrict_sites,
                    sites_of_infection=filter_state.sites_of_infection,
                )
                results_area.clear()
                with results_area:
                    for code in build_full_codes():
                        result = interpret_single(
                            config,
                            organism_select.value,
                            code,
                            measurement_input.value or '',
                        )
                        ui.label(f'{code}: {result or "(none)"}').classes('font-mono')

            def show_breakpoints() -> None:
                if not validate_common():
                    ui.notify('One or more selections is invalid.', type='negative')
                    return
                breakpoints = get_applicable_breakpoints(
                    organism_select.value,
                    [],
                    prioritized_guidelines=filter_state.guidelines if restrict_guidelines_cb.value else None,
                    prioritized_guideline_years=(
                        [filter_state.guideline_year] if restrict_years_cb.value else None
                    ),
                    prioritized_breakpoint_types=(
                        filter_state.breakpoint_types if filter_state.restrict_breakpoint_types else None
                    ),
                    prioritized_sites_of_infection=(
                        filter_state.sites_of_infection if filter_state.restrict_sites else None
                    ),
                    prioritized_whonet_abx_full_drug_codes=(
                        build_full_codes() if restrict_drugs_cb.value else None
                    ),
                )
                open_breakpoint_dialog(breakpoints)

            def show_expert_rules() -> None:
                if not validate_common():
                    ui.notify('One or more selections is invalid.', type='negative')
                    return
                antimicrobial_codes, other_tests = split_full_test_codes(build_full_codes())
                rules = get_applicable_expert_rules(
                    organism_select.value,
                    antimicrobial_codes,
                    other_tests,
                    RuleCodes.ALL,
                )
                open_expert_dialog(rules)

            def show_intrinsic_rules() -> None:
                if not validate_common():
                    ui.notify('One or more selections is invalid.', type='negative')
                    return
                rules = get_applicable_expected_resistance_rules(
                    organism_select.value,
                    prioritized_guidelines=(
                        filter_state.guidelines if restrict_guidelines_cb.value else None
                    ),
                )
                open_intrinsic_dialog(rules)

            ui.button('Get interpretations', on_click=run_interpretations).classes('w-full')
            ui.button('Applicable breakpoints', on_click=show_breakpoints).classes('w-full')
            ui.button('Applicable expert rules', on_click=show_expert_rules).classes('w-full')
            ui.button('Applicable intrinsic rules', on_click=show_intrinsic_rules).classes('w-full')
