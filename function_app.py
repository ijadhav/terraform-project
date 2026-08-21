import json
import logging
import os
import mimetypes
import azure.functions as func
import html
import azure.functions as func
from shared_code.keyvault_loader import load_keyvault_secrets
load_keyvault_secrets()

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def json_response(payload: dict, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
    )


def read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def render_template_response(template_name: str) -> func.HttpResponse:
    template_path = os.path.join(TEMPLATES_DIR, template_name)

    if not os.path.isfile(template_path):
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "error": f"{template_name} not found",
                    "expected_path": template_path,
                    "base_dir": BASE_DIR,
                }
            ),
            status_code=404,
            mimetype="application/json",
        )

    return func.HttpResponse(
        read_text_file(template_path),
        status_code=200,
        mimetype="text/html",
        headers=NO_CACHE_HEADERS if template_name == "drift.html" else None,
    )


def _request_json(req: func.HttpRequest) -> dict:
    try:
        body = req.get_json()
        return body if isinstance(body, dict) else {}
    except ValueError:
        return {}


def _query_dict(req: func.HttpRequest) -> dict:
    return {key: value for key, value in req.params.items()}


def _terrabot_service():
    """Load the refactored Terrabot compatibility facade lazily.

    Keeping this import package-qualified is required after moving the stateful
    implementation to shared_code.terrabot_service_core. Lazy loading preserves
    the existing Function App startup behavior for routes that do not use Terrabot.
    """
    from shared_code import terrabot_service

    return terrabot_service

def get_authenticated_user(req: func.HttpRequest) -> dict:
    return {
        "email": req.headers.get("X-MS-CLIENT-PRINCIPAL-NAME", ""),
        "id": req.headers.get("X-MS-CLIENT-PRINCIPAL-ID", ""),
        "provider": req.headers.get("X-MS-CLIENT-PRINCIPAL-IDP", ""),
    }


def require_authenticated(req: func.HttpRequest):
    if os.getenv("AUTH_DISABLED", "").lower() == "true":
        return None

    if not req.headers.get("X-MS-CLIENT-PRINCIPAL-NAME"):
        return json_response(
            {"ok": False, "error": "Unauthorized"},
            status_code=401,
        )

    return None


def require_extension_api_token(req: func.HttpRequest):
    expected = (os.getenv("TERRABOT_API_TOKEN") or "").strip()
    if not expected:
        # Local/dev compatibility. Production should always configure TERRABOT_API_TOKEN.
        return None
    authorization = (req.headers.get("Authorization") or "").strip()
    supplied = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not supplied or not __import__("hmac").compare_digest(supplied, expected):
        return json_response(
            {"ok": False, "reply": "Unauthorized: invalid or missing Terrabot API token."},
            status_code=401,
        )
    return None

@app.route(route="auth/me", methods=["GET"])
def auth_me(req: func.HttpRequest) -> func.HttpResponse:
    auth_error = require_authenticated(req)
    if auth_error:
        return auth_error

    return json_response({
        "ok": True,
        "user": get_authenticated_user(req),
        "login_url": "/.auth/login/okta",
        "logout_url": "/.auth/logout",
    })

@app.route(route="", methods=["GET"])
def root(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        status_code=302,
        headers={
            "Location": "/index"
        }
    )

@app.route(route="index", methods=["GET"])
def home(req: func.HttpRequest) -> func.HttpResponse:
    return render_template_response("index.html")


@app.route(route="drift", methods=["GET"])
def drift(req: func.HttpRequest) -> func.HttpResponse:
    return render_template_response("drift.html")


@app.route(route="drift-trigger", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def drift_trigger(req: func.HttpRequest) -> func.HttpResponse:

    auth_error = require_authenticated(req)
    if auth_error:
       return auth_error
    data = _request_json(req)
    if not data:
        data = _query_dict(req)

    try:
        from shared_code.commit_drift_service import handle_commit_drift_refresh_request

        result, status_code = handle_commit_drift_refresh_request(data, req.headers)
    except Exception as e:
        return json_response(
            {
                "ok": False,
                "reply": "Backend GitHub context drift refresh failed to load.",
                "error": str(e),
            },
            status_code=500,
        )

    return json_response(result, status_code=status_code)


@app.route(route="drift-refresh", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def drift_refresh(req: func.HttpRequest) -> func.HttpResponse:
    auth_error = require_authenticated(req)
    if auth_error:
       return auth_error
    data = _request_json(req)
    if not data:
        data = _query_dict(req)

    try:
        from shared_code.commit_drift_service import handle_commit_drift_refresh_request

        result, status_code = handle_commit_drift_refresh_request(data, req.headers)
    except Exception as e:
        return json_response(
            {
                "ok": False,
                "reply": "Backend GitHub context drift refresh failed to load.",
                "error": str(e),
            },
            status_code=500,
        )

    return json_response(result, status_code=status_code)


@app.route(route="drift-status", methods=["GET", "POST"], auth_level=func.AuthLevel.ANONYMOUS)
def drift_status(req: func.HttpRequest) -> func.HttpResponse:

    auth_error = require_authenticated(req)
    if auth_error:  
       return auth_error
    if req.method == "POST":
        data = _request_json(req)
    else:
        data = _query_dict(req)

    try:
        from shared_code.commit_drift_service import handle_commit_drift_status_request

        result, status_code = handle_commit_drift_status_request(data, req.headers)
    except Exception as e:
        return json_response(
            {
                "ok": False,
                "reply": "Backend GitHub context drift status failed to load.",
                "error": str(e),
            },
            status_code=500,
        )

    return json_response(result, status_code=status_code)


@app.route(route="drift-attribution", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def drift_attribution(req: func.HttpRequest) -> func.HttpResponse:
    data = _request_json(req)

    try:
        from shared_code.commit_drift_service import handle_commit_drift_attribution_request

        result, status_code = handle_commit_drift_attribution_request(data, req.headers)
    except Exception as e:
        return json_response(
            {
                "ok": False,
                "reply": "Backend GitHub context drift attribution failed to load.",
                "error": str(e),
            },
            status_code=500,
        )

    return json_response(result, status_code=status_code)


@app.route(route="drift-agent-chat", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def drift_agent_chat(req: func.HttpRequest) -> func.HttpResponse:
    data = _request_json(req)

    try:
        from shared_code.commit_drift_service import handle_commit_drift_question_request

        result, status_code = handle_commit_drift_question_request(data, req.headers)
    except Exception as e:
        return json_response(
            {
                "ok": False,
                "reply": "Backend GitHub context drift question failed to load.",
                "error": str(e),
            },
            status_code=500,
        )

    return json_response(result, status_code=status_code)


@app.route(route="drift-ingest", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def drift_ingest(req: func.HttpRequest) -> func.HttpResponse:

    data = _request_json(req)

    try:
        from shared_code.commit_drift_service import handle_commit_drift_ingest_request

        result, status_code = handle_commit_drift_ingest_request(data, req.headers)
    except Exception as e:
        return json_response(
            {
                "ok": False,
                "reply": "Backend GitHub context drift ingest compatibility failed to load.",
                "error": str(e),
            },
            status_code=500,
        )

    return json_response(result, status_code=status_code)


@app.route(route="static/{*filepath}", methods=["GET"])
def static_files(req: func.HttpRequest) -> func.HttpResponse:
    filepath = req.route_params.get("filepath", "")

    if not filepath:
        return func.HttpResponse(
            "Filename is required",
            status_code=400,
            mimetype="text/plain",
        )

    normalized = os.path.normpath(filepath).replace("\\", "/").lstrip("/")
    file_path = os.path.join(STATIC_DIR, normalized)

    if not file_path.startswith(STATIC_DIR):
        return func.HttpResponse(
            "Invalid file path",
            status_code=400,
            mimetype="text/plain",
        )

    if not os.path.isfile(file_path):
        return func.HttpResponse(
            f"Static file not found: {file_path}",
            status_code=404,
            mimetype="text/plain",
        )

    mime_type, _ = mimetypes.guess_type(file_path)
    mime_type = mime_type or "application/octet-stream"

    with open(file_path, "rb") as f:
        content = f.read()

    static_headers = NO_CACHE_HEADERS if normalized.endswith((".js", ".css")) else None

    return func.HttpResponse(
        body=content,
        status_code=200,
        mimetype=mime_type,
        headers=static_headers,
    )

@app.route(route="vscode/github-branch", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def vscode_github_branch(req: func.HttpRequest) -> func.HttpResponse:
  
    data = _request_json(req)
    try:
        service = _terrabot_service()
        return json_response(service.handle_workspace_branch_request(data), status_code=200)
    except PermissionError as exc:
        return json_response({"ok": False, "reply": str(exc)}, status_code=403)
    except ValueError as exc:
        return json_response({"ok": False, "reply": str(exc)}, status_code=400)
    except Exception as exc:
        return json_response({"ok": False, "reply": "GitHub branch creation failed.", "error": str(exc)}, status_code=502)

@app.route(route="vscode/github-pr-metadata", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def vscode_github_pr_metadata(req: func.HttpRequest) -> func.HttpResponse:
    data = _request_json(req)
    try:
        service = _terrabot_service()
        return json_response(service.handle_workspace_pr_metadata_request(data), status_code=200)
    except PermissionError as exc:
        return json_response({"ok": False, "reply": str(exc)}, status_code=403)
    except ValueError as exc:
        return json_response({"ok": False, "reply": str(exc)}, status_code=400)
    except Exception as exc:
        logging.exception("GitHub PR metadata generation failed")
        return json_response(
            {
                "ok": False,
                "reply": "GitHub PR metadata generation failed.",
                "error": str(exc),
            },
            status_code=502,
        )

@app.route(route="vscode/github-pr", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def vscode_github_pr(req: func.HttpRequest) -> func.HttpResponse:
    
    data = _request_json(req)
    try:
        service = _terrabot_service()
        return json_response(service.handle_workspace_pr_request(data), status_code=200)
    except PermissionError as exc:
        return json_response({"ok": False, "reply": str(exc)}, status_code=403)
    except ValueError as exc:
        return json_response({"ok": False, "reply": str(exc)}, status_code=400)
    except Exception as exc:
        return json_response({"ok": False, "reply": "GitHub PR creation failed.", "error": str(exc)}, status_code=502)

@app.route(
    route="teams/health",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def teams_health(req: func.HttpRequest) -> func.HttpResponse:
    del req

    app_id = (
        os.getenv("MicrosoftAppId")
        or os.getenv("TEAMS_BOT_APP_ID")
        or ""
    ).strip()

    app_password = (
        os.getenv("MicrosoftAppPassword")
        or os.getenv("TEAMS_BOT_APP_PASSWORD")
        or ""
    ).strip()

    tenant_id = (
        os.getenv("MicrosoftAppTenantId")
        or os.getenv("TEAMS_BOT_TENANT_ID")
        or os.getenv("AZURE_TENANT_ID")
        or ""
    ).strip()

    app_type = (
        os.getenv("MicrosoftAppType")
        or os.getenv("TEAMS_BOT_APP_TYPE")
        or ("SingleTenant" if tenant_id else "MultiTenant")
    ).strip()

    project_endpoint = (
        os.getenv("PROJECT_ENDPOINT_STRING")
        or ""
    ).strip()

    agent_name = (
        os.getenv("AZURE_AGENT_NAME")
        or ""
    ).strip()

    adapter_loaded = False
    adapter_error = ""

    try:
        from shared_code.teams_bot import ADAPTER

        adapter_loaded = ADAPTER is not None
    except Exception as exc:
        adapter_error = str(exc)

    single_tenant_ready = (
        app_type.lower() != "singletenant"
        or bool(tenant_id)
    )

    bot_ready = bool(
        app_id
        and app_password
        and single_tenant_ready
        and adapter_loaded
    )

    foundry_ready = bool(
        project_endpoint
        and agent_name
    )

    ready = bot_ready and foundry_ready

    return json_response(
        {
            "ok": ready,
            "service": "terrabot-teams",
            "messaging_endpoint": "/api/teams/messages",
            "microsoft_app_type": app_type,
            "microsoft_app_id_configured": bool(app_id),
            "microsoft_app_password_configured": bool(app_password),
            "microsoft_app_tenant_id_configured": bool(tenant_id),
            "bot_adapter_loaded": adapter_loaded,
            "bot_adapter_error": adapter_error,
            "foundry_project_endpoint_configured": bool(project_endpoint),
            "foundry_agent_name_configured": bool(agent_name),
        },
        status_code=200 if ready else 503,
    )




@app.route(route="chat", methods=["POST"])
def chat(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
    except ValueError:
        return json_response(
            {
                "ok": False,
                "reply": "Invalid JSON request body.",
            },
            status_code=400,
        )

    try:
        service = _terrabot_service()

        result, status_code = service.handle_chat_request(data)
    except Exception as e:
        return json_response(
            {
                "ok": False,
                "reply": "Chat backend failed to load.",
                "error": str(e),
            },
            status_code=500,
        )

    return json_response(result, status_code=status_code)


@app.route(route="trigger-pr-pipeline", methods=["POST"])
def trigger_pr_pipeline(req: func.HttpRequest) -> func.HttpResponse:
    
    auth_error = require_authenticated(req)
    if auth_error:
       return auth_error
    try:
        data = req.get_json()
    except ValueError:
        return json_response(
            {
                "ok": False,
                "reply": "Invalid JSON request body.",
            },
            status_code=400,
        )

    required = ["repo_owner", "repo_name", "pr_number", "source_branch", "target_branch"]
    missing = [k for k in required if not data.get(k)]

    if missing:
        return json_response(
            {
                "ok": False,
                "reply": f"Missing required fields: {', '.join(missing)}",
            },
            status_code=400,
        )

    try:
        service = _terrabot_service()

        result = service.trigger_test_branch_pipeline_for_pr(
            repo_owner=str(data["repo_owner"]),
            repo_name=str(data["repo_name"]),
            pr_number=int(data["pr_number"]),
            source_branch=str(data["source_branch"]),
            target_branch=str(data["target_branch"]),
        )
    except Exception as e:
        return json_response(
            {
                "ok": False,
                "reply": "Failed to trigger Azure pipeline.",
                "error": str(e),
            },
            status_code=500,
        )

    return json_response(
        {
            "ok": True,
            "reply": "Azure pipeline triggered successfully.",
            "run": result,
        },
        status_code=200,
    )


@app.route(route="plan-risk", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def plan_risk(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
    except ValueError:
        return json_response(
            {
                "ok": False,
                "reply": "Invalid JSON request body.",
            },
            status_code=400,
        )

    try:
        service = _terrabot_service()

        result, status_code = service.handle_plan_risk_request(data, req.headers)
    except Exception as e:
        return json_response(
            {
                "ok": False,
                "reply": "Plan-risk backend failed to load.",
                "error": str(e),
            },
            status_code=500,
        )

    return json_response(result, status_code=status_code)


@app.route(route="drift-jira-ticket", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def drift_jira_ticket(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
    except ValueError:
        data = {}

    try:
        from shared_code.commit_drift_service import handle_commit_drift_create_jira_request
        result, status_code = handle_commit_drift_create_jira_request(data, req.headers)
    except Exception as e:
        return json_response({"ok": False, "reply": "Jira drift ticket backend failed to load.", "error": str(e)}, status_code=500)

    return json_response(result, status_code=status_code)


@app.route(route="commit-drift/create-jira-ticket", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def commit_drift_create_jira_ticket(req: func.HttpRequest) -> func.HttpResponse:
   
    try:
        data = req.get_json()
    except ValueError:
        data = {}

    try:
        from shared_code.commit_drift_service import handle_commit_drift_create_jira_request
        result, status_code = handle_commit_drift_create_jira_request(data, req.headers)
    except Exception as e:
        return json_response({"ok": False, "reply": "Jira drift ticket backend failed to load.", "error": str(e)}, status_code=500)

    return json_response(result, status_code=status_code)



# ── Centralized repository context APIs ─────────────────────────────────────

def _repository_context_api_error(operation: str, exc: Exception) -> func.HttpResponse:
    logging.exception("Repository context API failed: operation=%s", operation)
    return json_response(
        {"ok": False, "operation": operation, "error": str(exc)},
        status_code=500,
    )


@app.route(route="repository-context/search", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def repository_context_search(req: func.HttpRequest) -> func.HttpResponse:
    auth_error = require_extension_api_token(req)
    if auth_error:
        return auth_error
    data = _request_json(req)
    try:
        service = _terrabot_service()

        result = service.search_repository_context(
            str(data.get("repo_owner") or ""),
            str(data.get("repo_name") or ""),
            str(data.get("query") or ""),
            current_commit_sha=str(data.get("current_commit_sha") or ""),
            top_k=int(data.get("top_k") or 8),
        )
        return json_response(result)
    except (TypeError, ValueError) as exc:
        return json_response({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        return _repository_context_api_error("search_repository_context", exc)


@app.route(route="repository-context/add", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def repository_context_add(req: func.HttpRequest) -> func.HttpResponse:
    auth_error = require_extension_api_token(req)
    if auth_error:
        return auth_error
    data = _request_json(req)
    try:
        service = _terrabot_service()

        result = service.add_repository_context(
            str(data.get("repo_owner") or ""),
            str(data.get("repo_name") or ""),
            str(data.get("evidence_commit_sha") or ""),
            data.get("candidate") if isinstance(data.get("candidate"), dict) else {},
            evidence_branch=str(data.get("evidence_branch") or ""),
            source_task_hash=str(data.get("source_task_hash") or ""),
        )
        return json_response(result, status_code=200 if result.get("ok") else 400)
    except (TypeError, ValueError) as exc:
        return json_response({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        return _repository_context_api_error("add_repository_context", exc)


@app.route(route="repository-context/update", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def repository_context_update(req: func.HttpRequest) -> func.HttpResponse:
    auth_error = require_extension_api_token(req)
    if auth_error:
        return auth_error
    data = _request_json(req)
    try:
        service = _terrabot_service()

        result = service.update_repository_context(
            str(data.get("context_id") or ""),
            str(data.get("repo_owner") or ""),
            str(data.get("repo_name") or ""),
            str(data.get("evidence_commit_sha") or ""),
            data.get("candidate") if isinstance(data.get("candidate"), dict) else {},
            evidence_branch=str(data.get("evidence_branch") or ""),
            source_task_hash=str(data.get("source_task_hash") or ""),
        )
        return json_response(result, status_code=200 if result.get("ok") else 400)
    except (TypeError, ValueError) as exc:
        return json_response({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        return _repository_context_api_error("update_repository_context", exc)


@app.route(route="repository-context/invalidate", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def repository_context_invalidate(req: func.HttpRequest) -> func.HttpResponse:
    auth_error = require_extension_api_token(req)
    if auth_error:
        return auth_error
    data = _request_json(req)
    try:
        service = _terrabot_service()

        result = service.invalidate_repository_context(
            str(data.get("context_id") or ""),
            str(data.get("reason") or ""),
            current_commit_sha=str(data.get("current_commit_sha") or ""),
        )
        return json_response(result, status_code=200 if result.get("ok") else 400)
    except (TypeError, ValueError) as exc:
        return json_response({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        return _repository_context_api_error("invalidate_repository_context", exc)


@app.route(route="repository-context/tools", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def repository_context_tools(req: func.HttpRequest) -> func.HttpResponse:
    auth_error = require_extension_api_token(req)
    if auth_error:
        return auth_error
    try:
        service = _terrabot_service()

        return json_response({"ok": True, "tools": service.repository_context_tool_schemas()})
    except Exception as exc:
        return _repository_context_api_error("repository_context_tool_schemas", exc)


# ── Step 1: /api/generate — unified generation endpoint ──────────────────────
# Accepts { prompt, files[], workspace_name } from VS Code / CLI,
# or { context_pack } forwarded directly from generator.py's HTTP client.
# Delegates all logic to shared_code/generate_handler.py.

@app.route(route="generate", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def generate(req: func.HttpRequest) -> func.HttpResponse:

    data = _request_json(req)
    if not data:
        return json_response({"ok": False, "reply": "Request body must be JSON."}, status_code=400)

    try:
        from shared_code.generate_handler import handle_generate_request
        result, status_code = handle_generate_request(data, req.headers)
    except Exception as e:
        return json_response(
            {"ok": False, "reply": "Generate backend failed.", "error": str(e)},
            status_code=500,
        )

    return json_response(result, status_code=status_code)

@app.route(
    route="teams/messages",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def teams_messages(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
    except ValueError:
        logging.warning("Teams endpoint received an invalid JSON activity.")
        return json_response(
            {
                "ok": False,
                "reply": "Invalid Teams activity payload.",
            },
            status_code=400,
        )

    if not isinstance(data, dict) or not data:
        return json_response(
            {
                "ok": False,
                "reply": "Invalid Teams activity payload.",
            },
            status_code=400,
        )

    authorization = (
        req.headers.get("Authorization")
        or req.headers.get("authorization")
        or ""
    )

    logging.info(
        "Teams activity received: "
        "type=%s channel=%s activity_id=%s "
        "authorization_present=%s text_length=%s",
        data.get("type"),
        data.get("channelId"),
        data.get("id"),
        bool(authorization),
        len(str(data.get("text") or "")),
    )

    try:
        from shared_code.teams_bot import handle_teams_bot_activity

        result, status_code = await handle_teams_bot_activity(
            data,
            authorization,
        )
    except Exception:
        logging.exception("Teams bot backend failed")
        return json_response(
            {
                "ok": False,
                "reply": "Teams bot backend failed.",
            },
            status_code=500,
        )

    if result:
        return json_response(
            result,
            status_code=status_code or 200,
        )

    return func.HttpResponse(
        body="",
        status_code=status_code or 200,
    )

@app.route(
    route="github/teams/callback",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def github_teams_callback(req: func.HttpRequest) -> func.HttpResponse:
    service = _terrabot_service()

    code = (req.params.get("code") or "").strip()
    state = (req.params.get("state") or "").strip()
    error = (req.params.get("error") or "").strip()
    error_description = (req.params.get("error_description") or "").strip()

    if error:
        detail = html.escape(error_description or error)
        return func.HttpResponse(
            f"<html><body><h2>GitHub connection failed</h2><p>{detail}</p></body></html>",
            status_code=400,
            mimetype="text/html",
        )

    if not code or not state:
        return func.HttpResponse(
            "<html><body><h2>GitHub connection failed</h2>"
            "<p>The OAuth callback did not include code and state.</p></body></html>",
            status_code=400,
            mimetype="text/html",
        )

    try:
        service.handle_teams_github_oauth_callback(code, state)
    except Exception as exc:
        return func.HttpResponse(
            "<html><body><h2>GitHub connection failed</h2>"
            f"<p>{html.escape(str(exc))}</p></body></html>",
            status_code=400,
            mimetype="text/html",
        )

    return func.HttpResponse(
        "<html><body><h2>GitHub connected</h2>"
        "<p>You can close this window, return to Microsoft Teams, and reply "
        "<strong>continue</strong>.</p></body></html>",
        status_code=200,
        mimetype="text/html",
    )

@app.route(
    route="teams/test",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def teams_test(req: func.HttpRequest) -> func.HttpResponse:
    data = _request_json(req)

    prompt = str(data.get("prompt") or "hey").strip()

    try:
        service = _terrabot_service()

        result, status_code = service.handle_teams_chat_request(
            {
                "prompt": prompt,
                "thread_id": "",
                "source": "teams-test",
            }
        )
    except Exception as exc:
        logging.exception("Teams backend test failed")
        return json_response(
            {
                "ok": False,
                "reply": "Teams backend test failed.",
                "error": str(exc),
            },
            status_code=500,
        )

    return json_response(
        result,
        status_code=status_code or 200,
    )