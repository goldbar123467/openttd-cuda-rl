# 04 — Evaluation bottlenecks

Static review of commit `0595a72`. **No timing, profiling or benchmark was run for
this report.** Every statement is one of:

- **Code-established**: the work provably happens, and its volume follows from
  constants in the code.
- **Recorded**: a measurement the repository's own documents report, cited.
- **Hypothesis**: a plausible cost whose size needs profiling.

Byte volumes are arithmetic on code constants, not measurements.

---

## 1. Measurements already in the repository

None of these is an evaluation-specific timing breakdown.

| Source | What was measured | Relevance |
| --- | --- | --- |
| `docs/PROGRESS_HISTORY_2026-09-23.md:361-373` | A 128-update V1 live CUDA MLP run: 1,216.8 s of collection and optimization, of which 137.4 s were inference calls and 67.8 s update calls. A 2-update cProfile attributed 14.9 s to spatial validation and 16.0 s to bridge decoding out of 34.8 s (instrumented, overlapping). Nsight recorded 16,825 launches, 3,052 stream synchronizations and 3,573 async copies (API side only). | The game, bridge and validation dominate V1 collection; the same code runs in evaluation. |
| `docs/CUDA_EXPERIMENT.md`; `PROGRESS_HISTORY:416-423` | The fused kernel took the masked distribution from 763.70 to 79.39 µs at batch 4 (9.62×). End to end the speedup was **1.0047×** (range 1.0007–1.0087 over two pairs). | GPU operation speed is not the constraint. |
| `CUDA_EXPERIMENT.md` "Subsequent measured CPU bottleneck"; `DEVELOPMENT.md` | Vectorized spatial validation gave a median 1.147× end-to-end training speedup with byte-identical traces. | Python validation of observations is expensive. **`evaluate_live.py` does not use it** (see §2). |
| `PROGRESS.md:1164-1177` | V2 reference run of 5,100.77 s: UPDATE 33.55%, ACT 8.16%, unattributed remainder 58.29% (game requests, REWARD, TENSORS, archival, resets). | The V2 remainder is uncharacterized. |
| `PROGRESS.md:1180-1194` | V2 `--reuse-bootstrap-tensors` saved 5.81% of wall time (median ratio 1.06168). Native TENSORS time was about 21 s. | Frame handling is a measurable cost. |
| `evaluate_live.py:206`, `--profile` (215–220) | Every episode records `elapsed_seconds`; optional per-episode cProfile. | The instruments exist, but no committed evaluation profile. |

---

## 2. V1 complete-episode evaluation: per-decision work

Path: `evaluate_live.py:episode` (74–207) with a native CPU `m09_evaluator`.
Everything below runs **once per decision**, 512 times per episode.

| Stage | Code | Work | Status |
| --- | --- | --- | --- |
| 2a. Python input validation | `evaluate_live.py:118,121-122,138` → `m07.structured` (`run_m07_cpu_ppo.py:111-115`, twice), `m07.legal_mask`, `m08.spatial` (`run_m08_live_architectures.py:58-71`) | A pure-Python `all(...)` over 32,768 spatial values and 256 structured values (structured twice). The vectorized validator (`scripts/dev/policy_inputs.py:5-21`) is applied only inside `train_live.py:137`. **Evaluation uses the slow reference path.** | Code-established; cost is Hypothesis (the recorded training profile suggests it is large) |
| 2b. Request packing | `m09_evaluator_client.py:124-131` | `struct.pack` of 256 + 32,768 floats. The request is 132,142 bytes per decision (5 + 1,024 + 131,072 + 41). | Code-established |
| 2c. Native decode | `m09_evaluator_main.cpp:141-180` | `Reader::f32()` with a bounds check per element: 33,024 calls per decision | Code-established |
| 2d. Native validation | `evaluation_model.cpp:201-221` | `isfinite` plus two range reductions over the 32,768-float spatial tensor | Code-established |
| 2e. Inference | `evaluation_model.cpp:328-344`; INSPECT at `m09_evaluator_main.cpp:209-245` | The MLP forward pass **ignores spatial** (`multimodal_model.cpp:134-139`). `masked_categorical` runs **twice** per INSPECT: once inside `policy.act`, again at 220. There are 41 + 41 float64 values in the response. | Code-established; compute is Hypothesis (small) |
| 2f. Game step | `run_m06_reward_trajectory.py:198-252` | SNAPSHOT (209), then STEP, which advances 128 ticks in OpenTTD. | Round trips code-established; simulation cost is Hypothesis |
| 2g. Observe and mask | `run_m06_reward_trajectory.py:162-196` | OBSERVE (the large JSON with the spatial array), then LEGAL_ACTIONS | Code-established |
| 2h. Bridge validation, per response ×4 | `m03_bridge_protocol.py:187-245` | CRC32C over header + payload. The default `reference` mode loops 8 times per byte in Python (96–103); `fast` is a table loop, still per byte in Python (`bridge_validation.py:27-31`). Then a UTF-8 decode, `json.loads` with a duplicate-key hook, a full canonical **re-serialization** (`json.dumps(sort_keys=True)`) and a byte-scan normalization of both strings (61–93). **`evaluate_live.py` defaults to `--bridge-validation reference` (297).** | Code-established; size of OBSERVE payload unknown (Measure) |
| 2i. Trace logging | `evaluate_live.py:145-153` | One JSON line with `structured_before` (256 floats), a snapshot, reward source and prediction (41 logits + 41 probabilities), followed by `flush()` every decision | Code-established; cost is Hypothesis (moderate) |

Decisions through validated round trips: 4 bridge requests + 1 evaluator request.
All are strictly sequential within an episode.

### Per-episode fixed costs

| Cost | Code | Status |
| --- | --- | --- |
| Spawn an OpenTTD process, load the scenario, RESET, first OBSERVE and mask | `run_m07_cpu_ppo.py:68-96` | Code-established; duration is Hypothesis |
| Spawn an evaluator, initialize LibTorch, read and SHA-256 the manifest and model, load it, hash the parameter state | `m09_evaluator_client.py:73-90`; `evaluation_model.cpp:295-326`; `m09_evaluator_main.cpp:252` | Code-established; small MLP, so likely modest (Hypothesis) |
| Package snapshot hashing before and after | `evaluate_live.py:110,194` | Code-established; small |
| Initial SNAPSHOT and `initial.json` | 104–108 | Small |

### Parallelism and contention

- Episodes run in a `ProcessPoolExecutor(spawn)` with 1–4 workers
  (`evaluate_live.py:266-271, 294`).
- Each running episode uses one Python process, one OpenTTD process and one
  evaluator with **6 intra-op threads** (`m09_evaluator_main.cpp:319`).
- With 4 workers that is up to 12 busy processes plus 24 LibTorch threads. Whether
  this oversubscribes the host is a Hypothesis; `DEVELOPMENT.md` describes a
  WSL2 laptop-class machine.
- The Python GIL is not shared across processes, so bridge decoding parallelizes
  across episodes.
- There is no parallelism within an episode.

### Checkpoint loading

- Evaluation loads only an inference package (`model.pt` + `manifest.json`), once per
  episode, via a new evaluator process.
- Reset checkpoints (`trainer.pt` with the Adam state) are never loaded during
  evaluation. `export_checkpoint.py` converts one to an inference package once.
- Checkpoint loading is **not** a per-decision cost. Its per-episode cost scales with
  the episode count (8 per model for V1, 9 for V2).

### Data transfers

V1 evaluation is CPU-only; there are no host/device transfers. The only large
transfers are the pipe payloads (§2b) and bridge JSON (§2g–h).

---

## 3. V2 evaluation: per-decision work (`infer_v2.py`)

| Stage | Code | Work | Status |
| --- | --- | --- | --- |
| OBSERVE + TENSORS | `infer_v2.py:198-200` | The native side writes about 2.97 MB of tensor files per frame (2,182,927 + 790,528 bytes). Python reads both and SHA-256-hashes them (`checked_tensors`, 24–45). | Code-established |
| Guide | `infer_v2.py:201-203`; `guide_v2.py` | The public planner filters the mask and writes a new candidate file | Code-established; cost is Hypothesis |
| Duplicate state check | `infer_v2.py:204-205` | **A second OBSERVE and TENSORS on every decision**, to prove the state is unchanged | Code-established |
| Policy | `v2_live_infer.cpp:56-75`; `v2_live_input.cpp:145-201` | The native side re-reads about 2.97 MB and runs a finiteness scan per tensor (`Reader::floats` 36). It copies to the device, then runs the forward pass, which includes **about 20 `.item()` host syncs in validators** (`scalable_policy.cpp:17-41, 240-251, 294-297`), and the distribution with 8 more (`ppo.cpp:154-163` ×2). It prints **4,096 probabilities as JSON text**. | Code-established; cost is Hypothesis |
| Python check | `infer_v2.py:211-213` | Parses the 4,096 floats, then sums and mask-checks them in Python | Code-established |
| Optional CPU reference | `infer_v2.py:214-219` | Doubles the inference work when `--compare-cpu` is set | Code-established |
| ACT + STEP | 224–231 | 128 ticks | Simulation cost is Hypothesis |
| Archival at episode end | `live_v2_artifacts.py:7-19` | For each frame file: gzip it, **decompress to verify SHA-256**, then unlink. A 512-decision episode writes about 1.52 GB of raw frames (512 × 2,973,455 bytes). | Code-established volume; time is Hypothesis |

Per decision: 6 game requests + 1 policy request, plus about 3 MB written, about
6 MB read, and one SHA-256 pass over about 3 MB in Python.

The same frame pipeline dominates V2 **training**. There, UPDATE adds five
host→device uploads of every stored transition input per update: the audit pass
plus 4 epochs (`v2_live_train.cpp:151-176`). The recorded UPDATE share is 33.55%
(`PROGRESS.md:1169`).

---

## 4. Where the custom kernel fits

The kernel (`training/dev/fused_policy_kernel.cu`) is **not on any evaluation path**:

- the V1 evaluator is CPU and calls `masked_categorical`;
- ONNX deployment uses ONNX Runtime;
- V2 uses a different, hierarchical 4,096-candidate distribution.

It affects only V1 training collection on CUDA, including the embedded 64-step
probes. See 05.

---

## 5. Proposals to reduce evaluation cost while keeping comparisons trustworthy

Every proposal is **output-preserving**: it must reproduce byte-identical
`actions.jsonl` traces (or V2 `predictions.jsonl` actions) for the same package,
maps and seeds. That is the acceptance gate. The repository already has
`compare_replay.py` for V1 full-trace equality and the paired, counterbalanced
design in `compare_training_backends.py` (33–79).

Ranked by expected value relative to risk:

| # | Change | Why it should help | Keeps results trustworthy because | How to measure later | Risk |
| --- | --- | --- | --- | --- | --- |
| B1 | **Use the vectorized spatial validator in `evaluate_live.py`.** Wrap `run()` jobs with `policy_inputs.spatial_validation(m08, "vectorized")`, or call `policy_inputs.vectorized_spatial` directly; record the mode in `run.json`. | Removes about 33k Python-level checks per decision (2a). The same change gave 1.147× in training. | Same checks, same list returned (`policy_inputs.py:5-21`); differentially tested by `tests/dev/test_policy_inputs.py`. | Evaluate one package twice (reference vs vectorized), alternating order, 3 pairs. Traces must be byte-identical; compare the median `elapsed_seconds` per episode. | Low |
| B2 | **Default development evaluation to `--bridge-validation fast`.** Keep `reference` for reproducing old runs; the registered route already uses fast (`evaluate_registered.py:119`). | Replaces the 8-iterations-per-byte CRC and the byte-by-byte scanner (2h). | Byte-equivalence of the fast mode is tested (`tests/dev/test_bridge_validation.py`) and recorded (`DEVELOPMENT.md`). | Same paired design as B1. | Low |
| B3 | **Native CRC32C.** Optional dependency, such as a vetted `crc32c` wheel, or a tiny C helper built with the dev tree, kept behind the `bridge_validation` switch. | Even the "fast" CRC is a per-byte Python loop. | Differentially test against the reference implementation on recorded frames, including corrupted frames that must be rejected. | Micro-benchmark per frame size, then the B1-style paired episode timing. | Low–Medium (new dependency) |
| B4 | **Skip spatial transport for `structured-mlp-v1` packages** in a development evaluator protocol: a new message type carrying structured + mask only; the evaluator asserts `architecture == structured-mlp-v1`. Still run the frozen OBSERVE, and keep one cheap spatial shape/range check per episode if desired. | Removes about 131 KB of packing, piping, decoding and validation per decision (2a–2d). | The MLP forward provably never reads spatial (`multimodal_model.cpp:134-139`), so actions cannot change. | `compare_replay.py` between old and new protocol runs (exact action/state/economic equality); paired timing. | Medium (new protocol, dev-only) |
| B5 | **Reuse one evaluator process per worker** across episodes. Add a development RESEED message that re-creates the sampling generator from a seed and re-verifies the state hash. | Removes per-episode LibTorch initialization, model load and hashing. | The sampling stream is fully determined by its seed (`evaluation_model.cpp:300`); the parameter-state hash is still checked at each episode end. | Record `evaluator_ready_ns` per episode before the change, to see whether it matters at all. Then byte-identical traces. | Low–Medium |
| B6 | **Evaluator threads = 1 for MLP; tune `--workers`.** | May remove oversubscription (§2 Parallelism). | Thread count can change float reduction order. Require byte-identical traces across settings; if not identical, treat it as a backend change and do not mix results. | Throughput (episodes/hour) over workers ∈ {1..4} × threads ∈ {1, 6}, with the machine otherwise idle. | Low (if gated by equality) |
| B7 | **Buffered trace flushing.** Flush at 128-action window boundaries and on exit or exception instead of every line; keep identical content. | Reduces syscalls and disk sync pressure (2i). | Same bytes at completion; `summarize_evaluation.py` already tolerates a partial last line (27–28). | File hash equality; paired timing. | Low |
| B8 | **V2: stop re-issuing OBSERVE and TENSORS every decision.** Do it on the first decision and every Nth (for example 64); rely on the native stale-token rejection of ACT for the rest. | Removes 2 of 6 game requests per decision. | ACT carries `token=observation["token"]` (224) and the native side rejects stale tokens (`DEVELOPMENT.md` V2 section), so state drift would still fail closed. | Identical `predictions.jsonl` actions and economics; per-request timing. | Low–Medium |
| B9 | **V2: binary probability output.** Write the 4,096 probabilities to a binary file (or return only the row, value, log-probability, entropy and a checksum) and move the sum and mask checks into the native process. | Removes formatting and parsing of 4,096 decimal numbers per decision. | Keep a replayable binary record; the native checks are equivalent to `infer_v2.py:211-213`. | Identical actions; per-request timing. | Medium |
| B10 | **V2: archive frames off the critical path.** Write frames to a tmpfs directory during play; after the game closes, archive them in a background process with the same gzip and verify step. | Removes the multi-GB archive and verify pass from episode latency. The volume is code-established (§3). | The archive bytes and SHA-256 are unchanged, and failures still mark the run failed before it is declared complete. | Time from game close to `run.json` completion; SHA equality of archives. | Medium (tmpfs capacity: about 1.5 GB per 512-decision game) |
| B11 | **Screening vs confirmation protocol for development.** Stage A: 1 greedy and 1 sampled seed on 2 maps for screening only. Stage B: the full paired matrix (8 V2 maps × 3 seeds, or V1 2 maps × 3 seeds × 3 training seeds) on **fresh** seeds for any candidate that proceeds; decisions use Stage B only. | Cuts the average cost per rejected candidate. | Screening outcomes never enter confirmatory statistics, so there is no winner's-curse contamination. | Count episodes per decision before and after; audit that Stage B seeds are disjoint from Stage A. | Low (process change) |
| B12 | **Common random numbers and paired analysis for sample size.** Already partly done (shared seeds). Formalize: compute the paired standard deviation from existing results and choose the number of seeds and maps for a target detectable effect. | Fewer episodes for the same precision, or better precision per episode. | This is standard variance reduction; the unbiasedness of paired differences is unchanged. | A retrospective power table from existing `run.json` files. | Low |
| B13 | **OpenTTD process reuse across episodes** via repeated RESET in one worker. | Removes per-episode engine start and scenario load. | Only valid if traces are byte-identical to fresh-process episodes on every map. Determinism across RESET is not established. | Measure spawn + reset time first (`run_m07_cpu_ppo.py:80-93` timestamps). If it is small, drop this. | High |

Not recommended: cutting episodes short, lowering the 512-action budget,
subsampling decisions, or reusing controls across engine or guide versions for
speed. Each changes what is measured.

---

## 6. Profiling plan (for a future agent; not performed)

1. **Cheap stage timers first.** In a development copy of the evaluation loop, add
   `time.monotonic_ns()` deltas per decision for 2a, 2b–2e (the evaluator request),
   2f, 2g and 2i, and store them in each `actions.jsonl` row under `timing`. In
   `m09_evaluator`, optionally print per-request decode, validate, forward and
   respond timings to stderr behind a flag.

   This avoids cProfile's distortion, which the docs already warn about
   (`DEVELOPMENT.md` "`--profile` … affects timing").
2. **A sampling profiler for Python.** `py-spy record` on one worker process gives
   low-overhead attribution to CRC, JSON, canonical checks and validation.
3. **Engine side.** Time STEP separately from bridge decode: native wall time per
   STEP response versus the Python request/response span. Use `perf` on the OpenTTD
   process if the simulation dominates.
4. **System view.** `pidstat -u -t 1` while running with `--workers` 1..4, to test
   the oversubscription hypothesis.
5. **V2.** Add per-request timings for OBSERVE, TENSORS, the policy, ACT and STEP
   to `predictions.jsonl`, plus the archival duration in `run.json`. This splits the
   58.29% "unattributed" share recorded in `PROGRESS.md:1169-1171`.
6. **Measurement design.** Same idle host; alternate A/B order; ≥ 3 pairs; report the
   median and range of per-episode `elapsed_seconds` and episodes/hour; require
   byte-identical traces. This is the protocol of
   `scripts/dev/compare_training_backends.py`.

## 7. Open questions

- The byte size of a typical V1 OBSERVE response. It determines whether CRC and
  canonical checks (2h) or validation (2a) dominate.
- Whether evaluation runs on the development machine use `--bridge-validation fast`
  in practice. `PROGRESS.md` records "fast" for registered runs, but
  `evaluate_live.py` defaults to reference.
- The OpenTTD simulation cost of 128 ticks on the small versus the large map.
- Whether TENSORS frames on the host are on the Linux filesystem or the Windows
  mount (`/mnt/c`), which would change I/O costs substantially. `DEVELOPMENT.md`
  recommends the Linux filesystem for builds; the run directories are under
  `~/.local/share`.
