"""Shared CSV / delimited-text utilities.

Port of the ``IO_Library.SplitLine``, ``IO_Library.ToLine``, and
``IO_Library.GetResourceHeaders`` helpers from ``IO_Library.cs``. These are kept
in a separate module so that both ``io_library`` (user data files) and the
resource-loading modules (``breakpoint``, ``expert_rule``, etc.) can import them
without creating circular dependencies.
"""

from __future__ import annotations

from amrie import constants as C


def get_resource_headers(headers: list[str]) -> dict[str, int]:
    """Build a column-name → index mapping from a list of header strings.

    Args:
        headers: Ordered list of column names, typically obtained from the first
            row of a resource TSV file.

    Returns:
        Dictionary mapping each header name to its zero-based column index.
    """
    return {name: i for i, name in enumerate(headers)}


def split_line(record: str, delimiter: str) -> list[str]:
    """Split a delimited record respecting quoted fields.

    Implements the same quote-aware parsing as ``IO_Library.SplitLine`` in the
    C# source. Fields wrapped in double quotes may contain the delimiter character
    without being split. A doubled quote (``""``) inside a quoted field represents
    a literal quote character.

    Args:
        record: The raw text line to split.
        delimiter: A **single** character used as the field separator. Passing a
            multi-character string raises :exc:`ValueError`.

    Returns:
        List of field strings. Leading and trailing whitespace is stripped from
        each field unless the field is quoted.

    Raises:
        ValueError: If *delimiter* is not exactly one character long.
    """
    if len(delimiter) != 1:
        raise ValueError(f"delimiter must be a single character, got {delimiter!r}")
    if not record or delimiter not in record:
        return [record] if record is not None else [""]

    results: list[str] = []
    result: list[str] = []
    in_qualifier = False
    in_field = False
    row = f"{record}{delimiter}"

    idx = 0
    while idx < len(row):
        ch = row[idx]
        if ch == delimiter:
            if not in_qualifier:
                results.append("".join(result).strip())
                result = []
                in_field = False
            else:
                result.append(ch)
        else:
            if ch != " ":
                if ch == C.QUOTE:
                    if in_qualifier:
                        next_idx = _index_of_next_non_whitespace(row, idx + 1)
                        if next_idx >= 0 and row[next_idx] == delimiter:
                            in_qualifier = False
                            idx += 1
                            continue
                        in_field = True
                        result.append(ch)
                    else:
                        in_qualifier = True
                else:
                    result.append(ch)
                    in_field = True
            elif in_qualifier or in_field:
                result.append(ch)
        idx += 1

    return results


def _index_of_next_non_whitespace(source: str, start_index: int) -> int:
    """Return the index of the first non-whitespace character at or after *start_index*.

    Args:
        source: String to search.
        start_index: Position to begin searching from.

    Returns:
        Index of the next non-whitespace character, or ``-1`` if none is found.
    """
    if start_index < 0 or source is None:
        return -1
    for i in range(start_index, len(source)):
        if not source[i].isspace():
            return i
    return -1


def to_line(values: list[str], delimiter: str) -> str:
    """Join a list of field values into a single delimited line.

    Fields that contain the delimiter character or a double-quote are wrapped in
    double quotes; any existing double-quotes within such fields are escaped as
    ``""``. Fields that need no quoting are written as-is.

    Args:
        values: Ordered list of field values to join.
        delimiter: Single-character field separator (e.g. ``"\\t"`` or ``","``).

    Returns:
        A single string with fields joined by *delimiter*, ready to be written as
        a line in a delimited output file.
    """
    def format_field(v: str) -> str:
        if not v or (delimiter not in v and C.QUOTE not in v):
            return v
        escaped = v.replace(C.QUOTE, C.TWO_QUOTES) if C.QUOTE in v else v
        return f"{C.QUOTE}{escaped}{C.QUOTE}"

    return delimiter.join(format_field(v) for v in values)
