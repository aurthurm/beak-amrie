"""Shared read-only lookup tables built at import time."""

from __future__ import annotations

from amrie import constants as C
from amrie.antibiotic import ALL_ANTIBIOTICS, GuidelineNames
from amrie.breakpoint import BreakpointTypes
from amrie.config import InterpretationConfiguration
from amrie.organism import ALL_ORGANISMS

_PLACEHOLDER = '[Select a value]'

ORGANISM_OPTIONS: dict[str, str] = {
    _PLACEHOLDER: _PLACEHOLDER,
    **{
        org.WHONET_ORG_CODE: f'{org.ORGANISM} - ({org.WHONET_ORG_CODE})'
        for org in ALL_ORGANISMS
    },
}

ANTIBIOTIC_OPTIONS: dict[str, str] = {
    _PLACEHOLDER: _PLACEHOLDER,
    **{
        abx.WHONET_ABX_CODE: f'{abx.ANTIBIOTIC} - ({abx.WHONET_ABX_CODE})'
        for abx in ALL_ANTIBIOTICS
    },
}

GUIDELINE_OPTIONS: list[str] = [
    GuidelineNames.CLSI,
    GuidelineNames.EUCAST,
    GuidelineNames.SFM,
]

BREAKPOINT_TYPE_OPTIONS: list[str] = [
    BreakpointTypes.HUMAN,
    BreakpointTypes.ANIMAL,
    BreakpointTypes.ECOFF,
]

SITES_OPTIONS: list[str] = list(C.SitesOfInfection.DEFAULT_ORDER)

SELECT_PLACEHOLDER = _PLACEHOLDER

__all__ = [
    'InterpretationConfiguration',
    'ORGANISM_OPTIONS',
    'ANTIBIOTIC_OPTIONS',
    'GUIDELINE_OPTIONS',
    'BREAKPOINT_TYPE_OPTIONS',
    'SITES_OPTIONS',
    'SELECT_PLACEHOLDER',
]
