"""Load config.yaml once and expose it as a dict."""
import functools
import os

import yaml

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "config.yaml")


@functools.lru_cache(maxsize=1)
def load_config():
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)
