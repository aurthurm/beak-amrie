"""Per-antibiotic interpretation rules engine.

Port of ``AntibioticSpecificInterpretationRules.cs``. This module owns two
module-level caches and provides the core numeric interpretation logic.

**Caches**

* ``_intrinsic_cache`` — stores the most-applicable intrinsic resistance rule for
  each ``(organism, guideline, drug_code)`` triple so it is looked up only once
  per session.  Protected by ``_intrinsic_cache_lock``.

* ``_breakpoint_cache`` — stores the most-applicable breakpoint for each
  ``(organism, guideline, year, drug_column)`` quadruple.  Uses double-checked
  locking: the fast (lockless) read avoids contention on cache hits; the write
  acquires ``_breakpoint_cache_lock`` and double-checks to handle concurrent
  misses.

**Parallelism**

:func:`preheat_breakpoint_cache` warms the breakpoint cache in parallel using
:class:`~concurrent.futures.ThreadPoolExecutor` before a batch interpretation run
begins, eliminating lock contention during the main per-row processing loop.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from amrie import constants as C
from amrie.antibiotic import TestMethods
from amrie.breakpoint import Breakpoint, BreakpointTypes, get_applicable_breakpoints
from amrie.expected_resistance import (
    ExpectedResistancePhenotypeRule,
    get_applicable_expected_resistance_rules,
)
from amrie.parsing import AntibioticComponents, parse_result, round_etest_half_dilutions_up

_intrinsic_cache: dict[str, dict[str, dict[str, ExpectedResistancePhenotypeRule | None]]] = {}
_intrinsic_cache_lock = threading.Lock()
_breakpoint_cache: dict[str, dict[str, dict[int, dict[str, Breakpoint | None]]]] = {}
_breakpoint_cache_lock = threading.Lock()


def clear_breakpoints() -> None:
    """Evict all entries from the breakpoint cache.

    Intended for testing and for scenarios where the underlying breakpoint
    resource data has changed between calls within the same process.
    """
    _breakpoint_cache.clear()


def _cache_has_key(
    whonet_organism_code: str,
    guideline: str,
    guideline_year: int,
    whonet_antimicrobial_full_code: str,
) -> bool:
    """Return ``True`` if the breakpoint cache already holds an entry for this key."""
    org_cache = _breakpoint_cache.get(whonet_organism_code)
    if not org_cache:
        return False
    gl_cache = org_cache.get(guideline)
    if not gl_cache:
        return False
    yr_cache = gl_cache.get(guideline_year)
    if not yr_cache:
        return False
    return whonet_antimicrobial_full_code in yr_cache


def preheat_breakpoint_cache(
    user_defined_breakpoints: list[Breakpoint],
    guideline_year: int,
    prioritized_breakpoint_types: list[str] | None,
    prioritized_sites_of_infection: list[str] | None,
    distinct_interpretation_keys: list[tuple[str, str, str]],
    max_workers: int | None = None,
) -> None:
    """Pre-populate the breakpoint cache for all distinct drug–organism combinations.

    Called once before a parallel interpretation run.  Warming the cache
    up-front means that per-row processing threads find their breakpoints already
    cached and do not contend on ``_breakpoint_cache_lock``.

    Keys already present in the cache are skipped.

    Args:
        user_defined_breakpoints: Extra breakpoints from the user-defined file.
        guideline_year: The requested guideline year for interpretation.
        prioritized_breakpoint_types: Breakpoint type filter passed through to
            :func:`~amrie.breakpoint.get_applicable_breakpoints`.
        prioritized_sites_of_infection: Site priority list passed through to
            :func:`~amrie.breakpoint.get_applicable_breakpoints`.
        distinct_interpretation_keys: List of ``(organism, guideline, drug_column)``
            3-tuples, typically collected from the input file rows.
        max_workers: Override the number of worker threads.  Defaults to
            ``min(32, cpu_count + 4, len(keys))``.
    """
    keys_to_load = [
        key
        for key in distinct_interpretation_keys
        if not _cache_has_key(key[0], key[1], guideline_year, key[2])
    ]
    if not keys_to_load:
        return

    def _load_key(key: tuple[str, str, str]) -> None:
        _determine_most_applicable_breakpoint(
            user_defined_breakpoints,
            guideline_year,
            prioritized_breakpoint_types,
            prioritized_sites_of_infection,
            key[0],
            key[1],
            key[2],
        )

    if len(keys_to_load) < 2:
        _load_key(keys_to_load[0])
        return

    effective_workers = max_workers if max_workers is not None else min(
        32, (os.cpu_count() or 1) + 4, len(keys_to_load)
    )
    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        list(executor.map(_load_key, keys_to_load))


class AntibioticSpecificInterpretationRules:
    """Evaluation context for a single antibiotic measurement on a single isolate.

    Instantiation resolves and caches the most applicable intrinsic resistance
    rule and breakpoint for the given drug–organism combination.
    :meth:`get_interpretation` then applies them in priority order:

    1. If a matching intrinsic resistance rule exists (and
       ``use_intrinsic_resistance_rules`` is ``True``), return ``"R*"``.
    2. Otherwise, compare the numeric measurement against the breakpoint
       thresholds and return ``"S"``, ``"I"``, ``"SDD"``, ``"R"``, ``"NS"``,
       ``"WT"``, ``"NWT"``, or ``""`` (uninterpretable).

    Measurement modifiers (``"<"``, ``"<="`, ``">"``) are handled by doubling or
    halving the numeric value before comparison.

    Thread safety: All cache interactions are protected by module-level locks.
    """

    def __init__(
        self,
        whonet_organism_code: str,
        whonet_antimicrobial_full_code: str,
        antimicrobial_result: str,
        user_defined_breakpoints: list[Breakpoint],
        guideline_year: int = -1,
        round_half_dilutions: bool = True,
        use_intrinsic_resistance_rules: bool = True,
        prioritized_breakpoint_types: list[str] | None = None,
        prioritized_sites_of_infection: list[str] | None = None,
    ) -> None:
        """Prepare the rule context for one drug measurement.

        Looks up (or populates) both caches so that :meth:`get_interpretation`
        can run without further I/O.

        Args:
            whonet_organism_code: WHONET organism code for the isolate.
            whonet_antimicrobial_full_code: Full WHONET column name
                (e.g. ``"AMP_ND10"``).
            antimicrobial_result: Raw measurement string from the input file.
            user_defined_breakpoints: Extra breakpoints from the config.
            guideline_year: Requested year; ``-1`` defers to the config year.
            round_half_dilutions: When ``True`` (default), E-test values are
                snapped to the next standard dilution before comparison.
            use_intrinsic_resistance_rules: When ``False``, intrinsic resistance
                rules are skipped and breakpoints are always applied.
            prioritized_breakpoint_types: Breakpoint type filter.
            prioritized_sites_of_infection: Site priority list.
        """
        self.round_half_dilutions = round_half_dilutions
        self.use_intrinsic_resistance_rules = use_intrinsic_resistance_rules
        abx = AntibioticComponents(whonet_antimicrobial_full_code)
        self.antimicrobial_test_method = abx.test_method
        self.antimicrobial_result = antimicrobial_result

        parsed, self.numeric_result, self.result_modifier = parse_result(
            self.antimicrobial_test_method, antimicrobial_result
        )
        if not parsed:
            self.numeric_result = Decimal(0)

        with _intrinsic_cache_lock:
            cache_org = _intrinsic_cache.setdefault(whonet_organism_code, {})
            cache_guideline = cache_org.setdefault(abx.guideline, {})
            if abx.code not in cache_guideline:
                rules = get_applicable_expected_resistance_rules(
                    whonet_organism_code,
                    [abx.guideline],
                    [abx.code],
                )
                cache_guideline[abx.code] = rules[0] if rules else None
            self.most_applicable_intrinsic = cache_guideline[abx.code]

        self.most_applicable_breakpoint: Breakpoint | None = None
        if self.numeric_result > 0:
            self.most_applicable_breakpoint = _determine_most_applicable_breakpoint(
                user_defined_breakpoints,
                guideline_year,
                prioritized_breakpoint_types,
                prioritized_sites_of_infection,
                whonet_organism_code,
                abx.guideline,
                whonet_antimicrobial_full_code,
            )

    def get_interpretation(self) -> str:
        """Return the interpretation string for this drug–organism measurement.

        Returns:
            One of the :class:`~amrie.constants.InterpretationCodes` values,
            optionally suffixed with ``"*"``, ``"!"``, or ``"?"``.  Returns an
            empty string (``UNINTERPRETABLE``) when no applicable breakpoint or
            rule exists, or when the measurement could not be parsed.
        """
        intrinsic = self._apply_intrinsic_resistance_rules()
        if intrinsic != C.InterpretationCodes.UNINTERPRETABLE:
            return intrinsic
        return self._apply_breakpoints()

    def _apply_intrinsic_resistance_rules(self) -> str:
        """Return ``"R*"`` if an intrinsic resistance rule applies, else ``""``."""
        if self.use_intrinsic_resistance_rules and self.most_applicable_intrinsic is not None:
            return C.InterpretationCodes.RESISTANT + C.InterpretationCodes.ASTERISK
        return C.InterpretationCodes.UNINTERPRETABLE

    def _apply_breakpoints(self) -> str:
        """Evaluate the numeric measurement against the most-applicable breakpoint."""
        if self.numeric_result <= 0:
            return C.InterpretationCodes.UNINTERPRETABLE

        bp = self.most_applicable_breakpoint
        if bp is None:
            return C.InterpretationCodes.UNINTERPRETABLE

        if bp.BREAKPOINT_TYPE == BreakpointTypes.ECOFF:
            return self._apply_ecoff(bp)

        return self._apply_human_animal(bp)

    def _rounded_mic(self) -> Decimal:
        """Return the numeric result after optional E-test half-dilution rounding."""
        if self.round_half_dilutions:
            return round_etest_half_dilutions_up(self.numeric_result)
        return self.numeric_result

    def _apply_ecoff(self, bp: Breakpoint) -> str:
        """Apply an ECOFF (epidemiological cut-off) breakpoint and return WT/NWT."""
        if self.antimicrobial_test_method == TestMethods.DISK:
            if self.numeric_result >= bp.ECV_ECOFF:
                return C.InterpretationCodes.WILD_TYPE
            return C.InterpretationCodes.NON_WILD_TYPE

        temp = self._rounded_mic()
        mod = self.result_modifier or ""

        if not mod:
            if temp <= bp.ECV_ECOFF:
                return C.InterpretationCodes.WILD_TYPE
            return C.InterpretationCodes.NON_WILD_TYPE

        if mod.startswith(C.MeasurementModifiers.GREATER_THAN):
            if temp > bp.ECV_ECOFF:
                return C.InterpretationCodes.NON_WILD_TYPE
            return C.InterpretationCodes.NON_WILD_TYPE + C.InterpretationCodes.QUESTION_MARK

        if temp <= bp.ECV_ECOFF:
            return C.InterpretationCodes.WILD_TYPE
        return C.InterpretationCodes.WILD_TYPE + C.InterpretationCodes.QUESTION_MARK

    def _apply_human_animal(self, bp: Breakpoint) -> str:
        """Apply a Human or Animal clinical breakpoint and return S/I/SDD/R/NS."""
        if self.antimicrobial_test_method == TestMethods.DISK:
            if bp.S > 0:
                if self.numeric_result <= bp.R:
                    return C.InterpretationCodes.RESISTANT
                if self.numeric_result >= bp.S:
                    return C.InterpretationCodes.SUSCEPTIBLE
                if bp.R > 0:
                    if bp.I:
                        return C.InterpretationCodes.INTERMEDIATE
                    return C.InterpretationCodes.SUSCEPTIBLE_DOSE_DEPENDENT
                return C.InterpretationCodes.NON_SUSCEPTIBLE
            return C.InterpretationCodes.UNINTERPRETABLE

        if self.antimicrobial_test_method == TestMethods.MIC:
            if bp.S <= 0:
                return C.InterpretationCodes.UNINTERPRETABLE

            temp = self._rounded_mic()
            mod = self.result_modifier or ""

            if not mod or mod == C.MeasurementModifiers.EQUALS_SIGN:
                if temp <= bp.S:
                    return C.InterpretationCodes.SUSCEPTIBLE
                if temp >= bp.R:
                    if bp.R > 0:
                        return C.InterpretationCodes.RESISTANT
                    return C.InterpretationCodes.NON_SUSCEPTIBLE
                if bp.I:
                    return C.InterpretationCodes.INTERMEDIATE
                return C.InterpretationCodes.SUSCEPTIBLE_DOSE_DEPENDENT

            if mod.startswith(C.MeasurementModifiers.GREATER_THAN):
                temp *= Decimal(2)
                if temp >= bp.R:
                    if bp.R > 0:
                        return C.InterpretationCodes.RESISTANT
                    if temp > bp.S:
                        return C.InterpretationCodes.NON_SUSCEPTIBLE
                    return C.InterpretationCodes.NON_SUSCEPTIBLE + C.InterpretationCodes.QUESTION_MARK
                if temp > bp.S:
                    return C.InterpretationCodes.NON_SUSCEPTIBLE
                return C.InterpretationCodes.RESISTANT + C.InterpretationCodes.QUESTION_MARK

            # Less-than modifier
            if temp <= bp.S:
                return C.InterpretationCodes.SUSCEPTIBLE
            if bp.S == C.MIC.MINIMUM_MIC_MEASUREMENT:
                if temp >= bp.R:
                    if bp.I:
                        return C.InterpretationCodes.INTERMEDIATE + C.InterpretationCodes.QUESTION_MARK
                    return C.InterpretationCodes.SUSCEPTIBLE_DOSE_DEPENDENT + C.InterpretationCodes.QUESTION_MARK
                if bp.I:
                    return C.InterpretationCodes.INTERMEDIATE
                return C.InterpretationCodes.SUSCEPTIBLE_DOSE_DEPENDENT
            return C.InterpretationCodes.SUSCEPTIBLE + C.InterpretationCodes.QUESTION_MARK

        return C.InterpretationCodes.UNINTERPRETABLE


def _determine_most_applicable_breakpoint(
    user_defined_breakpoints: list[Breakpoint],
    guideline_year: int,
    prioritized_breakpoint_types: list[str] | None,
    prioritized_sites_of_infection: list[str] | None,
    whonet_organism_code: str,
    guideline: str,
    whonet_antimicrobial_full_code: str,
) -> Breakpoint | None:
    """Look up (or compute and cache) the single best breakpoint for a drug–organism pair.

    Uses a double-checked locking pattern:

    1. Fast lockless read — returns immediately on a cache hit.
    2. Expensive computation outside the lock.
    3. Write under ``_breakpoint_cache_lock`` with a second check to handle races.

    Returns:
        The highest-priority :class:`~amrie.breakpoint.Breakpoint`, or ``None``
        if no applicable breakpoint exists.
    """
    # Fast path: lockless read (dict.get is atomic in CPython)
    org_cache = _breakpoint_cache.get(whonet_organism_code)
    if org_cache is not None:
        gl_cache = org_cache.get(guideline)
        if gl_cache is not None:
            yr_cache = gl_cache.get(guideline_year)
            if yr_cache is not None and whonet_antimicrobial_full_code in yr_cache:
                return yr_cache[whonet_antimicrobial_full_code]

    # Compute outside the lock — the expensive part
    bps = get_applicable_breakpoints(
        whonet_organism_code,
        user_defined_breakpoints,
        prioritized_guidelines=[guideline],
        prioritized_guideline_years=[guideline_year],
        prioritized_breakpoint_types=prioritized_breakpoint_types,
        prioritized_sites_of_infection=prioritized_sites_of_infection,
        prioritized_whonet_abx_full_drug_codes=[whonet_antimicrobial_full_code],
        return_first_breakpoint_only=True,
    )
    most = bps[0] if bps else None

    # Write under lock; double-check to avoid overwriting a concurrent write
    with _breakpoint_cache_lock:
        org_level = _breakpoint_cache.setdefault(whonet_organism_code, {})
        gl_level = org_level.setdefault(guideline, {})
        yr_level = gl_level.setdefault(guideline_year, {})
        if whonet_antimicrobial_full_code not in yr_level:
            yr_level[whonet_antimicrobial_full_code] = most
        return yr_level[whonet_antimicrobial_full_code]
