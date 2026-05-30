"""Resource directory resolution.

Replaces ``Constants.SystemRootPath`` from the C# source. The C# engine located
resources relative to the executing assembly's directory; here they live inside
the ``amrie/resources/`` package directory and are resolved at import time.
"""

from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
RESOURCES_DIR = _PACKAGE_DIR / "resources"
"""Absolute path to the ``resources/`` directory bundled with the package."""


def resource_path(relative: str) -> Path:
    """Resolve a filename relative to the bundled ``resources/`` directory.

    Backslashes in *relative* are converted to forward slashes so that paths
    copied verbatim from Windows config files work on POSIX systems.

    Args:
        relative: Filename or sub-path within the resources directory
            (e.g. ``"Breakpoints.txt"`` or ``"sub/file.txt"``).

    Returns:
        Absolute :class:`~pathlib.Path` to the requested resource.
    """
    return RESOURCES_DIR / relative.replace("\\", "/")


def system_root_path() -> str:
    """Return the package directory with a trailing path separator.

    Provided for C# parity: ``Constants.SystemRootPath`` always ended with
    ``Path.DirectorySeparatorChar`` so that string-concatenated paths worked
    without an extra separator.

    Returns:
        Absolute directory string ending with ``"/"``.
    """
    return str(_PACKAGE_DIR) + "/"
