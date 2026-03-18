"""Granola MCP Proxy — multi-user meeting aggregation.

Reads ALL stored Granola OAuth tokens from PostgreSQL and aggregates
meeting data across the entire team. This bypasses the per-user limitation
of Granola's API (each token only sees that user's meetings).

For list/search: calls Granola API with each user's token, deduplicates.
For get/transcript: tries each token until one succeeds (meeting owner's works).

Deployed as a standalone service. The executor routes here via MCP_GRANOLA_URL.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
import psycopg2
import psycopg2.extras
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="granola-mcp")
logger = logging.getLogger("uvicorn")

DATABASE_URL = os.environ.get("DATABASE_URL", "")
GRANOLA_API_BASE = os.environ.get("GRANOLA_API_BASE", "https://api.granola.ai")


# --- Models ---

class ToolCallRequest(BaseModel):
    name: str
    arguments: dict


class HealthResponse(BaseModel):
    status: str


# --- Tool definitions ---

TOOLS = [
    {
        "name": "list_meetings",
        "description": (
            "List recent meetings from Granola across all connected team members. "
            "Returns meetings from all users who have completed Granola OAuth, "
            "deduplicated by meeting ID. Sorted by start time descending."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum meetings to return (default 20, max 100)",
                    "default": 20,
                },
                "days_back": {
                    "type": "integer",
                    "description": "Number of days to look back (default 7)",
                    "default": 7,
                },
            },
        },
    },
    {
        "name": "search_meetings",
        "description": (
            "Search for meetings matching a query across all connected team members. "
            "Searches meeting titles, participants, and notes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to match against meeting titles, participants, and notes",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default 20)",
                    "default": 20,
                },
                "days_back": {
                    "type": "integer",
                    "description": "Number of days to look back (default 30)",
                    "default": 30,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_meeting",
        "description": "Get detailed information about a specific meeting by its Granola document ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "meeting_id": {
                    "type": "string",
                    "description": "Granola document/meeting ID",
                },
            },
            "required": ["meeting_id"],
        },
    },
    {
        "name": "get_meeting_transcript",
        "description": "Get the full transcript of a specific meeting.",
        "input_schema": {
            "type": "object",
            "properties": {
                "meeting_id": {
                    "type": "string",
                    "description": "Granola document/meeting ID",
                },
            },
            "required": ["meeting_id"],
        },
    },
]


# --- Token management ---

def _get_all_granola_tokens() -> list[dict]:
    """Read all Granola OAuth tokens from the database."""
    if not DATABASE_URL:
        logger.error("DATABASE_URL not set — cannot read tokens")
        return []

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT user_identifier, access_token, refresh_token, expires_at, "
                "client_id, client_secret FROM mcp_user_tokens WHERE provider = 'granola'"
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _refresh_token(token_row: dict) -> str | None:
    """Refresh an expired Granola token. Returns new access_token or None."""
    refresh_token = token_row.get("refresh_token")
    if not refresh_token:
        return None

    # Granola uses DCR — discover token endpoint dynamically
    try:
        resp = httpx.get("https://mcp.granola.ai/.well-known/oauth-protected-resource", timeout=10)
        resp.raise_for_status()
        resource_meta = resp.json()
        auth_server_url = resource_meta.get("authorization_servers", [None])[0]
        if not auth_server_url:
            return None

        well_known = auth_server_url.rstrip("/") + "/.well-known/oauth-authorization-server"
        resp = httpx.get(well_known, timeout=10)
        resp.raise_for_status()
        auth_meta = resp.json()
        token_url = auth_meta["token_endpoint"]
    except Exception:
        logger.exception("Failed to discover Granola auth server for refresh")
        return None

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    if token_row.get("client_id"):
        data["client_id"] = token_row["client_id"]
    if token_row.get("client_secret"):
        data["client_secret"] = token_row["client_secret"]

    try:
        resp = httpx.post(token_url, data=data, timeout=10)
        resp.raise_for_status()
        tokens = resp.json()
        new_access = tokens["access_token"]

        # Update DB
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor() as cur:
                expires_at = None
                if tokens.get("expires_in"):
                    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(tokens["expires_in"]))
                cur.execute(
                    """UPDATE mcp_user_tokens SET access_token = %s, refresh_token = COALESCE(%s, refresh_token),
                       expires_at = %s, updated_at = CURRENT_TIMESTAMP
                       WHERE user_identifier = %s AND provider = 'granola'""",
                    (new_access, tokens.get("refresh_token"), expires_at, token_row["user_identifier"]),
                )
            conn.commit()
        finally:
            conn.close()

        return new_access
    except Exception:
        logger.exception("Granola token refresh failed for %s", token_row["user_identifier"])
        return None


def _get_valid_token(token_row: dict) -> str | None:
    """Get a valid access token, refreshing if expired."""
    expires_at = token_row.get("expires_at")
    if expires_at and expires_at < datetime.now(timezone.utc):
        return _refresh_token(token_row)
    return token_row.get("access_token")


# --- Granola API calls ---

def _granola_api(token: str, method: str, path: str, params: dict = None, json_body: dict = None) -> dict | None:
    """Call Granola REST API."""
    url = f"{GRANOLA_API_BASE}{path}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    try:
        if method == "GET":
            resp = httpx.get(url, headers=headers, params=params, timeout=30)
        else:
            resp = httpx.post(url, headers=headers, json=json_body, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            logger.debug("Granola API auth failed for path %s (token may be expired)", path)
        else:
            logger.warning("Granola API error: %s %s -> %s", method, path, e.response.status_code)
        return None
    except Exception:
        logger.exception("Granola API call failed: %s %s", method, path)
        return None


# --- Endpoints ---

@app.get("/health", response_model=HealthResponse)
def health():
    tokens = _get_all_granola_tokens()
    return HealthResponse(status=f"ready ({len(tokens)} users connected)")


@app.get("/tools")
def list_tools():
    return TOOLS


@app.post("/tools/call")
def call_tool(req: ToolCallRequest):
    handlers = {
        "list_meetings": _list_meetings,
        "search_meetings": _search_meetings,
        "get_meeting": _get_meeting,
        "get_meeting_transcript": _get_meeting_transcript,
    }
    handler = handlers.get(req.name)
    if not handler:
        return {"content": f"Unknown tool: {req.name}", "is_error": True}
    try:
        result = handler(req.arguments)
        return {"content": result}
    except Exception as e:
        logger.error(f"Tool {req.name} failed: {e}")
        return {"content": str(e), "is_error": True}


# --- Handlers ---

def _list_meetings(args: dict) -> str:
    limit = min(args.get("limit", 20), 100)
    days_back = args.get("days_back", 7)

    token_rows = _get_all_granola_tokens()
    if not token_rows:
        return json.dumps({"error": "No Granola users connected. Team members need to complete OAuth."})

    all_meetings: dict[str, dict] = {}  # meeting_id -> meeting
    errors = []

    for row in token_rows:
        token = _get_valid_token(row)
        if not token:
            errors.append(f"Expired token for {row['user_identifier']}")
            continue

        data = _granola_api(token, "GET", "/v1/documents", params={
            "limit": limit,
            "days_back": days_back,
        })
        if data and isinstance(data, list):
            for meeting in data:
                mid = meeting.get("id", "")
                if mid and mid not in all_meetings:
                    meeting["_source_user"] = row["user_identifier"]
                    all_meetings[mid] = meeting
        elif data and isinstance(data, dict) and "documents" in data:
            for meeting in data["documents"]:
                mid = meeting.get("id", "")
                if mid and mid not in all_meetings:
                    meeting["_source_user"] = row["user_identifier"]
                    all_meetings[mid] = meeting
        elif data and isinstance(data, dict) and "meetings" in data:
            for meeting in data["meetings"]:
                mid = meeting.get("id", "")
                if mid and mid not in all_meetings:
                    meeting["_source_user"] = row["user_identifier"]
                    all_meetings[mid] = meeting

    # Sort by start time descending
    meetings = sorted(all_meetings.values(), key=lambda m: m.get("start_time", m.get("created_at", "")), reverse=True)
    meetings = meetings[:limit]

    result = {
        "meeting_count": len(meetings),
        "users_queried": len(token_rows),
        "meetings": meetings,
    }
    if errors:
        result["warnings"] = errors
    return json.dumps(result, indent=2, default=str)


def _search_meetings(args: dict) -> str:
    query = args["query"]
    limit = min(args.get("limit", 20), 100)
    days_back = args.get("days_back", 30)

    token_rows = _get_all_granola_tokens()
    if not token_rows:
        return json.dumps({"error": "No Granola users connected."})

    all_meetings: dict[str, dict] = {}
    errors = []

    for row in token_rows:
        token = _get_valid_token(row)
        if not token:
            errors.append(f"Expired token for {row['user_identifier']}")
            continue

        # Try search endpoint first, fall back to list with filter
        data = _granola_api(token, "GET", "/v1/documents/search", params={
            "q": query,
            "limit": limit,
            "days_back": days_back,
        })
        if data is None:
            # Fallback: list and filter client-side
            data = _granola_api(token, "GET", "/v1/documents", params={
                "limit": 100,
                "days_back": days_back,
            })

        meetings_list = []
        if isinstance(data, list):
            meetings_list = data
        elif isinstance(data, dict):
            meetings_list = data.get("documents", data.get("meetings", data.get("results", [])))

        query_lower = query.lower()
        for meeting in meetings_list:
            mid = meeting.get("id", "")
            if mid and mid not in all_meetings:
                title = meeting.get("title", "").lower()
                notes = meeting.get("notes", "").lower()
                participants = json.dumps(meeting.get("participants", [])).lower()
                if query_lower in title or query_lower in notes or query_lower in participants:
                    meeting["_source_user"] = row["user_identifier"]
                    all_meetings[mid] = meeting

    meetings = sorted(all_meetings.values(), key=lambda m: m.get("start_time", m.get("created_at", "")), reverse=True)
    meetings = meetings[:limit]

    result = {
        "meeting_count": len(meetings),
        "users_queried": len(token_rows),
        "meetings": meetings,
    }
    if errors:
        result["warnings"] = errors
    return json.dumps(result, indent=2, default=str)


def _get_meeting(args: dict) -> str:
    meeting_id = args["meeting_id"]
    token_rows = _get_all_granola_tokens()
    if not token_rows:
        return json.dumps({"error": "No Granola users connected."})

    for row in token_rows:
        token = _get_valid_token(row)
        if not token:
            continue
        data = _granola_api(token, "GET", f"/v1/documents/{meeting_id}")
        if data:
            data["_source_user"] = row["user_identifier"]
            return json.dumps(data, indent=2, default=str)

    return json.dumps({"error": f"Meeting {meeting_id} not found (tried {len(token_rows)} user tokens)"})


def _get_meeting_transcript(args: dict) -> str:
    meeting_id = args["meeting_id"]
    token_rows = _get_all_granola_tokens()
    if not token_rows:
        return json.dumps({"error": "No Granola users connected."})

    for row in token_rows:
        token = _get_valid_token(row)
        if not token:
            continue
        data = _granola_api(token, "GET", f"/v1/documents/{meeting_id}/transcript")
        if data:
            if isinstance(data, dict):
                data["_source_user"] = row["user_identifier"]
            return json.dumps(data, indent=2, default=str)

    return json.dumps({"error": f"Transcript for {meeting_id} not found (tried {len(token_rows)} user tokens)"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8094)
