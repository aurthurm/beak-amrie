"""Quality control interpretation tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from amrie import interpret_qc_single
from amrie.qc import (
    get_applicable_quality_control_range,
    get_quality_control_interpretation,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestQualityControl:
    def test_applicable_range_atcc25922_sam(self):
        qc_range = get_applicable_quality_control_range("atcc25922", "SAM_ND10")
        assert qc_range is not None
        assert qc_range.STRAIN.lower() == "atcc25922"
        assert qc_range.WHONET_ABX_CODE == "SAM"
        assert qc_range.MINIMUM == pytest.approx(19)
        assert qc_range.MAXIMUM == pytest.approx(24)

    def test_in_range_disk_measurement(self):
        assert get_quality_control_interpretation("atcc25922", "SAM_ND10", "22") == "IN"

    def test_out_of_range_disk_measurement(self):
        assert get_quality_control_interpretation("atcc25922", "SAM_ND10", "18") == "OUT"

    def test_empty_measurement_uninterpretable(self):
        assert get_quality_control_interpretation("atcc25922", "SAM_ND10", "") == ""

    def test_unknown_strain_uninterpretable(self):
        assert get_quality_control_interpretation("unknownstrain", "SAM_ND10", "22") == ""

    def test_library_wrapper(self):
        assert interpret_qc_single("atcc25922", "SAM_ND10", "22") == "IN"

    def test_cli_qc_command(self, tmp_path):
        out = tmp_path / "qc.json"
        proc = subprocess.run(
            [
                "amrie",
                "qc",
                "--organism",
                "atcc25922",
                "--antibiotic",
                "SAM_ND10",
                "--measurement",
                "22",
                "--output",
                str(out),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert proc.stdout.strip() == "IN"
        assert b'"Interpretation": "IN"' in out.read_bytes()
