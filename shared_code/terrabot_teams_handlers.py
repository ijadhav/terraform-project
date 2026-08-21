from __future__ import annotations
from typing import Any


def handle_teams_chat_request(core: Any, data: dict):
    """Stable Teams entrypoint delegated to the stateful Terrabot core.

    Keeping the public Teams handler in its own module prevents HTTP/Teams
    adapters from depending on the internal service file layout while the
    stateful workflow is migrated incrementally without breaking behavior.
    """
    return core.handle_teams_chat_request(data)
