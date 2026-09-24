#!/usr/bin/env python3
"""Exercise actual MCP stdio requests with a scripted client, not an LLM claim."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

from mcp import Client, StdioServerParameters

from local import ROOT, write_json


async def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    command = [str(ROOT / "scripts/dev/mcp_v2.py"), "--openttd", str(args.openttd.resolve()),
        "--policy", str(args.policy.resolve()), "--training-run", str(args.training_run.resolve()),
        "--device", args.device, "--decisions", "8", "--player-label", "scripted-mcp-smoke",
        "--output", str(root / "match")]
    record = {"kind": "actual-mcp-stdio-shared-game-smoke", "status": "running",
              "claim": "Scripted SDK client verifies MCP transport and native control; no LLM participated",
              "calls": []}
    write_json(root / "run.json", record)
    try:
        async with Client(StdioServerParameters(command=sys.executable, args=command, cwd=ROOT), read_timeout_seconds=60) as client:
            listed = await client.list_tools()
            record["negotiated_protocol"] = client.protocol_version
            record["server_info"] = client.server_info.model_dump(mode="json")
            record["tools"] = [tool.name for tool in listed.tools]
            if set(record["tools"]) != {"game_info", "start_match", "observe", "map_region", "legal_actions", "submit_action", "step", "wait_turns"}:
                raise ValueError("MCP tool inventory differs")

            async def call(name, arguments=None, *, expect_error=False):
                result = await client.call_tool(name, arguments or {})
                record["calls"].append({"tool": name, "arguments": arguments or {}, "response": result.model_dump(mode="json")})
                write_json(root / "run.json", record)
                if bool(result.is_error) != expect_error:
                    raise ValueError(f"Unexpected MCP error status for {name}: {result}")
                if expect_error:
                    return None
                if result.structured_content is not None:
                    return result.structured_content
                if len(result.content) != 1 or result.content[0].type != "text":
                    raise ValueError("MCP JSON tool response shape differs")
                return json.loads(result.content[0].text)

            info = await call("game_info")
            if info["company_id"] != 0 or info["action_budget_per_company"] != 4:
                raise ValueError("MCP company/budget differs")
            initial = await call("start_match")
            await call("start_match", expect_error=True)
            await call("step", expect_error=True)
            legal = await call("legal_actions", {"family": "WAIT", "limit": 1})
            candidate = legal["candidates"][0]["key"]
            reject = await call("submit_action", {"token": "stale", "candidate_key": candidate})
            if reject.get("reason") != "STALE_TOKEN" or reject["tick"] != initial["tick"]:
                raise ValueError("MCP stale action rejection differs")
            observed = await call("observe")
            if observed != initial:
                raise ValueError("Read-only/rejected MCP calls changed game state")
            compact = await call("observe", {"include_map": False})
            if compact != {key: value for key, value in initial.items() if key != "map"}:
                raise ValueError("Compact MCP observation changed fields other than map inclusion")
            region = await call("map_region", {"x": 16, "y": 16, "width": 16, "height": 16})
            def inside(tile):
                return 16 <= tile % initial["map"]["width"] < 32 and 16 <= tile // initial["map"]["width"] < 32
            for key in ("clear_tiles", "flat_tiles", "houses"):
                if region[key] != [tile for tile in initial["map"][key] if inside(tile)]:
                    raise ValueError("Public region differs from the full public map")
            if region["roads"] != [road for road in initial["map"]["roads"] if inside(road[0])] or region["token"] != initial["token"]:
                raise ValueError("Public region changed road information or native state")
            await call("map_region", {"x": 63, "y": 63, "width": 2, "height": 2}, expect_error=True)
            await call("wait_turns", {"count": 9}, expect_error=True)
            accepted = await call("submit_action", {"token": legal["token"], "candidate_key": candidate})
            if accepted["status"] != "OK" or accepted["next_required_tool"] != "step":
                raise ValueError("MCP legal action failed")
            await call("submit_action", {"token": legal["token"], "candidate_key": candidate}, expect_error=True)
            await call("wait_turns", {"count": 1}, expect_error=True)
            pending = await call("game_info")
            if not pending["pending_action_requires_step"] or pending["global_decisions_completed"] != 0:
                raise ValueError("MCP pending-action state or rejection timing differs")
            stepped = await call("step")
            if stepped["global_decisions_completed"] != 2 or stepped["observation"]["tick"] - initial["tick"] != 256:
                raise ValueError("MCP player/opponent step budget differs")
            if "map" in stepped["observation"]:
                raise ValueError("MCP step unexpectedly repeated the full public map")
            finished = await call("wait_turns", {"count": 3})
            if not finished["match_complete"] or finished["global_decisions_completed"] != 8:
                raise ValueError("MCP shared match did not reach its native boundary")
            record["status"] = "passed"
        native = json.loads((root / "match/run.json").read_text())
        if native["status"] != "completed" or len(native["native_result"]["companies"]) != 2:
            raise ValueError("Server did not retain complete two-company native results")
        artifacts = root / "match/worker/artifacts"
        expected_files = 8 if native["neural_guidance"] == "none" else 12
        if native["archived_neural_observations"] != 4 or list(artifacts.glob("tensors-*.bin")) or len(list(artifacts.glob("tensors-*.bin.gz"))) != expected_files:
            raise ValueError("MCP neural snapshots were not archived before the client closed")
        neural = [json.loads(line) for line in (root / "match/neural-actions.jsonl").read_text().splitlines()]
        if native["neural_guidance"] != "none" and any(row["guidance"]["guidance"] != native["neural_guidance"] or
            row["candidate"]["stable_key"] not in row["guidance"]["allowed_keys"] for row in neural):
            raise ValueError("Shared neural controller omitted its trained planner mask")
        record["match_result"] = native["native_result"]
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(root / "run.json", record)
    print(f"Actual MCP stdio/native shared smoke: {root}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("openttd", "policy", "training-run", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda:0"), required=True)
    asyncio.run(run(parser.parse_args()))
