"""Compatibility facade for the refactored Terrabot backend.

Stateful orchestration remains in ``terrabot_service_core`` so existing callers,
imports, global workflow state, and Teams/VS Code behavior remain intact. Stable
leaf helpers are now separated under ``shared_code/terrabot_*_helpers.py``.

This facade deliberately exports every non-dunder core symbol, including private
compatibility functions used by the existing Teams bot/function app.
"""
from __future__ import annotations

from shared_code import terrabot_service_core as _core
from shared_code.terrabot_teams_handlers import handle_teams_chat_request as _teams_handle
from shared_code.automated_tests.terrabot_test_runner import (
    handle_teams_automated_test_request as _automated_test_handle,
)
from shared_code.automated_tests.terrabot_test_worker import (
    process_automated_test_queue_message as _automated_test_worker,
)

for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals()[_name] = _value

def __getattr__(name: str):
    return getattr(_core, name)

def __dir__():
    return sorted(set(globals()) | set(dir(_core)))

# Explicit public handler override: adapters call the modular Teams entrypoint.
def handle_teams_chat_request(data: dict):
    return _teams_handle(_core, data)

# Explicit automated-test handler. The isolated runner receives the loaded core
# module so it can exercise the real Teams backend without duplicating workflow
# logic in this compatibility facade.
def handle_teams_automated_test_request(data: dict):
    return _automated_test_handle(_core, data)


# Queue-trigger adapter: the Function App passes the queue message here so the
# long-running test worker stays outside the Teams HTTP invocation.
def process_automated_test_queue_message(message):
    return _automated_test_worker(_core, message)
