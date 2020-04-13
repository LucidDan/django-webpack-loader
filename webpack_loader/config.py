import re
from typing import TYPE_CHECKING, Optional, List, Dict, Pattern

from django.conf import settings


__all__ = ('load_config',)


if TYPE_CHECKING:
    try:
        from typing import TypedDict
    except ImportError:
        try:
            from mypy_extensions import TypedDict
        except ImportError:
            TypedDict = None

    # note if TypedDict does not exist, mypy will fail here
    if TypedDict is not None:
        class WebpackConfig(TypedDict, total=True):
            CACHE: bool
            BUNDLE_DIR_NAME: str
            STATS_FILE: str
            POLL_INTERVAL: float
            TIMEOUT: Optional[int]
            IGNORE: List[str]
            LOADER_CLASS: str
            ignores: List[Pattern]


DEFAULT_CONFIG: "WebpackConfig" = {
    'CACHE': not settings.DEBUG,
    'BUNDLE_DIR_NAME': 'webpack_bundles/',
    'STATS_FILE': 'webpack-stats.json',
    # FIXME: Explore usage of fsnotify
    'POLL_INTERVAL': 0.1,
    'TIMEOUT': None,
    'IGNORE': [".+\\.hot-update.js", ".+\\.map"],
    'LOADER_CLASS': 'webpack_loader.loader.WebpackLoader',
    'ignores': []
}


def process_config(cfg: "WebpackConfig") -> "WebpackConfig":
    """Merge in DEFAULT_CONFIG items for missing keys, and parse IGNORE into list of compiled regex"""

    # Merge configs, overriding the defaults
    return {
        **DEFAULT_CONFIG,  # type: ignore
        **cfg,
        # add a cache of compiled regex
        'ignores': [re.compile(pattern) for pattern in cfg.get('IGNORE', DEFAULT_CONFIG['IGNORE'])]
    }


# For each key-value pair in WEBPACK_LOADER settings:
# 1. Merge DEFAULT_CONFIG values into the dictionary
# 2. Compile regex patterns from IGNORE
LOADED_CONFIG: Dict[str, "WebpackConfig"] = {
    name: process_config(val) for name, val in getattr(settings, 'WEBPACK_LOADER', {'DEFAULT': {}}).items()
}


def load_config(name: str) -> "WebpackConfig":
    """Return the configuration dictionary for `name`"""
    return LOADED_CONFIG[name]


def get_all_configs() -> Dict[str, "WebpackConfig"]:
    """Return the whole configuration"""

    return LOADED_CONFIG
