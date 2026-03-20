"""Gmail MCP Server — read + write operations for Gmail.

Provides tools for: search, read messages/threads, send email, drafts.
OAuth token passed via Authorization header from the executor's per-user
OAuth resolution (_build_mcp_bindings tier 1).
"""

import base64
import json
import logging
import os
from email.mime.text import MIMEText

from fastapi import FastAPI, Request
from pydantic import BaseModel

app = FastAPI(title="gmail-mcp")
logger = logging.getLogger("uvicorn")

# Default "Send as" address — set to a Google Group or alias configured
# as "Send mail as" in the authenticating user's Gmail settings.
# If unset, emails send from the OAuth user's primary address.
DEFAULT_SEND_AS = os.environ.get("GMAIL_SEND_AS", "")


def _service(token: str):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(token=token)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _extract_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return ""


# --- Models ---

class ToolCallRequest(BaseModel):
    name: str
    arguments: dict


class HealthResponse(BaseModel):
    status: str


# --- Tool definitions ---

TOOLS = [
    {
        "name": "gmail_search_messages",
        "description": "Search Gmail messages using Gmail search syntax (e.g. 'from:user@example.com subject:meeting').",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Gmail search query (same syntax as Gmail search bar)"},
                "max_results": {"type": "integer", "description": "Maximum messages to return (default 10, max 50)", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "gmail_read_message",
        "description": "Read a specific Gmail message by ID. Returns subject, from, to, date, and body.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Gmail message ID"},
            },
            "required": ["message_id"],
        },
    },
    {
        "name": "gmail_read_thread",
        "description": "Read all messages in a Gmail thread.",
        "input_schema": {
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "Gmail thread ID"},
            },
            "required": ["thread_id"],
        },
    },
    {
        "name": "gmail_send_email",
        "description": "Send an email. Sends from the configured team address (e.g. equities-pm@aspora.com) by default.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address(es), comma-separated"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body (plain text)"},
                "cc": {"type": "string", "description": "CC recipients, comma-separated"},
                "bcc": {"type": "string", "description": "BCC recipients, comma-separated"},
                "thread_id": {"type": "string", "description": "Thread ID to reply in (optional)"},
                "in_reply_to": {"type": "string", "description": "Message-ID header of message being replied to"},
                "from_address": {"type": "string", "description": "Override sender address (must be a configured Send-as alias)"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "gmail_create_draft",
        "description": "Create a draft email without sending it. Uses the configured team address by default.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address(es), comma-separated"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body (plain text)"},
                "cc": {"type": "string", "description": "CC recipients, comma-separated"},
                "thread_id": {"type": "string", "description": "Thread ID (optional, for reply drafts)"},
                "from_address": {"type": "string", "description": "Override sender address (must be a configured Send-as alias)"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "gmail_list_drafts",
        "description": "List Gmail drafts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "description": "Maximum drafts to return (default 10)", "default": 10},
            },
        },
    },
    {
        "name": "gmail_send_draft",
        "description": "Send an existing draft by its draft ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string", "description": "Draft ID to send"},
            },
            "required": ["draft_id"],
        },
    },
    {
        "name": "gmail_get_current_email",
        "description": "Get the email address of the currently authenticated Gmail user.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]

# Store request context for token extraction
_current_request: Request | None = None


# --- Endpoints ---

@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ready")


@app.get("/tools")
def list_tools():
    return TOOLS


@app.post("/tools/call")
async def call_tool(req: ToolCallRequest, request: Request):
    token = _extract_token(request)
    if not token:
        return {"content": "No Authorization Bearer token provided", "is_error": True}

    handlers = {
        "gmail_search_messages": _search_messages,
        "gmail_read_message": _read_message,
        "gmail_read_thread": _read_thread,
        "gmail_send_email": _send_email,
        "gmail_create_draft": _create_draft,
        "gmail_list_drafts": _list_drafts,
        "gmail_send_draft": _send_draft,
        "gmail_get_current_email": _get_current_email,
    }
    handler = handlers.get(req.name)
    if not handler:
        return {"content": f"Unknown tool: {req.name}", "is_error": True}
    try:
        result = handler(token, req.arguments)
        return {"content": result}
    except Exception as e:
        logger.error(f"Tool {req.name} failed: {e}")
        return {"content": str(e), "is_error": True}


# --- Helpers ---

def _parse_message(msg: dict) -> dict:
    """Extract useful fields from a Gmail message resource."""
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    body = ""
    payload = msg.get("payload", {})

    # Try plain text body first
    if payload.get("body", {}).get("data"):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    elif payload.get("parts"):
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                break
        if not body:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    break

    return {
        "id": msg.get("id", ""),
        "thread_id": msg.get("threadId", ""),
        "subject": headers.get("subject", ""),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "cc": headers.get("cc", ""),
        "date": headers.get("date", ""),
        "snippet": msg.get("snippet", ""),
        "body": body[:10000],  # Truncate very long bodies
        "label_ids": msg.get("labelIds", []),
    }


def _build_mime_message(to: str, subject: str, body: str, cc: str = "", bcc: str = "",
                        in_reply_to: str = "", references: str = "",
                        from_address: str = "") -> dict:
    """Build a Gmail API message resource from components."""
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    # Set From to the shared team address (e.g. equities-pm@aspora.com)
    # The authenticating user must have this configured as a "Send mail as" alias
    sender = from_address or DEFAULT_SEND_AS
    if sender:
        message["from"] = sender
    if cc:
        message["cc"] = cc
    if bcc:
        message["bcc"] = bcc
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        message["References"] = references or in_reply_to

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {"raw": raw}


# --- Handlers ---

def _search_messages(token: str, args: dict) -> str:
    service = _service(token)
    max_results = min(args.get("max_results", 10), 50)
    resp = service.users().messages().list(
        userId="me", q=args["query"], maxResults=max_results
    ).execute()

    messages = resp.get("messages", [])
    if not messages:
        return json.dumps({"message_count": 0, "messages": []})

    results = []
    for msg_ref in messages:
        msg = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="metadata",
            metadataHeaders=["Subject", "From", "To", "Date"]
        ).execute()
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        results.append({
            "id": msg["id"],
            "thread_id": msg.get("threadId", ""),
            "subject": headers.get("subject", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "date": headers.get("date", ""),
            "snippet": msg.get("snippet", ""),
        })

    return json.dumps({"message_count": len(results), "messages": results}, indent=2)


def _read_message(token: str, args: dict) -> str:
    service = _service(token)
    msg = service.users().messages().get(
        userId="me", id=args["message_id"], format="full"
    ).execute()
    return json.dumps(_parse_message(msg), indent=2)


def _read_thread(token: str, args: dict) -> str:
    service = _service(token)
    thread = service.users().threads().get(
        userId="me", id=args["thread_id"], format="full"
    ).execute()
    messages = [_parse_message(m) for m in thread.get("messages", [])]
    return json.dumps({"thread_id": args["thread_id"], "message_count": len(messages), "messages": messages}, indent=2)


def _send_email(token: str, args: dict) -> str:
    service = _service(token)
    msg_body = _build_mime_message(
        to=args["to"],
        subject=args["subject"],
        body=args["body"],
        cc=args.get("cc", ""),
        bcc=args.get("bcc", ""),
        in_reply_to=args.get("in_reply_to", ""),
        from_address=args.get("from_address", ""),
    )
    if args.get("thread_id"):
        msg_body["threadId"] = args["thread_id"]

    sent = service.users().messages().send(userId="me", body=msg_body).execute()
    return json.dumps({"ok": True, "id": sent["id"], "thread_id": sent.get("threadId", "")})


def _create_draft(token: str, args: dict) -> str:
    service = _service(token)
    msg_body = _build_mime_message(
        to=args["to"], subject=args["subject"], body=args["body"],
        cc=args.get("cc", ""),
        from_address=args.get("from_address", ""),
    )
    draft_body = {"message": msg_body}
    if args.get("thread_id"):
        draft_body["message"]["threadId"] = args["thread_id"]

    draft = service.users().drafts().create(userId="me", body=draft_body).execute()
    return json.dumps({"ok": True, "draft_id": draft["id"], "message_id": draft["message"]["id"]})


def _list_drafts(token: str, args: dict) -> str:
    service = _service(token)
    max_results = min(args.get("max_results", 10), 50)
    resp = service.users().drafts().list(userId="me", maxResults=max_results).execute()

    drafts = []
    for d in resp.get("drafts", []):
        draft = service.users().drafts().get(userId="me", id=d["id"], format="metadata").execute()
        headers = {h["name"].lower(): h["value"]
                   for h in draft.get("message", {}).get("payload", {}).get("headers", [])}
        drafts.append({
            "draft_id": d["id"],
            "message_id": draft.get("message", {}).get("id", ""),
            "subject": headers.get("subject", ""),
            "to": headers.get("to", ""),
            "snippet": draft.get("message", {}).get("snippet", ""),
        })

    return json.dumps({"draft_count": len(drafts), "drafts": drafts}, indent=2)


def _send_draft(token: str, args: dict) -> str:
    service = _service(token)
    sent = service.users().drafts().send(userId="me", body={"id": args["draft_id"]}).execute()
    return json.dumps({"ok": True, "id": sent["id"], "thread_id": sent.get("threadId", "")})


def _get_current_email(token: str, args: dict) -> str:
    service = _service(token)
    profile = service.users().getProfile(userId="me").execute()
    return json.dumps({"email": profile.get("emailAddress", ""), "messages_total": profile.get("messagesTotal", 0)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8093)
