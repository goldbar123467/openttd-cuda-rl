#!/usr/bin/env python3
"""Prepare the existing V1 engine and six trainer-visible scenarios for development."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from local import ROOT, source_identity, write_json

sys.path.insert(0, str(ROOT / "scripts/v1"))
import generate_m02_scenario  # noqa: E402
from run_m12_release_gate import compose_m11_source  # noqa: E402


def prepare(output: Path) -> None:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    tree = compose_m11_source(ROOT, output / "source")
    contract, corpus, ledger = generate_m02_scenario.load_and_validate(
        ROOT / "config/v1/m02-scenario-contract.json",
        ROOT / "docs/project/schema/v1-m02-scenario-contract.schema.json",
        ROOT / "config/v1/m02-scenario-corpus.json",
        ROOT / "docs/project/schema/v1-m02-scenario-corpus.schema.json",
        ROOT / "config/v1/m02-seed-ledger.json",
        ROOT / "docs/project/schema/v1-m02-seed-ledger.schema.json",
    )
    templates = []
    for template in corpus["templates"]:
        if template["split"] not in {"training", "development"}:
            continue
        instance = generate_m02_scenario.build_instance(
            contract, corpus, ledger, template,
            ROOT / "docs/project/schema/v1-m02-scenario-instance.schema.json")
        generate_m02_scenario.write_new(output / "instances" / f"{template['template_id']}.json", instance)
        templates.append({"id": template["template_id"], "split": template["split"]})
    write_json(output / "development-engine.json",
               {"kind": "development-engine-source", "source": source_identity(),
                "composed_tree": tree, "templates": templates})
    print(f"Prepared existing V1 engine: {output / 'source'}")
    print(f"Generated training/development instances: {output / 'instances'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="new directory; existing outputs are preserved")
    args = parser.parse_args()
    prepare(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
