from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class RouterDecision:
    request_type: str   # chat | infra
    cloud: Optional[str]   # aws | azure | None
    workflow: Optional[str]  # aws_module_consumer | azure_consumer_generation | azure_module_repo_creation | clarification_required | None
    reason: str
    debug: Dict[str, Any]