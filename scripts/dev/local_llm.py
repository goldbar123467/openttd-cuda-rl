#!/usr/bin/env python3
"""Bounded local Ollama client and a recorded tool-calling capability probe."""
import argparse
import json
from pathlib import Path
import subprocess
import time

from local import ROOT, capture_source, write_json


def ollama_schema(schema):
    """Represent optional nullable scalar fields as optional non-null scalars.

    Omission still selects the server default. This only narrows model-visible
    argument syntax; it neither changes MCP validation nor supplies arguments.
    Complex unions are retained rather than guessing an equivalent type.
    """
    if isinstance(schema, list):
        return [ollama_schema(value) for value in schema]
    if not isinstance(schema, dict):
        return schema
    result = {key: ollama_schema(value) for key, value in schema.items() if key != "title"}
    choices = result.get("anyOf", [])
    present = [value for value in choices if value != {"type": "null"}]
    if len(choices) == 2 and len(present) == 1 and present[0].get("type") in ("integer", "string", "boolean", "number"):
        result.pop("anyOf")
        result.update(present[0])
        if result.get("default", False) is None:
            result.pop("default")
    return result


class LocalLLM:
    def __init__(self, host_python):
        bridge = subprocess.check_output(["wslpath", "-w", str(ROOT / "scripts/dev/ollama_host_bridge.py")], text=True).strip()
        self.process = subprocess.Popen([str(host_python), "-X", "utf8", bridge],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)

    def request(self, path, body=None, timeout_seconds=45):
        self.process.stdin.write(json.dumps({"path": path, "body": body, "timeout_seconds": timeout_seconds}) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(f"Local LLM bridge exited: {self.process.poll()}")
        result = json.loads(line)
        if not result["ok"]:
            raise RuntimeError(result["error"])
        return result["response"]

    def identity(self, model):
        tags = self.request("/api/tags")
        selected = next((row for row in tags["models"] if model in (row["name"], row["model"])), None)
        if selected is None:
            raise ValueError("Requested model is not installed; this runner never downloads models")
        shown = self.request("/api/show", {"model": model})
        return {"server": self.request("/api/version"), "model": selected,
                "details": shown["details"], "capabilities": shown.get("capabilities", []),
                "model_info": shown.get("model_info", {})}

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=3)


def probe(args):
    args.output.mkdir(parents=True, exist_ok=False)
    capture_source(args.output / "source")
    llm = LocalLLM(args.host_python)
    record = {"kind": "local-llm-tool-capability-probe", "status": "running", "claim": "No OpenTTD game is started by this probe"}
    try:
        record["identity"] = llm.identity(args.model)
        request = {"model": args.model, "stream": False, "think": False, "keep_alive": "10m",
            "messages": [{"role": "system", "content": "You control a game through tools. Call game_info now to read the game rules and assigned company. Do not invent its response."},
                         {"role": "user", "content": "Read the game information."}],
            "tools": [{"type": "function", "function": {"name": "game_info", "description": "Read the game rules and assigned company.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}}],
            "options": {"temperature": 0, "seed": 20260923, "num_ctx": 8192, "num_predict": 160}}
        record["request"] = request
        write_json(args.output / "probe.json", record)
        started = time.monotonic_ns()
        response = llm.request("/api/chat", request, timeout_seconds=120)
        record.update(response=response, elapsed_ns=time.monotonic_ns() - started,
                      running_models=llm.request("/api/ps"))
        calls = response.get("message", {}).get("tool_calls", [])
        if len(calls) != 1 or calls[0]["function"].get("name") != "game_info" or calls[0]["function"].get("arguments") != {}:
            raise ValueError("Installed model did not emit the requested structured tool call")
        record["status"] = "passed"
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(args.output / "probe.json", record)
        llm.close()
    print(json.dumps({"status": record["status"], "elapsed_ns": record["elapsed_ns"],
                      "message": record["response"]["message"], "running_models": record["running_models"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-python", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    probe(parser.parse_args())
