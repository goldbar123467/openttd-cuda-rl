"""Eight training-only reset probes; native PROBE never samples or advances PPO."""
from pathlib import Path

from guide_v2 import PublicPlanGuide
from infer_v2 import checked_tensors
from live_v2 import LiveV2
from local import write_json
from studies.execution_v2 import artifact
from studies.protocol_v2 import PROTOCOL_SHA256, load_protocol


def prepare(engine, output, seeds, horizon, guidance):
    protocol = load_protocol()
    if seeds != protocol["training_maps"] or horizon != protocol["fixed_training"]["episode_horizon"]:
        raise ValueError("Recovery probes require the exact eight registered training resets")
    result = []
    for seed in seeds:
        root = output / str(seed)
        game = LiveV2(engine, root, seed=seed, decisions=horizon)
        try:
            observation = game.request("OBSERVE")["observation"]
            obs, candidates, rows, mask = checked_tensors(game.request("TENSORS"), observation)
            guide = PublicPlanGuide(observation, root, guidance=guidance)
            guided, _, info = guide.prepare(observation, candidates, rows, mask)
            proposal = next(row for row, value in rows.items() if value["stable_key"] == info["proposed_key"])
            result.append({"map_seed": seed, "observation": artifact(obs), "candidates": artifact(guided),
                           "reset": artifact(root / "reset.json"), "proposal_row": proposal})
            game.close(); game = None
        finally:
            if game is not None:
                game.abort()
    write_json(output / "manifest.json", {"protocol_sha256": PROTOCOL_SHA256, "inputs": result})
    return result


def probe(trainer, entries, update):
    # Validate retained tensors at use, so stale/corrupted probe caches cannot
    # silently decide a registered early stop.
    result = []
    for entry in entries:
        for key in ("observation", "candidates", "reset"):
            if artifact(Path(entry[key]["path"])) != entry[key]:
                raise ValueError("Training reset probe input changed")
        observed = trainer.request(f"PROBE\t{entry['observation']['path']}\t{entry['candidates']['path']}\t{entry['proposal_row']}")
        result.append({"map_seed": entry["map_seed"], **observed})
    return {"update": update, "maps": result}
