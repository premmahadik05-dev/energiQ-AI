"""Library versions of the interpreter that produced a result, so a number can be traced to the environment that made it."""
from __future__ import annotations

import importlib.metadata as md
import platform

_PACKAGES = ("numpy", "pandas", "scipy", "scikit-learn", "xgboost", "torch", "joblib")


def environment_info() -> dict[str, str]:
    """Python, OS and the versions of the numerical libraries that influence results (missing packages are omitted)."""
    info = {"python": platform.python_version(), "platform": f"{platform.system()} {platform.machine()}"}
    for name in _PACKAGES:
        try:
            info[name] = md.version(name)
        except md.PackageNotFoundError:
            continue
    return info
