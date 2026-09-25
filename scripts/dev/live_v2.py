#!/usr/bin/env python3
"""Bounded interactive control of the native development V2 bus environment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import struct
import subprocess
import sys
import time

from local import ROOT, capture_source, positive, source_identity, write_json

SCHEMA = "openttd-rl-development-v2-live-1"
SHARED_SCHEMA = "openttd-rl-development-v2-shared-1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def reset_manifest(executable, baseset, seed, split, width=64, height=64):
    if split not in ("training", "development"):
        raise ValueError("Live development forbids held-out splits")
    return _reset_manifest_payload(executable, baseset, seed, split, width, height)


def _reset_manifest_payload(executable, baseset, seed, split, width=64, height=64):
    """Shared encoder; reserved splits require the registered executor's permit."""
    if type(width) is not int or type(height) is not int or (seed is not None and type(seed) is not int):
        raise ValueError("Live seed/dimensions must be integers")
    contract_path = ROOT / "config/v2/m15-scalable-contract.json"
    contract = json.loads(contract_path.read_text())
    allowed = contract["seeds"]["sets"][split]["seeds"]
    seed = allowed[0] if seed is None else seed
    if seed not in allowed or [width, height] not in contract["map"]["native_rectangles"] or max(width, height) > 128:
        raise ValueError("Seed/dimensions outside the selected development split/bounds")
    def stream(label):
        value = hashlib.sha256(f"openttd-rl-v2-m15-reset-stream-v1:{label}:{seed}".encode()).digest()
        return int.from_bytes(value[:4], "big") & 0x7FFFFFFF
    source = json.loads((ROOT / "config/v2/m15-native-source.json").read_text())
    return {"schema_version": "openttd-rl-v2-m15-reset-manifest-1",
            "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
            "engine_source_tree": source["base"]["engine_source_tree"],
            "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "map_width": width, "map_height": height, "map_seed": seed,
            "simulation_seed": stream("simulation"), "candidate_tiebreak_seed": stream("candidate-tiebreak"),
            "split": split, "climate": "temperate", "start_year": 1950,
            "settings_manifest_sha256": hashlib.sha256((ROOT / "config/v2/setting-inventory.json").read_bytes()).hexdigest(),
            "content_manifest_sha256": hashlib.sha256(baseset.read_bytes()).hexdigest(),
            "generation_mode": "native-seeded", "town_target": max(2, min(128, width * height // 4096)),
            "industry_target": 256, "company_count": 1, "resource_tier": "curriculum",
            "v1_adapter": False, "rejection_reason": None}


class LiveV2:
    def __init__(self, engine, output, *, seed=None, split="training", decisions=8, ticks=128, companies=1, first_company=0,
                 visible=False, _reset_factory=None):
        self.engine, self.output = Path(engine).resolve(), Path(output).resolve()
        if type(visible) is not bool:
            raise ValueError("Visible display flag must be boolean")
        if visible and (companies != 1 or os.environ.get("SDL_VIDEODRIVER") in ("dummy", "offscreen") or
                        not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))):
            raise ValueError("Visible playback requires one company and a real native display")
        if type(decisions) is not int or type(ticks) is not int or not 1 <= decisions <= 512 or not 1 <= ticks <= 128:
            raise ValueError("Live decision/tick bounds invalid")
        if type(companies) is not int or companies not in (1, 2) or type(first_company) is not int or not 0 <= first_company < companies or decisions % companies:
            raise ValueError("Company count, first actor or balanced action budget invalid")
        self.schema = SHARED_SCHEMA if companies == 2 else SCHEMA
        factory = reset_manifest if _reset_factory is None else _reset_factory
        manifest = factory(self.engine, self.engine.parent / "baseset/opengfx-8.0.tar", seed, split)
        self.output.mkdir(parents=True, exist_ok=False)
        (self.output / "artifacts").mkdir()
        (self.output / "openttd.cfg").write_text("\n")
        (self.output / "reset.json").write_bytes(canonical(manifest) + b"\n")
        input_child, self.input = os.pipe()
        self.output_fd, output_child = os.pipe()
        config = {"schema_version": self.schema, "company_id": first_company, "input_fd": input_child,
                  "output_fd": output_child, "maximum_decisions": decisions, "step_ticks": ticks}
        if companies == 2:
            config["company_count"] = companies
        (self.output / "live.json").write_bytes(canonical(config) + b"\n")
        self.request_id = 0
        self.events = (self.output / "requests.jsonl").open("x")
        command = [str(self.engine), "-x", "-X", "-Q", "-I", "OpenGFX", "-v", "sdl" if visible else "null", "-s", "null", "-m", "null",
                   "-c", str(self.output / "openttd.cfg"), "-V", str(self.output / "reset.json"),
                   "-U", str(self.output / "reset-projection.json"), "-E", str(self.output / "live.json"),
                   "-F", str(self.output / "transitions.jsonl"), "-H", str(self.output / "artifacts")]
        environment = None
        if visible:
            environment = os.environ.copy()
            if not environment.get("SDL_VIDEODRIVER"):
                environment["SDL_VIDEODRIVER"] = "x11" if environment.get("DISPLAY") else "wayland"
            command += ["-b", "32bpp-anim", "-r", "1280x800"]
            write_json(self.output / "display.json", {"mode": "native-sdl-view-only", "command": command,
                "display": {name: environment.get(name) for name in ("DISPLAY", "WAYLAND_DISPLAY", "SDL_VIDEODRIVER")},
                "isolation": "Explicit empty per-run configuration, -X local paths and separate working directory"})
        try:
            with (self.output / "openttd.log").open("x") as log:
                self.process = subprocess.Popen(command, cwd=self.output, pass_fds=(input_child, output_child),
                                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=environment)
        except BaseException:
            for descriptor in (self.input, self.output_fd):
                os.close(descriptor)
            self.events.close()
            raise
        finally:
            os.close(input_child)
            os.close(output_child)

    def _read(self, size, deadline):
        result = bytearray()
        while len(result) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.output_fd], [], [], remaining)[0]:
                raise TimeoutError("Native live V2 response timed out")
            value = os.read(self.output_fd, size - len(result))
            if not value:
                raise RuntimeError(f"Native live V2 closed its response pipe; see {self.output / 'openttd.log'}")
            result.extend(value)
        return bytes(result)

    def request(self, operation, *, company_id=0, **fields):
        if "id" in fields:
            raise ValueError("Request identity belongs to the transport")
        request = {"id": self.request_id + 1, "company_id": company_id, "operation": operation, **fields}
        payload = canonical(request)
        if len(payload) > 16384:
            raise ValueError("Request exceeds native frame limit")
        self.request_id += 1
        started = time.monotonic_ns()
        self.events.write(json.dumps({"kind": "request", "request": request, "monotonic_ns": started}) + "\n")
        self.events.flush()
        frame = struct.pack("<I", len(payload)) + payload
        sent = 0
        while sent < len(frame):
            count = os.write(self.input, frame[sent:])
            if count <= 0:
                raise RuntimeError("Native live V2 request pipe accepted no bytes")
            sent += count
        deadline = time.monotonic() + 60
        size = struct.unpack("<I", self._read(4, deadline))[0]
        if not 0 < size <= 4 * 1024 * 1024:
            raise RuntimeError("Native response exceeds frame limit")
        response = json.loads(self._read(size, deadline))
        if response.get("schema_version") != self.schema or response.get("id") != self.request_id:
            raise RuntimeError("Native response identity differs")
        self.events.write(json.dumps({"kind": "response", "response": response, "elapsed_ns": time.monotonic_ns() - started}) + "\n")
        self.events.flush()
        return response

    def close(self):
        try:
            self.request("CLOSE")
            if self.process.wait(timeout=10) != 0:
                raise RuntimeError("Native live V2 exited unsuccessfully")
        finally:
            self.abort()

    def abort(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for name in ("input", "output_fd"):
            descriptor = getattr(self, name, None)
            if descriptor is not None:
                os.close(descriptor)
                setattr(self, name, None)
        self.events.close()


def smoke(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    record = {"kind": "interactive-native-v2-development-smoke", "status": "running", "source": source_identity(),
              "claim": "Interactive native control correctness; scripted actions, not neural learning or shared-company competition"}
    capture_source(root / "source")
    write_json(root / "run.json", record)
    client = None
    try:
        client = LiveV2(args.openttd, root / "worker", seed=args.seed, split=args.split, decisions=args.decisions)
        first = client.request("OBSERVE")["observation"]
        if client.request("OBSERVE")["observation"] != first:
            raise RuntimeError("Read-only observation advanced the game")
        checks = [(client.request("OBSERVE", company_id=1), "COMPANY_SCOPE"),
                  (client.request("STEP"), "NO_PENDING_ACTION"),
                  (client.request("ACT", token="stale", candidate=first["candidates"][0]["key"]), "STALE_TOKEN"),
                  (client.request("ACT", token=first["token"], candidate="not-a-candidate"), "ILLEGAL_CANDIDATE")]
        if any(value["status"] != "REJECTED" or value.get("reason") != expected or value["tick"] != first["tick"]
               for value, expected in checks):
            raise RuntimeError("Protocol rejection changed native time or lost its reason")
        transitions = []
        for index in range(args.decisions):
            observation = first if index == 0 else client.request("OBSERVE")["observation"]
            family = "WAIT"
            if args.policy == "reactive-build":
                if not observation["depots"]:
                    family = "BUILD_ROAD_DEPOT"
                elif not observation["vehicles"]:
                    family = "BUY_BUS"
            candidates = [c for c in observation["candidates"] if c["family"] == family]
            if not candidates:
                raise RuntimeError(f"Reactive smoke has no legal {family} candidate")
            result = client.request("ACT", token=observation["token"], candidate=candidates[0]["key"])
            if result["status"] != "OK" or result["action"]["status"] not in ("SUCCESS", "NO_OP"):
                raise RuntimeError("Native legal candidate failed")
            if index == 0:
                duplicate = client.request("ACT", token=observation["token"], candidate=candidates[0]["key"])
                if duplicate.get("reason") != "DECISION_BOUNDARY" or duplicate["tick"] != observation["tick"]:
                    raise RuntimeError("Two actions were accepted before a simulation step")
            transition = client.request("STEP")["transition"]
            if transition["tick_after"] - transition["tick_before"] != 128:
                raise RuntimeError("Native fixed-step budget differs")
            transitions.append(transition)
            if transition["terminal"]:
                break
        final = client.request("OBSERVE")["observation"]
        if args.policy == "reactive-build" and (len(final["depots"]) < 1 or len(final["vehicles"]) != 1):
            raise RuntimeError("Reactive actions did not create a native depot and bus")
        client.close()
        client = None
        record.update(status="passed", policy=args.policy, transitions=len(transitions), final_observation=final,
                      native_result=json.loads((root / "worker/artifacts/live-result.json").read_text()))
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        if client is not None:
            client.abort()
        write_json(root / "run.json", record)
    print(f"Interactive V2 smoke: {record['status']} {root}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openttd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--split", choices=("training", "development"), default="training")
    parser.add_argument("--decisions", type=positive, default=8)
    parser.add_argument("--policy", choices=("wait", "reactive-build"), default="reactive-build")
    smoke(parser.parse_args())
