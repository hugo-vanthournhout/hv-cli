from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def load_config(config_type: str = "variables") -> Dict[str, Any]:
    """Load configuration from YAML file."""
    config_path = Path(__file__).parent / "config" / f"{config_type}.yaml"
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_credential(service: str, key: str) -> Optional[str]:
    """Get a specific credential from credentials.yaml."""
    creds = load_config("credentials")
    return creds.get(service, {}).get(key)
