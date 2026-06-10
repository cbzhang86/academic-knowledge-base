#!/usr/bin/env python3
"""
cc-switch 兼容代理 — 修复 Agent 调用时 thinking + reasoning_effort 参数冲突

问题: Claude Code 2.1.166+ 对子 Agent 硬编码 thinking:{type:disabled}，
同时继承了 reasoning_effort，DeepSeek API 拒绝两者共存。

修复方案来自 DeepSeek-V3 Issue #1397：
  "modify proxy to strip thinking altogether when reasoning_effort is set"

用法:
  python cc_switch_fix_proxy.py
  # 然后将 ANTHROPIC_BASE_URL 改为 http://127.0.0.1:15722
"""

import json, sys
sys.stdout.reconfigure(encoding='utf-8')
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen, HTTPError
import ssl

UPSTREAM = "http://127.0.0.1:15721"
LISTEN = ("127.0.0.1", 15722)
SKIP_HEADERS = {"host", "content-length", "transfer-encoding", "connection"}


class FixProxy(BaseHTTPRequestHandler):
    """转发请求到 upstream，按 #1397 方案修复 thinking+reasoning_effort 冲突"""

    def _fix_body(self, body: bytes) -> bytes:
        """Issue #1397 workaround: 当 reasoning_effort 存在时 pop thinking"""
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return body

        if "thinking" in data and data.get("reasoning_effort"):
            data.pop("thinking", None)
            new_body = json.dumps(data).encode("utf-8")
            sys.stderr.write(
                f"[FIX] pop thinking (model={data.get('model','?')}, "
                f"reasoning_effort={data.get('reasoning_effort','?')}, "
                f"msg_count={len(data.get('messages', []))})\n"
            )
            sys.stderr.flush()
            return new_body

        return body

    def _forward(self, method: str):
        content_length = int(self.headers.get("content-length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        if body:
            body = self._fix_body(body)

        path_only = self.path.split("?")[0] if "?" in self.path else self.path
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        url = f"{UPSTREAM}{path_only}"
        if query:
            url = f"{url}?{query}"

        req = Request(url, data=body, method=method)
        for key, value in self.headers.items():
            if key.lower() not in SKIP_HEADERS:
                req.add_header(key, value)
        if body:
            req.add_header("Content-Length", str(len(body)))

        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            resp = urlopen(req, context=ctx, timeout=60)
            resp_body = resp.read()

            self.send_response(resp.status)
            for key, value in resp.headers.items():
                if key.lower() not in SKIP_HEADERS:
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(resp_body)

        except HTTPError as e:
            self.send_response(e.code)
            for key, value in e.headers.items():
                if key.lower() not in SKIP_HEADERS:
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            sys.stderr.write(f"[ERROR] {e}\n")
            sys.stderr.flush()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Proxy error: {e}".encode("utf-8"))

    def do_GET(self): self._forward("GET")
    def do_POST(self): self._forward("POST")
    def do_PUT(self): self._forward("PUT")
    def do_DELETE(self): self._forward("DELETE")
    def do_PATCH(self): self._forward("PATCH")
    def do_HEAD(self): self._forward("HEAD")
    def do_OPTIONS(self): self._forward("OPTIONS")


def main():
    try:
        req = Request(f"{UPSTREAM}/v1/models", method="GET")
        urlopen(req, timeout=3)
        sys.stderr.write(f"[PROXY] upstream {UPSTREAM} ready\n")
    except Exception as e:
        sys.stderr.write(f"[PROXY] upstream {UPSTREAM} unavailable: {e}\n")

    server = HTTPServer(LISTEN, FixProxy)
    host, port = LISTEN
    sys.stderr.write(f"[PROXY] listening on {host}:{port} → {UPSTREAM}\n")
    sys.stderr.write(f"[PROXY] fix: pop thinking when reasoning_effort present (#1397)\n")
    sys.stderr.write(f"[PROXY] set ANTHROPIC_BASE_URL=http://{host}:{port}\n")
    sys.stderr.flush()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
