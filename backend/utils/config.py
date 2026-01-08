import yaml
import os
from typing import Dict, Any

def load_agents_config(path: str = "backend/config/agents.yaml") -> Dict[str, Any]:
    """
    Loads agent configurations (prompts, models) from YAML.
    """
    if not os.path.exists(path):
        # Fallback to defaults if file missing (or raise error)
        return {}
        
    with open(path, "r") as f:
        return yaml.safe_load(f)
