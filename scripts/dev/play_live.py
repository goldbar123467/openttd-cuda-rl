#!/usr/bin/env python3
"""Run a saved neural policy in an isolated native OpenTTD window."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import struct

from local import capture_source, source_identity, write_json


def native_screenshot(output, stem="m11-playback"):
    paths = [output / "screenshot" / f"{stem}.{extension}" for extension in ("png", "bmp")]
    present = [path for path in paths if path.is_file()]
    if len(present) != 1:
        raise RuntimeError("Expected exactly one native SDL PNG or BMP viewport screenshot")
    path = present[0]
    with path.open("rb") as stream:
        header = stream.read(26)
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        dimensions = struct.unpack(">II", header[16:24])
    elif header.startswith(b"BM"):
        width, height = struct.unpack("<ii", header[18:26])
        dimensions = width, abs(height)
    else:
        raise RuntimeError("Unknown native screenshot encoding")
    if dimensions != (1280, 800):
        raise RuntimeError(f"Native viewport dimensions differ: {dimensions}")
    return path


def run(args):
    instance = args.instance.resolve()
    allowed = {f"m02-template-{i:02d}.json" for i in range(1, 7)}
    if instance.name not in allowed:
        raise ValueError("Playback accepts only training/development instance filenames")
    scenario = json.loads(instance.read_text())
    if scenario["split"] not in {"training", "development"} or instance.stem != scenario["template_id"]:
        raise ValueError("Playback forbids held-out scenarios and mismatched instance identities")
    if args.actions < 0 or args.actions > 4096 or (args.actions == 0 and not args.watch):
        raise ValueError("Use 1..4096 bounded actions, or --watch --actions 0 for interactive playback")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    config = {"schema_version": "openttd-rl-development-playback-config-1",
              "contract_sha256": "3f331f7852b0174714de30b8ab6015178d7e01d4691832f8af2085d32bb01e42",
              "package_path": str(args.package.resolve()), "scenario_instance": str(instance),
              "inference": {"mode": "greedy" if args.mode == "greedy" else "seeded-stochastic",
                            "sampling_seed": args.seed, "interval_ticks": 128},
              "logging": {"actions": True, "path": str(output / "actions.jsonl"), "maximum_records": 4096},
              "inspection": {"window": True, "debug_overlay": False, "report_path": str(output / "inspection.json")},
              "controls": {"start_agent_paused": False, "native_pause_button": True, "agent_step_button": True},
              "acceptance": {"maximum_actions": args.actions, "exit_when_complete": not args.watch}}
    (output / "playback.json").write_text(json.dumps(config, sort_keys=True, separators=(",", ":")) + "\n")
    (output / "openttd.cfg").write_text("\n")
    command = [str(args.openttd.resolve()), "-v", "sdl", "-b", "32bpp-anim", "-r", "1280x800",
               "-X", "-s", "null", "-m", "null", "-I", "OpenGFX", "-Q", "-x",
               "-c", str(output / "openttd.cfg"), "-A", str(output / "playback.json")]
    environment = os.environ.copy()
    # Real WSLg/native display; never substitute SDL's offscreen dummy driver.
    if environment.get("SDL_VIDEODRIVER") == "dummy":
        raise ValueError("Visible playback refuses SDL_VIDEODRIVER=dummy")
    record = {"kind": "visible-development-neural-playback", "status": "starting", "source": source_identity(),
              "command": command, "scenario": scenario, "package": str(args.package.resolve()),
              "engine_sha256": hashlib.sha256(args.openttd.read_bytes()).hexdigest(),
              "display": {name: environment.get(name) for name in ("DISPLAY", "WAYLAND_DISPLAY", "SDL_VIDEODRIVER")},
              "isolation": "OpenTTD -X local paths, explicit empty per-run config, separate working directory; no normal game data",
              "claim": "development playback, not a held-out or historical release result"}
    capture_source(output / "source")
    write_json(output / "run.json", record)
    with (output / "openttd.log").open("x") as log:
        process = subprocess.Popen(command, cwd=output, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    record.update(pid=process.pid, status="launched")
    write_json(output / "run.json", record)
    if not args.watch:
        try:
            code = process.wait(timeout=args.timeout)
            if code != 0:
                raise RuntimeError(f"Visible OpenTTD exited with status {code}; see openttd.log")
            report = json.loads((output / "inspection.json").read_text())
            if report["status"] != "COMPLETE" or report["action_count"] != args.actions:
                raise RuntimeError("Native playback did not complete its configured actions")
            screenshot = native_screenshot(output)
            record.update(status="completed", report=report, screenshot=str(screenshot),
                          screenshot_sha256=hashlib.sha256(screenshot.read_bytes()).hexdigest())
        except BaseException as exc:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            record.update(status="failed", error=str(exc))
            raise
        finally:
            write_json(output / "run.json", record)
    print(json.dumps({key: record[key] for key in ("status", "pid")}, indent=2))
    print(f"Playback artifacts: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("openttd", "package", "instance", "output"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--mode", choices=("greedy", "sampled"), default="sampled")
    parser.add_argument("--seed", type=int, default=20260923)
    parser.add_argument("--actions", type=int, default=512)
    parser.add_argument("--watch", action="store_true", help="Keep the native game window open; does not enable fast-forward")
    parser.add_argument("--timeout", type=int, default=180)
    run(parser.parse_args())
