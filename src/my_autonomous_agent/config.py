"""
Loads business_config.json from the project root.
Edit that file and restart agents to apply changes — no code edits needed.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent.parent / "business_config.json"


def load_config() -> dict:
    if not _CONFIG_PATH.exists():
        logger.warning(f"business_config.json not found at {_CONFIG_PATH} — using empty config")
        return {}
    try:
        cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        logger.info(f"Config loaded from {_CONFIG_PATH}")
        return cfg
    except Exception as e:
        logger.error(f"Failed to load business_config.json: {e}")
        return {}
