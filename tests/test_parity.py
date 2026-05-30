"""Parity tests against reference interpretations.

Golden-file output is generated from this Python port. The upstream C# AMRIE
CLI is Windows/.NET-only, so automated golden parity against the original
binary is not available on Linux CI hosts.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from amrie import InterpretationConfig, interpret_file, interpret_qc_single, interpret_single
from amrie.config import read_configuration
from amrie.io_library import (
    FileInterpretationParameters,
    OutputAntibioticColumns,
    generate_output_file,
    interpret_isolates,
    load_input_file,
)
from amrie.isolate import IsolateInterpretation
from amrie.paths import resource_path

RESOURCES = resource_path("")
SAMPLE_CONFIG = RESOURCES / "SampleConfig.json"
SAMPLE_INPUT = RESOURCES / "SampleInputFile.txt"
SAMPLE_UDB = RESOURCES / "SampleUserDefinedBreakpoints.txt"
GOLDEN_OUTPUT = Path(__file__).parent / "fixtures" / "golden_sample_output.txt"
VERTICAL_CONFIG = Path(__file__).parent / "fixtures" / "vertical_config.json"
VERTICAL_UDB_CONFIG = Path(__file__).parent / "fixtures" / "vertical_udb_config.json"
ESBL_CONFIG = Path(__file__).parent / "fixtures" / "esbl_config.json"


@pytest.fixture(scope="module")
def interpretation_config():
    return read_configuration(SAMPLE_CONFIG)


@pytest.fixture(scope="module")
def file_interpretation_results():
    params = FileInterpretationParameters(
        input_file=str(SAMPLE_INPUT),
        delimiter="|",
        guideline_year=-1,
        config_file=str(SAMPLE_CONFIG),
        output_file="",
    )
    config = read_configuration(params.config_file)
    columns, rows = load_input_file(params.input_file, params.delimiter)
    return config, columns, interpret_isolates(config, columns, rows)


class TestSingleInterpretation:
    """Hand-verified cases aligned with SampleInputFile rows and known CLSI 2026 breakpoints."""

    # --- Disk: Enterococcus / Penicillin (CLSI 2026: S≥19, I=15-18, R≤14 for ND10) ---

    def test_ent_pen_disk_susceptible(self, interpretation_config):
        assert (
            IsolateInterpretation.get_single_interpretation(
                interpretation_config, "ent", "PEN_ND10", "19"
            )
            == "S"
        )

    def test_ent_ery_disk_intermediate(self, interpretation_config):
        assert (
            IsolateInterpretation.get_single_interpretation(
                interpretation_config, "ent", "ERY_ND15", "17"
            )
            == "I"
        )

    def test_ent_pen_disk_resistant(self, interpretation_config):
        assert (
            IsolateInterpretation.get_single_interpretation(
                interpretation_config, "ent", "PEN_ND10", "06"
            )
            == "R"
        )

    # --- Disk: E. coli / Cefotaxime ---

    def test_eco_ctx_disk_resistant(self, interpretation_config):
        assert (
            IsolateInterpretation.get_single_interpretation(
                interpretation_config, "eco", "CTX_ND30", "06"
            )
            == "R"
        )

    # --- MIC: E. coli / Ampicillin (CLSI 2026: S≤8, R≥32) ---

    def test_eco_amp_mic_susceptible(self, interpretation_config):
        assert (
            IsolateInterpretation.get_single_interpretation(
                interpretation_config, "eco", "AMP_NM", "4"
            )
            == "S"
        )

    def test_eco_amp_mic_resistant(self, interpretation_config):
        assert (
            IsolateInterpretation.get_single_interpretation(
                interpretation_config, "eco", "AMP_NM", "64"
            )
            == "R"
        )

    # --- MIC modifiers ---

    def test_eco_amp_mic_less_than_susceptible(self, interpretation_config):
        # <4 → <=2 (halved), well below S≤8
        assert (
            IsolateInterpretation.get_single_interpretation(
                interpretation_config, "eco", "AMP_NM", "<4"
            )
            == "S"
        )

    def test_eco_amp_mic_greater_than_resistant(self, interpretation_config):
        # >16 → >16, doubled to 32 ≥ R(32)
        assert (
            IsolateInterpretation.get_single_interpretation(
                interpretation_config, "eco", "AMP_NM", ">16"
            )
            == "R"
        )

    # --- Intrinsic resistance: Klebsiella is intrinsically resistant to ampicillin ---

    def test_kpn_amp_disk_intrinsic_resistant(self, interpretation_config):
        assert (
            IsolateInterpretation.get_single_interpretation(
                interpretation_config, "kpn", "AMP_ND10", "20"
            )
            == "R*"
        )

    def test_remove_comments_strips_modifiers(self):
        assert IsolateInterpretation.remove_comments("R*") == "R"
        assert IsolateInterpretation.remove_comments("R!") == "R"


class TestFileModeRows:
    def test_sample_row0_interpretations(self, file_interpretation_results):
        _, _, results = file_interpretation_results
        row, interps = results[0]
        assert row["ORGANISM"] == "ent"
        assert interps.get("PEN_ND10") == "S"
        assert interps.get("ERY_ND15") == "I"
        assert interps.get("NIT_ND300") == "S"

    def test_sample_row2_eco_amk(self, file_interpretation_results):
        _, _, results = file_interpretation_results
        row, interps = results[2]
        assert row["ORGANISM"] == "eco"
        assert interps.get("AMK_ND30") == "S"


class TestGoldenFile:
    """Regression: file-mode output matches committed golden TSV."""

    @pytest.fixture(scope="class")
    def generated_output(self, tmp_path_factory):
        out = tmp_path_factory.mktemp("out") / "output.txt"
        params = FileInterpretationParameters(
            input_file=str(SAMPLE_INPUT),
            delimiter="|",
            guideline_year=-1,
            config_file=str(SAMPLE_CONFIG),
            output_file=str(out),
        )
        config = read_configuration(params.config_file)
        columns, rows = load_input_file(params.input_file, params.delimiter)
        results = interpret_isolates(config, columns, rows)
        generate_output_file(str(out), config, columns, results)
        return out.read_text(encoding="utf-8")

    def test_matches_golden(self, generated_output):
        if not GOLDEN_OUTPUT.exists():
            GOLDEN_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN_OUTPUT.write_text(generated_output, encoding="utf-8")
            pytest.skip("Golden file created on first run")
        golden = GOLDEN_OUTPUT.read_text(encoding="utf-8")
        assert generated_output == golden


class TestCLI:
    def test_cli_file_command(self, tmp_path):
        out = tmp_path / "out.txt"
        subprocess.run(
            [
                "amrie",
                "file",
                "--config",
                str(SAMPLE_CONFIG),
                "--delimiter",
                "|",
                "--input",
                str(SAMPLE_INPUT),
                "--output",
                str(out),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert out.exists()
        assert "PEN_ND10_INTERP" in out.read_text(encoding="utf-8")

    def test_cli_single_command(self, tmp_path):
        out = tmp_path / "result.json"
        proc = subprocess.run(
            [
                "amrie",
                "single",
                "--config",
                str(SAMPLE_CONFIG),
                "--organism",
                "ent",
                "--antibiotic",
                "PEN_ND10",
                "--measurement",
                "19",
                "--output",
                str(out),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert proc.stdout.strip() == "S"
        assert b'"Interpretation": "S"' in out.read_bytes()


class TestLibraryAPI:
    def test_interpret_single(self, interpretation_config):
        assert interpret_single(interpretation_config, "ent", "PEN_ND10", "19") == "S"

    def test_interpret_qc_single(self):
        assert interpret_qc_single("atcc25922", "SAM_ND10", "22") == "IN"

    def test_interpret_file(self, tmp_path, interpretation_config):
        out = tmp_path / "api_out.txt"
        interpret_file(interpretation_config, SAMPLE_INPUT, out, delimiter="|")
        assert out.exists()
        assert "PEN_ND10_INTERP" in out.read_text(encoding="utf-8")

    def test_interpretation_config_alias(self, interpretation_config):
        assert isinstance(interpretation_config, InterpretationConfig)


class TestVerticalOutputMode:
    def test_vertical_columns_in_output(self, tmp_path):
        out = tmp_path / "vertical.txt"
        config = read_configuration(VERTICAL_CONFIG)
        columns, rows = load_input_file(str(SAMPLE_INPUT), "|")
        results = interpret_isolates(config, columns, rows, parallel=False)
        generate_output_file(str(out), config, columns, results)
        header = out.read_text(encoding="utf-8").splitlines()[0]
        for field in OutputAntibioticColumns.VERTICAL_ANTIBIOTIC_FIELDS:
            assert field in header.split("\t")
        lines = out.read_text(encoding="utf-8").splitlines()
        assert len(lines) > 2
        assert "PEN_ND10" in lines[1]


class TestUserDefinedBreakpoints:
    @pytest.fixture
    def udb_config(self, tmp_path):
        raw = json.loads(VERTICAL_UDB_CONFIG.read_text(encoding="utf-8"))
        raw["UserDefinedBreakpointsFile"] = str(SAMPLE_UDB)
        path = tmp_path / "udb_config.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        return read_configuration(path)

    def test_afb_pen_user_defined_breakpoints(self, udb_config):
        assert interpret_single(udb_config, "afb", "PEN_ND10", "19") == "R"
        assert interpret_single(udb_config, "afb", "PEN_ND10", "28") == "S"


class TestParallelAndPreheat:
    def test_parallel_matches_sequential(self, interpretation_config):
        columns, rows = load_input_file(str(SAMPLE_INPUT), "|")
        sequential = interpret_isolates(
            interpretation_config, columns, rows, parallel=False
        )
        parallel = interpret_isolates(
            interpretation_config, columns, rows, parallel=True
        )
        assert sequential == parallel


class TestUseIntrinsicResistanceRules:
    """Verify the UseIntrinsicResistanceRules config flag is wired through the call chain."""

    def test_disabled_falls_back_to_breakpoint(self):
        from amrie.config import InterpretationConfiguration

        config = InterpretationConfiguration(
            use_intrinsic_resistance_rules=False,
            guideline_year=2026,
            prioritized_breakpoint_types=["Human", "Animal", "ECOFF"],
        )
        # kpn (Klebsiella) is intrinsically resistant to AMP — normally returns R*.
        # With intrinsic rules disabled the disk breakpoint applies (S≥17).
        assert IsolateInterpretation.get_single_interpretation(config, "kpn", "AMP_ND10", "20") == "S"
        assert IsolateInterpretation.get_single_interpretation(config, "kpn", "AMP_ND10", "06") == "R"

    def test_enabled_returns_intrinsic_resistant(self, interpretation_config):
        assert (
            IsolateInterpretation.get_single_interpretation(
                interpretation_config, "kpn", "AMP_ND10", "20"
            )
            == "R*"
        )


class TestIO:
    def test_split_line_requires_single_char_delimiter(self):
        from amrie.io_utils import split_line

        with pytest.raises(ValueError, match="single character"):
            split_line("a,b,c", ",,")

    def test_split_line_empty_delimiter_raises(self):
        from amrie.io_utils import split_line

        with pytest.raises(ValueError, match="single character"):
            split_line("a,b", "")


class TestESBLExpertRules:
    @pytest.fixture
    def esbl_config(self):
        return read_configuration(ESBL_CONFIG)

    def test_esbl_confirmed_marks_affected_antibiotics(self, esbl_config):
        row = {
            "ORGANISM": "eco",
            "ESBL": "+",
            "MOX_ND30": "25",
        }
        interp = IsolateInterpretation(
            row,
            list(row.keys()),
            esbl_config.enabled_expert_interpretation_rules,
            esbl_config.user_defined_breakpoints,
            guideline_year=int(esbl_config.guideline_year),
            prioritized_breakpoint_types=esbl_config.prioritized_breakpoint_types,
            prioritized_sites_of_infection=esbl_config.prioritized_sites_of_infection,
        ).get_all_interpretations()
        assert interp.get("MOX_ND30") == "R!"
