#!/usr/bin/env python3
"""Train the existing C++ imitation objective on the best scripted games of a database.

`export` picks the best completed games per map from a *training* database
(`game_database_v2.py`), replays each one natively from its seed with its
recorded candidate keys, and requires every decision to reproduce its recorded
state token. At labelled decisions it captures the public tensors a live policy
sees, with the full native legal mask, and writes the manifest that
`rl_dev_v2_imitation` reads. Every scripted action, including WAIT, is an
explicit choice among exposed legal candidates; WAIT is labelled at a fixed
decision stride because it dominates the games.

`train` runs `rl_dev_v2_imitation` on that manifest. Export adds whole games
until `--max-examples` is reached. Up to 512 examples the trainer keeps them in
memory and takes one full-dataset step per epoch, as for the human games;
larger manifests (up to 65,536) are streamed from disk, usually with
`--minibatch` and `--evaluate-every`.

`evaluate` lets the trained network play complete games from reset on
development maps (never the training seeds), greedy and sampled, with the
same accounting as the scripted games, so it can be compared with the best
scripted route on those maps.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import time

from evaluate_bus_orders_campaign_v2 import archive_metadata
from game_database_v2 import contract_seeds
from infer_v2 import PolicyClient, checked_tensors
from live_v2_artifacts import archive_tensors
from local import capture_source, positive, source_identity, write_json
from order_projection_v3 import project_pair
from route_player_v2 import open_game
from service_v2 import summarize

SCHEMA = "openttd-rl-development-scripted-imitation-dataset-1"
NATIVE_SCHEMA = "openttd-rl-development-v2-imitation-1"
ORDER_FEATURES = ("signed-log-orders-v1", "signed-log-orders-v2", "signed-log-orders-v3")


def artifact(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def select_games(database, per_map):
    """Rank by final cash minus loan, then operating profit; sustained service only."""
    connection = sqlite3.connect(database / "games.sqlite")
    rows = connection.execute(
        "SELECT map_id, game_id, directory, net_cash, operating_profit, passengers FROM games "
        "WHERE status = 'completed' AND bankrupt = 0 AND sustained_service = 1 "
        "ORDER BY map_id, net_cash DESC, operating_profit DESC, game_id").fetchall()
    connection.close()
    chosen, counts = [], {}
    for map_id, game_id, directory, net_cash, profit, passengers in rows:
        if counts.get(map_id, 0) < per_map:
            counts[map_id] = counts.get(map_id, 0) + 1
            chosen.append({"map_id": map_id, "game_id": game_id, "directory": directory, "net_cash": net_cash,
                           "operating_profit": profit, "passengers": passengers})
    return chosen


def labelled(row, wait_stride):
    return row["family"] != "WAIT" or row["decision"] % wait_stride == 0


def replay(engine, game, output, *, wait_stride, focus, features):
    """Reproduce one game natively and capture its labelled decisions."""
    directory = Path(game["directory"])
    result = json.loads((directory / "result.json").read_text())
    with gzip.open(directory / "decisions.jsonl.gz", "rt") as stream:
        rows = [json.loads(line) for line in stream]
    last = max(index for index, row in enumerate(rows) if labelled(row, wait_stride))
    client = open_game(engine, output / "worker", result["world"], result["decisions_budget"], focus=focus)
    examples = []
    try:
        for row in rows[:last + 1]:
            observation = client.request("OBSERVE")["observation"]
            if observation["token"] != row["token"]:
                raise ValueError(f"Replay diverged before decision {row['decision']}; engine or map differs")
            if labelled(row, wait_stride):
                obs_path, candidate_path, records, mask = checked_tensors(client.request("TENSORS"), observation,
                                                                          observation_mode="orders-v1")
                action = next(index for index, record in records.items() if record["stable_key"] == row["key"])
                example = {"sample_id": f"decision-{row['decision']:03d}", "game_id": game["game_id"], "map_id": game["map_id"],
                           "decision": row["decision"], "phase": row["phase"], "action_family": records[action]["family_index"],
                           "family": row["family"], "action_row": action, "candidate_key": row["key"],
                           "legal_rows": [index for index, value in enumerate(mask) if value],
                           "observation_tensor": artifact(obs_path), "candidate_tensor": artifact(candidate_path)}
                example["source_tensors"] = [example["observation_tensor"], example["candidate_tensor"]]
                if features == "signed-log-orders-v3":
                    pair, projection = project_pair(obs_path, candidate_path, output / f"v3-{row['decision']:03d}",
                                                    public_state=observation)
                    example.update(observation_tensor=artifact(pair[0]), candidate_tensor=artifact(pair[1]), order_projection=projection)
                examples.append(example)
            action = client.request("ACT", token=observation["token"], candidate=row["key"])
            if action["status"] != "OK":
                raise ValueError(f"Recorded action was rejected at decision {row['decision']}")
            client.request("STEP")
        client.close()
        client = None
    finally:
        if client is not None:
            client.abort()
    if features == "signed-log-orders-v3":
        # The trainer reads the projections; keep the raw native tensors as
        # verified lossless archives (their recorded hashes are uncompressed).
        archive_tensors(output / "worker")
        archive_metadata(output / "worker")
    return examples


def export(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    database = args.database.resolve()
    identity = json.loads((database / "database.json").read_text())
    engine = args.openttd.resolve(strict=True)
    if identity["split"] != "training":
        raise ValueError("Imitation examples come only from a training-split database")
    if hashlib.sha256(engine.read_bytes()).hexdigest() != identity["engine_sha256"]:
        raise ValueError("Replay engine differs from the engine that played the database")
    record = {"schema_version": SCHEMA, "status": "running", "source": source_identity(), "database": str(database),
              "database_identity": identity, "selection": {"per_map": args.per_map, "rank": "net_cash, operating_profit",
              "requires": "completed, not bankrupt, service with profit in all final three 128-decision windows"},
              "wait_stride": args.wait_stride, "max_examples": args.max_examples, "financial_features": args.financial_features,
              "games": [], "skipped_games": []}
    write_json(output / "dataset.json", record)
    started = time.monotonic()
    examples = []
    try:
        record["source_capture"] = capture_source(output / "source")
        for game in select_games(database, args.per_map):
            replayed = replay(engine, game, output / "games" / game["game_id"], wait_stride=args.wait_stride,
                              focus=identity.get("candidate_focus") == "town-pair-v1", features=args.financial_features)
            if len(examples) + len(replayed) > args.max_examples:
                record["skipped_games"].append({**game, "examples": len(replayed), "reason": "example budget"})
                continue
            examples.extend(replayed)
            record["games"].append({**game, "examples": len(replayed)})
            write_json(output / "dataset.json", record)
            print(json.dumps({"game": game["game_id"], "map": game["map_id"], "examples": len(replayed), "total": len(examples)}), flush=True)
        if not examples:
            raise ValueError("No qualifying games were found")
        lines = [NATIVE_SCHEMA] + ["\t".join([e["sample_id"], e["game_id"], e["observation_tensor"]["path"], e["candidate_tensor"]["path"],
                                               str(e["action_row"]), str(e["action_family"]), ",".join(map(str, e["legal_rows"]))])
                                    for e in examples]
        (output / "native-imitation.tsv").write_text("\n".join(lines) + "\n")
        write_json(output / "labels.json", {"examples": examples})
        families = {}
        for example in examples:
            families[example["family"]] = families.get(example["family"], 0) + 1
        record.update(status="completed", examples=len(examples), families=families,
                      native_manifest=artifact(output / "native-imitation.tsv"), labels=artifact(output / "labels.json"))
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        record["elapsed_seconds"] = round(time.monotonic() - started, 1)
        write_json(output / "dataset.json", record)


def train(args):
    dataset = json.loads((args.dataset.resolve() / "dataset.json").read_text())
    if dataset.get("schema_version") != SCHEMA or dataset["status"] != "completed":
        raise ValueError("Train requires a completed scripted imitation export")
    if dataset["financial_features"] != args.financial_features:
        raise ValueError("Export and training preprocessing differ")
    manifest = artifact(dataset["native_manifest"]["path"])
    if manifest["sha256"] != dataset["native_manifest"]["sha256"]:
        raise ValueError("Native manifest changed after export")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    model = output / "inference-weights.pt"
    command = [str(args.trainer.resolve(strict=True)), "--device", args.device, "--seed", str(args.seed),
               "--epochs", str(args.epochs), "--learning-rate", str(args.learning_rate),
               "--financial-features", args.financial_features, "--manifest", manifest["path"], "--output", str(model)]
    if dataset["examples"] > 512:
        command += ["--max-examples", str(dataset["max_examples"])]
    if args.minibatch:
        command += ["--minibatch", str(args.minibatch)]
    if args.evaluate_every != 1:
        command += ["--evaluate-every", str(args.evaluate_every)]
    record = {"kind": "native-v2-scripted-imitation", "status": "running", "source": source_identity(),
              "device": args.device, "seed": args.seed, "epochs": args.epochs, "learning_rate": args.learning_rate,
              "minibatch": args.minibatch or "full-dataset", "evaluate_every": args.evaluate_every,
              "financial_features": args.financial_features, "dataset": str(args.dataset.resolve()), "manifest": manifest,
              "trainer": artifact(args.trainer), "command": command,
              "objective": "mean negative log likelihood of the scripted player's exact native candidate",
              "claim": "Training-set fit of scripted demonstrations; gameplay strength needs separate evaluation"}
    write_json(output / "run.json", record)
    started = time.monotonic()
    try:
        with (output / "native-metrics.jsonl").open("x") as metrics, (output / "trainer.log").open("x") as log:
            subprocess.run(command, stdout=metrics, stderr=log, check=True)
        events = [json.loads(line) for line in (output / "native-metrics.jsonl").read_text().splitlines()]
        result = events[-1]
        if (result["event"] != "completed" or result["device"] != args.device or result["examples"] != dataset["examples"] or
                not result["finite_gradients"] or not result["exact_legal_masks"] or result["final"]["loss"] >= result["initial"]["loss"]):
            raise ValueError("Native imitation result differs from the requested fit")
        summary = {key: result["final"][key] for key in ("count", "loss", "accuracy", "unique_exact_accuracy", "family_head_accuracy")}
        summary["by_family"] = {family: {key: value[key] for key in ("count", "accuracy", "unique_exact_accuracy")}
                                for family, value in result["final"]["by_family"].items()}
        record.update(status="completed", initial_loss=result["initial"]["loss"], final=summary,
                      model={**artifact(model), "financial_features": args.financial_features})
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        record["elapsed_seconds"] = round(time.monotonic() - started, 1)
        write_json(output / "run.json", record)
    print(json.dumps({key: record.get(key) for key in ("status", "initial_loss", "final", "elapsed_seconds")}, indent=1))


def play_policy(engine, infer, model, output, world, mode, seed, *, decisions, focus, features):
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "world": world, "mode": mode, "action_seed": seed, "model": model,
              "decisions_budget": decisions, "candidate_focus": "town-pair-v1" if focus else None}
    client = policy = None
    started = time.monotonic()
    try:
        client = open_game(engine, output / "worker", world, decisions, focus=focus)
        policy = PolicyClient(infer, output / "policy.log", "cpu", seed, mode=mode, weights=Path(model["path"]),
                              financial_features=features)
        policy.check_financial_features()
        initial = state = client.request("OBSERVE")["observation"]
        transitions, families = [], Counter()
        with gzip.open(output / "decisions.jsonl.gz", "wt") as log:
            for _ in range(decisions):
                obs_path, candidate_path, records, mask = checked_tensors(client.request("TENSORS"), state, observation_mode="orders-v1")
                policy.request("RESET")
                prediction = policy.request(f"{obs_path}\t{candidate_path}",
                                            **({"public_state": state} if features == "signed-log-orders-v3" else {}))
                if prediction["row"] not in records or not mask[prediction["row"]]:
                    raise ValueError("Policy chose outside the exact native mask")
                key = records[prediction["row"]]["stable_key"]
                candidate = next(row for row in state["candidates"] if row["key"] == key)
                action = client.request("ACT", token=state["token"], candidate=key)
                if action["status"] != "OK" or action["action"]["status"] not in ("SUCCESS", "NO_OP"):
                    raise RuntimeError(f"Policy action failed natively: {action}")
                transition = client.request("STEP")["transition"]
                transitions.append(transition)
                families[candidate["family"]] += 1
                log.write(json.dumps({"decision": transition["decision"], "family": candidate["family"],
                                      "parameters": candidate["parameters"][:4], "probability": prediction["probabilities"][prediction["row"]],
                                      "after": transition["after"]}, separators=(",", ":")) + "\n")
                for path in (output / "worker/artifacts").glob("tensors-*"):
                    path.unlink()
                state = client.request("OBSERVE")["observation"]
                if transition["terminal"] or transition["truncated"]:
                    break
        client.close()
        client = None
        policy.close()
        policy = None
        report.update(status="completed", summary=summarize(transitions, initial, state), families=dict(families),
                      final_state={key: state[key] for key in ("economy", "stations", "depots", "vehicles")})
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
    finally:
        for process in (client, policy):
            if process is not None:
                process.abort()
        report["wall_seconds"] = round(time.monotonic() - started, 1)
        write_json(output / "run.json", report)
    return report


def evaluate(args):
    training = json.loads((args.training_run.resolve() / "run.json").read_text())
    if training.get("kind") != "native-v2-scripted-imitation" or training["status"] != "completed":
        raise ValueError("Evaluate requires a completed scripted imitation training run")
    model = training["model"]
    if artifact(model["path"])["sha256"] != model["sha256"]:
        raise ValueError("Trained weights changed after training")
    dataset = json.loads((Path(training["dataset"]) / "dataset.json").read_text())
    engine = args.openttd.resolve(strict=True)
    if hashlib.sha256(engine.read_bytes()).hexdigest() != dataset["database_identity"]["engine_sha256"]:
        raise ValueError("Evaluation engine differs from the engine that produced the training games")
    focus = dataset["database_identity"].get("candidate_focus") == "town-pair-v1"
    seeds = args.seeds or contract_seeds("development")[:args.maps]
    if not set(seeds) <= set(contract_seeds("development")):
        raise ValueError("Evaluation maps come only from the development ledger")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {"kind": "scripted-imitation-gameplay-evaluation", "status": "running", "source": source_identity(),
              "training_run": str(args.training_run.resolve()), "model": model, "split": "development",
              "seeds": seeds, "size": args.size, "modes": args.modes, "decisions": args.decisions, "games": [],
              "claim": "Complete games from reset with the trained network choosing every action; no guide or mask filtering"}
    write_json(output / "evaluation.json", record)
    for seed in seeds:
        world = {"seed": seed, "split": "development", "width": args.size, "height": args.size}
        for mode in args.modes:
            report = play_policy(engine, args.infer.resolve(strict=True), model, output / f"{seed}-{mode}", world, mode,
                                 args.action_seed, decisions=args.decisions, focus=focus, features=training["financial_features"])
            summary = report.get("summary") or {}
            record["games"].append({"seed": seed, "mode": mode, "status": report["status"], "error": report.get("error"),
                                    **{key: summary.get(key) for key in ("passengers", "operating_profit", "buses", "stations",
                                       "first_delivery_action", "service_in_all_final_three_windows", "action_counts")}})
            write_json(output / "evaluation.json", record)
            print(json.dumps(record["games"][-1]), flush=True)
    record["status"] = "completed"
    write_json(output / "evaluation.json", record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    exporter = commands.add_parser("export")
    exporter.add_argument("--database", type=Path, required=True)
    exporter.add_argument("--openttd", type=Path, required=True)
    exporter.add_argument("--output", type=Path, required=True)
    exporter.add_argument("--per-map", type=positive, default=1)
    exporter.add_argument("--wait-stride", type=positive, default=32)
    exporter.add_argument("--max-examples", type=positive, default=512, help="up to 65536; above 512 the trainer streams")
    exporter.add_argument("--financial-features", choices=ORDER_FEATURES, default="signed-log-orders-v3")
    trainer = commands.add_parser("train")
    trainer.add_argument("--dataset", type=Path, required=True)
    trainer.add_argument("--trainer", type=Path, required=True, help="rl_dev_v2_imitation")
    trainer.add_argument("--output", type=Path, required=True)
    trainer.add_argument("--device", choices=("cpu", "cuda:0"), required=True)
    trainer.add_argument("--seed", type=int, default=20261002)
    trainer.add_argument("--epochs", type=positive, default=256)
    trainer.add_argument("--learning-rate", type=float, default=0.0003)
    trainer.add_argument("--financial-features", choices=ORDER_FEATURES, default="signed-log-orders-v3")
    trainer.add_argument("--minibatch", type=int, default=0, help="examples per Adam step; 0 is one full-dataset step per epoch")
    trainer.add_argument("--evaluate-every", type=positive, default=1, help="epochs between full training-set measurements")
    evaluator = commands.add_parser("evaluate")
    evaluator.add_argument("--training-run", type=Path, required=True)
    evaluator.add_argument("--infer", type=Path, required=True, help="rl_dev_v2_infer from the same build")
    evaluator.add_argument("--openttd", type=Path, required=True)
    evaluator.add_argument("--output", type=Path, required=True)
    evaluator.add_argument("--seeds", type=int, nargs="*", help="development ledger seeds (default: the first --maps)")
    evaluator.add_argument("--maps", type=positive, default=4)
    evaluator.add_argument("--size", type=int, choices=(64, 128), default=64)
    evaluator.add_argument("--modes", nargs="+", choices=("greedy", "sampled"), default=["greedy", "sampled"])
    evaluator.add_argument("--action-seed", type=int, default=20261028)
    evaluator.add_argument("--decisions", type=positive, default=512)
    arguments = parser.parse_args()
    if arguments.command == "export" and arguments.max_examples > 65536:
        parser.error("--max-examples is at most 65536")
    {"export": export, "train": train, "evaluate": evaluate}[arguments.command](arguments)
