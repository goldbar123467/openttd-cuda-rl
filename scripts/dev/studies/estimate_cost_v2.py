"""Estimate the frozen recovery matrix from retained runs before scheduling it."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local import capture_source, source_identity, write_json
from studies.evidence_v2 import Inputs
from studies.protocol_v2 import PROTOCOL_PATH, PROTOCOL_SHA256, development_matrix, load_protocol


def request_span(path, inputs):
    """Stream large logs; parse only short request records and CLOSE response."""
    path = path.resolve()
    if not path.exists():
        path = Path(str(path) + ".gz")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(4 * 1024 * 1024):
            digest.update(data)
    inputs.sha256[str(path)] = digest.hexdigest()
    first, last, close_ns = None, None, None
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as stream:
        for line in stream:
            if line.startswith(b'{"kind": "request"'):
                last = json.loads(line)
                if first is None:
                    first = last
            elif last is not None and last["request"]["operation"] == "CLOSE":
                response = json.loads(line)
                if response["kind"] != "response" or response["response"]["id"] != last["request"]["id"]:
                    raise ValueError("CLOSE request/response timing identity differs")
                close_ns = response["elapsed_ns"]
    if first is None or last["request"]["operation"] != "CLOSE" or close_ns is None:
        raise ValueError("Request log has no completed game timing span")
    seconds = (last["monotonic_ns"] - first["monotonic_ns"] + close_ns) / 1e9
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Invalid retained timing")
    return seconds


def sizes(root):
    files = [p for p in root.rglob("*") if p.is_file()]
    return {"total_bytes": sum(p.stat().st_size for p in files),
            "request_log_bytes": sum(p.stat().st_size for p in files if p.name in ("requests.jsonl", "requests.jsonl.gz"))}


def distribution(values):
    if not values or any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("Cost input is empty or nonfinite")
    return {"observations": len(values), "median": statistics.median(values), "minimum": min(values), "maximum": max(values)}


def workload(protocol):
    models = len(protocol["training_seeds"]) * len(protocol["arms"])
    matrix = len(development_matrix(protocol))
    guides = len({arm["guide"] for arm in protocol["arms"]})
    return {"training_runs": models, "training_decisions": models * protocol["fixed_training"]["decisions"],
            "candidate_games": models * matrix,
            "control_games_with_verified_reuse": guides * len(protocol["controls"]["controllers"]) * matrix,
            "control_games_without_reuse": len(protocol["arms"]) * len(protocol["controls"]["controllers"]) * matrix,
            "conditional_heldout_games": (len(protocol["training_seeds"]) + len(protocol["controls"]["controllers"])) * matrix}


def render(report):
    w = report["workload"]
    lines = ["# Recovery study cost estimate", "", report["claim"], "",
             f"The mandatory matrix has {w['training_runs']} training runs ({w['training_decisions']:,} decisions), "
             f"{w['candidate_games']} candidate games and {w['control_games_with_verified_reuse']} control games with verified reuse. "
             f"Without reuse, controls increase to {w['control_games_without_reuse']}. Eligible held-out confirmation adds "
             f"{w['conditional_heldout_games']} games, excluded from the table below.", "",
             "| Verified control reuse | Retained statistic | Sequential hours, lower bound | Artifacts, GiB | Request logs, GiB |",
             "| --- | --- | ---: | ---: | ---: |"]
    for r in report["estimates"]:
        lines.append(f"| {r['verified_control_reuse']} | {r['retained_statistic']} | {r['sequential_hours_lower_bound']:.2f} | "
                     f"{r['artifact_bytes']/2**30:.2f} | {r['request_log_bytes']/2**30:.2f} |")
    lines += ["", f"Free space at audit: {report['free_bytes_at_audit']/2**30:.2f} GiB. "
              "A numerical fit is not a safe scheduling margin; hold-out, build, scratch and other storage remain additional.", "",
              *["- " + s for s in report["limitations"]], "", "Per-run observations, paths, sizes, hashes and the cited power table are in cost.json."]
    return "\n".join(lines) + "\n"


def run(args):
    protocol = load_protocol()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    capture_source(root / "source")
    inputs = Inputs()
    inputs.read(PROTOCOL_PATH)
    report = {"status": "running", "source": source_identity(), "protocol_sha256": PROTOCOL_SHA256,
              "training": [], "neural_evaluation": [], "controls": [], "workload": workload(protocol),
              "claim": "Offline planning estimate from retained workloads; no speedup or new learning result.",
              "limitations": ["Neural request-span timing excludes source capture, model/process setup and final archive; totals are lower-bound estimates, not wall-time guarantees.",
                              "Current recovery mechanisms and eight-map population may change cost; retained runs used historical guides/settings.",
                              "Sequential estimates give no unmeasured concurrency speedup. Only one CUDA training job is allowed.",
                              "Directory byte counts describe retained artifacts at audit time; they are not a quota or a storage guarantee."]}
    try:
        for paths in (args.training, args.neural, args.controls):
            if len({p.resolve() for p in paths}) != len(paths):
                raise ValueError("Repeated cost input would overweight a retained run")
        power = inputs.json(args.power)
        if power["status"] != "passed":
            raise ValueError("Cost registration requires a completed planning power table")
        report["power_table"] = {"path": str(args.power.resolve()), "sha256": inputs.sha256[str(args.power.resolve())]}
        for path in args.training:
            r = inputs.json(path / "run.json")
            if r["status"] != "completed" or r["requested_updates"] * r["rollout_steps"] != 8192 or r["episode_horizon"] != 128 or len(r["training_map_seeds"]) != 8:
                raise ValueError("Training cost input differs from the 8192-decision/128-horizon/eight-map workload")
            report["training"].append({"path": str(path.resolve()), "wall_seconds": r["wall_seconds"],
                                       "device": r["device"], "guide": r["guidance"], **sizes(path)})
        for label, paths in (("neural_evaluation", args.neural), ("controls", args.controls)):
            for path in paths:
                r = inputs.json(path / "run.json")
                if r["status"] not in ("completed", "passed") or r["decisions"] != 512 or r["split"] != "development" or r["final_evaluation_accessed"]:
                    raise ValueError("Cost input is not a completed full-development game")
                seconds = request_span(path / "worker/requests.jsonl", inputs) if label == "neural_evaluation" else r["wall_seconds"]
                report[label].append({"path": str(path.resolve()), "seconds": seconds, "guide": r["guidance"],
                                      "engine_sha256": r["engine_sha256"], **sizes(path)})
        report["distributions"] = {"training_seconds": distribution([r["wall_seconds"] for r in report["training"]]),
            **{label + "_seconds": distribution([r["seconds"] for r in report[label]]) for label in ("neural_evaluation", "controls")}}
        w = report["workload"]
        estimates = []
        for reuse in (True, False):
            controls = w["control_games_with_verified_reuse" if reuse else "control_games_without_reuse"]
            counts = {"training": w["training_runs"], "neural_evaluation": w["candidate_games"], "controls": controls}
            for quantile in ("median", "maximum"):
                seconds = sum(counts[label] * report["distributions"][label + "_seconds"][quantile] for label in counts)
                storage = sum(counts[label] * distribution([r["total_bytes"] for r in report[label]])[quantile] for label in counts)
                requests = sum(counts[label] * distribution([r["request_log_bytes"] for r in report[label]])[quantile] for label in counts)
                estimates.append({"verified_control_reuse": reuse, "retained_statistic": quantile,
                                  "sequential_hours_lower_bound": seconds / 3600, "artifact_bytes": storage, "request_log_bytes": requests})
        free = shutil.disk_usage(root).free
        report.update(estimates=estimates, free_bytes_at_audit=free,
                      storage_fits_retained_maximum_with_verified_reuse=estimates[1]["artifact_bytes"] <= free)
        inputs.unchanged()
        report["status"] = "passed"
    except BaseException as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        report["inputs_sha256"] = inputs.sha256
        write_json(root / "cost.json", report)
    (root / "cost.md").write_text(render(report))
    print(json.dumps({k: report[k] for k in ("status", "workload", "estimates", "free_bytes_at_audit", "storage_fits_retained_maximum_with_verified_reuse")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("training", "neural", "controls"):
        parser.add_argument("--" + name, type=Path, nargs="+", required=True)
    parser.add_argument("--power", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
