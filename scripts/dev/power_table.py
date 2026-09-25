"""Descriptive paired variance and explicitly conditional study-size projections."""
import argparse
import json
import math
from pathlib import Path
import statistics

from local import capture_source, source_identity, write_json
from studies.evidence_v2 import Inputs

T95 = {3: 4.302652729911275, 5: 2.7764451051977987}


def t_power(delta, n, *, steps=4096):
    """Two-sided noncentral-t power by integrating over sqrt(chi-square/df).

    T=(Z+delta)/S; independent standard-normal Z and S=sqrt(V/df).
    Composite Simpson integration on [0,12]; omitted chi-square tails are
    negligible for the supported df=2 and df=4. No fitted distribution library.
    """
    df = n - 1
    critical = T95[n]
    constant = 2 * (df / 2) ** (df / 2) / math.gamma(df / 2)
    h, total = 12 / steps, 0.
    for i in range(steps + 1):
        s = i * h
        rejection = .5 * (math.erfc((critical * s + delta) / math.sqrt(2)) + math.erfc((critical * s - delta) / math.sqrt(2)))
        value = rejection * constant * s ** (df - 1) * math.exp(-df * s * s / 2)
        total += value * (1 if i in (0, steps) else 4 if i % 2 else 2)
    return total * h / 3


def detectable_multiplier(n):
    lo, hi = 0., 32.
    for _ in range(40):
        mid = (lo + hi) / 2
        if t_power(mid, n) < .8:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def variance_components(rows):
    groups = {}
    for r in rows:
        key = r["training_seed"], r["map_seed"], r["action_seed"]
        values = groups.setdefault(key[0], {}).setdefault(key[1], {})
        if key[2] in values or not math.isfinite(r["difference"]):
            raise ValueError("Duplicate or nonfinite paired observation")
        values[key[2]] = r["difference"]
    seeds = sorted(groups)
    if len(seeds) < 2:
        raise ValueError("Cannot estimate training-seed variance from one trained model")
    maps = sorted(groups[seeds[0]])
    actions = sorted(groups[seeds[0]][maps[0]])
    n, m, a = len(seeds), len(maps), len(actions)
    if m < 2 or a < 2 or any(sorted(g) != maps or any(sorted(v) != actions for v in g.values()) for g in groups.values()):
        raise ValueError("Variance projection needs a balanced matrix with at least two maps and action seeds")
    map_means = {(s, k): statistics.mean(groups[s][k].values()) for s in seeds for k in maps}
    seed_means = {s: statistics.mean(map_means[s, k] for k in maps) for s in seeds}
    center = statistics.mean(seed_means.values())
    ms_action = sum((value - map_means[s, k]) ** 2 for s in seeds for k in maps for value in groups[s][k].values()) / (n * m * (a - 1))
    ms_map = a * sum((map_means[s, k] - seed_means[s]) ** 2 for s in seeds for k in maps) / (n * (m - 1))
    ms_seed = m * a * sum((seed_means[s] - center) ** 2 for s in seeds) / (n - 1)
    raw = {"training_seed": (ms_seed - ms_map) / (m * a), "map_within_seed": (ms_map - ms_action) / a, "action_within_map": ms_action}
    return {"observed_training_seeds": n, "observed_maps": m, "observed_action_seeds": a,
            "paired_mean": center, "paired_training_seed_sd": statistics.stdev(seed_means.values()),
            "raw_variance_components": raw, "nonnegative_planning_components": {k: max(0., v) for k, v in raw.items()},
            "negative_component_estimates": [k for k, v in raw.items() if v < 0]}


def project(rows, multipliers):
    result = variance_components(rows)
    n = result["observed_training_seeds"]
    result["observed_conditional_t_half_width_95"] = T95[n] * result["paired_training_seed_sd"] / math.sqrt(n) if n in T95 else None
    v = result["nonnegative_planning_components"]
    result["planning_table"] = []
    for seeds in (3, 5):
        for maps in (2, 8):
            se = math.sqrt((v["training_seed"] + v["map_within_seed"] / maps + v["action_within_map"] / (maps * 3)) / seeds)
            result["planning_table"].append({"training_seeds": seeds, "maps": maps, "action_seeds": 3,
                "episodes_per_controller": seeds * maps * 3, "projected_standard_error": se,
                "projected_t_half_width_95": T95[seeds] * se,
                "projected_minimum_absolute_difference_80_percent_power": multipliers[seeds] * se})
    return result


def render(report):
    lines = ["# Paired study-size planning", "", report["claim"], "", *["- " + s for s in report["assumptions"]], "",
             "| Metric | Training seeds | Maps | Actions per map | Episodes per controller | Projected 95% half-width | Projected 80% detectable difference |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for metric, result in report["metrics"].items():
        for row in result["planning_table"]:
            lines.append(f"| {metric} | {row['training_seeds']} | {row['maps']} | 3 | {row['episodes_per_controller']} | "
                         f"{row['projected_t_half_width_95']:.2f} | {row['projected_minimum_absolute_difference_80_percent_power']:.2f} |")
    lines += ["", "All figures retain their native outcome units. No acceptance threshold is derived from this table.",
              "Original t-width reproduction, raw and truncated variance estimates, and input hashes are in power.json."]
    return "\n".join(lines) + "\n"


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    capture_source(root / "source")
    inputs = Inputs()
    report = {"status": "running", "source": source_identity(), "metrics": {},
              "claim": "Planning projections from retained V1 paired contrasts, not measured V2 power or a new acceptance threshold.",
              "assumptions": ["Seed/map/action random-effects hierarchy; variance estimates treated as known for projected noncentral-t power.",
                              "Two observed maps give weak variance information. Eight-map rows extrapolate the same population, not observed precision.",
                              "Negative variance-component estimates are shown and truncated at zero only for planning; n=3 is imprecise.",
                              "Action seeds remain repeated games. Shared fixed maps and controls may induce dependencies this hierarchy cannot identify.",
                              "V2 has no matched three-training-seed recovery sample yet; V1 estimates must not be represented as V2 power."]}
    try:
        comparison = inputs.json(args.comparison)
        for path, expected in comparison["inputs_sha256"].items():
            inputs.read(path)
            if inputs.sha256[str(Path(path).resolve())] != expected:
                raise ValueError("Retained paired report input changed: " + path)
        paired = comparison["hierarchical_paired_differences"]["sampled"]["metrics"]
        multipliers = {n: detectable_multiplier(n) for n in T95}
        for metric, data in paired.items():
            result = project(data["episode_differences"], multipliers)
            previous = comparison.get("paired_training_seed_differences", {}).get("sampled", {}).get(metric)
            if previous:
                lower, upper = previous["conditional_t_interval_95"]
                error = abs((upper - lower) / 2 - result["observed_conditional_t_half_width_95"])
                if error > 1e-9:
                    raise ValueError("Power inputs do not reproduce retained t-interval width")
                result["historical_t_half_width_error"] = error
            report["metrics"][metric] = result
        inputs.unchanged()
        report.update(status="passed", noncentral_t_delta_for_80_percent_power=multipliers)
    except BaseException as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        report["inputs_sha256"] = inputs.sha256
        write_json(root / "power.json", report)
    (root / "power.md").write_text(render(report))
    print(json.dumps({"status": report["status"], "metrics": list(report["metrics"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True, help="V1 report including hash-verified paired episode differences")
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
