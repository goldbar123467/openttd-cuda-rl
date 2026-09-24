#!/usr/bin/env python3
"""JSON-line bridge to this Windows host's loopback-only Ollama service.

Run with the host's Python from WSL. No listener, credentials, shell commands,
model downloads, or changes to Ollama configuration are involved.
"""
import json
import sys
import urllib.error
import urllib.request


def main():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    allowed = {"/api/version", "/api/tags", "/api/ps", "/api/show", "/api/chat"}
    for line in sys.stdin:
        try:
            request = json.loads(line)
            path = request["path"]
            timeout = request.get("timeout_seconds", 45)
            if path not in allowed or not 1 <= timeout <= 120:
                raise ValueError("Unsupported local API request or timeout")
            payload = request.get("body")
            data = None if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
            req = urllib.request.Request("http://127.0.0.1:11434" + path, data=data,
                                         headers={"Content-Type": "application/json"})
            with opener.open(req, timeout=timeout) as response:
                raw = response.read(16 * 1024 * 1024 + 1)
                if len(raw) > 16 * 1024 * 1024:
                    raise ValueError("Local API response exceeds 16 MiB")
            result = {"ok": True, "response": json.loads(raw)}
        except urllib.error.HTTPError as exc:
            result = {"ok": False, "error": f"HTTP {exc.code}: {exc.read(16384).decode('utf-8', errors='replace')}"}
        except Exception as exc:
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(result, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
