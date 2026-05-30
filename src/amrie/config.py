"""Interpretation engine configuration.

Port of ``InterpretationConfiguration.cs``. Reads a JSON configuration file into
:class:`InterpretationConfiguration` and provides :func:`default_configuration`
for programmatic use without a file.

JSON key names use PascalCase to match the C# original
(e.g. ``"GuidelineYear"``, ``"HorizontalAntibioticResults"``). They are mapped
to snake_case dataclass fields by :func:`_snake_to_pascal`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import orjson

from amrie import constants as C
from amrie.breakpoint import Breakpoint, BreakpointTypes, load_breakpoints
from amrie.expert_rule import RuleCodes
from amrie.paths import resource_path, system_root_path


@dataclass
class InterpretationConfiguration:
    """All settings that control a single interpretation run.

    Attributes:
        round_half_dilutions: When ``True`` (default), E-test MIC values are
            snapped to the next standard dilution before comparison.
        include_interpretation_comments: When ``False`` (default), ``"*"`` and
            ``"!"`` suffixes are stripped from the output.
        use_intrinsic_resistance_rules: When ``False``, intrinsic resistance
            rules are bypassed and only breakpoints are applied.
        enabled_expert_interpretation_rules: Whitelist of expert rule codes to
            apply; ``None`` enables all rules.
        guideline_year: The breakpoint table year to use.
        prioritized_breakpoint_types: Ordered list of breakpoint type names
            (e.g. ``["Human", "Animal", "ECOFF"]``); ``None`` allows any type.
        prioritized_sites_of_infection: Ordered list of site names;
            :meth:`update_sites_of_infection` fills in any missing default sites.
        disabled_sites_of_infection: Sites to exclude even if they appear in the
            default order.
        horizontal_antibiotic_results: When ``True`` (default), the output file
            appends ``"_INTERP"`` columns beside each measurement column.  When
            ``False``, antibiotics are transposed into three vertical columns.
        user_defined_breakpoints_file: Path to a user-defined breakpoints TSV;
            loaded into :attr:`user_defined_breakpoints` at read time.
        user_defined_breakpoints: Loaded user-defined breakpoints.
    """
    round_half_dilutions: bool = True
    include_interpretation_comments: bool = False
    use_intrinsic_resistance_rules: bool = True
    enabled_expert_interpretation_rules: list[str] | None = None
    guideline_year: int = C.BREAKPOINT_TABLE_REVISION_YEAR
    prioritized_breakpoint_types: list[str] | None = None
    prioritized_sites_of_infection: list[str] | None = None
    disabled_sites_of_infection: list[str] | None = None
    horizontal_antibiotic_results: bool = True
    user_defined_breakpoints_file: str = ""
    user_defined_breakpoints: list[Breakpoint] = field(default_factory=list)

    def update_sites_of_infection(self) -> None:
        """Reconcile the site-of-infection lists against the canonical default order.

        Called automatically by :func:`read_configuration` after loading.

        * Removes any site name not present in ``DEFAULT_ORDER``.
        * Appends any ``DEFAULT_ORDER`` sites not already in the list (and not
          in ``disabled_sites_of_infection``) so that newly introduced sites are
          included automatically in future table revisions.
        """
        if self.prioritized_sites_of_infection is None:
            return

        default_order = C.SitesOfInfection.DEFAULT_ORDER
        self.prioritized_sites_of_infection = [
            s for s in self.prioritized_sites_of_infection if s in default_order
        ]

        if self.disabled_sites_of_infection is not None:
            self.disabled_sites_of_infection = [
                s for s in self.disabled_sites_of_infection if s in default_order
            ]
            self.prioritized_sites_of_infection = self.prioritized_sites_of_infection + [
                s
                for s in default_order
                if s not in self.prioritized_sites_of_infection
                and s not in self.disabled_sites_of_infection
            ]
        else:
            self.prioritized_sites_of_infection = self.prioritized_sites_of_infection + [
                s for s in default_order if s not in self.prioritized_sites_of_infection
            ]


def _filter_config_keys(data: dict) -> dict:
    """Remove comment and disabled keys from the raw JSON dict."""
    return {
        k: v
        for k, v in data.items()
        if not k.startswith("_Comment") and not k.startswith("DISABLED_")
    }


def _snake_to_pascal(name: str) -> str:
    """Map a JSON PascalCase key to the corresponding dataclass field name."""
    mapping = {
        "RoundHalfDilutions": "round_half_dilutions",
        "IncludeInterpretationComments": "include_interpretation_comments",
        "UseIntrinsicResistanceRules": "use_intrinsic_resistance_rules",
        "EnabledExpertInterpretationRules": "enabled_expert_interpretation_rules",
        "GuidelineYear": "guideline_year",
        "PrioritizedBreakpointTypes": "prioritized_breakpoint_types",
        "PrioritizedSitesOfInfection": "prioritized_sites_of_infection",
        "DisabledSitesOfInfection": "disabled_sites_of_infection",
        "HorizontalAntibioticResults": "horizontal_antibiotic_results",
        "UserDefinedBreakpointsFile": "user_defined_breakpoints_file",
    }
    return mapping.get(name, name)


def read_configuration(config_file: str | Path) -> InterpretationConfiguration:
    """Load an :class:`InterpretationConfiguration` from a JSON file.

    Keys prefixed with ``"_Comment"`` or ``"DISABLED_"`` are silently ignored,
    allowing the config file to carry documentation and temporarily disabled
    settings without breaking parsing.

    Empty lists for ``EnabledExpertInterpretationRules``,
    ``PrioritizedBreakpointTypes``, ``PrioritizedSitesOfInfection``, and
    ``DisabledSitesOfInfection`` are converted to ``None`` to match the C#
    convention of treating empty lists the same as absent fields.

    If ``UserDefinedBreakpointsFile`` is set and the file exists (resolved
    relative to the package root when a relative path is given), the breakpoints
    are loaded and stored in :attr:`~InterpretationConfiguration.user_defined_breakpoints`.

    Args:
        config_file: Path to the JSON configuration file.

    Returns:
        Populated :class:`InterpretationConfiguration` with sites of infection
        reconciled by :meth:`~InterpretationConfiguration.update_sites_of_infection`.
    """
    path = Path(config_file)
    raw = orjson.loads(path.read_bytes())
    filtered = _filter_config_keys(raw)

    kwargs: dict = {}
    for key, value in filtered.items():
        field_name = _snake_to_pascal(key)
        if field_name == "enabled_expert_interpretation_rules" and value == []:
            value = None
        if field_name == "prioritized_breakpoint_types" and value == []:
            value = None
        if field_name == "prioritized_sites_of_infection" and value == []:
            value = None
        if field_name == "disabled_sites_of_infection" and value == []:
            value = None
        kwargs[field_name] = value

    config = InterpretationConfiguration(**kwargs)

    udb_file = config.user_defined_breakpoints_file
    if udb_file:
        udb_path = Path(udb_file)
        if not udb_path.is_absolute():
            udb_path = Path(system_root_path()) / udb_file.replace("\\", "/")
        if udb_path.exists():
            config.user_defined_breakpoints = load_breakpoints(udb_path, user_defined=True)

    config.update_sites_of_infection()
    return config


def default_configuration() -> InterpretationConfiguration:
    """Return a sensible default :class:`InterpretationConfiguration`.

    Enables MRS, BLNAR, and ICR expert rules; restricts to Human breakpoints;
    and enables all default sites of infection in the standard priority order.
    Equivalent to ``InterpretationConfiguration.DefaultConfiguration()`` in C#.

    Returns:
        A ready-to-use configuration with comments included in output.
    """
    return InterpretationConfiguration(
        round_half_dilutions=True,
        include_interpretation_comments=True,
        enabled_expert_interpretation_rules=[
            RuleCodes.MRSTAPH,
            RuleCodes.BLNAR,
            RuleCodes.ICR,
        ],
        guideline_year=C.BREAKPOINT_TABLE_REVISION_YEAR,
        prioritized_breakpoint_types=[BreakpointTypes.HUMAN],
        prioritized_sites_of_infection=list(C.SitesOfInfection.DEFAULT_ORDER),
        disabled_sites_of_infection=[],
        user_defined_breakpoints_file="",
    )
