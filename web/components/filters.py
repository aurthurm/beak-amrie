"""Shared filter controls for interpretation pages."""

from __future__ import annotations

from dataclasses import dataclass, field

from nicegui import ui

from amrie import constants as C
from web.state import BREAKPOINT_TYPE_OPTIONS, GUIDELINE_OPTIONS, SITES_OPTIONS


@dataclass
class FilterState:
    guidelines: list[str] = field(default_factory=lambda: ['CLSI'])
    guideline_year: int = C.BREAKPOINT_TABLE_REVISION_YEAR
    restrict_breakpoint_types: bool = False
    breakpoint_types: list[str] = field(default_factory=lambda: ['Human'])
    restrict_sites: bool = False
    sites_of_infection: list[str] = field(default_factory=list)


def filters_panel(state: FilterState) -> None:
    ui.label('Guidelines').classes('text-subtitle2')
    for guideline in GUIDELINE_OPTIONS:
        ui.checkbox(
            guideline,
            value=guideline in state.guidelines,
            on_change=lambda e, g=guideline: _toggle_guideline(state, g, e.value),
        )

    ui.number(
        'Guideline year',
        value=state.guideline_year,
        on_change=lambda e: setattr(state, 'guideline_year', int(e.value or state.guideline_year)),
    ).classes('w-full')

    ui.checkbox(
        'Restrict breakpoint types',
        value=state.restrict_breakpoint_types,
        on_change=lambda e: setattr(state, 'restrict_breakpoint_types', e.value),
    )
    for bp_type in BREAKPOINT_TYPE_OPTIONS:
        ui.checkbox(
            bp_type,
            value=bp_type in state.breakpoint_types,
            on_change=lambda e, t=bp_type: _toggle_bp_type(state, t, e.value),
        )

    ui.checkbox(
        'Restrict sites of infection',
        value=state.restrict_sites,
        on_change=lambda e: setattr(state, 'restrict_sites', e.value),
    )
    for site in SITES_OPTIONS:
        ui.checkbox(
            site or '(Blank)',
            value=site in state.sites_of_infection,
            on_change=lambda e, s=site: _toggle_site(state, s, e.value),
        )


def _toggle_guideline(state: FilterState, guideline: str, checked: bool) -> None:
    if checked and guideline not in state.guidelines:
        state.guidelines.append(guideline)
    elif not checked and guideline in state.guidelines:
        state.guidelines.remove(guideline)


def _toggle_bp_type(state: FilterState, bp_type: str, checked: bool) -> None:
    if checked and bp_type not in state.breakpoint_types:
        state.breakpoint_types.append(bp_type)
    elif not checked and bp_type in state.breakpoint_types:
        state.breakpoint_types.remove(bp_type)


def _toggle_site(state: FilterState, site: str, checked: bool) -> None:
    if checked and site not in state.sites_of_infection:
        state.sites_of_infection.append(site)
    elif not checked and site in state.sites_of_infection:
        state.sites_of_infection.remove(site)
