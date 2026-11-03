from __future__ import annotations

import argparse
import json
import threading
import uuid
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlparse

from .agent import MusicStoreAgent
from .cli import build_agent
from .config import Settings

MAX_BODY_BYTES = 64 * 1024
MAX_MESSAGE_CHARS = 4000
COOKIE_NAME = "emporio_session"

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Empório da Música | Virtual assistant</title>
<style>
  :root {
    color-scheme: light;
    --bg: #f6f1e7;
    --panel: #fffdf8;
    --ink: #1f2937;
    --muted: #6b7280;
    --accent: #b45309;
    --accent-dark: #92400e;
    --border: #e7e1d8;
    --user: #fef3c7;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    min-height: 100vh;
    background: radial-gradient(circle at top left, #fff7ed, var(--bg) 45%);
    color: var(--ink);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  .app {
    display: flex;
    flex-direction: column;
    max-width: 860px;
    min-height: 100vh;
    margin: 0 auto;
    padding: 24px 18px 12px;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 8px 4px 18px;
    border-bottom: 1px solid var(--border);
  }
  h1 { margin: 0; font-size: 1.35rem; color: var(--accent-dark); }
  header p { margin: 4px 0 0; color: var(--muted); font-size: 0.85rem; }
  #messages {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 12px;
    overflow-y: auto;
    padding: 18px 4px;
  }
  .message {
    max-width: 82%;
    padding: 12px 14px;
    border: 1px solid var(--border);
    border-radius: 14px;
    background: #ffffff;
    line-height: 1.45;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
  }
  .message.user {
    align-self: flex-end;
    border-color: #fde68a;
    border-bottom-right-radius: 4px;
    background: var(--user);
  }
  .message.assistant {
    align-self: flex-start;
    border-bottom-left-radius: 4px;
  }
  .message.error {
    align-self: flex-start;
    border-color: #fecaca;
    background: #fef2f2;
    color: #991b1b;
  }
  .tools { margin-top: 6px; color: var(--muted); font-size: 0.78rem; }
  .tools pre {
    max-height: 180px;
    overflow: auto;
    margin: 6px 0 0;
    padding: 8px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: #f9fafb;
    font-size: 0.75rem;
  }
  form {
    display: flex;
    gap: 10px;
    padding: 14px 4px 4px;
    border-top: 1px solid var(--border);
  }
  input[type="text"] {
    flex: 1;
    min-width: 0;
    padding: 12px 14px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: #ffffff;
    color: var(--ink);
    font: inherit;
  }
  input[type="text"]:focus { outline: 2px solid #fcd34d; outline-offset: 1px; }
  button {
    padding: 12px 18px;
    border: 0;
    border-radius: 10px;
    background: var(--accent);
    color: #ffffff;
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }
  button:hover:not(:disabled) { background: var(--accent-dark); }
  button:disabled { cursor: not-allowed; opacity: 0.55; }
  button.secondary {
    padding: 8px 12px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--accent-dark);
    font-weight: 500;
  }
  .hint { margin: 8px 0 0; color: var(--muted); font-size: 0.75rem; text-align: center; }
  @media (max-width: 600px) {
    .app { padding: 16px 12px 8px; }
    .message { max-width: 92%; }
    form { flex-wrap: wrap; }
    input[type="text"] { flex-basis: 100%; }
    button { width: 100%; }
  }
</style>
</head>
<body>
<div class="app">
  <header>
    <div>
      <h1>Empório da Música</h1>
      <p>Virtual assistant · demo data</p>
    </div>
    <button class="secondary" id="reset" type="button">Reset</button>
  </header>
  <main id="messages" aria-live="polite"></main>
  <form id="chat-form">
    <input id="message" type="text" autocomplete="off" maxlength="4000" aria-label="Message" placeholder="Ask about instruments, orders, or store policies…" required>
    <button id="send" type="submit">Send</button>
  </form>
  <p class="hint">Local demo. Orders use sample data and have no customer authentication.</p>
</div>
<script>
  const messages = document.getElementById("messages");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("message");
  const send = document.getElementById("send");
  const reset = document.getElementById("reset");

  function addMessage(role, text) {
    const bubble = document.createElement("div");
    bubble.className = "message " + role;
    bubble.textContent = text;
    messages.appendChild(bubble);
    messages.scrollTop = messages.scrollHeight;
    return bubble;
  }

  function addTools(bubble, toolCalls) {
    if (!toolCalls || !toolCalls.length) return;
    const box = document.createElement("div");
    box.className = "tools";
    box.textContent = "Tools used: " + toolCalls.map((call) => call.name).join(", ");
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Details";
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(toolCalls, null, 2);
    details.appendChild(summary);
    details.appendChild(pre);
    box.appendChild(details);
    bubble.appendChild(box);
    messages.scrollTop = messages.scrollHeight;
  }

  async function postJson(path, body) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Request failed (" + response.status + ")");
    return data;
  }

  async function loadHistory() {
    try {
      const response = await fetch("/api/history", { credentials: "same-origin" });
      if (!response.ok) return;
      const data = await response.json();
      for (const message of data.messages || []) addMessage(message.role, message.content);
    } catch (error) {
      addMessage("error", "Could not load previous messages.");
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    addMessage("user", text);
    input.value = "";
    input.disabled = true;
    send.disabled = true;
    send.textContent = "Sending…";
    try {
      const data = await postJson("/api/chat", { message: text });
      const bubble = addMessage("assistant", data.answer);
      addTools(bubble, data.tool_calls);
    } catch (error) {
      addMessage("error", error.message || "Could not reach the agent.");
    } finally {
      input.disabled = false;
      send.disabled = false;
      send.textContent = "Send";
      input.focus();
    }
  });

  reset.addEventListener("click", async () => {
    reset.disabled = true;
    try {
      await postJson("/api/reset");
      messages.replaceChildren();
      addMessage("assistant", "Conversation reset. How can I help?");
    } catch (error) {
      addMessage("error", error.message || "Could not reset the conversation.");
    } finally {
      reset.disabled = false;
      input.focus();
    }
  });

  loadHistory().then(() => input.focus());
</script>
</body>
</html>
"""


class SessionStore:
    def __init__(self, settings: Settings, agent_factory: Callable[[], MusicStoreAgent] | None = None):
        self.settings = settings
        self._agent_factory = agent_factory or (lambda: build_agent(settings))
        self._sessions: dict[str, tuple[MusicStoreAgent, threading.Lock]] = {}
        self._guard = threading.Lock()

    def get(self, session_id: str) -> tuple[MusicStoreAgent, threading.Lock]:
        with self._guard:
            session = self._sessions.get(session_id)
            if session is None:
                session = (self._agent_factory(), threading.Lock())
                self._sessions[session_id] = session
            return session

    def peek(self, session_id: str) -> MusicStoreAgent | None:
        with self._guard:
            session = self._sessions.get(session_id)
            return session[0] if session else None

    def reset(self, session_id: str) -> bool:
        with self._guard:
            session = self._sessions.get(session_id)
        if session is None:
            return False
        agent, lock = session
        with lock:
            agent.reset()
        return True


class ChatServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], sessions: SessionStore):
        super().__init__(server_address, ChatHandler)
        self.sessions = sessions


class ChatHandler(BaseHTTPRequestHandler):
    server: ChatServer

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        session_id, new_session = self._session_id()
        if path == "/":
            self._send_html(INDEX_HTML, session_id, new_session)
        elif path == "/health":
            self._send_json({"status": "ok"}, session_id=session_id, new_session=new_session)
        elif path == "/api/history":
            agent = self.server.sessions.peek(session_id)
            history = []
            if agent is not None:
                history = [
                    {"role": message["role"], "content": message["content"]}
                    for message in agent.history
                    if message.get("role") in {"user", "assistant"}
                    and message.get("content")
                    and not message.get("tool_calls")
                ]
            self._send_json({"messages": history}, session_id=session_id, new_session=new_session)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        session_id, new_session = self._session_id()
        if path == "/api/reset":
            self.server.sessions.reset(session_id)
            self._send_json({"status": "reset"}, session_id=session_id, new_session=new_session)
            return
        if path != "/api/chat":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            payload = self._read_json()
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST, session_id=session_id, new_session=new_session)
            return

        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            self._send_json(
                {"error": "Message must be a non-empty string."},
                status=HTTPStatus.BAD_REQUEST,
                session_id=session_id,
                new_session=new_session,
            )
            return
        message = message.strip()
        if len(message) > MAX_MESSAGE_CHARS:
            self._send_json(
                {"error": f"Message must be at most {MAX_MESSAGE_CHARS} characters."},
                status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                session_id=session_id,
                new_session=new_session,
            )
            return

        try:
            agent, lock = self.server.sessions.get(session_id)
            with lock:
                answer = agent.respond(message)
                tool_calls = list(agent.last_tool_calls)
        except Exception as exc:
            self._send_json(
                {"error": f"{type(exc).__name__}: {exc}"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                session_id=session_id,
                new_session=new_session,
            )
            return

        self._send_json(
            {"answer": answer, "tool_calls": tool_calls},
            session_id=session_id,
            new_session=new_session,
        )

    def _session_id(self) -> tuple[str, bool]:
        try:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
        except CookieError:
            cookie = SimpleCookie()
        if COOKIE_NAME in cookie:
            return cookie[COOKIE_NAME].value, False
        return uuid.uuid4().hex, True

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Missing Content-Length.")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length.") from exc
        if length <= 0:
            raise ValueError("Empty request body.")
        if length > MAX_BODY_BYTES:
            raise ValueError("Request body too large.")
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Invalid JSON body.") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")
        return payload

    def _send_html(self, html: str, session_id: str, new_session: bool) -> None:
        self._send(
            html.encode("utf-8"),
            "text/html; charset=utf-8",
            session_id=session_id,
            new_session=new_session,
        )

    def _send_json(
        self,
        payload: dict[str, Any],
        status: HTTPStatus = HTTPStatus.OK,
        session_id: str | None = None,
        new_session: bool = False,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(
            body,
            "application/json; charset=utf-8",
            status=status,
            session_id=session_id,
            new_session=new_session,
        )

    def _send(
        self,
        body: bytes,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
        session_id: str | None = None,
        new_session: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        if new_session and session_id:
            self.send_header("Set-Cookie", f"{COOKIE_NAME}={session_id}; Path=/; HttpOnly; SameSite=Lax")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Empório da Música local web chat.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000; use 0 for a free port).")
    args = parser.parse_args()

    settings = Settings()
    try:
        settings.validate_llm()
    except RuntimeError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc
    sessions = SessionStore(settings)
    try:
        server = ChatServer((args.host, args.port), sessions)
    except OSError as exc:
        raise SystemExit(f"Could not bind {args.host}:{args.port}: {exc}") from exc
    host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    port = server.server_address[1]
    print(f"Empório da Música web chat: http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
