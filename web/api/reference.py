"""Reference data REST endpoints."""

from __future__ import annotations

from nicegui import app

from amrie.antibiotic import ALL_ANTIBIOTICS
from amrie.organism import ALL_ORGANISMS
from web.helpers import get_potency_options
from web.models.responses import AntibioticItem, OrganismItem
from web.state import (
    BREAKPOINT_TYPE_OPTIONS,
    GUIDELINE_OPTIONS,
    SITES_OPTIONS,
)


@app.get('/api/organisms')
async def api_organisms() -> list[OrganismItem]:
    return [
        OrganismItem(code=org.WHONET_ORG_CODE, name=org.ORGANISM)
        for org in ALL_ORGANISMS
    ]


@app.get('/api/antibiotics')
async def api_antibiotics() -> list[AntibioticItem]:
    return [
        AntibioticItem(
            code=abx.WHONET_ABX_CODE,
            name=abx.ANTIBIOTIC,
            potencies=get_potency_options(abx.WHONET_ABX_CODE, GUIDELINE_OPTIONS),
        )
        for abx in ALL_ANTIBIOTICS
    ]


@app.get('/api/guidelines')
async def api_guidelines() -> list[str]:
    return list(GUIDELINE_OPTIONS)


@app.get('/api/breakpoint-types')
async def api_breakpoint_types() -> list[str]:
    return list(BREAKPOINT_TYPE_OPTIONS)


@app.get('/api/sites')
async def api_sites() -> list[str]:
    return list(SITES_OPTIONS)
