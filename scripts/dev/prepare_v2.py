#!/usr/bin/env python3
"""Compose the existing V2 native bus components in a separate development tree.

This prepares executable prerequisites for an interactive bridge. It does not
run corpus training, access evaluation manifests, or claim live V2 learning.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from local import ROOT, capture_source, positive, source_identity, write_json


STAGES = ("m15-native", "m15-observation", "m15-action", "m15-episode", "m15-competence")


def git(source, *arguments):
    return subprocess.check_output(["git", "-C", str(source), *arguments], text=True).strip()


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {"kind": "development-v2-native-composition", "status": "preparing",
              "source": source_identity(), "stages": [],
              "claim": "Existing native V2 components; not interactive learning or historical release reproduction"}
    write_json(output / "preparation.json", record)
    try:
        base = args.base_source.resolve()
        initial = json.loads((ROOT / "config/v2/m15-native-source.json").read_text())
        if git(base, "status", "--porcelain") or git(base, "rev-parse", "HEAD^{tree}") != initial["base"]["tree"]:
            raise ValueError("V2 preparation requires the pristine recorded V1 M11 source tree")
        source = output / "source"
        subprocess.run(["git", "clone", "--no-hardlinks", "--no-checkout", str(base), str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "checkout", "--detach", git(base, "rev-parse", "HEAD")], check=True)
        for name in STAGES[:STAGES.index(args.through) + 1]:
            config_path = ROOT / f"config/v2/{name}-source.json"
            config = json.loads(config_path.read_text())
            if git(source, "write-tree") != config["base"]["tree"]:
                raise ValueError(f"Recorded source boundary differs before {name}")
            if "patch_series" in config:
                series = config["patch_series"]
                patches = [(ROOT / series["directory"] / item["name"], item["sha256"]) for item in series["patches"]]
                if hashlib.sha256((ROOT / series["series"]).read_bytes()).hexdigest() != series["series_sha256"]:
                    raise ValueError("V2 patch series identity differs")
            else:
                patches = [(ROOT / config["patch"]["path"], config["patch"]["sha256"])]
            for patch, expected in patches:
                if hashlib.sha256(patch.read_bytes()).hexdigest() != expected:
                    raise ValueError(f"Frozen patch identity differs: {patch}")
                subprocess.run(["git", "-C", str(source), "apply", "--check", "--whitespace=error-all", str(patch)], check=True)
                subprocess.run(["git", "-C", str(source), "apply", "--index", "--whitespace=error-all", str(patch)], check=True)
            actual_tree = git(source, "write-tree")
            if actual_tree != config["result"]["tree"]:
                raise ValueError(f"Composed source differs from recorded result: {name}")
            record["stages"].append({"name": name, "tree": actual_tree,
                                     "configuration_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest()})
            write_json(output / "preparation.json", record)
        (output / "composition.patch").write_bytes(subprocess.check_output(["git", "diff", "--cached", "--binary"], cwd=source))
        capture_source(output / "preparation-source")
        record["status"] = "prepared"
        if args.build:
            build = output / "build"
            command = ["cmake", "-S", str(source), "-B", str(build), "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                       "-DOPTION_RL_ENVIRONMENT=ON", "-DOPTION_RL_NEURAL_AGENT=OFF", "-DOPTION_USE_ASSERTS=ON",
                       "-DOPTION_DEDICATED=ON", "-DPERSONAL_DIR=.openttd-rl-v2-development"]
            record["configure"] = command
            write_json(output / "preparation.json", record)
            subprocess.run(command, check=True)
            subprocess.run(["cmake", "--build", str(build), "--parallel", str(args.jobs)], check=True)
            baseset = args.baseset.resolve()
            if hashlib.sha256(baseset.read_bytes()).hexdigest() != "9389bcb0807058c80bd95121e978f05d9ef86b4b1bc3ac2da8da8bb02456043c":
                raise ValueError("OpenGFX 8.0 archive differs")
            (build / "baseset").mkdir(exist_ok=True)
            shutil.copyfile(baseset, build / "baseset/opengfx-8.0.tar")
            record.update(status="built", executable_sha256=hashlib.sha256((build / "openttd").read_bytes()).hexdigest())
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(output / "preparation.json", record)
    print(f"V2 native development source: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--through", choices=STAGES, default="m15-competence")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--baseset", type=Path)
    parser.add_argument("--jobs", type=positive, default=2)
    args = parser.parse_args()
    if args.build and args.baseset is None:
        parser.error("--build requires --baseset")
    run(args)
