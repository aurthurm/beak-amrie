"""Organism taxonomy reference data.

Port of ``Organism.cs``. Loads ``resources/Organisms.txt`` at import time and
exposes three module-level collections:

* :data:`ALL_ORGANISMS` — every row in the file.
* :data:`CURRENT_ORGANISMS` — organisms whose ``TAXONOMIC_STATUS`` is ``"C"``
  (current), keyed by ``WHONET_ORG_CODE``.
* :data:`MERGED_ORGANISMS` — mapping from a deprecated code to the current code
  that replaced it, used to handle legacy organism codes in input files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from amrie import constants as C
from amrie.io_utils import get_resource_headers
from amrie.paths import resource_path

_CURRENT_ORG_CODE = "C"
"""Value of the ``TAXONOMIC_STATUS`` column that marks an organism as current."""

_REPLACED_BY = "REPLACED_BY"
"""Column name that holds the successor code for a deprecated organism."""


@dataclass(frozen=True)
class Organism:
    """A single row from ``resources/Organisms.txt``.

    Represents one microbial taxon with its WHONET code, taxonomic hierarchy
    (kingdom → genus → species group → serovar group), and phenotypic flags
    (``ANAEROBE``, ``SUBKINGDOM_CODE``, ``MORPHOLOGY``).

    These fields are used extensively in breakpoint and expert-rule organism
    matching, where rules may apply at any level of the hierarchy (e.g. all
    members of a family, or only a specific serovar group).
    """

    WHONET_ORG_CODE: str
    ORGANISM: str
    TAXONOMIC_STATUS: str
    COMMON: bool
    COMMON_COMMENSAL: bool
    ORGANISM_TYPE: str
    ANAEROBE: bool
    MORPHOLOGY: str
    SUBKINGDOM_CODE: str
    FAMILY_CODE: str
    GENUS_GROUP: str
    GENUS_CODE: str
    SPECIES_GROUP: str
    SEROVAR_GROUP: str
    SCT_CODE: str
    SCT_TEXT: str
    GBIF_TAXON_ID: str
    GBIF_DATASET_ID: str
    GBIF_TAXONOMIC_STATUS: str
    KINGDOM: str
    PHYLUM: str
    CLASS: str
    ORDER: str
    FAMILY: str
    GENUS: str


def _load_all_organisms(path: Path | None = None) -> list[Organism]:
    """Load every row from the organisms resource file.

    Args:
        path: Override path for testing; defaults to the bundled resource.

    Returns:
        List of :class:`Organism` instances in file order.

    Raises:
        FileNotFoundError: If the resource file does not exist.
    """
    organisms_file = path or resource_path("Organisms.txt")
    if not organisms_file.exists():
        raise FileNotFoundError(str(organisms_file))

    df = pd.read_csv(
        organisms_file,
        sep=C.Delimiters.TAB_CHAR,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        quotechar=C.QUOTE,
    )
    header_map = get_resource_headers(list(df.columns))
    organisms: list[Organism] = []

    for _, row in df.iterrows():
        organisms.append(
            Organism(
                WHONET_ORG_CODE=row.iloc[header_map["WHONET_ORG_CODE"]],
                ORGANISM=row.iloc[header_map["ORGANISM"]],
                TAXONOMIC_STATUS=row.iloc[header_map["TAXONOMIC_STATUS"]],
                COMMON=row.iloc[header_map["COMMON"]] == "X",
                COMMON_COMMENSAL=row.iloc[header_map["COMMON_COMMENSAL"]] == "X",
                ORGANISM_TYPE=row.iloc[header_map["ORGANISM_TYPE"]],
                ANAEROBE=row.iloc[header_map["ANAEROBE"]] == "X",
                MORPHOLOGY=row.iloc[header_map["MORPHOLOGY"]],
                SUBKINGDOM_CODE=row.iloc[header_map["SUBKINGDOM_CODE"]],
                FAMILY_CODE=row.iloc[header_map["FAMILY_CODE"]],
                GENUS_GROUP=row.iloc[header_map["GENUS_GROUP"]],
                GENUS_CODE=row.iloc[header_map["GENUS_CODE"]],
                SPECIES_GROUP=row.iloc[header_map["SPECIES_GROUP"]],
                SEROVAR_GROUP=row.iloc[header_map["SEROVAR_GROUP"]],
                SCT_CODE=row.iloc[header_map["SCT_CODE"]],
                SCT_TEXT=row.iloc[header_map["SCT_TEXT"]],
                GBIF_TAXON_ID=row.iloc[header_map["GBIF_TAXON_ID"]],
                GBIF_DATASET_ID=row.iloc[header_map["GBIF_DATASET_ID"]],
                GBIF_TAXONOMIC_STATUS=row.iloc[header_map["GBIF_TAXONOMIC_STATUS"]],
                KINGDOM=row.iloc[header_map["KINGDOM"]],
                PHYLUM=row.iloc[header_map["PHYLUM"]],
                CLASS=row.iloc[header_map["CLASS"]],
                ORDER=row.iloc[header_map["ORDER"]],
                FAMILY=row.iloc[header_map["FAMILY"]],
                GENUS=row.iloc[header_map["GENUS"]],
            )
        )
    return organisms


def _load_current_organisms(all_orgs: list[Organism]) -> dict[str, Organism]:
    """Index current-status organisms by their WHONET code.

    Args:
        all_orgs: Full organism list as returned by :func:`_load_all_organisms`.

    Returns:
        Dictionary mapping ``WHONET_ORG_CODE`` → :class:`Organism` for every
        organism whose ``TAXONOMIC_STATUS`` equals ``"C"``.
    """
    return {o.WHONET_ORG_CODE: o for o in all_orgs if o.TAXONOMIC_STATUS == _CURRENT_ORG_CODE}


def _load_merged_organisms(path: Path | None = None) -> dict[str, str]:
    """Build a mapping from deprecated organism codes to their current successors.

    When genetic sequencing reveals that two phenotypically distinct organisms are
    the same taxon, the older code is retired and its ``REPLACED_BY`` column points
    to the current code. This mapping lets the engine silently reroute legacy codes
    found in input files.

    Args:
        path: Override path for testing; defaults to the bundled resource.

    Returns:
        Dictionary mapping deprecated ``WHONET_ORG_CODE`` → current
        ``WHONET_ORG_CODE``.
    """
    organisms_file = path or resource_path("Organisms.txt")
    df = pd.read_csv(
        organisms_file,
        sep=C.Delimiters.TAB_CHAR,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        quotechar=C.QUOTE,
    )
    header_map = get_resource_headers(list(df.columns))
    merged: dict[str, str] = {}
    for _, row in df.iterrows():
        taxonomic_status = row.iloc[header_map["TAXONOMIC_STATUS"]]
        old_code = row.iloc[header_map["WHONET_ORG_CODE"]]
        new_code = row.iloc[header_map[_REPLACED_BY]]
        if taxonomic_status != _CURRENT_ORG_CODE and new_code and old_code not in merged:
            merged[old_code] = new_code
    return merged


ALL_ORGANISMS: list[Organism] = _load_all_organisms()
"""All organisms from ``resources/Organisms.txt`` (current and deprecated)."""

CURRENT_ORGANISMS: dict[str, Organism] = _load_current_organisms(ALL_ORGANISMS)
"""Current organisms indexed by ``WHONET_ORG_CODE``; the primary lookup table."""

MERGED_ORGANISMS: dict[str, str] = _load_merged_organisms()
"""Deprecated code → current code mapping for silently handling legacy input."""
