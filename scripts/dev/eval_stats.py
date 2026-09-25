"""Paired development statistics with training seed as the outer sampling unit."""
import math
import random
import statistics


def pair_episodes(policies, controls, metric):
    """Pair controls reusable across training seeds by exact map/action-seed key.

    Callers verify guide, engine, budget and source identity before passing rows.
    Each policy row has training_seed, map_seed, action_seed and numeric metrics;
    control rows omit training_seed. Missing and duplicate pairs fail closed.
    """
    reference = {}
    for row in controls:
        key = row["map_seed"], row["action_seed"]
        if key in reference:
            raise ValueError("Duplicate control pair")
        if not math.isfinite(row[metric]):
            raise ValueError("Nonfinite control outcome")
        reference[key] = row[metric]
    seen, result, required = set(), [], set()
    for row in policies:
        key = row["map_seed"], row["action_seed"]
        identity = row["training_seed"], *key
        if identity in seen or key not in reference:
            raise ValueError("Duplicate policy or missing matched control")
        if not math.isfinite(row[metric]):
            raise ValueError("Nonfinite policy outcome")
        seen.add(identity)
        required.add(key)
        result.append({"training_seed": row["training_seed"], "map_seed": key[0], "action_seed": key[1],
                       "difference": row[metric] - reference[key]})
    if not result or required != set(reference):
        raise ValueError("Empty comparison or unmatched extra controls")
    return sorted(result, key=lambda r: (r["training_seed"], r["map_seed"], r["action_seed"]))


def quantile(values, probability):
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lo, hi = math.floor(position), math.ceil(position)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def nested_bootstrap(rows, *, iterations=10000, seed=20260925):
    """Percentile interval: training seeds, then maps, then paired action seeds.

    Greedy runs belong in a separate call with one action seed per map. Equal
    weight is given to each training seed and map. This descriptive bootstrap
    does not turn three trained models into a well-powered confirmation study.
    """
    if not isinstance(iterations, int) or isinstance(iterations, bool) or iterations < 100:
        raise ValueError("Use at least 100 bootstrap iterations")
    groups = {}
    identities = set()
    for row in rows:
        identity = row["training_seed"], row["map_seed"], row["action_seed"]
        if identity in identities or not math.isfinite(row["difference"]):
            raise ValueError("Duplicate pair or nonfinite difference")
        identities.add(identity)
        groups.setdefault(identity[0], {}).setdefault(identity[1], {})[identity[2]] = row["difference"]
    if not groups:
        raise ValueError("Empty paired bootstrap")
    training_seeds = sorted(groups)
    maps = sorted(groups[training_seeds[0]])
    actions = sorted(groups[training_seeds[0]][maps[0]])
    if any(sorted(group) != maps or any(sorted(values) != actions for values in group.values()) for group in groups.values()):
        raise ValueError("Incomplete training/map/action matrix")
    means = {s: statistics.mean(statistics.mean(groups[s][m].values()) for m in maps) for s in training_seeds}
    map_means = {m: statistics.mean(statistics.mean(groups[s][m].values()) for s in training_seeds) for m in maps}
    rng = random.Random(seed)
    samples = []
    for _ in range(iterations):
        sampled_seeds = []
        for _ in training_seeds:
            s = rng.choice(training_seeds)
            sampled_maps = []
            for _ in maps:
                m = rng.choice(maps)
                sampled_maps.append(statistics.mean(groups[s][m][rng.choice(actions)] for _ in actions))
            sampled_seeds.append(statistics.mean(sampled_maps))
        samples.append(statistics.mean(sampled_seeds))
    return {"mean": statistics.mean(means.values()), "per_training_seed": means, "per_map": map_means,
            "training_seed_sign_counts": {"positive": sum(v > 0 for v in means.values()),
                                          "zero": sum(v == 0 for v in means.values()),
                                          "negative": sum(v < 0 for v in means.values())},
            "nested_percentile_95_interval": [quantile(samples, .025), quantile(samples, .975)],
            "training_seeds": len(training_seeds), "maps_per_training_seed": len(maps),
            "action_seeds_per_map": len(actions), "iterations": iterations, "bootstrap_seed": seed,
            "claim": "Descriptive nested uncertainty; action seeds are not independent trained models"}
