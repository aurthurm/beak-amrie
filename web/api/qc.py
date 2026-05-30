"""QC REST endpoint."""

from __future__ import annotations

import asyncio

from nicegui import app

from amrie.qc import get_quality_control_interpretation
from web.models.requests import QCRequest
from web.models.responses import QCResponse


@app.post('/api/qc')
async def api_qc(req: QCRequest) -> QCResponse:
    result = await asyncio.to_thread(
        get_quality_control_interpretation,
        req.strain,
        req.antibiotic,
        req.measurement,
        req.round_half_dilutions,
    )
    return QCResponse(result=result)
