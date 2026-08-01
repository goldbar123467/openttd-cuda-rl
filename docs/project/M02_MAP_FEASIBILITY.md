# M02 conditional 32 by 32 map feasibility

## Result and claim boundary

The conditional engine-feasibility slice of `M02` passes. OpenTTD 15.3 can
create, save, reload, and soak a true empty 32 by 32 editor map when the
default-off `OPTION_RL_ENVIRONMENT` build option is enabled. With the option
disabled, the ordinary 64-tile minimum and the accepted M01 64 by 64 map
behavior remain unchanged.

This feasibility slice alone was not a `G02` pass. The later passenger-bus
scenario, controlled reset, and scripted native acceptance trajectory now pass
separately in [`M02_SCENARIO_RESET_CONTRACT.md`](M02_SCENARIO_RESET_CONTRACT.md)
and [`G02_GATE_REPORT.md`](G02_GATE_REPORT.md). No RL bridge,
observation/action/reward implementation, PPO trainer, CUDA learning workload,
ONNX production policy, or in-game neural agent exists yet.

## Frozen inputs and source identity

| Input | Accepted identity |
|---|---|
| OpenTTD source | commit `14ec60f248547d4d062a1160f0fc26d742319888` |
| Accepted M01 prepared tree | `c63a866377547631870efb48ac547948da19916a` |
| M02 patch | `8c4c9f8511c4eea96d5ef1d2ca23a68a673c75692972243d8ddb11d91b28207f` |
| M02 prepared tree | `eba8f4bd3c37042c184d968d2f038864184e3132` |
| Composed source identity | `2140e34ccee8534dbf712487acd2225eda4b66d1c807b9e0ce07243ba40afdbd` |
| Feasibility plan | `344bae1f25a394700667e38d2cee1e4409ee322218165cb01ce9884327b3da79` |
| Offline build lock | 34 archives; `099675da5a508cd5a58405767e7713f5dbbc810b7dae52e6fc2687341bbc6985` |

The M02 patch is isolated under `integration/openttd/patches/15.3/m02/`; the
accepted M01 profile, root series, and GCC portability patch remain byte
unchanged. The conditional delta covers the audited minimum-map-size
dependencies, deterministic terrain generation, save/load chunk sizing,
viewport bounds, and related unit coverage. It also contains two narrow
whole-program sanitizer corrections discovered by the mandatory matrix:

- release the engine pool repopulated by `ResetNewGRFData()` during RL-enabled
  process shutdown, fixing an ASan/LSan leak of 256 engine entries; and
- declare integer-valued `ScriptDate::Date` with its existing fixed 32-bit ABI,
  so valid day counts are within the compiler-visible enum range under UBSan.

## Executed matrix

Both accepted runs built every profile cleanly with GCC/G++ 13.3.0, CMake/CTest
3.28.3, and Ninja 1.11.1. Strict warnings remained fatal.

| Profile | Flag | Sanitizer | Unit result | Native regressions |
|---|---:|---|---:|---|
| `rl-off-assert` | off | none | 96 cases / 2,183 assertions | 2/2 pass |
| `rl-on-assert` | on | none | 96 cases / 2,193 assertions | 2/2 pass |
| `rl-on-asan` | on | ASan + leak detection | 96 cases / 2,193 assertions | 2/2 pass |
| `rl-on-ubsan` | on | fail-fast UBSan | 96 cases / 2,193 assertions | 2/2 pass |

Each profile generated a normal 64 by 64 map whose serialized map chunks equal
the accepted M01 reference byte for byte. The common map hash is
`240f8c1c92731f16e445d0ff7ed097a61b2dd88ce3438e764829a90339b8be77`.

The flag-off profile requested 32 by 32 and correctly remained 64 by 64. Every
flag-on profile produced two byte-identical true-empty saves with exactly 900
clear and 124 void tiles. Their canonical map hash is
`7d342e9d3808f180f14ba1c196f9c68d967ed17ea80bdddc0dba47bdc957a003`.
Each flag-on profile then reloaded and soaked that map for 4,194,304 ticks and
ran a generated 32 by 32 map for 65,536 ticks using seed `123456789`.

## Reproducibility evidence

The accepted independent roots are:

```text
/home/thecl/.codex/artifacts/openttd-rl/m02-map-feasibility-20260801-n
/home/thecl/.codex/artifacts/openttd-rl/m02-map-feasibility-20260801-o
```

Both report identity
`5ccf48b693ea4dc2ea0a2143655f1b3dd0e274b6cd84be9bacc7bad7ea884841`.
The authoritative comparison is:

```text
/home/thecl/.codex/artifacts/openttd-rl/m02-map-feasibility-comparison-20260801-b.json
```

It passes with comparison identity
`249ed176c3720f00d41be1504999e35f83ef658dbb2081858126bcbb92382e6c`.
The following canonical files are byte-identical:

| File | SHA-256 |
|---|---|
| `map-feasibility-report.json` | `4680ed83e58f0243639222c3ab3ef718ef50b6a4fd3bcab350f65015ccfd6bc0` |
| `map-feasibility-report.txt` | `b44e077953cd59dbcf51e2c0426dcc0fbdf9179390dbf3df12fd07e148efe83c` |
| `composed-source.json` | `1508aa68432106db4126ac41e069f43c33bdb7890156c1f7b0c65d763ce7b880` |
| `commands.json` | `bec85b794b6de0a494c531b72e2aade2f22326fc3dfe04539bd00a34ebe8b5d0` |

All eight built executables also match across the two roots. Their accepted
hashes, in profile order, are:

| Profile | `openttd` | `openttd_test` |
|---|---|---|
| `rl-off-assert` | `922cb36d81a631aa468964fb30d866ab1c1abf33a8e0857b10a3803f508e4d57` | `8efc54c61f5936631e9de721e9a89af3bf1dc93c2827a2295326c443d40218a1` |
| `rl-on-assert` | `7b0010846704585b36d455b77376b0b20f4fdb6043c2ed9c66c97bf4351099ad` | `ad9a9a306b19e08e2e599d6377ef4a34fad99afaa47b4eeff982c1d9329f8a1d` |
| `rl-on-asan` | `0124ea96ba52001c611ff928d5f702d5118ac0a7c0a60c0e278a94ec22596c17` | `916235dd29373b99ea4752028b96bcbc7219849c22eec0ea7805c466e5f4decc` |
| `rl-on-ubsan` | `993ea46662edd2d5219ab0900a227ac5a8ec4b9ba7c44b524cc686cbb3c4b965` | `43c5ab4458903f8af5e5180f06f63bfa57586a48a9d66b7dcac61eb3d6343348` |

The runner uses a stable, fail-closed physical workspace for source, build, and
sysroot paths because GCC sanitizer metadata retains input filenames even when
prefix-map flags are present. ELF RPATH/RUNPATH is disabled; validated runtime
library paths are supplied explicitly. Accepted products contain no accepted-run
root path. Build directories are removed after each passing profile, and the
workspace is moved into the failed artifact root if a run stops early.

OpenTTD normal-game saves intentionally carry a unique session ID. Raw normal
save containers are therefore noncanonical evidence; reproducibility is decided
from all serialized map chunks. Empty-editor repetitions are additionally
required to be whole-file byte-identical.

## Automated verification

Repository-level coverage is in
`tests/project/traceability/test_v1_m02_map_feasibility.py`. It validates strict
schemas, immutable M01 identities, exact patch application/tree identity, patch
scope, maximal LFSR periods, save parsing, true-empty semantics, diagnostic
fail-closed behavior, canonical workspace preservation, and comparison drift.

The final repository gate must include:

```bash
./scripts/v1/traceability.sh --tools-python /usr/bin/python3
git diff --check
```

## Manual QA

Review the accepted human report and machine report first:

```bash
sed -n '1,160p' /home/thecl/.codex/artifacts/openttd-rl/m02-map-feasibility-20260801-n/map-feasibility-report.txt
python3 -m json.tool /home/thecl/.codex/artifacts/openttd-rl/m02-map-feasibility-20260801-n/map-feasibility-report.json
python3 -m json.tool /home/thecl/.codex/artifacts/openttd-rl/m02-map-feasibility-comparison-20260801-b.json
```

To visually inspect the accepted empty map without mutating evidence, copy its
runtime directory to a disposable location and launch the assertion build from a
desktop session:

```bash
m02_qa_root=$(mktemp -d)
cp -a /home/thecl/.codex/artifacts/openttd-rl/m02-map-feasibility-20260801-n/profiles/rl-on-assert/runtime-empty32-1/. "$m02_qa_root/"
cd "$m02_qa_root"
env LD_LIBRARY_PATH=/home/thecl/.codex/artifacts/openttd-rl/m02-map-feasibility-20260801-n/sysroot/usr/lib/x86_64-linux-gnu:/home/thecl/.codex/artifacts/openttd-rl/m02-map-feasibility-20260801-n/sysroot/usr/lib/x86_64-linux-gnu/pulseaudio:/home/thecl/.codex/artifacts/openttd-rl/m02-map-feasibility-20260801-n/sysroot/lib/x86_64-linux-gnu \
  /home/thecl/.codex/artifacts/openttd-rl/m02-map-feasibility-20260801-n/products/rl-on-assert/openttd \
  -e -g "$m02_qa_root/save/rl-on-assert-empty32-1.sav" -s null -m null -b null -I OpenGFX
```

Confirm that the scenario editor opens a 32 by 32 temperate map with a one-tile
void border and a 30 by 30 clear interior. Do not treat a successful visual load
as a substitute for the automated tile counts, save hashes, sanitizer runs, or
independent comparison.

## Next allowed work

The work that followed this feasibility checkpoint is now accepted: the frozen
contract, eight-template corpus, disjoint seed ledger, semantic initial-state
projection, forbidden-scope validator, repeated clean/same-process resets, and
scripted passenger-bus acceptance trajectory close G02. Preserve this document
as the narrower feasibility evidence. M03 is the next milestone; PPO remains
downstream.
