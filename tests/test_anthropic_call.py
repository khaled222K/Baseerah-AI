"""answer.anthropic_call against a local fake of the Messages endpoint: request shape and response parsing."""
import json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
import answer

SEEN = []
REPLY = {}


class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        SEEN.append({"path": self.path, "beta": self.headers.get("anthropic-beta", ""), "body": body})
        out = json.dumps(REPLY).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


@pytest.fixture
def server(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    SEEN.clear()
    yield
    srv.shutdown()


def message(content, stop="end_turn"):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": answer.MODEL, "content": content,
            "stop_reason": stop, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}


def test_reads_text_after_thinking_and_sends_fallback(server):
    REPLY.clear()
    REPLY.update(message([{"type": "thinking", "thinking": "", "signature": "sig"},
                          {"type": "text", "text": '{"ok": true}'}]))
    assert answer.anthropic_call("sys", "user") == '{"ok": true}'
    req = SEEN[0]
    assert req["path"].startswith("/v1/messages")
    assert req["body"]["model"] == answer.MODEL and req["body"]["max_tokens"] == answer.LLM_MAX_TOKENS
    assert req["body"]["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in req["beta"]


def test_refusal_raises(server):
    REPLY.clear()
    REPLY.update(message([], stop="refusal"))
    with pytest.raises(RuntimeError, match="declined"):
        answer.anthropic_call("sys", "user")
