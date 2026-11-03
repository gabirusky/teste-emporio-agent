from __future__ import annotations

import json
import threading
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from emporio_agent.config import Settings
from emporio_agent.web import ChatServer, SessionStore


class FakeAgent:
    def __init__(self) -> None:
        self.history: list[dict[str, Any]] = []
        self.last_tool_calls: list[dict[str, Any]] = []
        self.reset_count = 0

    def respond(self, message: str) -> str:
        self.history.append({"role": "user", "content": message})
        self.last_tool_calls = [{"name": "search_products", "arguments": {"query": message}}]
        answer = f"echo: {message}"
        self.history.append({"role": "assistant", "content": answer})
        return answer

    def reset(self) -> None:
        self.reset_count += 1
        self.history.clear()
        self.last_tool_calls.clear()


@pytest.fixture()
def server() -> str:
    sessions = SessionStore(Settings(), agent_factory=FakeAgent)
    httpd = ChatServer(("127.0.0.1", 0), sessions)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def request(
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    cookie: str | None = None,
) -> tuple[int, bytes, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers: dict[str, str] = {}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if cookie:
        headers["Cookie"] = cookie
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, response.read(), response.headers
    except HTTPError as exc:
        return exc.code, exc.read(), exc.headers


def cookie_from(headers: Any) -> str:
    set_cookie = headers.get("Set-Cookie", "")
    assert "emporio_session=" in set_cookie
    return set_cookie.split(";", 1)[0]


def test_index_serves_chat_page(server: str) -> None:
    status, body, headers = request(server + "/")
    text = body.decode("utf-8")
    assert status == 200
    assert "Empório da Música" in text
    assert "Virtual assistant" in text
    assert "emporio_session=" in headers.get("Set-Cookie", "")


def test_health_endpoint(server: str) -> None:
    status, body, _ = request(server + "/health")
    assert status == 200
    assert json.loads(body) == {"status": "ok"}


def test_chat_returns_answer_and_tool_calls(server: str) -> None:
    _, _, headers = request(server + "/")
    cookie = cookie_from(headers)
    status, body, _ = request(server + "/api/chat", "POST", {"message": "guitarra"}, cookie)
    data = json.loads(body)
    assert status == 200
    assert data["answer"] == "echo: guitarra"
    assert data["tool_calls"] == [{"name": "search_products", "arguments": {"query": "guitarra"}}]


def test_chat_rejects_empty_message(server: str) -> None:
    status, body, _ = request(server + "/api/chat", "POST", {"message": "   "})
    assert status == 400
    assert "non-empty" in json.loads(body)["error"]


def test_chat_rejects_long_message(server: str) -> None:
    status, body, _ = request(server + "/api/chat", "POST", {"message": "x" * 4001})
    assert status == 413
    assert "4000" in json.loads(body)["error"]


def test_reset_clears_history(server: str) -> None:
    _, _, headers = request(server + "/")
    cookie = cookie_from(headers)
    request(server + "/api/chat", "POST", {"message": "hello"}, cookie)
    _, body, _ = request(server + "/api/history", cookie=cookie)
    assert len(json.loads(body)["messages"]) == 2
    status, _, _ = request(server + "/api/reset", "POST", cookie=cookie)
    assert status == 200
    _, body, _ = request(server + "/api/history", cookie=cookie)
    assert json.loads(body)["messages"] == []


def test_sessions_are_isolated(server: str) -> None:
    _, _, headers_a = request(server + "/")
    _, _, headers_b = request(server + "/")
    cookie_a = cookie_from(headers_a)
    cookie_b = cookie_from(headers_b)
    assert cookie_a != cookie_b
    request(server + "/api/chat", "POST", {"message": "hello"}, cookie_a)
    _, body_a, _ = request(server + "/api/history", cookie=cookie_a)
    _, body_b, _ = request(server + "/api/history", cookie=cookie_b)
    assert len(json.loads(body_a)["messages"]) == 2
    assert json.loads(body_b)["messages"] == []
