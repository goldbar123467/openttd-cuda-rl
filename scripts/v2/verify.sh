#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository_root="$(cd -- "$script_dir/../.." && pwd -P)"
tools_python="$(command -v python3)"

if (($#)); then
    if (($# != 2)) || [[ "$1" != "--tools-python" ]]; then
        echo "usage: $0 [--tools-python /absolute/path/to/python]" >&2
        exit 2
    fi
    tools_python="$2"
fi

[[ "$tools_python" = /* && -x "$tools_python" ]] || {
    echo "v2 verify: Python must be an executable absolute path" >&2
    exit 2
}

"$tools_python" "$repository_root/scripts/v2/validate_research_baseline.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_setting_inventory.py" \
    --root "$repository_root" \
    --object-repo "$repository_root/openttd-upstream"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_opponent_package_evidence.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_opponent_runtime_evidence.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_competition_manifest.py" \
    --root "$repository_root"

"$tools_python" "$repository_root/scripts/v2/validate_m15_scalable_contract.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m15_policy_contract.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m15_policy_evidence.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/run_m15_map_matrix.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m15_native_source.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m15_native_reset_evidence.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/run_m15_native_reset_matrix.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m15_observation_contract.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m15_observation_source.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/freeze_m15_observation_evidence.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m15_action_contract.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m15_action_source.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/freeze_m15_action_evidence.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m15_episode_source.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/freeze_m15_episode_evidence.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m15_cross_scale_replay_evidence.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m15_competence_source.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m15_competence_evidence.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m16_cargo_source.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m16_cargo_evidence.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m17_rail_source.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m17_rail_evidence.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m18_ship_source.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m18_shipai_evidence.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m18_ship_evidence.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m19_air_source.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m19_air_evidence.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m20_competition_source.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m20_competition_evidence.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m21_broad_source.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m21_broad_evidence.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m22_learning_contract.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m22_native_corpus.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" -c \
    'import pathlib,sys; import encode_m22_native_corpus as e; root=pathlib.Path(sys.argv[1]); data=e.encode(root); decoded=e.decode(data); print(f"V2_M22_CORPUS_BINARY=PASS entries={len(decoded.entries)} bytes={len(data)}")' \
    "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m22_recovery_evidence.py" \
    --root "$repository_root" \
    --report "$repository_root/config/v2/m22-recovery-evidence.json"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m22_recovery_evidence.py" \
    --root "$repository_root" \
    --report "$repository_root/config/v2/m22-recovery-evidence-v2.json"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" "$repository_root/scripts/v2/validate_m22_training_evidence.py" \
    --root "$repository_root" \
    --report "$repository_root/config/v2/m22-training-evidence.json"

"$tools_python" "$repository_root/scripts/v2/validate_traceability.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v2" \
    "$tools_python" -m unittest discover \
    -s "$repository_root/tests/project/v2" \
    -p 'test_*.py' \
    -v

"$repository_root/scripts/v1/traceability.sh" --tools-python "$tools_python"
