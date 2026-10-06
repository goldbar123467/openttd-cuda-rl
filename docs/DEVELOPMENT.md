# Local training and the path to agentic economies

## Ten-game training and saved benchmark (October 5)

All ten human games are preserved and pass native replay and partition-appropriate
input checks. Games 01–07 supply 186 training choices; game 08 supplies 34 development
choices; games 09–10 supply 64 test choices. Training remains separate from evaluation.
Runtime evidence is under `/home/imsa/.local/share/openttd-rl/runs/human-ten-game-training-20261005-01/`.

The unchanged C++/LibTorch trainer completed 256 CUDA updates at learning rate
0.0003 and seed 20261002 in 2,976.5 seconds. The selected final archive is
`seven-game-256/inference-weights.pt`, SHA-256
`05d306e26a6b3b71e0a33df7630e06b9fdb8993aa880135acfa585cbfb7f854d`.
Training NLL falls from 4.666104 to 1.228980; unique exact fit is 128/186.
Gradients are finite, masks exact, target aliases and ties zero. Reload error is
zero and CPU/CUDA maximum probability error is 3.13e-7. There are no PPO updates.

| Frozen policy | Updates / training choices | Development game 08 | Test games 09–10 | Test excluding repayments |
| --- | --- | --- | --- | --- |
| Original one-game model | 1,000 / 12 | 8/34 | 18/64 | 18/44 |
| Equal-update one-game control | 256 / 12 | 5/34 | 14/64 | 14/44 |
| Four-game model | 256 / 79 | 12/34 | 19/64 | 19/44 |
| Seven-game model | 256 / 186 | 18/34 | 41/64 | 21/44 |

Twenty of the 22 additional correct test choices relative to the four-game model
are repayments. These are two test recordings, not 64 independent games.
The training set contains 43 inserts, 43 Full load any changes, 32 repayments,
29 starts, 25 purchases, seven copies, five deletions and two other load changes.
The new model fits inserts 6/43, copies 0/7 and repayments 32/32.

The owner's requested independent insertion audit covers every one of the 43
training targets: no aliases, 43/43 targets present and aligned, and no semantic
choice changes after row permutation (maximum probability error 1.19e-7).
Errors are 11 wrong stations with correct vehicle/position, 12 wrong target
vehicles and 14 wrong action/order primitives. Six are exact; there are no
position-only errors when the correct bus and station are selected. All eleven
wrong-station pairs differ only in encoded station ID slot 28. The candidate
vectors provide vehicle position, not target-station geometry/demand; station and
vehicle context is pooled once for every candidate. Weak entity binding is a
hypothesis, not proof of an input-information ceiling.

Uniform guessing over insertion candidates with an oracle primitive hint averages
6.39%, versus 13.95% actual exact fit. Copy guessing averages 32.97%; repayments
50%. The unrestricted full-mask baseline is approximately 0.04% per choice. The
hinted baseline knows the correct family/order primitive, not loan direction;
average reciprocal candidate counts must not be replaced by reciprocal mean counts.
See `choice-diagnostics/` and `insertion-structure/` in the experiment root.

The isolated 43-insertion CUDA diagnostic fits 12/43 after 256 updates, loss
1.509522, with native masks/numerics and shuffled-row checks passing. A fresh
1,000-update diagnostic completes at 21/43, loss 1.143390, selected from training
diagnostics only. Both trials clear native mask/numerical and row-permutation
checks. More optimization and isolating the class help, but still do not memorize
these examples. Representation or optimization remains unresolved; this is not
proof of an absolute information ceiling or a label bug.
Neither diagnostic supplies test labels to the optimizer or replaces a benchmark
actor. Use `train_insertion_diagnostic_v2.py` to reproduce those bounded fits.

The saved benchmark is complete: four frozen neural actors plus one script,
50 attempted episodes each. All 250 outcomes have native final saves: 247 full
budgets and three explicit order-interface failures. The frozen
`fifty-game-protocol.json` binds models,
engine and 25 initial saves. Each world runs greedy and sampled modes at 512
decisions × 128 ticks. Eight distinct development map seeds recur across 64×64,
128×128 and rectangular maps; there are not 50 independent maps. Two stops, a
depot and scripted road infrastructure are supplied; no buses are supplied and
construction learning is not claimed. The script buys one bus, configures two
Full load any orders and repays 10,000 when balance is at least 20,000.

| Frozen actor | Delivering attempts (greedy / sampled; each out of 25) | Mean operating profit (all 50) | Sustained profitable service | Interface failures |
| --- | --- | --- | --- | --- |
| one-game-1000 | 1 / 4 | -18,744.46 | 0/50 | 1 |
| one-game-256 | 0 / 22 | -10,256.58 | 0/50 | 0 |
| four-game-256 | 3 / 22 | -26,342.34 | 0/50 | 2 |
| seven-game-256 | 0 / 24 | -9,484.70 | 0/50 | 0 |
| scripted-one-bus-repay | 24 / 24 | +3,623.16 | 44/50 | 0 |

The new model improves mean operating profit by 17,202.58 relative to the
four-game model at matched horizons (95% map-seed cluster interval
[16,432.62, 17,843.92]), but remains 13,107.86 below the script
([-14,258.04, -12,069.79] for new minus script). It delivers more passengers
on average than the four-game model but does not achieve sustained profitability.
Its sampled fleet averages 18.32 buses. Greedy service remains absent.
The independent verifier recomputes all 250 native ledgers, 127,427 decisions and
16,310,656 ticks; every reset engine hash and final save hash matches.
Zero invalid actions and bankruptcies do not imply successful service.
The full report, figures, CSVs, model archives, human input evidence and 250 final
saves are exported under `%LOCALAPPDATA%/OpenTTD-RL/analysis/human-ten-game-training-20261005-01/`.

All attempted cases remain in the results, including unsupported order-state
failures. Native `orders-v1` rejects noncanonical lists such as dummy orders after
station removal. Capture these as explicit interface terminations with partial
budgets and final saves; never change masks/features/weights to manufacture
completion. The three captures reproduce all 395, 329 and 239 original
transitions/choices, save the same boundaries and pass native reloads. Financial paired
comparisons use the minimum common simulated horizon when a case ends early.
Saving consumes no action/ticks and pending actions reject CHECKPOINT. Preserve
the original failed attempts and interrupted sequential jobs.

`run_bus_orders_benchmark_v2.py` runs independent native cases with up to eight
process workers and hash-validates reused complete cases. After all attempts,
`summarize_bus_benchmark_v2.py` recomputes native accounting and exports episode,
operation and paired tables with uncertainty clustered by the eight map seeds.
`write_bus_benchmark_report_v2.py`, `plot_bus_benchmark_v2.py` and
`export_bus_benchmark_evidence.ps1` produce the portable report, scientific figures,
model archives and all 250 final saved games. Complete source/tensor/transition
evidence remains in the runtime; none belongs in Git.

Comparison commands require a completed batch, including explicit saved interface
terminations rather than silently dropping failed cases. Reuse binds each worker's
engine checksum and the originating actor's protocol/reader provenance. Offline
model/run/reader identities must match the frozen gameplay actors. The exporter
rejects a truncated or repeated case CSV, changed protocols and plots generated
from another results file.

```bash
experiment_root=/home/imsa/.local/share/openttd-rl/runs/human-ten-game-training-20261005-01
python3 scripts/dev/summarize_bus_benchmark_v2.py \
  --protocol "$experiment_root/fifty-game-protocol.json" \
  --offline "$experiment_root/offline-comparison-02/report.json" \
  --batch "$experiment_root/gameplay-batch-02/report.json" \
  --choice-diagnostics "$experiment_root/choice-diagnostics/report.json" \
  --insertion-structure "$experiment_root/insertion-structure/report.json" \
  --insertion-run "$experiment_root/insertions-only-256/run.json" \
  --insertion-run "$experiment_root/insertions-only-1000/run.json" \
  --output "$experiment_root/comparison-evidence-01"
python3 scripts/dev/write_bus_benchmark_report_v2.py \
  --results "$experiment_root/comparison-evidence-01/results.json" \
  --output "$experiment_root/comparison-evidence-01/report.md"
```

Use a fresh output directory when reproducing; finished reports never overwrite
earlier attempts. Render figures from `results.json` before exporting the Windows
package. The final inventory records every owned experiment file, including the
preserved failures and exact native input archives.

## Ten human games: current collection plan (October 5)

The owner selected passenger buses and money management for a ten-game human
dataset experiment. [The collection plan](HUMAN_DATASET_10_GAMES.md) proposes
seven training games, one development game and two held-out games. The owner
wants ten consecutive fresh recorder sessions, followed by native replay/import
audits and dataset preparation. Each game has two passenger routes, with extra
buses when service and demand justify them.
Explicit WAIT capture remains a tooling gap;
ordinary command silence cannot teach waiting. Qualify those boundaries before
exporting affected labels and training. This direction supersedes the earlier collection
deferral while preserving the October 2 recordings and results below.

Game 01 completed raw recording on October 5 in session
`20261005-100753-human-7a080369` (seed 1268495509). All 14 allowlisted capture files,
including five saves, match the preserved-copy hashes. The final manual save is
`Garfingburg Transport, 1954-01-07.sav`, marker 44. All 11 native checks pass and
31 commands replay successfully, providing 18 exact choices: three purchases,
six inserts, six Full load any changes and three starts. Twenty records are
excluded. The checkpoint has three running buses on two routes, cash 103,186 and
loan 100,000. Replay is `runs/human-campaign-20261005/game-01/replay-manual/`.

At the owner's request, game 02 was checked before game 03. Session
`20261005-101658-human-2eeb36f1` (seed 212758682) passes all 11 native equality and
accounting checks against `Brunston Transport, 1954-08-23.sav`, marker 48. The
training-data consumer accepts 24 exact examples: four purchases, eight inserts,
eight Full load any changes and four starts. Four buses are running on two routes
at the checkpoint; cash is 100,745 and loan remains 100,000. Eighteen records are
excluded, and no new model training ran. WSL reports/dataset are in
`runs/human-campaign-20261005/game-02/` under the local runtime root; the Windows
verification report is in `%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-02/`.

Game 03, session `20261005-113936-human-24383522` (seed 476793754), also passes all
11 native checks against `Ginthill Transport, 1956-03-08.sav`, marker 56. All 14
capture files are preserved. Its 22 exact choices include four purchases, five
inserts, four Full load any changes, two independent copies, one deletion, four
starts and two 10,000 repayments. The checkpoint confirms two depots, two disjoint
routes and two running buses per route; cash is 101,020 and debt is 80,000.
Twenty-eight records are excluded. The human's explanation of avoiding the
isolated largest town is attached separately to the campaign ledger.

Game 03 exposed an internal link-graph pause during native order-state restoration.
The replay loop now permits only that pause, optionally with `CommandDuringPause`,
so upstream `StateGameLoop` can poll and release it. Human/control pauses still
fail when the next event needs time; no pause is forcibly cleared. The original
engine and both failed attempts remain intact. The repaired isolated engine is
`/home/imsa/.local/share/openttd-rl/human-orders-replay-engine-20261005-linkgraph/`;
its preparation and refresh records bind source and binary hashes. Three native
pause controls pass, and game 02 still matches its checkpoint with 24 labels.
Game 03's successful replay is `replay-manual-linkgraph-v2/` under
`runs/human-campaign-20261005/game-03/` in the runtime root. The existing consumer
accepts all 22 examples with `signed-log-orders-v2`; no model was fitted. The
Windows verification report is in
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-03/verification.md`.
The campaign assembler now validates all four recordings together.

Game 04, session `20261005-123821-human-71704373` (seed 392546014), passes all 11
checks against `Plontford Transport, 1952-10-26.sav`, marker 43. The consumer
accepts 15 choices: three purchases, four inserts, four Full load any changes,
one independent copy and three starts. The checkpoint confirms one depot and
two routes sharing station 1: two buses on 0/1, one on 1/2, all running. Cash is
100,890 and debt remains 100,000. Twenty-two records are excluded; no WAIT or
finance labels are inferred. The owner's nearby-major-towns rationale is attached
separately. Reports/dataset are in the runtime's
`runs/human-campaign-20261005/game-04/`; the Windows report is
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-04/verification.md`.
All four games now provide 79 verified examples.

Game 05, session `20261005-152914-human-b8b97f37` (seed 2057442348), passes all
11 native checks against `Kinborough Transport, 1967-02-10.sav`, marker 69.
All 53 replayed commands succeed. Seventeen capture files, including eight saves,
and the 18-file runtime transfer are hash-verified. The consumer accepts 39
choices: five purchases, five inserts, five Full load any changes, six starts,
four independent copies, three deletions, one loading-mode-0 change and ten
10,000 repayments. Twenty-one records are excluded, including one vehicle clone
that replayed successfully but has no exact policy action. No WAIT is inferred.

The saved game has three stops, one depot and six running buses: four on 0/1 and
two on 0/2, all using independent two-order lists. One endpoint on bus 5 uses
loading mode 0; the other eleven use Full load any. Cash is 110,424 and debt zero.
The ten repayments each match -10,000 cash/principal with zero command cost.
The owner's selection of two largest cities and two stops in the largest is
preserved as an annotation. Initial populations rank towns 4 and 0 first; stops
1/2 are nearest town 4's public center and stop 0 is nearest town 0. This is
consistent geometry, not a direct station-town lookup or inferred selection label.

Game 05's replay and consumer are under `runs/human-campaign-20261005/game-05/`.
Its Windows report is
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-05/verification.md`.
The training-only assembler passes with 118 choices across five games at
`runs/human-campaign-20261005/datasets/train-games-01-05/`. This adds no new model
training or PPO updates; the four-game pilot below remains unchanged.

Game 06, session `20261005-154603-human-5745f1c6` (seed 2020301813), passes all
11 native checks against `Trendhattan Ridge Transport, 1972-05-06.sav`, marker 65.
All 49 replayed commands succeed. Seventeen capture files, including eight saves,
and the 18-file runtime transfer match hashes. The consumer accepts 39 choices:
four purchases, nine inserts, ten Full load any changes, four starts, one deletion,
one loading-mode-4 change and ten 10,000 repayments. Seventeen records are excluded.

At log lines 49–54, native vehicle 5 changes from stations 2/1 to 0/1. This moves
the fleet from three buses on 1/2 and one on 0/1 to two per route. Five edits are
exact supported labels. The intervening unload-mode-1 command at line 50 succeeds
but has no policy label; subsequent samples use its actual resulting state.
Vehicle IDs differ later; ID 5 identifies the bus at edit time only. The final
save has three stops, one depot and four running buses, two per route. All eight
endpoints use Full load any; one has unloading mode 1. Cash is 103,214 and debt
zero. Finance and cargo counters remain checkpoint snapshots.

The owner's reported profitability reason is preserved as a retrospective
annotation. Native replay confirms the route edit; per-route causal profitability
is unmeasured. Replay and consumer are under `runs/human-campaign-20261005/game-06/`;
the Windows report is
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-06/verification.md`.
The six-game training-only assembler passes with 157 choices, including 22
repayments, at `runs/human-campaign-20261005/datasets/train-games-01-06/`.
No model training or PPO updates ran on game 06; the four-game pilot is preserved.

Game 07, session `20261005-165039-human-b595e313` (seed 1652481928), passes all
11 native checks against `Lathill Transport, 1979-01-02.sav`, marker 72. All 55
replayed commands succeed. Nineteen capture files, including ten saves, and all
20 runtime transfer files match hashes. The consumer accepts 29 choices: two
purchases, six inserts, six Full load any changes, five starts/restarts and ten
10,000 repayments. Thirty-two records are excluded, including depot/replacement
commands and the later bus purchase at line 60. That purchase succeeds at cost
5,742; its later supported orders and start use the actual resulting state.

After the second initial departure, 563,003 simulation ticks pass before the
next logged command, the first repayment. It starts with cash 150,468 and debt
100,000. Five repayments reduce debt to 50,000; later maintenance, repayments and
one additional purchase precede full repayment. The final save has three stops,
one depot and three running buses: two on 1/2 and one on 0/1, all independent
two-order lists with Full load any at each endpoint. Cash is 103,852 and debt
zero. Finance and passenger counters remain checkpoint snapshots.

The owner's delayed-investment explanation is a retrospective annotation. The
quiet interval has no explicit WAIT boundary or duration label. Reports/dataset
are under `runs/human-campaign-20261005/game-07/`; the Windows report is
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-07/verification.md`.
The seven-game training-only assembler passes with 186 choices, including 32
repayments, at `runs/human-campaign-20261005/datasets/train-games-01-07/`.
The proposed training partition is now qualified; games 08–10 remain excluded.
No game-07 model training or PPO updates ran. The four-game pilot is preserved.

Game 08, session `20261005-170721-human-7fc8c991` (seed 1070616272), completed
normally at 17:55:10 EDT. All 17 capture files, including eight saves, and all
18 runtime transfer files match hashes. All 11 native checks pass against
`Invenwell Transport, 1969-11-28.sav`, marker 66, with 51 successful commands.
The read-only development audit accepts 34 exact choices after checking public
tensors, targets and masks. Final replay and audit are under
`runs/human-campaign-20261005/game-08/replay-manual/` and `development-integrity/`.
Earlier manual snapshots and the failed locked-log snapshot attempt are preserved.

The checkpoint has five running buses, three on 1/2 and two on 0/1, with independent
two-order lists and Full load any at all ten endpoints. Cash is 109,219 and debt
zero. There are five buys, six inserts, six Full load any changes, five starts,
two copies and ten repayments; 23 records are excluded. The owner's explanation
of scaling by passenger queues is attached separately. Station 1 has 1,173 waiting
passengers before purchase line 41 and 553 before line 47. These are station totals,
without passenger destinations or an inferred purchase threshold.

Game 08 remains development data. The seven-game training set still validates
186 choices. Both direct imitation and the campaign assembler now check the
partition bound in preserved-capture metadata; a CLI label cannot turn a
development/test capture into training data. The campaign parent hash is also
rechecked before writing the combined native manifest.
`scripts/dev/audit_human_evaluation_v2.py --dataset NATIVE_DATASET --split development
--output NEW_OUTPUT` checks completed capture identity, replay, original commands,
public tensors and exact masks, producing a separate evaluation schema with no
trainer TSV, model fitting or scores. Its source records retain their immutable
native identities; the read-only export assigns the actual development/test split.
Game 08's development export is complete. Its Windows report is
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-08/verification.md`.
Both actual training input paths reject the completed development capture, and
the seven-game training regression still accepts 186 choices. No new model
training or model scoring ran on game 08.

Game 09, session `20261005-175528-human-8877f4a7` (seed 1846900543), completed
normally from 17:55:29 to 18:03:40 EDT. All 16 capture files, including seven
saves, and 17 runtime transfer files match hashes. All 11 checks pass against
`Wruningley Market Transport, 1961-04-16.sav`, marker 60; all 46 commands succeed.
The read-only test audit accepts 31 choices: five buys, four inserts, four Full
load any changes, five starts, three copies and ten repayments. Twenty-one
records are excluded. Its final orders are two two-stop routes across three
stations: two buses on 0/1 and three on 0/2, all independent with Full load any.
The owner's "three city loop" description is retained separately; no bus has a
three-station order cycle in the final save.

Reports are under `runs/human-campaign-20261005/game-09/replay-manual/` and
`test-integrity/`; the Windows report is
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-campaign-20261005/game-09/verification.md`.
Both actual training paths reject this test capture. No model scores, selection,
feature/reward tuning or fitting use game 09. Nine games supply 251 choices
across partitions: 186 training, 34 development and 31 test. No new model
training or PPO updates ran; the four-game pilot remains unchanged.

### Four-game pilot requested before the next six recordings

The pilot uses the unchanged native C++/LibTorch imitation trainer on CUDA,
256 mean full-dataset Adam updates, seed 20261002, learning rate 0.0003 and
`signed-log-orders-v2`. A fresh 12-example October 2 control uses the same update
budget; the preserved 1,000-update model is a separate historical reference.
The four new games contain 14 buys, 23 inserts, 22 Full load any changes,
14 starts, three copies, one deletion and two repayments. There are no borrowing,
WAIT or construction labels. All four native checkpoints match; the combined
manifest adds no synthetic or inferred choices.

The runtime experiment root is
`/home/imsa/.local/share/openttd-rl/runs/human-four-game-pilot-20261005-01/`.
`protocol.json` freezes the training budgets and live contexts. `assembly/`
binds every game's original replay and capture hashes. `one-game-256/` and
`four-game-256/` retain separate training inputs, losses and model archives.
The assembler accepts only whole training games, rejects duplicate seeds/logs,
and reuses the existing checkpoint, packet, accounting, candidate and mask checks.
The native 512-example bound remains sufficient for 79 labels.

To reproduce into fresh output directories (set the four individual dataset paths):

```bash
python scripts/dev/human_campaign_v2.py \
  --game game-01 "$GAME_01_DATASET" --game game-02 "$GAME_02_DATASET" \
  --game game-03 "$GAME_03_DATASET" --game game-04 "$GAME_04_DATASET" \
  --financial-features signed-log-orders-v2 --output "$RL_ROOT/runs/pilot-new/assembly"
python scripts/dev/imitate_v2.py \
  --trainer "$RL_ROOT/build/human-orders-20261002-02/rl_dev_v2_imitation" \
  --dataset "$RL_ROOT/runs/pilot-new/assembly/dataset.json" \
  --output "$RL_ROOT/runs/pilot-new/four-game-256" --device cuda:0 \
  --seed 20261002 --epochs 256 --learning-rate 0.0003 \
  --financial-features signed-log-orders-v2
```

`compare_human_imitation_v2.py --stage offline --model NAME RUN --corpus NAME REPORT
--policy EXECUTABLE --output NEW_OUTPUT` checks completed compatible models and
passed corpora, reporting unique exact choices by operation/game, training fit
versus unseen-recording transfer, probability margins and candidate permutation.
Supply `--corpus original ONE_GAME_RUN/run.json` and
`--corpus four-games ASSEMBLY/report.json` for the pilot's two corpora.
`--stage live --model NAME RUN --replay VERIFIED_OCTOBER_2_REPLAY --openttd ENGINE
--policy EXECUTABLE --output NEW_OUTPUT --device cpu` compares greedy and sampled
24-decision continuations with the same 128-tick budget and full legal masks.
Those contexts supply infrastructure; the copy/edit context also supplies two
buses. They are familiar to the original one-game models and transfer contexts
for the four-game model. These short checks do not estimate held-out strength.
Games 08–10 remain excluded from training and model selection.

The completed four-game fit takes 1,289.2 seconds (21.5 minutes), versus 218.9
seconds for the equal-update one-game control. Different dataset sizes mean
different example counts processed despite equal optimizer-update counts.

| Model | Adam updates | Original 12 choices | New 79 choices |
| --- | ---: | ---: | ---: |
| Fresh one-game control | 256 | 10/12 fit | 25/79 transfer |
| Fresh four-game pilot | 256 | 8/12 transfer | 53/79 fit |
| Preserved one-game reference | 1,000 | 12/12 fit | 23/79 transfer |

The four-game model gets 14/14 purchases, 22/22 Full load any settings and
12/14 starts, but only 4/23 station insertions, 1/3 copies, 0/1 deletions and
0/2 repayments. Its final mean negative log likelihood is 0.965040. All 79
inputs have zero aliases or target ties; maximum permutation probability error
is 2.98e-7 and CPU/CUDA probability error is 5.51e-7. The archived model is
`four-game-256/inference-weights.pt`, SHA-256
`f92bcb306c62f20b828cd595688689753d0e1a02d3715a090f18019f09a8345e`.

All four new live continuations use legal actions but fail to start the intended
target bus with the correct two-stop Full load any route, including the diagnostic
that allows reversed station order. They repeatedly insert duplicate stops and
make two to four purchases per continuation. Operating profits range from -233
to -65; the copy/edit cases deliver 31 passengers company-wide, which includes
the supplied source bus. The preserved reference starts its intended target
correctly in all four cases, but still overbuys and loses operating money.
The four-game model has not trained on these original-recording contexts; this
comparison demonstrates drift, not a held-out ranking of playing strength.

The Windows report and hash-bound JSON are in
`%LOCALAPPDATA%/OpenTTD-RL/analysis/human-four-game-pilot-20261005-01/`, with
`training-curves.csv`. Complete native traces remain in the runtime's
`offline-controls/`, `offline-four-game/`, `live-controls/` and `live-four-game/`.
Focused orchestration tests pass (38), fast checks pass (136), documentation
links pass and `git diff --check` passes. No PPO refinement ran. The next blockers
are station selection, sparse financing coverage and explicit hold/wait labels;
additional games alone do not fill choices absent from the recorder.

## Exact bus-order imitation (October 2)

The later bus recording now supplies **12 exact native training examples**,
including eight newly supported order decisions. The opt-in `orders-v1`
interface reuses the existing candidate-scoring network and separate C++/LibTorch
imitation objective. There is no second PPO implementation or Python trainer.

**Verified final fit: 12/12 unique exact choices**, on CUDA with
`signed-log-orders-v2`, 1,000 epochs, seed 20261002 and learning rate 0.0003.
The independent audit also passes all 12 after candidate-row permutation.
There are zero input aliases or target ties; the minimum target probability
margin is 0.733095 (required >1e-6), and maximum permutation probability error
is 1.19e-7. Final negative log likelihood is 0.0273864 and mean target probability
is 0.974287. This is fit to one recording, not held-out generalization.

| Demonstrated operation | Exact choices | Minimum target margin |
| --- | ---: | ---: |
| Buy bus | 2/2 | 0.998423 |
| Insert station order | 3/3 | 0.733095 |
| Full load any cargo | 3/3 | 0.995146 |
| Independent copy of orders | 1/1 | 0.965018 |
| Delete one order | 1/1 | 0.993058 |
| Start correct vehicle | 2/2 | 0.997620 |

The new action schema is `v2-m15-bus-orders-action-v1`. In this mode only,
family 6 (`SET_ROUTE` in the existing family inventory) contains primitive order
operations instead of the legacy route-reset macro. Parameter 1 is the target
vehicle; parameter 2 packs operation, order index, raw insert type (or
`MOF_LOAD=3`) and raw insert flags into four bytes; parameter 3 is the station,
copy source, loading mode or zero. Operations are insert=1, modify-load=2,
copy=3 and delete=4. Loading modes 0, 2, 3 and 4 remain distinct; **Full load any
is 3, not Full load all (2)**. Copy executes `CO_COPY`, never `CO_SHARE`.
Deletion requires an actual in-range order index, avoiding upstream's
out-of-range delete/declone behavior. Native command tests determine legality.

`signed-log-orders-v1` and `signed-log-orders-v2` bind these semantics to
`v2-m15-public-development-orders-v1`. Model archives carry both observation
and action tags, and structured tensor slot 511 marks the projection. Native
readers reject mismatched models/tensors, including callers that bypass Python
metadata validation. All three public uint32 action parameters still use the
injective byte-limb encoding in candidate slots 20–31. Historical `raw`,
`signed-log-v1`, `signed-log-loan-v1` and `signed-log-actions-v1` retain their
interpretations. ONNX export/playback explicitly rejects both native order modes.

The first 512-epoch CUDA fit, using `signed-log-orders-v1`, failed the strict
acceptance check: 6/12 unique choices, including 0/3 Full load any decisions.
It preferred No loading (4) to Full load any (3). Its input audit found zero
aliases; its strict prediction audit found zero ties, a minimum target margin
of -0.185859, and row-permutation probability error at most 1.20e-7. The failed
run and audit remain intact in `imitation-512/` and `failed-fit-audit-512/`.

Based only on those training diagnostics, `signed-log-orders-v2` adds one-hot
categories for operation, loading mode and order index. For order candidates,
slots 0–3 encode the four operations, 4–7 encode loading modes 0/2/3/4 (only
for loading modifications), and 8–11 encode indices 0–3 (absent for copying).
These replace redundant family one-hot features; the policy's separate family
embedding and exact parameter limbs remain intact. The network architecture
and native actions are unchanged. The immutable dataset keeps its original v1
reader tag; each run records its selected reader separately, and v1/v2 model
archives cannot be interchanged. No live exercise selected this encoding.

The independent compiled-reader audit passed on all **28,303 legal rows** in
the 12 training states: zero aliases, all 335 order candidates' categorical
slots correct, and every v1 feature digest identical to the preserved reader.
Only order-candidate slots 0–11 differ in v2. The native regression fixture also
checks 25 distinct rows, invalid index/one-hot rejection, exact archive reload
and bidirectional v1/v2 mismatch rejection on CPU and CUDA.

The first categorical fit used 512 epochs, seed 20261002 and learning rate
0.0003 on CUDA. It reached 11/12 unique choices (loss 0.271590), correctly
learning all loading/copy/delete/purchase/start decisions. The remaining
command-22 insertion selected station 1 instead of station 0, with target margin
-0.370187. This run is preserved in `imitation-categorical-512/`. The improving
training fit justified one bounded extension to 1,000 epochs at the same seed
and learning rate, before any live evaluation. The trainer has no imitation
resume entry point, so the longer run repeats the seeded prefix from scratch.
An attempted 1,024-epoch invocation was rejected by the existing 1,000-epoch
native limit before any update; its failed run is preserved separately.

The final run took 776.58 seconds on the RTX 2070 (`cuda:0`). Gradients and
losses remained finite, exact legal masks were retained, checkpoint reload
error was zero, CPU/CUDA probability error was at most 3.58e-7, and gradient
error at most 1.21e-9. Its model SHA256 is
`7dcd6c54a205594ec65a55ec852c135d6cdbe28ef87fea76290b3ac7ba7e461c`.
Fresh PPO import preserves all 12 exact choices and target probabilities,
with maximum value difference 1.20e-7, fresh optimizer/recurrent state and
**zero PPO updates**. No live PPO training was performed.

**Live sequence checks also passed in both greedy and sampled mode.** Each of
the four unforced continuations used the complete native legal mask, 24
decisions at 128 ticks each (3,072 ticks), sampling seed 20261002, and recurrent
reset before every decision to match imitation. Before-command-20 supplies
human-built roads, a depot and two stations, with no buses. Both modes chose
purchase → insert station 1 → insert station 0 → Full load any at index 0 →
Full load any at index 1 → start bus 1, at decision 6. Before-command-35 supplies
roads/depot/three stations, the human-configured running bus 1, and an already
human-purchased stopped bus 2. Both modes chose independent copy from bus 1 →
delete index 1 → insert station 2 → Full load any at index 1 → start bus 2, at
decision 5. Both endpoints were Full load any before each target started, and
all four target buses retained their intended routes at the end.

| Supplied context / policy | Target route | Final target cargo | Final company buses | Delivered passengers (company) | Operating profit |
| --- | --- | ---: | ---: | ---: | ---: |
| Before 20 / greedy | 1→0 | 12/31 | 4 | 0 | -221 |
| Before 20 / sampled | 1→0 | 13/31 | 2 | 0 | -206 |
| Before 35 / greedy | 1→2 | 28/31 | 5 | 31 | -83 |
| Before 35 / sampled | 1→2 | 22/31 | 5 | 31 | -77 |

All four runs had zero invalid actions, no bankruptcy and no loan changes.
The before-35 deliveries and finance are whole-company totals that include the
supplied source bus; they are not attributed to the newly configured bus 2.
Capital spending was 19,684 / 9,842 / 14,763 / 14,763 in table order; cash
changes were -19,930 / -10,073 / -14,871 / -14,865. These short runs were not
profitable. Continued actions overbought buses and repeatedly edited orders;
extra buses in the first context acquired duplicate endpoints, and the sampled
second context later changed the supplied source bus 1 to route 1→2.
Three extra starts in the first context used repeated endpoints; the source
route change in the sampled second context was an explicit later copy action,
not accidental sharing or copy aliasing. `live-categorical-1000/sequence-review.json`
records every start and hashes the action traces used for this assessment.

The remaining concrete limitation is **sustained fleet management**, including
when to stop buying/editing and preserving existing routes. Neither construction
nor the second live context's purchase was learned by that live exercise; the
two exact purchase decisions pass only the recorded-state fit check. There was
no full autonomous two-route build, no held-out evaluation and no claim of an
optimal strategy from one profitable human game. Live results did not select or
retune the model. No additional demonstration was requested.

The existing 40-column vehicle table now exposes stopped status, cargo/capacity,
order count, real/implicit order progress, current order type/destination/time,
and the complete sequence of up to four independent station orders. Each order
uses four columns: `(raw_type + 256*raw_flags)/65535`, destination/65535,
wait_time/65535 and travel_time/65535. The order count determines presence.
This preserves non-stop, loading/unloading and timetable state. Running buses
automatically accumulate timetable values, so existing orders must retain those
values even though a new insertion starts with zero timings. Shared lists,
longer sequences, refit/conditional and other unsupported order variants fail
closed. Public demand and finance remain available; targets, future orders,
future profit and candidate row positions are not added to inputs.

**Native verification passed through the latest manual save**, named
`Fluningbury Transport, 1958-06-18.sav`, explicitly selected with
`--checkpoint-occurrence latest`. Marker 47 represents actual date 1958-08-19,
tick 234,528. All 11 equality checks passed: roads, complete serialized orders,
vehicles, stations, depots, cash, loan, date, tick, finance and command-cost
accounting. All 30 replayed commands succeeded; costs totalled 13,893. Final
cash is 104,326 against initial 100,000, with debt unchanged at 100,000. Both
running buses have 31/31 passengers, on routes 1→0 and 1→2 with both endpoints
Full load any. Three modifications suffice because bus 2 inherits the first
endpoint's loading rule when copying bus 1's orders.

Eight additional native execution probes run each new demonstrated primitive,
compare complete resulting order bytes and unrelated vehicles, mutate a copy
source to verify independence, distinguish Full load any from all, and reject
invalid vehicle/order indices without mutation. Save/restore around these
probes also passes the final manual-checkpoint equality. Labels additionally
require the exact candidate at its pre-command state, successful native
execution and matching cost/principal accounting. The consumer rechecks the
source packet, operation, candidate, tensor hashes and replay evidence.

There remain 18 unlabelled executed commands (17 unsupported commands and one
depot absent from the retained candidate quota), eight failed/test/estimate
records, and one explicitly recorded ambiguous save-preview marker: 27
exclusions in total. The preview ambiguity remains subject to mandatory native
equality. No elapsed gap becomes WAIT and no human record enters PPO rollouts.
Construction, GUI viewing and the human's reasoning have not been learned.

Implementation is in `integration/dev/rl_bus_orders.inc`, the existing live and
human replay includes, `scripts/dev/prepare_bus_orders.py`, `replay_human.py`,
`orders_observation_v2.py`, `imitate_v2.py`, and `training/dev/v2_live_input.cpp`.
Independent checks are `audit_bus_orders_v2.py` and `live_bus_orders_v2.py`.
All runtime paths below are in WSL under `/home/imsa/.local/share/openttd-rl`:

- `bus-orders-engine-20261002-01/`: isolated live engine and final-build identity.
- `human-orders-replay-engine-20261002-01/`: isolated replay engine; original
  failed build/source retained in `pre-refresh/`, corrected identity in
  `final-build.json`.
- `build/human-orders-20261002-01/`: preserved original C++/LibTorch binaries.
- `build/human-orders-20261002-02/`: categorical reader, trainer and inference.
- `runs/human-orders-20261002-01/replay-manual-latest/`: verified dataset,
  source packets, exact public tensors, eight native semantic reports and
  pre-command 20/35 saves for explicitly supplied live exercises.
- `runs/human-orders-20261002-01/`: training, independent audits and test logs.
- `runs/human-orders-20261002-01/imitation-categorical-1000/`: selected model,
  full CUDA metrics, configuration, source archive, labels and hashed tensors.
- `runs/human-orders-20261002-01/final-fit-audit-categorical-1000/`: independent
  packet/native/input/prediction audit and row-permutation evidence.
- `runs/human-orders-20261002-01/human-ppo-import-categorical-1000/`: all-example
  fresh-PPO import parity with no updates.
- `runs/human-orders-20261002-01/live-categorical-1000/`: four greedy/sampled
  traces, exact initial/final public states, action probabilities and economics.

Verification logs include all 12 V2 CPU/CUDA CTests passing in the new build,
291 Python development tests (287 passed, four MCP-environment skips), the four
MCP tests passing in the separate MCP environment, and all 136 portable fast
checks passing. The final consumer tests reject coordinated sample/config
packet corruption by reconstructing events from the original hashed command
log; the actual v2 consumer import also passed all 12 records with the immutable
dataset hash unchanged. These checks supplement the eight native order execution
probes and the legacy-mode depot/purchase live smoke test.
Native ONNX playback rejects both order reader versions before reading weights;
the raw-mode control reaches weight-file validation. Its supplemental build
report confirms the trainer/infer/audit/common-library hashes did not change.

To repeat the fit and its independent checks from the WSL checkout, choose a
fresh output directory (these commands refuse to overwrite existing runs):

```bash
set -e
runtime=/home/imsa/.local/share/openttd-rl
py="$runtime/venv/bin/python"
build="$runtime/build/human-orders-20261002-02"
evidence="$runtime/runs/human-orders-20261002-01"
out="$runtime/runs/human-orders-repeat"
"$py" scripts/dev/imitate_v2.py --trainer "$build/rl_dev_v2_imitation" \
  --dataset "$evidence/replay-manual-latest/dataset.json" --output "$out/imitation" \
  --device cuda:0 --seed 20261002 --epochs 1000 --learning-rate 0.0003 \
  --financial-features signed-log-orders-v2
"$py" scripts/dev/audit_bus_orders_v2.py --imitation-run "$out/imitation" \
  --audit-executable "$build/rl_dev_v2_action_audit" --policy "$build/rl_dev_v2_infer" \
  --output "$out/audit"
"$py" scripts/dev/verify_imitation_v2.py --build-dir "$build" \
  --imitation-run "$out/imitation" --output "$out/ppo-import" --device cuda:0 \
  --financial-features signed-log-orders-v2
"$py" scripts/dev/live_bus_orders_v2.py \
  --openttd "$runtime/bus-orders-engine-20261002-01/build/openttd" \
  --policy "$build/rl_dev_v2_infer" --imitation-run "$out/imitation" \
  --output "$out/live" --device cuda:0 --seed 20261002 --decisions 24 --ticks 128
```

## Distinct native action inputs (October 2)

**Verified: 11/11 unique human choices, with no input or prediction ties.**
The final 512-epoch CUDA fit reproduced all three purchases, four starts and
four repayments. In `command-26`, vehicle 1 now receives probability 0.885299
versus 0.106080 for vehicle 2, a margin of 0.779219. Every target beats every
legal alternative by at least that margin. Reversing legal rows within each
family preserved all 11 semantic choices; maximum probability change was
1.20e-7. This is training fit on the original one-game recording.

The actual native input audit covered **25,936 legal rows across 11 archived
observations**, including repeated states. Same-input/different-parameter groups
fell from **8,543 to zero**: roads 4,753, stops 2,203, depots 1,465, routes 120,
starts 1 and sales 1 were removed. Loans remained distinguishable. A fresh audit
of the archived loan-only models reports 10/11 unique choices before PPO and
6/11 after PPO, while preserving their historical 11/11 and 7/11 row scores.

The first new-mode 256-epoch fit reached 10/11: its remaining START mistake had
distinct inputs and a negative margin of -0.019671, not an accidental correct tie.
Its failed strict audit is retained. The single extension to 512 epochs used
training fit only, with unchanged seed 20261002 and learning rate 0.0003; no
development map or held-out evaluation selected it. Final negative log likelihood
was 0.020136 and mean target probability 0.980603. CPU/CUDA probability error was
at most 2.38e-7, gradient error 1.86e-9, and checkpoint reload error zero.

New native imitation runs default to **`signed-log-actions-v1`**. This extends
the loan correction to every active M15 action parameter without changing the
32-feature policy architecture, game commands, legal masks or PPO objective.
The historical `--financial-features` option names the combined preprocessing
version. `raw`, `signed-log-v1` and `signed-log-loan-v1` retain their original
input behavior and archive interpretation; existing models must retain their tag.

The current native schema uses family plus three uint32 parameter words:

| Action | Parameters exposed to the policy |
| --- | --- |
| Town pair | Ordered origin and destination town IDs |
| Single-tile road | Tile, road bits (X/Y), length |
| Bus stop / road depot | Tile and diagonal orientation |
| Buy bus | Depot tile and engine ID |
| Set route | Vehicle ID, ordered origin and destination station IDs |
| Start / stop / send to depot / sell | Vehicle ID |
| Manage loan | Borrow/repay direction and amount |

Reserved feature slots 20–23 encode parameter 1, 24–27 parameter 2, and 28–31
parameter 3. Each word is split into four little-endian bytes; each byte becomes
`log1p(byte) / log(256)`. This is injective in float32 for all 256 byte values,
including at uint32 carry boundaries, and gives small vehicle IDs a useful scale.
It does not encode candidate row, target label, stable-key hash or future state.
Family embeddings and original features 0–19 remain in place, with the existing
signed-log finance transform. Occupied reserved features, active parameter words
4–15, or unsupported loan amounts fail closed. Masked padding remains ignored.
New archives reject mismatched preprocessing; ONNX export/playback reject the
new mode until equivalent parameter preprocessing is qualified.

The imitation metrics retain `accuracy` as historical greedy row accuracy and
add `unique_exact_accuracy`, input-alias counts, target ties, minimum probability
margin, per-family summaries and initial/final per-example details. Unique success
requires no same-input legal target alias and a target probability more than
`1e-6` above every legal alternative. New-mode training rejects an aliased target
before its first optimizer update. A completed low-epoch fit is not automatically
a successful unique-action fit.

`audit_action_inputs_v2.py` runs the actual C++ reader over every legal candidate
in archived training observations, preserving its emitted float32 features. It
compares loan-only and complete-action preprocessing, checks original artifact
hashes, and optionally verifies a new model against those exact human examples.
The prediction check reverses legal rows within each family and requires the
same unique semantic choices. Synthetic native tests additionally cover every
byte value, large adjacent IDs, orientation and route contrasts, policy gradients,
padding, row permutation, schema rejection and CPU/CUDA archive reload.

The recording still supplies only three purchases, four starts and four
repayments. Structural road/stop/depot/route distinctions are covered by input
audits and numerical fixtures, not demonstrated human learning of those actions.
Long drags, drive-through stops, cloning and GUI order edits remain outside the
exact supported imitation labels. This work does not establish held-out playing
strength or address the earlier PPO retention/debt-management failures.

Verification passed all 10 native V2 CPU/CUDA tests, all 59 focused Python tests
with no skips, and all 136 portable fast tests. Synthetic CPU and CUDA checks
passed fresh PPO weight import, finite updates and pre-update rejection of an
aliased target. All 11 human examples passed CUDA import parity and unique-choice
checks. Both Python and the independently compiled ONNX executable reject the
unsupported parameter modes before loading weights. Bash syntax and
`git diff --check` passed. Two initial compiler failures from signed-index/character
warnings were repaired; their records remain in the new build directory.

Artifacts are under `/home/imsa/.local/share/openttd-rl` in Ubuntu-24.04:

- `build/human-actions-20261002-01/`: isolated executables, build provenance,
  source snapshots, successful build log and preserved failed attempts.
- `runs/human-actions-20261002-01/imitation/` and `action-audit-256/`: the
  256-epoch diagnostic and failed strict fit audit.
- `runs/human-actions-20261002-01/imitation-fit/`: final 512-epoch fit, exact
  training tensors, source, metrics and weights.
- `runs/human-actions-20261002-01/action-audit/report.json`: full before/after
  alias groups, native transformed features, unique predictions, row permutations
  and unchanged input/model hashes.
- `runs/human-actions-20261002-01/historical-tie-audit/`: strict metrics for the
  untouched archived imitation/PPO pair.
- `runs/human-actions-20261002-01/import-check/`, `synthetic-cpu/`,
  `synthetic-cuda/`, `native-tests/`, `python-tests/` and `onnx-guard/`:
  verification reports and logs.

Reproduce in WSL using a fresh build and output directory:

```bash
RL_ROOT="$HOME/.local/share/openttd-rl"
PY="$RL_ROOT/venv/bin/python"
POLICY_BUILD="$RL_ROOT/build/human-actions-new"
EXPERIMENT="$RL_ROOT/runs/human-actions-new"
"$PY" scripts/dev/local.py build --v2-policy --jobs 2 \
  --cuda-root /usr/local/cuda-12.6 --build-dir "$POLICY_BUILD"
"$PY" scripts/dev/imitate_v2.py \
  --trainer "$POLICY_BUILD/rl_dev_v2_imitation" \
  --dataset "$RL_ROOT/runs/human-replay-full-20261002-01/dataset.json" \
  --device cuda:0 --seed 20261002 --epochs 512 --learning-rate 0.0003 \
  --financial-features signed-log-actions-v1 --output "$EXPERIMENT/imitation"
"$PY" scripts/dev/audit_action_inputs_v2.py \
  --imitation-run "$RL_ROOT/runs/human-imitation-20261002-01/imitation-loan-fit" \
  --audit-executable "$POLICY_BUILD/rl_dev_v2_action_audit" \
  --prediction-run "$EXPERIMENT/imitation" \
  --policy "$POLICY_BUILD/rl_dev_v2_infer" --output "$EXPERIMENT/action-audit"
"$PY" scripts/dev/verify_imitation_v2.py \
  --build-dir "$POLICY_BUILD" --device cuda:0 \
  --financial-features signed-log-actions-v1 \
  --imitation-run "$EXPERIMENT/imitation" --output "$EXPERIMENT/import-check"
```

## Human replay, imitation, and the loan-direction defect (October 2)

The first human recording has now been validated, its supported decisions have
trained the C++ policy through imitation and then live PPO, and the resulting
policy has been evaluated on different development maps. The owner deferred
collecting another
5–10 games. The later bus-only lesson request authorizes one focused new
recording, described under Local human command recording below.

**Native replay is now verified.** The prefix through
`Cartborough Transport, 1950-03-18.sav` replayed 29 commands and matched cash
82,819, debt 100,000, roads, complete serialized orders, vehicles, stations,
depots and date/fraction. Replaying all 65 commands through the final
`Cartborough Transport, 1967-09-01.sav` matched cash 120,938 and debt 60,000.
The independently rebuilt, guarded replay also matched tick 478,777 and the
complete public finance state. Replay-confirmed command costs totalled 16,751
for the early prefix and 38,087 for the final prefix. Every immediate command
reconciled `cash_change = loan_change - command_cost`. The stock recording did
not contain original execution costs; these are costs confirmed during replay,
with checkpoint equality providing the independent state check.

The final prefix supplies **11 exact supported human labels**: three `BUY_BUS`,
four `START_VEHICLE`, and four `MANAGE_LOAN` repayments of 10,000 each. The depot
command was outside the retained native candidate quota. Long road drags,
drive-through stops, cloning and GUI order edits were replayed for equivalence
but excluded from imitation because their semantics do not exactly match the
current policy actions. Failed/test/estimate records are excluded. No gaps were
labelled WAIT, and the game contains no explicit additional-borrowing examples.
Each retained example has pre-action public tensors, the exact native legal
mask, stable candidate identity, source command and confirmed cost.

**The first learning test exposed an action-representation defect.** Native
borrow and repay have distinct parameter values (direction 1 and 2), but the
policy loader discarded those parameters except the action family. Their
command costs are both zero; priorities `UINT32_MAX - direction`, normalized as
float32, both round to 1. Their entire 32-float feature vectors were identical.
This was independently confirmed from archived native tensor rows 3841/3842,
including the binary hash. Legal masks and financing observations alone could
not make the policy distinguish the directions.

The original fixed test used the existing `signed-log-v1` preprocessing, CUDA,
64 supervised epochs, learning rate 0.0003 and seed 20261002. Negative log
likelihood fell from 2.635650 to 0.792878 and exact-action accuracy rose from
3/11 to 7/11: all purchases and starts were reproduced, but none of the four
repayments. The old `family_accuracy` field in that run is the raw family-head
argmax, not the family of the globally greedy action; its name is corrected to
`family_head_accuracy` for future runs. A separate action audit found that the
four repayment contexts selected `BUY_BUS`. Do not call this learned repayment.

On each of the three fixed development maps, the original imitation model failed
to start service, made 138 borrow and 118 repay actions with 236 immediate opposite
loan-action pairs, and ended with 292,783 cash and 300,000 debt. Its cash result
excluding financing was -7,217. High cash here was borrowed principal, not earned
income. The associated PPO attempt was intentionally interrupted after two
updates and 289 recorded transitions once the feature collision was confirmed.
Its failed-behavior evidence, partial rollout and reset checkpoint are retained.
This correction follows an encoded-input defect, not selection on held-out maps.

The correction is an opt-in **`signed-log-loan-v1`** preprocessing mode in the
existing C++ input boundary. It retains signed-log money features and adds
borrow/repay indicators to reserved candidate features 30 and 31, derived only
from the visible native direction parameters. It preserves the existing native
actions, masks, rewards, and loan-principal accounting. Model archives bind the
preprocessing name; old modes retain their behavior. ONNX export for the new
mode is rejected until equivalent preprocessing is qualified. Python export and
package checks reject it, and an independently compiled native ONNX target also
rejects it before loading a model. This mode identifies the archived native loan-learning
experiments; do not silently change a historical model's preprocessing tag.

**The corrected small experiment completed.** At the same 64-epoch budget the
new encoding reached 8/11 exact decisions (four starts and four repayments,
but no purchases). A single bounded 256-epoch fit on the same 11 training
examples then reached **11/11 greedy target rows**: all three purchases, four
starts and four repayments, including one tied START candidate described below.
This extension was chosen from training fit, not development-map
scores. Negative log likelihood fell from 2.629874 to 0.065524; mean target
probability reached 0.952086. CPU/CUDA probability error was at most 3.58e-7,
gradient error 1.40e-9, and reload error zero. This is a training fit from one
game, not held-out imitation accuracy or proof that every action is distinguishable.

**The loan correction does not fix every action feature.** A final read-only
inventory of all legal candidates in the 11 archived training observations
confirmed zero remaining borrow/repay aliases under `signed-log-loan-v1`, but
found same-feature/different-parameter groups for roads, stops, depots, routes,
starts and selling. These are possible semantic aliases, not measurements of
their gameplay impact. Counts include repeated states across observations.
One alias directly affects a training label: in `command-26`, START rows 3073
and 3074 identify vehicles 1 and 2 but have identical features. The demonstrated
target is row 3073, which wins the greedy tie; its probability is only 0.499473
after imitation and 0.383774 after PPO. Therefore **11/11 includes one tie and
does not establish learned vehicle discrimination**. Preserve the verified loan
fix and baseline; version and test the remaining public action distinctions
before claiming complete route/vehicle learning.

The verified weights initialized fresh PPO Adam and recurrent state. Four CUDA
PPO updates collected 512 decisions on training map seeds 1110312784 and
786545128, using 128-step rollouts and 256-decision episodes, guide v5, finance
observations, choice-weighted policy loss, fp64 gradient-norm reduction and the
existing asset potential. All metrics were finite and behavior-probability replay
error was zero at every update. Training delivered 310 passengers on the first
map and none on the second. The first update's approximate KL was 0.256766;
this short run is not evidence of a conservative or converged update schedule.
Resuming from update 2 reproduced the final two updates, all 256 subsequent
decisions and economic transitions, and all 277 normalized native checkpoint
state fields exactly, including model, Adam, recurrent state and CPU/CUDA RNG.
The imitation weights are imported only at initialization, never over a resumed
PPO checkpoint.

**Service transfer occurred only with sampling; financing remains poor.** Every
row below uses the same three development maps, seed 20261002, 256 decisions,
starting cash/debt of 100,000 and the public guide v5. Values separated by `/`
follow map order 1630856436, 155097162, 1456534872. These are development maps,
not held-out human games or the frozen final evaluation corpus.

| Controller | Maps starting service | Passengers by map | Operating profit by map | Mean immediate loan reversals |
| --- | ---: | --- | --- | ---: |
| Scripted baseline | 3/3 | 673 / 465 / 732 | 2,688 / 781 / 2,761 | 0 |
| Imitation, greedy | 0/3 | 0 / 0 / 0 | -334 / -334 / -334 | 245 |
| Imitation + PPO, greedy | 0/3 | 0 / 0 / 0 | -334 / -334 / -334 | 245 |
| Imitation, sampled | 0/3 | 0 / 0 / 0 | -417 / -401 / -317 | 209.7 |
| Imitation + PPO, sampled | 3/3 | 186 / 93 / 205 | 450 / -226 / 496 | 147 |

Sampled evaluation was an explicitly paired diagnostic after greedy failure;
neither result selected or tuned a model. Sampled PPO started service at decision
175 on all three maps, ended with debt 20,000 / 30,000 / 20,000 and cash
12,732 / 18,407 / 13,780. Its minimum decision-boundary cash was only
2,011 / 4,160 / 3,057. Cash results excluding financing were
-7,268 / -11,593 / -6,220: the short services did not recover construction costs.
All reported controllers had zero invalid actions and no bankruptcy. Greedy
imitation and PPO reached minimum cash -25 and spent every decision on loans.
The scripted baseline also ran with small cash reserves; it is a service control,
not an optimal repayment policy. Immediate reversals count adjacent opposite
loan-action pairs, so an alternating sequence of three actions has two reversals.
Report interest as a lower bound from observed year-to-date counters; a reset
can hide charges at a year boundary.

**PPO also forgot the demonstrated repayments.** A read-only native audit on the
same 11 training examples, full native masks and independent recurrent resets
found 11/11 greedy target rows before PPO and 7/11 afterward, including the same
START tie. Purchases and starts were retained at the greedy-row level;
all four repayment contexts instead selected `BUY_BUS`. Mean repayment target
probability fell from 0.996780 to 0.001420. This is training-example retention,
not a new evaluation split. It motivates a bounded retention/learning-rate
experiment before a longer PPO run; it does not justify silently mixing human
examples into the on-policy rollout buffer or declaring debt management solved.

All paths below are under `/home/imsa/.local/share/openttd-rl` in Ubuntu-24.04:

- `runs/human-replay-early-20261002-02/report.json`: verified early prefix.
- `runs/human-replay-full-20261002-01/dataset.json`: immutable training dataset
  and its replay report; `runs/human-replay-full-20261002-02/report.json` independently
  rechecks the full prefix with additional company/cost/tick/finance guards.
- `human-input-20261002-01/transfer.json`: allowlisted original Windows capture
  hashes and verified Linux runtime copy; user saves and ordinary configuration
  were preserved.
- `human-replay-engine-20261002-02/final-build.json`: isolated source/binary
  identity, build logs and unchanged base-engine checks.
- `runs/human-imitation-20261002-01/imitation/`: original fixed human fit;
  `runs/human-imitation-20261002-01/human-import-actions/report.json`: actual
  selected actions and import parity.
- `runs/human-imitation-20261002-01/evaluation/`: original map tests, scripted
  baselines and `native-loan-feature-equality.json` with the independent defect
  evidence. The three map seeds are 1630856436, 155097162 and 1456534872, each
  evaluated for 256 decisions with guide v5 and finance observations.
- `runs/human-imitation-20261002-01/ppo/interruption-context.json`: why the
  original PPO attempt was stopped, with all earlier artifacts retained.
- `runs/human-imitation-20261002-01/imitation-loan/`: paired 64-epoch corrected
  diagnostic; `imitation-loan-fit/`: final 256-epoch training fit. Their
  `human-import-loan-actions/` and `human-import-loan-fit-actions/` sibling
  directories verify native import and the actual selected actions.
- `runs/human-imitation-20261002-01/ppo-loan/`: completed four-update refinement;
  `ppo-loan-resume/` and `resume-verification.json`: exact continuation proof.
- `runs/human-imitation-20261002-01/evaluation/main-greedy-report/` and
  `evaluation/main-sampled-report/`: paired JSON/Markdown outcomes and hashes.
  Effective environment settings match. Greedy baseline and model evaluations
  have different recorded evaluator source snapshots; this is disclosed rather
  than claiming identical source. The sampled pair shares its evaluator source.
- `runs/human-imitation-20261002-01/ppo-retention/report.json`: all 11 before/after
  native predictions with model, executable and tensor hashes verified.
- `runs/human-imitation-20261002-01/candidate-semantic-alias-inventory/`: read-only
  raw/corrected feature inventory, full alias groups, audit script and hashes.
  Only one retained training target has a non-loan alias, the START pair above.
- `runs/human-imitation-20261002-01/evaluation/outcome-plot/`: inspected PNG/SVG
  outcome chart, rendering script and report/evidence/output hashes.
- `runs/human-replay-parser-audit-20261002-01.json`: malformed-record rejection
  and unchanged event output for all 65 verified commands. Published replay
  reports remain immutable; their original cost wording is clarified above.
- `build/human-loan-onnx-guard-20261002-03/report.json`: compiled rejection check.
- `imitation-build-correction.json`: an initial build touched the prior pilot's
  trainer; it was restored to its exact recorded hash. All subsequent builds use
  isolated directories. Failed builds and experiments remain preserved.

The development workflow now uses `prepare_human_replay.py`, `replay_human.py`,
and `imitate_v2.py`; `train_v2.py --imitation-run` imports verified supervised
weights into fresh PPO optimizer/recurrent state. `infer_v2.py --imitation-run`
evaluates the policy before PPO. `report_imitation_eval_v2.py` audits actual
native service, command spending, liquidity, debt and immediate loan reversals.
PPO continues to collect its own behavior probabilities and exact sampling masks.
Sparse human examples use independent recurrent resets, and do not establish
learning of timing, complete route construction or whether additional borrowing
is productive. The imitation objective has no critic labels. The public guide
still supplies route geometry in live tests and restricts masks compared with
the original full native masks used for imitation and retention checks.

Verification passed six native policy/distribution/loan-feature CPU/CUDA tests,
the synthetic CPU/CUDA import/update checks, the real human-label import check,
the focused Python suite (128 tests: 127 passed, one skipped), and all 136
portable fast tests. The skipped direct-export test requires Torch; both tests
in its module passed when rerun in the training virtualenv. The compiled ONNX
rejection test and all three replay/parser tests passed. The new Bash examples
passed syntax checks, and `git diff --check` passed.

Reproduce the small learning sequence from this checkout in WSL with fresh
output directories. The following uses the verified engine and dataset already
on this host; the replay preparation commands are provided separately below.
Build into a new directory rather than overwriting a prior experiment's native
executables. `local.py build` uses the detected CUDA architecture.

```bash
RL_ROOT="$HOME/.local/share/openttd-rl"
PY="$RL_ROOT/venv/bin/python"
POLICY_BUILD="$RL_ROOT/build/human-imitation-new"
EXPERIMENT="$RL_ROOT/runs/human-imitation-new"
ENGINE="$RL_ROOT/v2-finance-engine-20261002-01/build/openttd"
"$PY" scripts/dev/local.py build --v2-policy --jobs 2 \
  --cuda-root /usr/local/cuda-12.6 --build-dir "$POLICY_BUILD"
"$PY" scripts/dev/imitate_v2.py \
  --trainer "$POLICY_BUILD/rl_dev_v2_imitation" \
  --dataset "$RL_ROOT/runs/human-replay-full-20261002-01/dataset.json" \
  --device cuda:0 --seed 20261002 --epochs 256 --learning-rate 0.0003 \
  --financial-features signed-log-loan-v1 --output "$EXPERIMENT/imitation"
"$PY" scripts/dev/verify_imitation_v2.py \
  --build-dir "$POLICY_BUILD" --device cuda:0 \
  --financial-features signed-log-loan-v1 \
  --imitation-run "$EXPERIMENT/imitation" --output "$EXPERIMENT/import-check"
"$PY" scripts/dev/train_v2.py \
  --openttd "$ENGINE" --trainer "$POLICY_BUILD/rl_dev_v2_train" \
  --device cuda:0 --seed 20261002 --updates 4 --rollout-length 128 \
  --episode-horizon 256 --training-map-count 2 --finance-observations \
  --financial-features signed-log-loan-v1 --guidance one-bus-public-plan-v5 \
  --policy-loss choice-weighted --gradient-norm fp64-v1 --asset-potential \
  --reuse-bootstrap-tensors --checkpoint-interval 2 \
  --imitation-run "$EXPERIMENT/imitation" --output "$EXPERIMENT/ppo"
for mode in greedy sampled; do
  for map in 1630856436 155097162 1456534872; do
    "$PY" scripts/dev/infer_v2.py \
      --openttd "$ENGINE" --policy "$POLICY_BUILD/rl_dev_v2_infer" \
      --device cpu --seed 20261002 --mode "$mode" --decisions 256 \
      --split development --map-seed "$map" \
      --imitation-run "$EXPERIMENT/imitation" \
      --guidance-override one-bus-public-plan-v5 \
      --output "$EXPERIMENT/imitation-$mode-$map"
    "$PY" scripts/dev/infer_v2.py \
      --openttd "$ENGINE" --policy "$POLICY_BUILD/rl_dev_v2_infer" \
      --device cpu --seed 20261002 --mode "$mode" --decisions 256 \
      --split development --map-seed "$map" --training-run "$EXPERIMENT/ppo" \
      --output "$EXPERIMENT/ppo-$mode-$map"
  done
done
"$PY" scripts/dev/audit_imitation_retention_v2.py \
  --imitation-run "$EXPERIMENT/imitation" --ppo-run "$EXPERIMENT/ppo" \
  --policy "$POLICY_BUILD/rl_dev_v2_infer" --output "$EXPERIMENT/retention"
```

The local CUDA toolkit path is host-specific; the verified loan build's
`CMakeCache.txt` records `/usr/local/cuda-12.6/bin/nvcc`. Inspect local build
provenance before building elsewhere. Generate comparisons with
`report_imitation_eval_v2.py --runs LABEL=PATH ... --output FRESH_DIRECTORY`,
using a separate report for each inference mode and repeated policy labels
across maps. To check continuation, run the same PPO configuration with
`--updates 2 --resume "$EXPERIMENT/ppo/checkpoints/update-000002"`, omit
`--imitation-run`, and use a new output directory. Then run
`compare_v2_resume.py --original ORIGINAL --resumed RESUMED --output NEW_REPORT.json`.
Do not edit archived source/configuration to bypass a resume compatibility check.

To replay the preserved Linux-accessible recording again, use fresh directories:

```bash
"$PY" scripts/dev/prepare_human_replay.py \
  --base-engine-root "$RL_ROOT/v2-finance-engine-20261002-01" \
  --engine-root "$RL_ROOT/human-replay-engine-new" --jobs 4
"$PY" scripts/dev/replay_human.py \
  --openttd "$RL_ROOT/human-replay-engine-new/build/openttd" \
  --recording "$RL_ROOT/human-input-20261002-01" \
  --checkpoint 'Cartborough Transport, 1967-09-01.sav' \
  --output "$RL_ROOT/runs/human-replay-full-new"
```

## Learning priority: debt and route investment (October 2)

The owner explicitly gives loan and debt management equal importance to route
placement. The learning objective includes choosing productive borrowing,
preserving enough cash for operation and construction, expanding at a sustainable
pace, and deciding when to repay. A successful bus builder must also demonstrate
these financing choices over time.

Native V2 already exposes `MANAGE_LOAN` borrow/repay actions. The historical v3/v4
one-bus guide restricts borrowing to blocked construction with no vehicle and
cash below 10,000; v4 also gates repayment on starting service and retaining at
least 20,000 cash before the repayment action. The new opt-in
`one-bus-public-plan-v5` guide keeps every native legal borrow/repay choice
available alongside WAIT and the proposed construction step. Historical guides
retain their behavior. Route geometry still comes from the public one-bus planner;
the policy chooses financing and whether/when to advance construction.

The opt-in `finance-v1` observation mode uses effective `GetMaxLoan()` rather than
the raw company override sentinel. It adds borrowing headroom, interest rate,
current-quarter income, expenses and operating profit, and current-year interest
paid. These are own-company observations, validated against native state. The
schema is `v2-m15-public-development-finance-v1`; reserved structured slots 16-22
encode the seven fields, with signed-log amounts and interest percent divided by
100. Own-company slot 4 contains the effective maximum loan divided by 1e9.
Legacy observations remain unchanged. Inference and reset checkpoints bind the
schema; the frozen study, MCP and ONNX paths do not accept this new schema yet.

For the human-data learning path, capture cash, outstanding principal, effective
borrowing limit/headroom, interest settings and paid interest, recent earned
income and operating costs, and actual construction/vehicle spending at decision
boundaries. Use only information available then; long-run outcomes belong in
later rewards and reports. Keep the distinct options to borrow, repay, invest or
wait in the same native action boundary used by the policy and MCP.

Account for principal separately from earnings and costs. The existing
`cash_result_excluding_financing = balance_change - loan_change` convention
should remain: a borrow/repay round trip must not create reward from principal
flows, and cash gained by borrowing must not look like business income. Evaluate
interest cost, liquidity shortages, debt trajectory, net investment, passenger
service and survival together. A fixed repay-first controller remains a baseline,
not evidence that the policy learned when repayment helps.

The first demonstration contains four repayment requests and use of its starting
finances; it contains no explicit `CmdIncreaseLoan` records. Preserve its value
as phased investment/repayment evidence without claiming it demonstrates every
borrowing decision. Broader borrowing behavior needs suitable decision contexts
and observed examples or live exploration. The verified replay and separate
imitation path are described above; the earlier finance pilot did not use them
and does not establish trained financing competence.

## Finance-aware live PPO pilot (October 2)

The first pilot completed four C++/LibTorch PPO updates on the local RTX 2070
(`cuda:0`), with 512 unique training decisions across two 256-decision episodes.
It uses guide v5 and finance observations, signed-log financial features,
choice-weighted policy loss, existing asset potential and fp64 gradient-norm
reduction. PPO mathematics and reward formulas were not changed for this pilot.
Borrowed principal does not count as earnings or add capital/potential reward.
This is live planner-assisted PPO, not training on the human recording.

Artifacts are under
`/home/imsa/.local/share/openttd-rl/runs/finance-pilot-20261002-01` in Ubuntu-24.04.
`report.json` and `finance-curves.png` summarize the actual traces; `train/`
contains source/configuration, tensors, native economics, weights and checkpoints.
The independent engine is `v2-finance-engine-20261002-01/build/openttd` under the
same `openttd-rl` root, with build provenance in its `preparation.json`. The base
engine, ordinary Windows game and human saves were preserved.

| Episode/controller | Map seed | Passengers | Operating profit | Cash result excluding financing | Final debt |
| --- | ---: | ---: | ---: | ---: | ---: |
| Training episode 1 | 1110312784 | 682 | 2,104 | -5,301 | 70,000 |
| Training episode 2 | 786545128 | 744 | 2,358 | -5,798 | 50,000 |
| Saved policy, greedy development | 1630856436 | 0 | -2,334 | -2,684 | 100,000 |
| Scripted development control | 1630856436 | 673 | 2,688 | -5,030 | 10,000 |

Every row covers 256 decisions and starts with 100,000 cash and debt. All had zero
invalid actions and no bankruptcy. Training operated one bus per map but made
127 borrow and 135 repay actions, including 73 immediate opposite-loan actions.
The saved policy chose WAIT for all 256 development decisions. Positive training
operating profit did not recover construction spending. Four updates and one
development map do not establish improved playing strength; the greedy policy
still fails to initiate service.

The native verification passed 27 paired legacy/finance snapshots, unchanged
gameplay, exact +/-10,000 principal flows, and actual charged interest. All 512
stored masks/log probabilities passed inspection; behavior replay error was zero.
Resuming update 2 reproduced the next two updates, economic trace and final
weights exactly (`resume-verification.json`). An eight-decision CPU/CUDA inference
comparison passed: probability maximum absolute error 5.9e-8, value 1.79e-7,
against tolerances 1e-5 and 1e-4. Focused development tests and the 136-test portable
fast suite passed. The first fast-suite attempt used an unsuitable virtualenv;
its missing Git/jsonschema failure log is retained, and the documented system
Python invocation passed.

Reproduce from the checkout in WSL using fresh output directories. This host
already has the unchanged native trainer/inference build shown below:

```bash
RL_ROOT="$HOME/.local/share/openttd-rl"
PY="$RL_ROOT/venv/bin/python"
POLICY_BUILD="$RL_ROOT/build/refactor-gradient-clip-01"
ENGINE_ROOT="$RL_ROOT/v2-finance-engine-new"
PILOT="$RL_ROOT/runs/finance-pilot-new"
"$PY" scripts/dev/prepare_finance_v2.py \
  --base-engine-root "$RL_ROOT/v2-live-engine" \
  --engine-root "$ENGINE_ROOT" --jobs 4
"$PY" scripts/dev/verify_v2_finance.py \
  --openttd "$ENGINE_ROOT/build/openttd" --output "$PILOT/native-finance-check"
"$PY" scripts/dev/train_v2.py \
  --openttd "$ENGINE_ROOT/build/openttd" \
  --trainer "$POLICY_BUILD/rl_dev_v2_train" --device cuda:0 --seed 20261002 \
  --updates 4 --rollout-length 128 --episode-horizon 256 --training-map-count 2 \
  --financial-features signed-log-v1 --finance-observations \
  --guidance one-bus-public-plan-v5 --policy-loss choice-weighted \
  --gradient-norm fp64-v1 --asset-potential --reuse-bootstrap-tensors \
  --checkpoint-interval 2 --output "$PILOT/train"
"$PY" scripts/dev/evaluate_guide_v2.py \
  --openttd "$ENGINE_ROOT/build/openttd" --controller scripted --mode greedy \
  --seed 20261002 --map-seed 1630856436 --split development --decisions 256 \
  --guidance one-bus-public-plan-v5 --finance-observations \
  --output "$PILOT/scripted-development"
"$PY" scripts/dev/infer_v2.py \
  --openttd "$ENGINE_ROOT/build/openttd" --policy "$POLICY_BUILD/rl_dev_v2_infer" \
  --training-run "$PILOT/train" --device cpu --seed 20261002 --mode greedy \
  --decisions 256 --split development --map-seed 1630856436 \
  --output "$PILOT/greedy-development"
```

The next slice from this pilot was verified human replay/action mapping and a
separate imitation objective before PPO refinement; that work is recorded above.
Financing scenarios also need varied
capital requirements and later expansion: the present one-bus task begins with
enough cash to build, so productive additional borrowing is not necessary.
Simply increasing this pilot's training budget would not test the owner's full
strategy. Keep the human recording as raw evidence until replay establishes
observations, legal actions and confirmed outcomes at each decision.

## Local human command recording (October 2)

`scripts/dev/record_human.ps1` launches the installed Windows OpenTTD 15.3 with
normal mouse/keyboard controls in a fresh, isolated 64x64 temperate game. It uses
the stock `desync=1` command logger, an explicit per-session `-c` configuration,
`-X` local-only search paths and `-x` to disable configuration persistence. It
does not read/copy the ordinary game configuration, credentials or saves. Runtime
artifacts go under `%LOCALAPPDATA%\OpenTTD-RL\demonstrations`, outside the checkout.

Run from this checkout in Windows PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/dev/record_human.ps1
```

For the owner's current focused bus lesson, add `-Lesson bus-routes`. The session
includes `BUS-LESSON.md` and an editable `route-notes.md`, with lesson preferences
recorded in `recording.json`: one directly purchased bus per initial route and
Full load any cargo at both endpoints before first start. Aim for two routes;
save `route-1-ready` before starting and `route-1-service` after passenger delivery,
then the corresponding route-2 saves and `final`. Avoid reloading or changing
maps mid-session. Corrections stay in the command history. Notes identify route
reasoning, consulted windows/metrics and management decisions by game date or
checkpoint; GUI navigation and video are not captured. Notes are annotations,
never inferred policy labels. Completion inventories their final hash and lists
missing requested checkpoints without pretending that capture verifies service.

The bus lesson passed the installed-engine `-SmokeTest -Lesson bus-routes` at
`C:\Users\imsa\AppData\Local\OpenTTD-RL\demonstrations\20261002-133745-smoke-6a437769`.
It produced initial/exit saves, a setup command log, lesson/notes metadata and
zero exit status. This checks recorder operation, not human gameplay or replay.
The fresh interactive bus lesson was then launched at
`C:\Users\imsa\AppData\Local\OpenTTD-RL\demonstrations\20261002-133851-human-eadd5d2c`
with seed 1792482899. Startup inspection confirmed a responding OpenTTD 15.3
process, `initial.sav` and the setup pause/save command records. It was left
running for the owner. The completed capture exited with code zero and retained
32 command records, 8 failed/test/estimate records and six saves.

**The later manual save is now the primary verified checkpoint**, as requested
by the owner. `Fluningbury Transport, 1958-06-18.sav` was overwritten at log line
47; its actual final game date is 1958-08-19. Native replay through that last
marker executed 30 commands successfully and matched all 11 checks (roads,
complete serialized orders, cash, debt, date, tick, finance, vehicles, stations,
depots and command-cost accounting). Two preliminary autosave replays passed
but do not replace this final manual checkpoint.

The final save has two directly purchased buses, one on station route 1 → 0 and
one on 1 → 2. Both endpoints were Full load any cargo before each first start.
The second bus copied the first bus's orders, deleted one endpoint, inserted a
new endpoint and set its full-load flag. Both final buses are running with 31/31
passengers. Cash rose from 100,000 to 104,326 while debt stayed at 100,000; total
replayed command spending was 13,893. The demonstrated operation recovered its
initial spending. Final current-quarter operating profit is 375. The adapter's
17,158 operating profit and 5,270 passengers cover current plus up to 24 retained
quarters, not lifetime totals. Continued simulation is outcome evidence, not
inferred supervised WAIT actions; GUI viewing and rationale are not recorded.

At capture verification, the importer exported only four exact labels (two purchases and two starts).
Route insertion, full-load modification, copying/deleting orders and construction
needed exact policy-action support before this recording could train those
choices. The depot fell outside retained legal candidates. The subsequent
orders-v1 implementation and learning results are documented at the top of this
guide. Preserve the distinction between verified gameplay and supported labels.

The hash-verified completed copy is under
`%LOCALAPPDATA%\OpenTTD-RL\demonstrations\completed\20261002-133851-human-eadd5d2c-bus-01`.
Windows `/mnt/c` visibility differed from native Windows AppData, so transfer used
WSL UNC and verified all 17 captured files. Linux input is
`/home/imsa/.local/share/openttd-rl/human-input-bus-20261002-01`; results are in
`/home/imsa/.local/share/openttd-rl/runs/human-bus-capture-20261002-01/`, especially
`replay-manual-latest/report.json` and `capture-report.json`. Exact Windows parser
and test copies plus hashes are retained in `tooling-latest/`. The user-facing
report is `%LOCALAPPDATA%\OpenTTD-RL\analysis\bus-capture-20261002-01\capture-report.md`.

Replay checkpoint discovery now supports both `save/` and `save/autosave/`,
rejecting ambiguous basenames. Duplicate save markers fail closed by default.
Explicit `--checkpoint-occurrence latest` chooses the last marker; it permits a
same-file load/preview marker only immediately before that selected save, with
the ambiguity recorded and native equality still mandatory before labels export.
OpenTTD logs `load:` for save-dialog previews too; never infer a user reload from
that marker alone. Other loads/map changes and overwritten initial saves reject.
All eight focused parser tests passed, along with the three native checkpoint
replays and `git diff --check`.

The game starts paused in 1950 with six towns. Unpause, build a passenger-bus
service, let it deliver passengers, save (any name is accepted), and quit normally.
Each launch uses a unique folder. Use one map per recording; do not reuse a recording folder
or its configuration because the stock logger truncates its file at process start.
The first capture should be brief, followed by an audit of actual construction and
order commands before spending time on larger demonstrations.

Each folder contains `READ-ME.txt`, `recording.json`, the exact recorder/config/
startup script, `save/initial.sav`, the native `save/autosave/commands-out.log`,
and periodic/manual/exit saves. Provenance includes seed, executable version/hash,
available base-asset hashes, source revision/dirty state, command line, native CPU
runtime and capture result. The setup `pause`/`save initial` and startup commands
are not human labels. No game command history before capture can be recovered
from a final save alone.

**This is raw evidence, not a training-ready dataset.** Stock command logging
precedes execution and its `cmdf` records include failed tests and estimate-only
queries. It lacks confirmed results/costs, public observation tensors, legal masks
and policy action labels. The new native replay and separate C++ imitation path
above accepts only a verified, exactly mapped subset. Do not feed raw records
directly into the on-policy PPO buffer or infer replay equivalence from capture.
Generated demonstration
maps are not registered development or held-out evaluations.

The installed Steam 15.3 binary passed the bounded `-SmokeTest -Seed 20261002`
capture check at
`C:\Users\imsa\AppData\Local\OpenTTD-RL\demonstrations\20261002-094318-smoke-9e79498d`.
The null video driver verified initial/exit saves, command-log creation, the native
setup pause record and a zero process exit; it did not exercise human mouse input
or a playable-company demonstration. Two earlier failed launcher checks are
retained beside it. A Steam version change is refused pending requalification.

The initial desktop shortcut failed before launching the game because Explorer
does not inherit Codex's Git path. The launcher now resolves the installed/bundled
Git executable explicitly (or accepts `-GitExecutable`), checks its exit status,
and imports the running PowerShell edition's built-in modules. Initialization
failures retain `launcher-error.log` and `recording.json`; interactive failures
show an error dialog. No global PATH or PowerShell configuration is changed.

Logging is enabled in the session's `scripts/autoexec.scr`, before game generation,
instead of with `-d`. The latter opens a Windows debug console whose QuickEdit
selection can stall startup. The final desktop-environment smoke passed in
`20261002-095916-smoke-d23cfabe`. The actual desktop shortcut then opened a playable
GUI and wrote `save/initial.sav` in `20261002-095952-human-066d342d`; its native log
also records human construction. That session was left running for the user.
Earlier failed starts are retained. These checks establish capture startup, not
replay equivalence, a successful bus trajectory or learning.

The first human session now contains manual saves and commands for two buses
with separate two-stop routes sharing one station. An allowlisted, hash-checked
snapshot through the `Cartborough Transport, 1955-01-25.sav` save record is in
that session's `audits/two-routes-20261002-100835-7926bd5c` directory. The snapshot
has the initial save, four manual saves, and the exact command-log prefix through
the selected save; later live gameplay is excluded. Order payloads were checked
against upstream tag 15.3. These are intended command sequences, not confirmed
deliveries or profits. The native replay and supported action mapping were
subsequently verified in the human-learning workflow above.

That session subsequently finished with four distinct bus routes and a clean
recorder exit. The final manual save is `Cartborough Transport, 1967-09-01.sav`;
the exit save is also retained. A verified copy of the complete capture is under
`%LOCALAPPDATA%\OpenTTD-RL\demonstrations\completed\20261002-095952-human-066d342d-b8b26671`.
It includes a lossless structured event timeline and the owner's verbatim strategy
annotation: phased expansion, careful initial borrowing, terrain-aware roads,
dense stop placement, limited bus capacity, and later loan repayment. Initial
and exit saves both passed isolated native load checks; results are in sibling
`verification-20261002-101536-b47f8d1c`. Loading is not replay verification or a
learning result. Preserve timing without labelling every inter-command gap WAIT.
The completed native replay above uses the pinned serialized-command dispatcher,
captures public state before supported decisions and confirms execution results.
The short-episode economics helper still cannot establish lifetime operating
totals for this long demonstration; the replay compares actual saved cash/debt
and public finance fields instead.

## Portable Vast.ai recovery study (September 25)

The [single-GPU package](../deployment/vast/README.md) builds and qualifies the
native engine/trainer before registering A0-A3. It preserves three fixed seeds,
the 8,192-decision budget, complete development matrices, failures/early stops,
and a conditional one-access generalization confirmation. Use a 1,500 GB
persistent volume; initial execution requires 1.25 TB free. Source and runtime
must remain fixed after registration. No instance rental, publication, or push
is part of the launcher.

`train_v2.py` now supports opt-in `--policy-loss choice-weighted`,
`--asset-potential`, `--recovery-diagnostics`, `--training-reset-probes`, and guide
`one-bus-public-plan-v4`. Historical defaults retain their original loss and UPDATE
fields. The asset potential is an explicit finite-episode clipped-capital history
ledger, not a state-only resale valuation. Only the supported one-bus action set
is accepted. Value loss still uses all transitions; choices-only policy loss does
not eliminate Adam momentum or shared-trunk drift.

The study's prospective protocol 2 selects `--gradient-norm fp64-v1` for every
arm. Only clipping's L2 reduction uses float64; the model, gradients and Adam
remain float32. This addresses measured accumulation error while preserving the
fixed 1e-4 agreement gate. Historical clipping stays the default reference mode.
See [the numerical investigation](V2_GRADIENT_NORM_2026-09-25.md) for evidence,
checkpoint binding and the unchanged study criteria.

`studies/unattended_v2.py` orchestrates build, correctness, registration, training,
development selection and conditional held-out confirmation. Training checkpoints
are episode-reset boundaries. Interrupted segments preserve their ancestry and
resume optimizer/RNG state; failed learning seeds cannot be replaced. Ordinary
inference/control CLIs still reject held-out splits. The isolated
`studies/heldout_v2.py` path requires frozen, reverified eligibility from every arm.

See [the refactor evidence record](REFACTOR_2026-09-25_STATUS.md) for actual local
checks and limitations. The pinned image and its complete native CPU/CUDA bundle
passed locally in a container, including exact checkpoint resume. The selected
Vast host still runs its own qualification before registration; no study learning
result is claimed here.

## What we are continuing

Keep the existing C++ PPO and source-integrated OpenTTD environment. The immediate
target is a small passenger-bus agent that learns from real game observations,
legal actions, and economic rewards. Extend to the V2 transport systems after this
loop is reproducible on the owner's machine. MCP opponents come after a reliable
shared observation/action boundary, not before basic training works.

There are two different learning paths in the repository:

| Path | What supplies transitions and rewards | What a successful run establishes |
| --- | --- | --- |
| V1 live PPO | OpenTTD worker processes through the M03-M06 bridge | Full development episodes demonstrate learned passenger service; greedy reliability and efficiency remain open |
| V2 M22 campaign | Fixed native-qualified corpus and per-action reward tables | Program-selection learning on that corpus |

`scripts/dev/train_live.py` reuses `m08.train_architecture`, the existing trainer
client, PPO implementation, masks, GAE semantics, and development evaluator.
It records locally compiled binary hashes instead of demanding the historical
release executable hash. Release validators and their expected hashes are intact.

Current development evidence: three independently trained balanced-reward MLPs
with 64-step rollouts sustain all 18 sampled development episodes, averaging
1,514 passengers and 4,670 operating profit. Mean cash after capital is -3,745;
the one-bus script is more cash-efficient. Greedy construction succeeds in 4/6
episodes. The frozen 36-episode held-out confirmation passed all its registered
criteria: sampled play sustained 18/18 episodes, averaging 2,017 passengers,
6,023 operating profit and -2,488 cash after capital. One-bus remains more
cash-efficient, and greedy succeeds in 4/6. Final results must not drive tuning.
Reset-boundary CUDA resume reproduced 512 continuation transitions exactly;
native/ONNX replay matched 4,096 transitions; the exported network ran visibly on
both development maps, including the newly selected 64-step model. These are
narrow V1 results on fixed maps, not general OpenTTD competence.
[PROGRESS.md](PROGRESS.md) retains the comparisons,
failed experiments and current hypotheses. The initial smoke below is historical.

## September 25 evaluation and study preparation

The full recovery program remains active; see
[its coverage/evidence record](REFACTOR_2026-09-25_STATUS.md) and
[the frozen protocol](V2_RECOVERY_PROTOCOL.md). Do not launch A0-A3 until the
execution and held-out safeguards, recovery mechanisms and resource checks pass.
Protocol 1 remains immutable. Protocol 2 records the numerical amendment before
execution; its scientific thresholds and workload are unchanged.

`infer_v2.py` now defaults to `--split development`. Training-map diagnostics
require `--split training`; ordinary launchers still forbid held-out splits.
For prospective evaluations always pass both `--split development --map-seed N`.
The registered matrix is eight maps times one greedy and three sampled games
per final model. `evaluate_guide_v2.py --mode sampled` preserves historical uniform
sampling. `--mode greedy` takes the lowest legal candidate row when uniform
probabilities tie. Public scripted controls preserve their fixed ordering in both
modes; repeated deterministic controls are not independent trained models.

`report_learning.py`, `report_credit_experiment.py` and `report_v2_learning.py`
now retain per-map, per-training-seed and continuous-window outcomes, exact paired
differences, signs and a fixed-seed nested bootstrap. Original V1 t intervals are
unchanged. The V2 reader rederives economics from hash-identified native traces,
checks reset projection/state continuity/final weights, and pairs only identical
guide/source/reset/action-mode controls. Historical controls without explicit mode
require `report_v2_learning.py --legacy-sampled-controls`; this does not qualify
them for the new protocol. Missing and duplicate cases fail. A one-model nested
interval describes map/action variation only. The privileged M09 script remains
distinct from public-information controls.

Reproduce the retained report migration in WSL, from this checkout:

```bash
RL_ROOT="$HOME/.local/share/openttd-rl"
python scripts/dev/studies/verify_report_migration.py \
  --v1-comparison "$RL_ROOT/runs/balanced-three-seed-comparison-01/comparison.json" \
  --credit-comparison "$RL_ROOT/runs/balanced-roll64-three-seed-comparison-01/comparison.json" \
  --v2-comparison "$RL_ROOT/runs/v2-entropy-learning-01/comparison.json" \
  --candidate entropy001 --output "$RL_ROOT/runs/report-migration-new"
python scripts/dev/power_table.py \
  --comparison "$RL_ROOT/runs/report-migration-new/v1/comparison.json" \
  --output "$RL_ROOT/runs/power-table-new"
```

The planning table reproduces the observed paired t width and estimates effects
for 3/5 training seeds, 2/8 maps and three action seeds. Its random-effects and
noncentral-t assumptions are explicit; it does not establish V2 power or change
acceptance thresholds. `studies/estimate_cost_v2.py` takes `--training`, `--neural`
and `--controls` lists of completed retained run directories, `--power` pointing
to `power.json`, and a new `--output`. It streams large request logs and records
every input hash, observed runtime and artifact size in `cost.json`/`cost.md`.

The completed `refactor-study-cost-01` estimate used the entropy study's one
8,192-decision training run, all eight development neural games and six uniform
controls. Its exact input paths are in `cost.json`. The mandatory 12-model,
512-game matrix with verified control reuse has a sequential lower bound of
about 41-42 hours and projects 654-656 GiB retained storage, versus 670 GiB free
at audit. It excludes an eligible 160-game held-out confirmation and unrecorded
neural startup/archive time. Lossless I/O reduction and measured performance
work therefore precede the large study. Existing models and evidence are retained.

## Initial local validation (2026-09-23)

The RTX 2070/WSL2 setup completed `live-cuda-02`: eight PPO updates, 1,024 real
OpenTTD transitions, model export, and both development evaluations. The seed was
20260923 and the architecture was `structured-mlp-v1`. Mean training rollout
reward went from -0.044775 on update 1 to +0.206734 on update 8. Both 64-step
development probes delivered **zero passengers and zero income**. This validates
the pipeline, not playing competence or a generalization claim. No training
episode reached its 512-action horizon during this short run.

Checks passed: 136 repository fast tests, 97 native game tests, seven native PPO
tests (including the CPU/CUDA export regression), eight development orchestration
tests, nine existing M09 evaluation tests, and all three architecture learning
smokes on CPU and CUDA. The full historical release/evidence suite was not run.

The Linux artifacts are in `~/.local/share/openttd-rl/runs/live-cuda-02`.
A local copy of the successful run, model, smoke reports, and test logs is in
`runs/2026-09-23/` inside the checkout (ignored by Git). The failed first run is
retained separately. The immediate research task is longer, matched-budget
training with full-episode development baselines before claiming improvement.

## Host and dependencies

Use Ubuntu 24.04, directly or under WSL2. The services use POSIX pipes. Keep build
outputs on the Linux filesystem for speed even if source lives on the Windows
drive. The current checkout is at:

```text
C:\Users\imsa\Documents\OpenTTD\openttd-cuda-rl
/mnt/c/Users/imsa/Documents/OpenTTD/openttd-cuda-rl
```

The parent is OpenTTD's user-data folder. Do not install development executables
over the normal game or write experiments into the user's saves/configuration.

The local development profile uses Python 3.12, GCC 13, CMake 3.28+, Ninja,
OpenSSL development headers, and PyTorch 2.9.1's C++ libraries. An RTX 2070 is
compute capability 7.5. `local.py` discovers this instead of using the historical
RTX 5070 `12.0` setting. CUDA runs are explicit and never fall back to CPU.

One-time environment setup in a WSL terminal (the current machine is already set
up):

```bash
cd /mnt/c/Users/imsa/Documents/OpenTTD/openttd-cuda-rl
python3 -m venv ~/.local/share/openttd-rl/venv
source ~/.local/share/openttd-rl/venv/bin/activate
python -m pip install torch==2.9.1 --index-url https://download.pytorch.org/whl/cu128
python -m pip install jsonschema==4.26.0 numpy==2.2.6
python scripts/dev/local.py doctor
```

`uv venv` and `uv pip install --python ...` are equivalent. The wheel provides
the CUDA 12.8 tensor runtime; this machine also has a CUDA 12.6 toolkit at
`/usr/local/cuda`. The current native targets are C++ callers of LibTorch, with
no project CUDA kernels. Do not assume that this combination validates future
custom kernels: add a compatible toolkit/kernel test when introducing `.cu` code.
GPU drivers are managed separately; the scripts do not install or replace them.

## Build and verify the existing C++ implementation

```bash
source ~/.local/share/openttd-rl/venv/bin/activate
python scripts/dev/local.py build --cuda-root /usr/local/cuda --jobs 2
python scripts/dev/local.py test
python scripts/dev/local.py smoke --device cpu \
  --output ~/.local/share/openttd-rl/runs/cpu-smoke-01
python scripts/dev/local.py smoke --device cuda:0 \
  --output ~/.local/share/openttd-rl/runs/cuda-smoke-01
```

Default build directory: `~/.local/share/openttd-rl/build/ppo`. Override with
`--build-dir`. Use a different directory when changing Torch environments to
avoid CMake retaining another environment's libraries. Output run directories
must be new; old results are never overwritten. `run.json` records the source
state, host, binary hash, result, and claim boundary; `learning.json` contains
the three-architecture learning smoke results. These are synthetic PPO checks.

The native CTests cover PPO math, independent differential vectors, learning,
architectures, checkpoint recovery/corruption, and evaluation serialization.
The export regression also verifies that saving preserves live parameter storage,
device, values, inference, Torch RNG, and subsequent optimizer updates for all
three architectures. The local build enables its CUDA variant when a GPU is
visible (seven tests on this host; six for a CPU-only test configuration).
The development build links GCC's standard library before Torch to avoid wheel
filesystem symbols intercepting checkpoint directory operations on this host.

The first live CUDA run exposed a separate existing export bug:
`save_evaluation_model` moved the trainer's own module to CPU, leaving its device
contract set to CUDA. The model file was valid, but the next inference failed.
Export now writes a CPU tensor snapshot without moving or reinitializing the
module. This also preserves optimizer parameter references and avoids reseeding
Torch. The original failed experiment remains under `runs/live-cuda-01` in the
Linux artifact directory; it must not be relabeled as a completed run.

## Prepare and build the existing game integration

```bash
python scripts/dev/prepare_engine.py --output ~/.local/share/openttd-rl/engine
cmake -S ~/.local/share/openttd-rl/engine/source \
  -B ~/.local/share/openttd-rl/engine/build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DOPTION_RL_ENVIRONMENT=ON \
  -DOPTION_RL_NEURAL_AGENT=OFF -DOPTION_USE_ASSERTS=ON -DOPTION_DEDICATED=ON
cmake --build ~/.local/share/openttd-rl/engine/build --parallel 4
```

Preparation calls the existing V1 source composer, validates every resulting
Git tree, and generates only the four training and two development scenarios.
It preserves the upstream submodule and produces an isolated source tree.

Download [OpenGFX 8.0](https://cdn.openttd.org/opengfx-releases/8.0/opengfx-8.0-all.zip),
extract `opengfx-8.0.tar`, verify its SHA-256, and copy it into the engine build's
`baseset/` directory:

```text
9389bcb0807058c80bd95121e978f05d9ef86b4b1bc3ac2da8da8bb02456043c
```

This is the asset required by the existing scenario contract. The current local
download is cached in `.cache/opengfx/`, excluded from Git. Then run:

```bash
cp .cache/opengfx/opengfx-8.0.tar ~/.local/share/openttd-rl/engine/build/baseset/
ctest --test-dir ~/.local/share/openttd-rl/engine/build --output-on-failure
```

## Train on real OpenTTD transitions

```bash
python scripts/dev/train_live.py \
  --trainer ~/.local/share/openttd-rl/build/ppo/m08_trainer \
  --openttd ~/.local/share/openttd-rl/engine/build/openttd \
  --instance-dir ~/.local/share/openttd-rl/engine/instances \
  --device cuda:0 --architecture structured-mlp-v1 --seed 20260923 \
  --updates 2 --evaluation-steps 64 \
  --output ~/.local/share/openttd-rl/runs/live-cuda-01
```

Start small: each update collects 128 transitions across four real games. Use
`--device cpu` for the reference, and `spatial-cnn-v1` or `combined-cnn-mlp-v1`
to exercise the existing spatial networks. More GPU work does not necessarily
mean faster end-to-end training; report collection and update time separately.

Each successful run retains training metrics, embedded pipeline probes on both
development scenarios, and inference weights under `models/`. New records name
the probes `pipeline_probe` with `claim: "not an evaluation"`; `quarter_income`
is the native quarter counter, not lifetime income. Use `evaluate_live.py` for
full economic evaluation. The exported
model is not an optimizer-resume checkpoint; use the separate native reset
checkpoints below to continue training. Failed runs retain a failure
record, `training.log`, and available diagnostics. This developer route does not run any held-out
final manifest or claim a release gate.

New development trainers audit behavior log probabilities before each update,
rejecting maximum absolute error above 1e-4 before optimizer or shuffle mutation.
The frozen UPDATE response remains unchanged. Separate development requests
7 (versioned ACT backend INFO) and 8 (versioned last replay error/sample count)
populate `act_distribution`, `trainer_diagnostics`, and `behavior_replay` in
`run.json`. Older binaries require an explicit fused-policy configure flag in
their adjacent build record; their unavailable replay query is recorded as such.
`compare_training_backends.py --require-exact` requires identical traces, update
metrics and final model identities even when comparing different binaries.

## Checkpoint and resume at native resets

For ordinary 512-action episodes with 32-action rollouts, all four games normally
reset every 16 updates. Request checkpoint publication at those boundaries:

```bash
python scripts/dev/train_live.py \
  --trainer ~/.local/share/openttd-rl/build/ppo/m08_trainer \
  --openttd ~/.local/share/openttd-rl/engine/build/openttd \
  --instance-dir ~/.local/share/openttd-rl/engine/instances \
  --device cuda:0 --seed 20260923 --updates 16 --evaluation-steps 512 \
  --bridge-validation fast --checkpoint-interval 16 \
  --output ~/.local/share/openttd-rl/runs/checkpoint-training-new

python scripts/dev/train_live.py \
  --trainer ~/.local/share/openttd-rl/build/ppo/m08_trainer \
  --openttd ~/.local/share/openttd-rl/engine/build/openttd \
  --instance-dir ~/.local/share/openttd-rl/engine/instances \
  --device cuda:0 --seed 20260923 --updates 16 --evaluation-steps 512 \
  --bridge-validation fast --checkpoint-interval 16 \
  --resume ~/.local/share/openttd-rl/runs/checkpoint-training-new/checkpoints/update-000016 \
  --output ~/.local/share/openttd-rl/runs/checkpoint-resumed-new
```

`--updates` means **additional** updates after restoration; native counters remain
cumulative. Keep the seed, architecture, device, horizon, rollout length and reward
mode identical. Checkpoints bind the trainer/engine hashes, training templates,
collection code and configuration. Recreated reset observations and masks must
match before training resumes. An early terminal can desynchronize games; such a
boundary is recorded as skipped instead of publishing a misleading recovery file.

The native archive includes model parameters, Adam moments/steps, counters, the
three mutable native RNG streams, Torch CPU and training-device RNG state, and
model mode. Checkpoint-enabled training uses deterministic cuDNN convolution
selection and records that choice. This matters for CNNs: preserving seeds alone
does not remove nondeterministic GPU reductions. Exactness is a same-host,
same-runtime claim at synchronized resets, not arbitrary mid-game or cross-device
recovery. Historical M07 checkpoint files and release trainer options remain
separate; the new requests are compiled only by the development build.

New runs retain a source patch plus new development files under `source/`.
Development builds retain the corresponding archive path in
`development-build.json`. Reconstruct older source in an isolated checkout before
resuming an older checkpoint if collection code has changed.

To evaluate an earlier saved checkpoint without collecting more experience:

```bash
python scripts/dev/export_checkpoint.py \
  --trainer ~/.local/share/openttd-rl/build/ppo/m08_trainer \
  --training-run ~/.local/share/openttd-rl/runs/checkpoint-training-new \
  --checkpoint ~/.local/share/openttd-rl/runs/checkpoint-training-new/checkpoints/update-000016 \
  --output ~/.local/share/openttd-rl/runs/checkpoint-export-new
```

The completed training run must register that checkpoint. Export verifies the
native binary, configuration, payload and counters before restoring into C++.
Use the resulting `run.json` model path with `evaluate_live.py` or the ONNX export
workflow. This is inference-only export; it neither resumes the environment nor
weakens the collection-source checks for training recovery. Final-checkpoint
export reproduced the original CNN model identity exactly in the native check.

To exercise a bounded real-game recovery comparison:

```bash
python scripts/dev/verify_live_resume.py \
  --trainer ~/.local/share/openttd-rl/build/ppo/m08_trainer \
  --openttd ~/.local/share/openttd-rl/engine/build/openttd \
  --instance-dir ~/.local/share/openttd-rl/engine/instances \
  --device cuda:0 --output ~/.local/share/openttd-rl/runs/resume-check-new
```

This compares eight uninterrupted updates with four updates plus a restored four,
using 128-action training episodes. It requires identical continuation metrics,
four full action/economic traces, and final exported model identity. Its one-step
development probes are only workflow checks, not gameplay evaluations.

## Complete-episode development baselines and policy replay

The completed held-out confirmation is a separate, frozen route. Its registration
binds all three selected models, evaluation code, native executables, simulation
budgets and acceptance criteria. Reproduce it from the matching archived source:

```bash
python scripts/dev/evaluate_registered.py \
  --registration "$RL_ROOT/runs/heldout-balanced-roll64-registration-02/registration.json" \
  --output "$RL_ROOT/runs/heldout-reproduction-new"
```

The registration's companion SHA-256 file and original model paths are required.
Ordinary `evaluate_live.py` refuses reserved final instances. The confirmation
passed all seven criteria in 36 episodes; see `PROGRESS.md` for the complete
comparison and the two zero-episode setup failures preceding the explicit
registration amendment. Future training must use training/development evidence,
not these reserved results.

The default training command above is a short pipeline check. A normal V1
episode is 512 actions at 128 ticks per action. Use the following evaluator for
gameplay claims; it runs every selected episode to an engine-reported terminal
or time limit and rejects unfinished episodes. It never selects final scenarios.

Development builds also expose the existing PPO coefficients through
`train_live.py --entropy-coefficient 0.01 --gae-lambda 0.95`. These defaults are
unchanged. Checkpoints bind nondefault values, and inference checkpoint export
restores them. A nondefault value requires a rebuilt development trainer; older
binaries fail explicitly. Higher entropy and longer GAE traces are experimental
options, not demonstrated improvements. `--credit-trace` records scalar rewards,
values and boundary flags entering C++ after any reward transform. After training,
`audit_credit.py --training-run RUN --output NEW_REPORT` reconstructs them offline,
checks native explained variance and groups advantages by action family. This
analysis never supplies training advantages or changes the native PPO update.
`plot_credit_trace.py --training-run RUN --output NEW_FIGURE` draws the first
rollout with an explicitly offline lambda counterfactual; use the analysis Python
environment with matplotlib. `report_credit_experiment.py --axis rollout` (or
`lambda`) compares complete final-model evaluations using `--reference` and
`--candidate` run directories, plus `--baseline`, `--one-bus` and `--output`.
Supply one matched seed pair or all three independent seeds. Different trainer
binaries additionally require the passed verification JSONs via
`--default-equivalence`; settings and experience must otherwise match the declared
comparison. Consult the current progress log before treating either setting as an
improvement.

```bash
python scripts/dev/evaluate_live.py \
  --openttd ~/.local/share/openttd-rl/engine/build/openttd \
  --instance-dir ~/.local/share/openttd-rl/engine/instances \
  --policies wait random scripted one-bus \
  --seeds 20260923 20260924 20260925 --workers 2 \
  --hypothesis 'Compare complete-episode service and economics before tuning PPO' \
  --output ~/.local/share/openttd-rl/runs/full-baselines-new
```

`scripted` preserves the existing M09 baseline (eight purchases, only bus 0
assigned and started). `one-bus` constructs and operates one bus using only the
public observation and legal mask. `random` samples uniformly over legal actions.
Deterministic baselines run once per map; action-sampling seeds are not new map
seeds or independent training runs. The default uses separate Python processes
so bridge decoding can use multiple CPU cores. `--executor thread` is available
for comparison. `--profile` saves per-episode cProfile data and affects timing.
`--bridge-validation fast` selects the differentially tested table/regex
implementation of the same checksum and canonical-response checks. The default
`reference` preserves the original bitwise/scanner implementation. This option
is also supported by `train_live.py`; it changes validation cost, not PPO or game
semantics. Full-episode byte-equivalence evidence is recorded in the progress log.

To replay saved neural weights, supply `--evaluator`, `--package` using the
`model.path` from a successful training `run.json`, and `--policies greedy sampled`:

```bash
python scripts/dev/evaluate_live.py \
  --openttd ~/.local/share/openttd-rl/engine/build/openttd \
  --instance-dir ~/.local/share/openttd-rl/engine/instances \
  --evaluator ~/.local/share/openttd-rl/build/ppo/m09_evaluator \
  --package /absolute/path/from/training/run.json \
  --policies greedy sampled --workers 2 \
  --hypothesis 'Test the saved policy for sustained service across full episodes' \
  --output ~/.local/share/openttd-rl/runs/policy-replay-new
python scripts/dev/summarize_evaluation.py \
  ~/.local/share/openttd-rl/runs/policy-replay-new
```

The optimizer-free evaluator explicitly runs inference on CPU. CUDA training is
unchanged. Visible playback uses the separate ONNX workflow below.
Each episode keeps actions, exact legal masks, neural probabilities, command
outcomes, rewards, engine termination, and lifetime economic counters. Profit
uses unclipped lifetime deltas, since snapshot income/expenses describe the
current quarter. Capital spend and balance change are separate metrics. Window
metrics require passenger delivery and positive operating profit in every final
128-action window; reward alone is insufficient. See [PROGRESS.md](PROGRESS.md)
for experiment hypotheses, actual results, limitations, and the next iteration.

## Next concrete milestones

1. **Stronger live V2 learning:** the recurrent policy now trains from native
   sequential decisions and resumes at verified resets. Establish improvement
   over uniform/scripted controls under the same public route guide; current
   guided service alone does not show a learned advantage. The human-imitation
   connection is now working; next make the remaining public candidate meanings
   distinguishable, then compare repayment retention, greedy/sampled service and
   cash under a bounded update change before scaling training. The
   October 2 evidence above is the baseline, and extra demonstrations remain
   deferred until the owner resumes that work.
2. **More transport:** native scripted passenger/mail service now works together
   on two development maps. Extend useful neural cargo control and then industrial
   freight. Historical M16 qualification fixtures are not live play.
   Retain executable bus regressions and version new policy inputs explicitly.
3. **Reproduction across changes:** retain V1 reset recovery, ONNX and visible
   replay checks; extend deployment to V2 once useful control is established.
4. **CUDA practice:** preserve the trusted reference and measured masked-policy
   experiment. Its large operation-level speedup did not improve full training
   materially; profile again before choosing another GPU target.
5. **Stronger MCP competition:** a real local LLM has completed a full match
   through the shared boundary, but neither it nor the weak neural opponent
   delivered passengers. Improve competence and retain fair map/role controls.
6. **Economic experiments:** expand the executed paired comparisons with stronger
   agents, reporting service, cash, survival, market share and inference costs
   separately, with uncertainty across independently trained models.

Keep new work small and executable. Historical frozen artifacts are retained;
they should not force every development experiment to reproduce an entire release.

For a construction-frequency experiment, `train_live.py --episode-horizon 128`
uses the engine's existing bounded reset variation on training maps, retaining
native time-limit and bootstrap flags. `256` and the ordinary `512` are also
supported. Development evaluation always restores the normal 512-action reset.
This is an explicitly labeled curriculum: short training episodes do not count
as full-horizon evaluations. New training runs retain native transition outcomes
and economic summaries under `episode-metrics/`, including partial final workers.
The scoped adapter restores the frozen controller after training or an exception;
run each training job in its own Python process.

The current 64-step balanced-reward experiment uses the following explicit
settings. Seed 20260924 has completed service in all eight development episodes;
the three-seed replication is recorded in the progress log. This is a development
recipe, not a held-out qualification:

```bash
python scripts/dev/train_live.py \
  --trainer "$RL_ROOT/build/ppo-credit/m08_trainer" \
  --openttd "$RL_ROOT/engine/build/openttd" \
  --instance-dir "$RL_ROOT/engine/instances" \
  --device cuda:0 --seed 20260924 --updates 64 --evaluation-steps 64 \
  --episode-horizon 128 --rollout-length 64 --training-reward balanced-economic \
  --gae-lambda 0.95 --entropy-coefficient 0.01 --credit-trace \
  --bridge-validation fast --spatial-validation reference --checkpoint-interval 8 \
  --output "$RL_ROOT/runs/balanced-roll64-new"
```

The embedded 64-action probes do not count as full evaluation. Use the completed
run's model path with the eight-episode evaluator command above. Keep
`--spatial-validation reference` for this registered comparison. New development
runs now default to `vectorized`: the isolated three-pair check reproduced all
native traces, PPO metrics and final models exactly, with median 1.147x end-to-end
speedup (range 1.144–1.228x). This is a CPU input-validation improvement. The
vectorized path needs NumPy, retains the original input list, and binds the NumPy
version/mode in checkpoint compatibility. The Torch environment already supplies
the dependency. Native PPO and CUDA math are unchanged.

Further opt-in development experiments leave native game rewards and the
C++ PPO implementation intact:

- `--rollout-length 64 --updates 16` collects the same 4,096 transitions as
  length 32 with 32 updates. The longer segment can contain construction and
  first delivery together. The existing service's frame bound currently limits
  this launcher to 32 or 64 decisions per worker.
- `--training-reward universal-decision-cost` extends M06's 1/64 WAIT penalty to
  all decisions, preventing free town-selection toggles from avoiding it.
- `--training-reward service-potential` adds `0.99 * Phi(next) - Phi(current)`
  to that uniform-cost reward. In the single-company bus scenario, Phi counts
  up to two stops, one depot, one purchased bus, and the presence of a running
  bus (maximum five). Extra buses get no extra potential. True terminals use
  zero potential; time-limit truncations retain the bootstrap state's potential.
- `--training-reward economic` rescales the native bounded terms to delivery
  /128, operating profit /256, and capital spend -/1024, with a uniform 1/64
  decision cost. Other native penalties remain. It adds no progress potential
  and is an explicit alternative economic objective, not a game-accounting change.
- `--training-reward balanced-economic` uses intermediate weights: delivery /64,
  native operating profit /1024, capital -/4096 and a uniform 1/64 decision cost.
  It retains the same clipping, failure terms, rollout masks, behavior log
  probabilities and C++ PPO implementation. This is an opt-in experiment;
  judge passenger service and cash outcomes against complete-episode controls.
- `--entropy-coefficient 0.05` increases the existing native PPO entropy bonus
  from its default0.01. It encourages a broader action distribution; it neither
  changes legal masks nor supplies a scripted action. Nondefault values require
  a newly compiled development trainer. Records/checkpoints preserve the value,
  and invalid/nonfinite values fail explicitly. The default omits the new CLI
  option so earlier development binaries remain usable. Treat changes as
  separately labeled experiments, not matched architecture comparisons.

The potential uses only own-company/public infrastructure counts; it does not
read RNG state, future deliveries, or evaluation data. Per-transition shaping
and raw rewards are retained separately. The ordered reward stream is checked
against the collector before entering PPO. This follows the discounted
[potential-shaping construction](https://people.eecs.berkeley.edu/~russell/papers/icml99-shaping.pdf),
but finite neural training still requires empirical evaluation. These switches
are research options, not established improvements or changed defaults.

## Export and watch a development policy

Run these commands inside the same WSL virtual environment. The development
exporter currently supports the structured MLP. It requires a completed full
development evaluation of that exact model; it does not assign a release PASS.
Install `onnx==1.22.0 onnxscript==0.7.2 onnxruntime==1.28.0` into the existing
environment without replacing its Torch installation. The C++ runtime is the
official `onnxruntime-linux-x64-1.28.0.tgz` release (SHA-256
`a3e1b79d7bb1bf09696ce675f49e4064e6c81f6202b8225624fff0e93f8d6407`).

```bash
RL_ROOT=$HOME/.local/share/openttd-rl
cmake -S training/v1 -B "$RL_ROOT/build/deployment" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DV1_DEPLOYMENT_ONLY=ON \
  -DV1_ONNXRUNTIME_ROOT="$RL_ROOT/deps/onnxruntime-linux-x64-1.28.0"
cmake --build "$RL_ROOT/build/deployment" --parallel 2
python scripts/dev/export_live.py \
  --package /absolute/path/to/native-model-package \
  --evaluation /absolute/path/to/completed-development-evaluation \
  --evaluator "$RL_ROOT/build/ppo/m09_evaluator" \
  --deployment-evaluator "$RL_ROOT/build/deployment/m10_onnx_evaluator" \
  --output "$RL_ROOT/runs/export-new"
```

The resulting `export.json` identifies the ONNX package and numerical comparison.
Use that package with `evaluate_live.py --backend onnx --evaluator
"$RL_ROOT/build/deployment/m10_onnx_evaluator"` and the other evaluation arguments
above. `compare_replay.py --reference NATIVE_EVALUATION --candidate ONNX_EVALUATION
--output NEW_DIRECTORY` checks complete action/state/economic replay equivalence.
Both deployment executables use CPU ONNX Runtime and require no LibTorch.

For an actual native window, install the SDL2 development dependency
(`sudo apt-get install libsdl2-dev`), then build a separate engine tree. The
preparation script applies a development-only overlay; historical patches,
release acceptance checks, and the headless training engine remain intact.

```bash
python scripts/dev/prepare_playback.py \
  --engine-root "$RL_ROOT/playback-engine" \
  --onnxruntime "$RL_ROOT/deps/onnxruntime-linux-x64-1.28.0" \
  --baseset "$RL_ROOT/engine/build/baseset/opengfx-8.0.tar" --jobs 2
python scripts/dev/play_live.py \
  --openttd "$RL_ROOT/playback-engine/build/openttd" \
  --package /absolute/path/from/export.json \
  --instance "$RL_ROOT/playback-engine/instances/m02-template-05.json" \
  --mode greedy --actions 512 --output "$RL_ROOT/runs/visible-new"
```

This bounded command opens a WSLg/SDL window, completes 512 decisions, saves a
native BMP or PNG screenshot and inspection trace, then exits. Add `--watch` to
keep the window open at normal speed; `--actions 0 --watch` runs without a preset
decision limit. Native inspector buttons pause the agent/game or step one action.
Playback accepts only training/development maps 01–06, uses an explicit empty
per-run configuration and OpenTTD `-X` local paths, and refuses the dummy video
driver. Normal OpenTTD saves and configuration are not needed.

The current demonstrated package can be watched without retraining:

```bash
python scripts/dev/play_live.py \
  --openttd "$RL_ROOT/playback-engine/build/openttd" \
  --package "$RL_ROOT/runs/demo-balanced-roll64-s20260924-01/export/fa5f64fc95cebf3ebd71e20eb8f9402078f7875de05407c8f97446d79bbe077f" \
  --instance "$RL_ROOT/playback-engine/instances/m02-template-05.json" \
  --mode sampled --seed 20260923 --actions 512 --watch \
  --output "$RL_ROOT/runs/watch-balanced-roll64-new"
```

This package was selected from development results before held-out outcomes.
Its full native/ONNX replay and both visible development maps passed comparison.
Use a fresh output directory for each launch; maps 05/06 are both supported.

`compare_visible.py --visible VISIBLE_RUN --reference HEADLESS_EPISODE` checks
the same decisions and lifetime economic counters. The GUI records immediately
after each command, before its next 128 ticks; it must be compared with headless
pre-state counters, not the final post-advance totals. See the progress log for
executed replay results and the selected policy's gameplay limitations.

## Interactive V2 development slice

The existing V2 M22 corpus campaign still selects prequalified programs. A new,
separate development adapter exposes the actual M15 bus environment through
OBSERVE, ACT, STEP and CLOSE requests. It currently controls company 0 on maps up
to 128x128; it is not shared-company competition or a trained V2 policy.

```bash
RL_ROOT=$HOME/.local/share/openttd-rl
python scripts/dev/prepare_v2.py \
  --base-source "$RL_ROOT/engine/source" \
  --output "$RL_ROOT/v2-live-engine" --through m15-competence --build \
  --baseset "$RL_ROOT/engine/build/baseset/opengfx-8.0.tar" --jobs 2
python scripts/dev/enable_v2_live.py --engine-root "$RL_ROOT/v2-live-engine" --jobs 2
python scripts/dev/live_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --policy reactive-build --decisions 8 \
  --output "$RL_ROOT/runs/v2-interactive-new"
```

Preparation verifies each frozen source-tree boundary and preserves the original
executable. The overlay reuses native legal-candidate predicates and commands;
it does not alter frozen patches. After editing the development include, use
`enable_v2_live.py --refresh` to archive and rebuild the recorded adapter.
Each experiment needs a new output directory. Default seeds come from the
training split; `--split development` selects only that separate ledger.

The smoke observes the live game, builds a depot and buys a bus, then waits.
It verifies read-only observations, stale/illegal/company rejection, one action
per step and exactly 128 ticks per step. It does not establish passenger service
or learned competence. `worker/transitions.jsonl` contains native before/after
economics; `worker/requests.jsonl` records all requests, rejections and wall time
separately from ticks. The native transport has a 60-second idle timeout that
ends a failed run without advancing simulation. Shared-match scheduling and
company-scoped shared control are described below; timeout outcomes are aborted
matches, not automatic opponent victories.

For complete scripted service through that same live boundary:

```bash
python scripts/dev/service_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --policy one-bus-repay --planner graph --native-site-checks --minimum-route-length 12 \
  --decisions 512 --output "$RL_ROOT/runs/v2-service-new"
```

The planner uses exposed candidates, visible houses and road bits. It connects
two catchments, buys/orders/starts one bus and optionally repays debt while
retaining 10,000 cash. Every primitive still requires its own legal ACT and
128-tick STEP; it never calls the old native SERVICE macro. `--policy wait`,
`--policy one-bus` (no repayment), and `--planner straight` provide controls.
`--split development` uses a separate seed ledger. Planning and execution failures
remain failed runs; a completed episode can still have zero deliveries or losses.
`summary.json` separates operating profit, capital, loan principal and balance
change, with 128-action service windows. These scripts establish interactive
baselines, not neural V2 training or shared-map competition.

The current V2 summaries also reconcile cash: `cash_result_excluding_financing`
is the balance change minus the loan-principal change; `cash_result_before_capital`
adds back net construction/vehicle spending, including resale proceeds. Native
`cur_economy` operating counters exclude `EXPENSES_OTHER`, including the monthly
charge in the pinned engine, so they are a narrower measure. Both native-profit
and positive-cash service-window flags are retained. `report_v2_learning.py
--runs RUN_A RUN_B ... --output NEW_REPORT` rederives these measures from original
native traces without rewriting historical summaries, and rejects mismatched
map/repetition matrices.

`--native-site-checks` uses the engine's actual bus catchment and present cargo
acceptance/production, and avoids constructing new intersections on slopes.
The earlier uncorrected graph planner remains an explicit experimental control;
its development failures are retained in the progress log.

The existing M15 neural architecture can be built on the same local Torch runtime
with `local.py build --v2-policy --build-dir "$RL_ROOT/build/v2-live-policy"
--cuda-root /usr/local/cuda-12.6 --jobs 2`. This separate build preserves V1
checkpoint binaries. CPU/CUDA policy gates use `ctest --test-dir
"$RL_ROOT/build/v2-live-policy" -R rl_dev_v2_ --output-on-failure`.

The live recurrent PPO adapter uses the same C++ GAE and PPO loss as V1. A small
correctness run (not a gameplay training budget) is:

```bash
python scripts/dev/train_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --trainer "$RL_ROOT/build/v2-live-policy/rl_dev_v2_train" \
  --device cuda:0 --updates 2 --episode-horizon 20 \
  --output "$RL_ROOT/runs/v2-ppo-new"
python scripts/dev/infer_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --policy "$RL_ROOT/build/v2-live-policy/rl_dev_v2_infer" \
  --training-run "$RL_ROOT/runs/v2-ppo-new" --device cuda:0 \
  --compare-cpu --decisions 8 --output "$RL_ROOT/runs/v2-inference-new"
```

Use `--device cpu` explicitly for a reference run; compare matching runs with
`compare_v2_training.py --cpu CPU_RUN --cuda CUDA_RUN --output NEW_COMPARISON`.
The trainer collects 32 decisions per update by default, replays consecutive eight-step
sequences with stored initial hidden states and exact masks, and shuffles whole
sequences for four PPO epochs. Native episode resets cut recurrent state and GAE
continuation; time limits still bootstrap the final physical state. By default,
the first four training ledger seeds are used. `--training-map-count N` chooses
the first N seeds from the training ledger in fixed order (currently 1 through
16); no development or final seeds enter collection. The exact ordered seed list
is recorded and bound into checkpoint compatibility. Resume must use the same
map count/order and archived collector source. The reward version and each raw
delivery/profit/capital contribution remain in `trajectory.jsonl`.

`--reuse-bootstrap-tensors` optionally reuses the validated native input frame
from bootstrap at the next action when its state token and company still match.
Every action runs fresh neural inference, including after a PPO update. A real
reset clears the frame, and checkpoint compatibility binds the option. Three
sequential counterbalanced 256-decision CUDA training pairs match all actions,
masks, PPO updates and final weights exactly, with median reference/reuse wall
ratio 1.06168 (5.81% less total time). Startup, source capture, archival and save
are included. This is a local collector optimization, not a CUDA kernel result;
the option remains off by default. The native TENSORS handler already writes
each decision's files once; reuse avoids requesting, rereading and validating
that same frame again in Python, rather than eliminating its first encoding.

The development trainer also accepts `--rollout-length 64`. This collects twice
as many observations before an update, while keeping eight-step recurrent
sequences and four PPO epochs. GAE sees the longer observed return window;
backpropagation through recurrent state still spans eight decisions at a time.
At matched experience, halve the update count: 32 updates of 64 decisions equal
64 updates of 32 decisions. Update timing and advantage-normalization grouping
also change, so this is not an isolated test of reward delay. The new build's
default CUDA behavior matches the preserved fixed-32 trainer exactly, and its
64-decision CPU/CUDA time-limit check passes the existing 1e-4 tolerance. Guided
64-step reset recovery also passes exactly on CPU and CUDA. The matched-budget
single-seed diagnostic improves sampled operating profit modestly, from 3,179
to 3,833 across two development maps, but greedy still fails both depot stages;
it does not meet the registered criterion for replication. Continuing that
archived run to 4,096 decisions establishes greedy service on both maps. Across
three action-sampling seeds, however, its mean sampled profit is 3,573 versus
3,807 for the earlier model and 3,682 for uniform with the same guide. Conditional
sampling intervals are wide; the failed advancement criterion remains failed.
See the progress log for full economic results and the preserved source needed
to resume that older checkpoint.

With a fresh build containing the rollout option, reproduce
the 256 versus 128-plus-128-decision check using `verify_v2_resume.py --trainer
TRAINER --openttd ENGINE --device cuda:0 --guidance one-bus-public-plan-v1
--rollout-length 64 --output NEW_CHECK`. At horizon 128, checkpoint intervals are
multiples of two 64-step updates. Resume with the same rollout length, binaries
and archived collector source.

The current development adapter additionally accepts `--rollout-length 128`
and `--gae-lambda NUMBER` in [0,1] (default .95). Build into a fresh directory
using `local.py build --v2-policy --build-dir NEW_BUILD --cuda-root /usr/local/cuda-12.6 --jobs 2`.
Native GAE/PPO remains the trusted implementation, with four epochs and eight-step
recurrent gradients. A rollout of 128 at horizon 128 aligns each update with a
reset; 16 updates collect 2,048 decisions. This changes return boundaries,
normalization and update cadence, and removes mid-episode weight changes with
carried recurrent state. It has not yet demonstrated improved learning.

The new binary exactly preserves the recorded 32-step CPU/CUDA and 64-step CUDA
defaults. The 128/lambda1 CPU/CUDA check passes all 128 native decisions across
six time limits, with max metric error 2.25e-5 within the existing 1e-4 tolerance.
Exact 128-step reset recovery passes for CPU/.95 and CUDA/1. Reproduce with:

```bash
python scripts/dev/verify_v2_resume.py \
  --trainer "$RL_ROOT/build/v2-live-full-return-02/rl_dev_v2_train" \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" --device cuda:0 \
  --guidance one-bus-public-plan-v1 --rollout-length 128 --gae-lambda 1 \
  --training-map-count 16 --reuse-bootstrap-tensors \
  --output "$RL_ROOT/runs/v2-return-resume-new"
```

Checkpoint intervals at horizon/rollout 128 can be any positive whole update
count. Resume requires the same return settings, tensor-reuse mode, binaries
and archived collector source. The numeric/return/rejection proofs are in
`runs/2026-09-24/v2-full-return-01/checks/`; they demonstrate correctness, not
playing strength.

Checkpoint file hashes bind a particular saved artifact. Do not use raw native
checkpoint bytes to compare independently started runs: LibTorch's Adam archive
contains process-specific parameter IDs and unordered state serialization.
Compare the model and optimizer tensors, steps/options, RNG, recurrent state
and counters by native parameter order, then verify resumed behavior. The
development map-coverage diagnostic preserves a failed byte-equality check and
its exact logical-state comparison in the progress log.

`inference-weights.pt` is **inference-only**. Development V2 optimizer/RNG recovery
uses separate reset checkpoints; raw-input V2 ONNX export is described below. Build the
current adapter into a separate directory before using the new requests:

```bash
python scripts/dev/local.py build --v2-policy \
  --build-dir "$RL_ROOT/build/v2-live-resume" \
  --cuda-root /usr/local/cuda-12.6 --jobs 2
python scripts/dev/train_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --trainer "$RL_ROOT/build/v2-live-resume/rl_dev_v2_train" \
  --device cuda:0 --seed 20260923 --updates 4 --episode-horizon 128 \
  --checkpoint-interval 4 --output "$RL_ROOT/runs/v2-checkpoint-new"
python scripts/dev/train_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --trainer "$RL_ROOT/build/v2-live-resume/rl_dev_v2_train" \
  --device cuda:0 --seed 20260923 --updates 4 --episode-horizon 128 \
  --checkpoint-interval 4 \
  --resume "$RL_ROOT/runs/v2-checkpoint-new/checkpoints/update-000004" \
  --output "$RL_ROOT/runs/v2-resumed-new"
```

Updates are additional after restoration. Save intervals must align with episode
resets (four updates for 128 decisions); early terminals can make a boundary
ineligible, in which case it is recorded as skipped. Checkpoints retain model,
Adam, recurrent state, native/Torch RNGs, mode and counters. The next training-map
reset is recreated and its public observation and native/sampling tensor hashes
must match before restoration. Binary, collection code, guide, reward and schema
identities must also match. Source archives allow older runs to be reconstructed.

Same-host reset recovery passed an unassisted real-game comparison on CPU and
CUDA: eight uninterrupted updates versus four plus four restored, with exact
continuation metrics, 128 native action/economic transitions and final weights.
`verify_v2_resume.py --trainer TRAINER --openttd ENGINE --device cuda:0
--output NEW_CHECK` reruns that check. This does not establish arbitrary mid-game
or cross-device recovery. CUDA initially failed even before saving because the
graph encoder's scatter reductions were nondeterministic. The current native
trainer requires strict deterministic algorithms and a process-local cuBLAS
workspace profile; these settings are part of checkpoint identity. Merely setting
a seed or deterministic cuDNN did not suffice. Unsupported deterministic operations
fail instead of silently relaxing the claim.

The final deterministic trainer also passed the guided CUDA comparison, including
every saved guide mask and actor value. `verify_v2_checkpoint_boundaries.py
--trainer TRAINER --checkpoint SAVED_RESET_DIRECTORY --output NEW_CHECK` verifies
nine native state/publication rejection cases using that checkpoint's archived
public reset tensors. It does not collect a new game trajectory. Exact recovery
remains limited to the declared reset boundary and matching host/runtime.

The V1 recovery/export workflow above remains available. Completed V2 workers retain tensor binaries as verified
lossless `.bin.gz` files alongside their original metadata (decompress to the
metadata's `.bin` filename before offline native replay). Public tensors redact
map/simulation seeds and private future breakdown timers. Live inference and
scripted control share the same candidate keys, native commands and tick budget.

An optional planner-assisted curriculum adds
`--guidance one-bus-public-plan-v1` to `train_v2.py`. It restricts sampling to the
next exposed primitive from a public road plan, WAIT, and affordable repayment.
Native legality is retained separately. The exact filtered mask and behavior
log probability enter C++ PPO, and previewing a bootstrap state never commits a
construction step. If the bounded candidate list drops the next primitive, the
guide tries another exposed step in the same plan or waits. The saved run binds
this configuration and `infer_v2.py --training-run ...` applies it automatically.
Route geometry comes from the planner, so passenger service by itself does not
demonstrate learning. Compare with `evaluate_guide_v2.py --controller uniform`
and `--controller scripted`, using the same engine, development map and full
512-decision budget. `--controller repay-first` adds a fixed financing-order
diagnostic: repay whenever the same guide allows it, otherwise execute its
proposal. All controls use exactly the same guide and legality. This rule can
leave too little cash to buy a bus; guide version 1 aborts when that service
continuation is unavailable. Such an abort is a failed evaluation.
MCP 0.2.2 also loads this guide from the saved run configuration and records its
exact sampling mask at each neural turn. Such opponents are explicitly labeled
neural+public-planner; route geometry is not attributed to learned discovery.
CPU/CUDA shared smoke checks match native actions and masks. Unknown guide
versions fail rather than silently dropping a sampling restriction.

`--guidance one-bus-public-plan-v2` is an optional continuation fix for new
training and baseline runs. When construction is complete but the next bus
purchase/order/start action is unavailable, it proposes the already legal WAIT
action and keeps the episode running. It adds no borrowing or cash. The
underfunded policy replay now records all 512 decisions and zero deliveries;
the fix improves failure accounting, not policy competence. Successful native
play remains unchanged. CUDA reset recovery is exact, with the same qualified
final model bytes, and the actual MCP smoke records the new guide version.

Saved runs bind their guide version, and checkpoint recovery rejects a version
change. For an explicit development diagnostic of existing planner-trained
weights, `infer_v2.py --guidance-override one-bus-public-plan-v2 ...` records
both the original training guide and the execution override. Keep these results
separate from the original evaluation. Omit the override to reproduce the saved
configuration; version 1 remains available. Preserve the archived collector
source when recovering an older checkpoint, as with other collector changes.

### Watch the live V2 network

The optional view-only SDL route uses the same OBSERVE/ACT/STEP boundary and
C++/LibTorch inference. The frozen raw-input 4,096-decision model replayed both
development maps visibly: all 1,024 native decisions and economic outcomes
matched its archived headless runs. CPU/CUDA probability and value errors were
at most 1.2e-7 and 1.91e-6. Native screenshots are retained. This is live neural
control with a public route planner. The optional ONNX deployment path below also
reproduces these complete visible episodes.

Build an isolated display engine, then launch one complete replay:

```bash
python scripts/dev/prepare_v2_playback.py \
  --base-engine-root "$RL_ROOT/v2-live-engine" \
  --engine-root "$RL_ROOT/v2-visible-engine-new" --jobs 2
python scripts/dev/infer_v2.py \
  --openttd "$RL_ROOT/v2-visible-engine-new/build/openttd" \
  --policy "$RL_ROOT/build/v2-live-policy/rl_dev_v2_infer" \
  --training-run "$RL_ROOT/runs/v2-roll64-budget4096-01/train" \
  --device cpu --mode greedy --seed 20260923 --split development \
  --map-seed 1630856436 --decisions 512 --visible \
  --output "$RL_ROOT/runs/v2-visible-new"
```

The qualified local display engine already exists at
`$RL_ROOT/v2-visible-engine-01/build/openttd`; reuse it to skip the build. Use
map seed 155097162 and a fresh output directory for the second development map.
The original headless engine remains available for training. The display build
uses SDL2 and a real X11/Wayland display (WSLg locally); dummy/offscreen drivers
are rejected. It currently supports one company and raw or signed-log weights.

Mouse and keyboard game commands are disabled in this viewer so they cannot
bypass the agent's action budget. Redrawing while waiting for requests preserves
native state, ticks and simulation RNG; closing the window aborts the replay.
The final native 1280x800 image is under `worker/screenshot/`; `run.json` records
its hash and display settings. Each run uses its own empty configuration and
local paths, preserving the user's ordinary game data.

### Export and watch a live V2 ONNX policy

The development exporter supports raw and `signed-log-v1` recurrent V2 weights.
It converts the C++ model's saved parameters, exports twice with identical
bytes, and checks all 512 archived inputs against native C++ inference. A package
binds the graph, source weights, observation schema, preprocessing and guide.
The optional C++ deployment target uses ONNX Runtime 1.28.0 on CPU for the neural
forward pass and retains LibTorch for input validation, masking and sampling.
Raw public tensors enter the graph; signed-log preprocessing is embedded once
inside the exported graph. Training, archive and package modes must agree.
The wrapper selects the recorded mode automatically. CUDA ONNX inference is
still rejected explicitly; CUDA PPO training remains separate.

To watch the already qualified local raw 4,096-decision model:

```bash
RL_ROOT=$HOME/.local/share/openttd-rl
source "$RL_ROOT/venv/bin/activate"
python scripts/dev/infer_v2.py \
  --openttd "$RL_ROOT/v2-visible-engine-01/build/openttd" \
  --policy "$RL_ROOT/build/v2-live-export-01/rl_dev_v2_onnx_infer" \
  --training-run "$RL_ROOT/runs/v2-roll64-budget4096-01/train" \
  --onnx-package "$RL_ROOT/runs/v2-live-onnx-package-01" \
  --device cpu --mode greedy --seed 20260923 --split development \
  --map-seed 1630856436 --decisions 512 --visible \
  --output "$RL_ROOT/runs/v2-onnx-visible-new"
```

Use a fresh output directory for each run. Choose map 155097162 for the second
development scenario. For headless evaluation, omit `--visible` and use
`$RL_ROOT/v2-live-engine/build/openttd`. `--mode sampled` uses the same native
seeded action sampler. The ONNX option requires `--training-run` and explicit
`--device cpu`; omit `--onnx-package` for the existing LibTorch path.

The completed signed-log 8,192-decision model also has a qualified package:

```bash
python scripts/dev/infer_v2.py \
  --openttd "$RL_ROOT/v2-visible-engine-01/build/openttd" \
  --policy "$RL_ROOT/build/v2-financial-export-01/rl_dev_v2_onnx_infer" \
  --training-run "$RL_ROOT/runs/v2-financial-eight-maps-budget8192-01/train" \
  --onnx-package "$RL_ROOT/runs/v2-financial-onnx-package-01" \
  --device cpu --mode greedy --seed 20260923 --split development \
  --map-seed 1630856436 --decisions 512 --visible \
  --output "$RL_ROOT/runs/v2-financial-onnx-visible-new"
```

This model still fails its learning economic gate. Its deployment qualification
does not replace the raw reference or establish stronger play.

For a new build, use the dependency versions and official ONNX Runtime archive
from the V1 export section above. Configure a fresh directory in the existing
Torch environment; the CUDA toolkit below is needed by that installed Torch
build, even though this deployment target runs on CPU:

```bash
cmake -S training/dev -B "$RL_ROOT/build/v2-onnx-new" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DRL_DEV_V2_POLICY=ON \
  -DCMAKE_PREFIX_PATH="$RL_ROOT/venv/lib/python3.12/site-packages/torch/share/cmake" \
  -DPython3_EXECUTABLE="$RL_ROOT/venv/bin/python" \
  -DCUDAToolkit_ROOT=/usr/local/cuda-12.6 \
  -DCUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda-12.6 \
  -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.6/bin/nvcc \
  -DTORCH_CUDA_ARCH_LIST=7.5 \
  -DRL_DEV_ONNXRUNTIME_ROOT="$RL_ROOT/deps/onnxruntime-linux-x64-1.28.0"
cmake --build "$RL_ROOT/build/v2-onnx-new" --parallel 2 \
  --target rl_dev_v2_infer rl_dev_v2_onnx_infer rl_dev_v2_export_oracle
python scripts/dev/export_v2.py \
  --training-run "$RL_ROOT/runs/v2-roll64-budget4096-01/train" \
  --evaluation "$RL_ROOT/runs/v2-visible-full-01/map-1630856436" \
  --policy "$RL_ROOT/build/v2-onnx-new/rl_dev_v2_infer" \
  --output "$RL_ROOT/runs/v2-onnx-package-new"
```

To export another raw or signed-log model, supply its completed training directory and
a complete 512-step greedy development evaluation of those exact weights with
the same guide. Export reads retained tensor archives and never enters a final
evaluation split. `export.json`, `verification.json` and `golden.jsonl` record
the numeric comparison; `manifest.json` is written only after it passes. This
archived-input check is separate from running the package in a fresh game.

The local package has passed four full headless runs (greedy and sampled on both
development maps), with every one of 2,048 native decisions and economic outcomes
equal to its LibTorch references. Complete visible qualification and screenshots
are recorded in the progress log. The public planner continues to supply route
geometry; these checks establish deployment equivalence, not stronger learning.

## Native passenger and mail service

The separate cargo engine adds ordinary truck-stop construction and mail-vehicle
purchase to the live boundary. Build it from the existing composed bus engine:

```bash
python scripts/dev/prepare_cargo_live.py \
  --base-engine "$RL_ROOT/v2-live-engine" \
  --output "$RL_ROOT/v2-live-mail-engine-new" --jobs 2
python scripts/dev/cargo_live.py \
  --openttd "$RL_ROOT/v2-live-mail-engine-new/build/openttd" \
  --controller mail --split development --seed 1630856436 --decisions 512 \
  --output "$RL_ROOT/runs/live-mail-new"
python scripts/dev/coordinated_cargo.py \
  --openttd "$RL_ROOT/v2-live-mail-engine-new/build/openttd" \
  --split development --seed 1630856436 --decisions 512 \
  --output "$RL_ROOT/runs/live-passenger-mail-new"
```

Use `--controller wait` for the standalone control, and repeat with development
map seed `155097162` for the paired comparison. `report_cargo.py --runs RUN_A
RUN_B ... --output NEW_REPORT` requires the same engine, map set and full budget
for each controller and rederives economics from the native traces. It retains
failed episodes. Every run uses a fresh isolated configuration and output path.
The original bus engine, frozen patches and ordinary game data are preserved.
`prepare_cargo_live.py --refresh` archives a prior cargo executable before
rebuilding an edited development include.

Cargo mode advertises `openttd-rl-development-v2-cargo-live-1`, discovers native
mail-capable road vehicles, and exposes current public mail acceptance/supply,
own-vehicle cargo and each own station's bus/truck facility tiles. The controller
uses these locations to protect existing stops and resolve facilities that join
an existing station. Each road, stop, purchase, order and start still consumes
an ordinary action and 128 simulation ticks. Towns produce the mail naturally;
no fixture cargo, forced acceptance or SERVICE macro is used.

The coordinated script sustains both cargo types on the two fixed development
maps, with combined operating profits of 8,749 and 3,419. Construction leaves
cash after capital at -7,363 and -16,039. The earlier failed controllers remain
in the progress log. This is scripted native transport integration. Cargo mode
explicitly rejects the old bus `TENSORS` request; neural mail control and shared
cargo games are not implemented.

## Shared-company games and MCP

The optional shared slice alternates two companies on the same map. A 512-action
global budget gives each company 256 decisions and advances the whole economy
65,536 ticks. `shared_v2.py --openttd ENGINE --output NEW_RUN` checks eight steps;
add `--first-company 1` to reverse the actor order. It verifies ownership,
out-of-turn rejection and redaction of opponent internal fields. Research traces
retain simultaneous financial snapshots for both companies; actor responses do
not include those private snapshots. This is still a limited bus environment.

The MCP adapter uses the [official Python SDK](https://github.com/modelcontextprotocol/python-sdk)
over [stdio](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).
Keep its dependencies separate from the Torch environment:

```bash
uv venv "$RL_ROOT/mcp-venv"
uv pip install --python "$RL_ROOT/mcp-venv/bin/python" 'mcp==2.2.0'
"$RL_ROOT/mcp-venv/bin/python" scripts/dev/smoke_mcp_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --policy "$RL_ROOT/build/v2-live-policy/rl_dev_v2_infer" \
  --training-run "$RL_ROOT/runs/v2-ppo-new" --device cuda:0 \
  --output "$RL_ROOT/runs/mcp-smoke-new"
```

The smoke is a scripted MCP client controlling one company against saved neural
weights; it is **not** an LLM match. `mcp_v2.py` is the actual stdio server and
accepts the same binary/model arguments plus `--company`, `--first-company`,
`--decisions`, `--split` and an optional ledger `--map-seed`. Its tools are
`game_info`, `start_match`, `observe`, `legal_actions`, `submit_action`, `step`
and `wait_turns`, plus `map_region` for a public rectangle up to 32 by 32 tiles.
Company identity is fixed at launch. Stepping also executes the opponent's equal
turn. WAIT batches are limited to eight own turns and still consume every native
action/tick.
The adapter accepts raw and `signed-log-v1` weights. It validates the saved
training/model modes and checks the native policy's preprocessing before starting
the game. For the completed financial-feature policy, use
`--policy "$RL_ROOT/build/v2-financial-export-01/rl_dev_v2_infer"` and
`--training-run "$RL_ROOT/runs/v2-financial-eight-maps-budget8192-01/train"`.
This is LibTorch inference; the MCP adapter does not load an ONNX package.
Both preprocessing modes passed the actual eight-step scripted MCP checks.
The optional focused tests run in the SDK environment:
`"$RL_ROOT/mcp-venv/bin/python" -m unittest discover -s tests/dev -p test_mcp_financial_features.py -v`.
`start_match` and `observe` include the public map; `observe(include_map=false)`
and step results omit its large tile arrays while retaining own state and token.
`start_match(include_map=false)` also permits a compact first observation.
Call `observe` to inspect the updated map after either company constructs.
The native 60-second idle timeout aborts without simulating extra time. Calls,
model outputs, inference wall time and native economics are retained separately.
`mcp_player_console.py` relays JSON-line tool requests through an SDK client for
interactive controllers; it does not choose actions. Completed shared accounting
can be reproduced with `report_shared_v2.py --worker WORKER --output NEW_REPORT`.

The local LLM runner uses the existing Windows Ollama service through a
loopback-only Python bridge. It requires an already-installed model; it does not
download weights, use an external paid API, or alter Ollama/network settings.
First run `local_llm.py --host-python HOST_PYTHON --model MODEL --output NEW_PROBE`
to record a structured tool-call probe. For the installed model used here:

```bash
HOST_PYTHON=/mnt/c/Users/imsa/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe
LOCAL_MODEL=hf.co/unsloth/gemma-4-E2B-it-qat-GGUF:UD-Q4_K_XL
"$RL_ROOT/mcp-venv/bin/python" scripts/dev/play_mcp_llm_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --policy "$RL_ROOT/build/v2-live-policy/rl_dev_v2_infer" \
  --training-run "$RL_ROOT/runs/v2-live-ppo-16u-01" --device cuda:0 \
  --host-python "$HOST_PYTHON" --model "$LOCAL_MODEL" \
  --company 0 --first-company 0 --map-seed 1630856436 \
  --decisions 8 --maximum-model-calls 64 --output "$RL_ROOT/runs/llm-smoke-new"
"$RL_ROOT/venv/bin/python" scripts/dev/verify_mcp_llm.py \
  --run "$RL_ROOT/runs/llm-smoke-new" --output "$RL_ROOT/runs/llm-audit-new"
```

This launches an actual LLM controller through the official MCP client. Use
`--decisions 512 --maximum-model-calls 1600` for the registered full development
budget. The model digest, prompt, tool schemas, bounded context, generation
settings, responses, tool errors, tokens and model wall time are saved. Warmup
precedes native game startup; model requests time out at 45 seconds. Sixteen
consecutive calls without advancing a turn or exhausting the model-call budget
abort with retained evidence. No script replaces unsuccessful model choices.
Optional nullable tool arguments are represented as optional scalar types for
Ollama; native validation remains unchanged. MCP 0.2.1 explicitly identifies
pending actions requiring `step`.

The completed eight-global-step LLM smoke proves this connection, not playing
strength: the LLM issued four stop-building commands at one tile, creating only
one stop, and neither company delivered passengers.
The full 512-decision development match also completed and passed the independent
audit: 256 actions per company, neither delivered passengers. Gemma made 1,272
model calls and 252 recoverable tool errors, taking 2,725.1 seconds excluding
warmup. This establishes actual MCP participation, not playing competence.
Temperature zero and a fixed seed do not
establish exact LLM reproducibility; recorded requests/responses and model
identity support audit. Provider cost is zero for these local requests; hardware
and electricity cost remain unknown. Neural and LLM runtime placement and wall
time are recorded separately from the shared economic clock.

`play_mcp_baseline_v2.py --controller one-bus-repay` (or `wait`) runs a distinctly
labeled scripted controller through the same MCP tools. It accepts the same
engine/policy/training-run/device/output/company/first-company/map-seed/decisions
arguments; it does not invoke an LLM. Use role swaps on the same registered maps
for descriptive comparisons, and preserve failed matches.

`--controller one-bus-repair` adds public road-connectivity checks every 16 own
turns after service starts. If the two existing stops become disconnected, it
plans a detour using currently exposed primitive road candidates; each road
command still consumes its ordinary turn. It does not rebuild the whole service
or use opponent-private observations. Four full map/role comparisons preserved
the fixed script's successful outcomes on one map and restored 818 and899
deliveries in the two roles on the disrupted map. The fixed script delivered zero
there after the opponent built a depot across a public through-road. All four
adaptive runs sustained positive operating/cash service in the final three
windows, but construction still left cumulative cash losses. This is an adaptive
scripted baseline, not a neural capability or a general reliability claim. Its
`repair_checks` and native action trace retain failed plans, spending and
subsequent connectivity checks.

Compare completed/failed registered full matches with:

```bash
python scripts/dev/report_mcp_matches.py \
  --runs "$RL_ROOT/runs/mcp-match-a" "$RL_ROOT/runs/mcp-match-b" \
  --output "$RL_ROOT/runs/mcp-comparison-new"
```

The report verifies common game/neural settings, rederives economic outcomes
from the shared native trace, and audits actual LLM calls when present. It keeps
tool failures, model identity, token counts and inference costs separate from
simulated cash and time; small map/role comparisons do not establish a ranking.

## Repository checks

For lossless compression of completed development logs and tensor snapshots,
see [artifact retention and restoration](STORAGE.md). Keep the latest run,
held-out evidence, source, models and checkpoints protected. This maintenance
workflow does not change training or its archived collector identities.

The optional inference CUDA experiment, its tensor layout, CPU oracle, numerical
tolerances and paired timing commands are described in
[CUDA_EXPERIMENT.md](CUDA_EXPERIMENT.md). It is disabled in ordinary builds.

```bash
python -m unittest discover -s tests/dev -v
bash scripts/v2/verify.sh --tier fast --tools-python /usr/bin/python3
git diff --check
```

The fast suite is a repository check, not live-game evidence. Use contract/full
tiers only with their documented dependencies and artifact roots. See
[V2 verification](project/V2_VERIFICATION.md) for those historical workflows.
On this Ubuntu host, `/usr/bin/python3` has `jsonschema` and shares its directory
with Git. The historical verifier resolves interpreter symlinks and restricts
PATH to tool directories, so the UV training virtual environment is unsuitable
for that wrapper: resolution loses its packages and leaves Git off PATH.
