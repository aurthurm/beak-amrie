"""Batch file interpretation tab."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from nicegui import background_tasks, ui

from amrie.config import read_configuration
from amrie.io_library import interpret_isolates, load_input_file
from web.components.header import render_header
from web.helpers import generate_output_str

_DELIMITER_OPTIONS = {
    '|': 'Pipe (|)',
    ',': 'Comma (,)',
    ';': 'Semicolon (;)',
    'TAB': 'Tab',
}
_DELIMITER_CHARS = {
    '|': '|',
    ',': ',',
    ';': ';',
    'TAB': '\t',
}
_BATCH_SIZE = 50


@ui.page('/file')
def file_mode_page() -> None:
    render_header('/file')

    data_bytes: bytes | None = None
    config_bytes: bytes | None = None
    cancel_requested = False
    running = False
    progress_value = 0.0

    with ui.column().classes('w-full max-w-3xl gap-4 p-4'):
        ui.label('File Mode').classes('text-h5')

        async def on_data_upload(e) -> None:
            nonlocal data_bytes
            data_bytes = e.content.read()

        async def on_config_upload(e) -> None:
            nonlocal config_bytes
            config_bytes = e.content.read()

        ui.upload(on_upload=on_data_upload, label='Input data file').classes('w-full')
        delimiter_select = ui.select(_DELIMITER_OPTIONS, value='|', label='Input delimiter').classes('w-full')
        ui.upload(on_upload=on_config_upload, label='Configuration JSON (required)').classes('w-full')
        guideline_year_input = ui.number('Guideline year', value=2026).classes('w-full')

        progress = ui.linear_progress(value=0).classes('w-full')
        status_label = ui.label('Ready')

        interpret_button = ui.button('Interpret')
        cancel_button = ui.button('Cancel').props('outline')
        cancel_button.disable()

        async def run_interpretation() -> None:
            nonlocal cancel_requested, running, progress_value, data_bytes, config_bytes

            if running:
                return
            if not data_bytes:
                ui.notify('Upload an input data file.', type='negative')
                return
            if not config_bytes:
                ui.notify('Upload a configuration JSON file.', type='negative')
                return

            running = True
            cancel_requested = False
            progress_value = 0.0
            progress.set_value(0)
            interpret_button.disable()
            cancel_button.enable()
            status_label.set_text('Loading input file...')

            delim = _DELIMITER_CHARS[delimiter_select.value]
            year = int(guideline_year_input.value or 2026)

            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    data_path = Path(tmpdir) / 'input.txt'
                    config_path = Path(tmpdir) / 'config.json'
                    data_path.write_bytes(data_bytes)
                    config_path.write_bytes(config_bytes)

                    columns, rows = await asyncio.to_thread(
                        load_input_file,
                        str(data_path),
                        delim,
                    )
                    config = await asyncio.to_thread(read_configuration, str(config_path))

                    if not rows:
                        status_label.set_text('No data rows found.')
                        ui.notify('Input file contains no data rows.', type='warning')
                        return

                    total = len(rows)
                    results: list[tuple[dict[str, str], dict[str, str]]] = []
                    for start in range(0, total, _BATCH_SIZE):
                        if cancel_requested:
                            status_label.set_text('Cancelled.')
                            ui.notify('Interpretation cancelled.', type='warning')
                            return
                        batch = rows[start:start + _BATCH_SIZE]
                        batch_results = await asyncio.to_thread(
                            interpret_isolates,
                            config,
                            columns,
                            batch,
                            year,
                        )
                        results.extend(batch_results)
                        progress_value = min(1.0, (start + len(batch)) / total)
                        progress.set_value(progress_value)
                        status_label.set_text(f'Processed {min(start + len(batch), total)} / {total} rows')

                    output = await asyncio.to_thread(
                        generate_output_str,
                        config,
                        columns,
                        results,
                    )
                    ui.download(output.encode('utf-8'), 'interpretations.txt')
                    status_label.set_text('Complete — download started.')
                    ui.notify('Interpretation complete.', type='positive')
            except Exception as exc:
                status_label.set_text(f'Error: {exc}')
                ui.notify(str(exc), type='negative')
            finally:
                running = False
                cancel_requested = False
                interpret_button.enable()
                cancel_button.disable()

        def request_cancel() -> None:
            nonlocal cancel_requested
            if running:
                cancel_requested = True
                status_label.set_text('Cancelling...')

        interpret_button.on_click(lambda: background_tasks.create(run_interpretation()))
        cancel_button.on_click(request_cancel)
