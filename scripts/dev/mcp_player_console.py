#!/usr/bin/env python3
"""JSON-line console that relays every game tool call through a real MCP client.

Input: {"tool":"observe","arguments":{}}. A literal CLOSE ends the connection.
The console does not select or invent any game actions.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys

from mcp import Client, StdioServerParameters


async def run(args):
    # Host-written launch data belongs to the coordinator, not the game tools.
    launch = json.loads(args.launch.read_text())
    params = StdioServerParameters(command=launch["command"], args=launch["args"], cwd=launch["cwd"])
    async with Client(params, read_timeout_seconds=60) as client:
        tools = await client.list_tools()
        print(json.dumps({"status": "MCP_CONNECTED", "protocol_version": client.protocol_version,
                          "tools": [tool.model_dump(mode="json") for tool in tools.tools]}), flush=True)
        while True:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line or line.strip() == "CLOSE":
                break
            try:
                request = json.loads(line)
                if set(request) != {"tool", "arguments"} or not isinstance(request["arguments"], dict):
                    raise ValueError("Expected exactly tool and arguments")
                result = await client.call_tool(request["tool"], request["arguments"])
                data = result.structured_content
                if data is None and len(result.content) == 1 and result.content[0].type == "text":
                    try:
                        data = json.loads(result.content[0].text)
                    except json.JSONDecodeError:
                        data = result.content[0].text
                print(json.dumps({"tool": request["tool"], "is_error": result.is_error,
                                  "result": data if data is not None else result.model_dump(mode="json")}), flush=True)
            except Exception as exc:
                print(json.dumps({"console_error": str(exc)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
