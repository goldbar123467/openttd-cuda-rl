# Version 2 implementation and release plan

## Status

- Status: active
- Started: 2026-08-02
- V1 prerequisite: `G13 PASS`, tag `v1.0.0`
- Research authority: [`V2_RESEARCH.md`](V2_RESEARCH.md)
- Machine research baseline: [`config/v2/research-baseline.json`](../../config/v2/research-baseline.json)
- Pinned setting inventory: [`config/v2/setting-inventory.json`](../../config/v2/setting-inventory.json)
- Frozen competition protocol: [`config/v2/m14-competition-manifest.json`](../../config/v2/m14-competition-manifest.json)
- Current gate: [`G18 PASS`](G18_GATE_REPORT.md); stopping point before M19
- M15 contract: [`M15_SCALABLE_CONTRACT.md`](M15_SCALABLE_CONTRACT.md)
- M16 contract: [`M16_CARGO_INDUSTRY_CONTRACT.md`](M16_CARGO_INDUSTRY_CONTRACT.md)
- M17 contract: [`M17_RAIL_NETWORK_CONTRACT.md`](M17_RAIL_NETWORK_CONTRACT.md)
- M18 contract: [`M18_SHIP_WATERWAY_CONTRACT.md`](M18_SHIP_WATERWAY_CONTRACT.md)

V2 expands V1 to scalable maps, every base-game transport/cargo system,
multimodal planning and reproducible competition against external OpenTTD AIs.
Every milestone retains the V1 build, environment, training, evaluation, package
and visible-play workflows. A V2 gate cannot pass by replacing a stronger V1
invariant with a broader but weaker smoke test.

## Gate rules inherited from V1

Every milestone freezes a versioned contract before final evidence and requires:

- atomic requirements with bidirectional implementation/test/evidence links;
- exact source, patch, dependency, content, scenario and seed provenance;
- independent slow oracles for native observations, legality and rewards;
- unit, mutation, integration, differential, sanitizer, fault and resource tests
  proportional to changed native code;
- deterministic replay or a precise seeded/statistical contract where engine
  behavior is intentionally stochastic;
- explicit defect disposition and zero release-blocking correctness defects;
- clean-root reproduction with retained commands and artifact digests; and
- unchanged executable/evaluable coverage for every earlier passed stage.

`RESEARCHED`, `PLANNED`, a compiled code path, or one successful trajectory never
means `PASS`.

## Milestone sequence

### M14 — V2 authority, inventory, source and opponent qualification

Required outputs:

- active V2 goal, research report, atomic requirements and roadmap;
- machine inventory covering every pinned 15.3 command exactly once;
- complete base-game feature and setting disposition;
- accepted ADR for retaining 15.3 versus rebasing, with measured patch-forward
  cost and NoAI compatibility;
- content downloader that pins full package/dependency bytes and license metadata;
- sandboxed qualification runs for the external-AI audit pool; and
- a frozen competition manifest schema with slot, start-delay and scoring rules.

`G14` passes only when the inventories are mutation-tested, all selected package
bytes are reproducibly acquired or truthfully rejected, V1's full quick suite
passes, and no source/content identity is floating.

### M15 — Scalable environment and hierarchical contracts

Required outputs:

- native map dimensions 64–4096 plus V1 32×32 compatibility;
- variable town/industry/company/entity counts and bounded resource policies;
- multi-resolution spatial observations, typed entity tables and network graphs;
- hierarchical, parameterized action schema and legal masks;
- crop/candidate selection that never changes native legality;
- scalable policy architecture, checkpoint format and ONNX/package plan; and
- exact reset/step/save/load/replay tests at curriculum, rectangular,
  generalization and boundary sizes.

`G15` requires useful passenger-bus service on 64, 128, 256 and 512 maps; unseen
rectangular and 1024 evaluation; bounded 2048/4096 smoke or explicit preflight
rejection; and unchanged V1 model/environment results.

### M16 — Mail, trucks, industries and production chains

Required outputs:

- mail service and passenger/mail coordination;
- truck stops, cargo vehicles, refits and all base cargo identities;
- industry production/acceptance, closures, subsidies and cargo distribution;
- single-leg and multi-leg production-chain planning;
- transfers, shared stations and road/rail-ready multimodal graph semantics; and
- all four climate cargo graphs in generated scenario corpora.

`G16` requires profitable delivery for every base cargo class, complete named
chains in every climate, no transfer-payment exploit, native accounting parity,
and V1/passenger regression.

### M17 — Rail networks

Required outputs:

- rail types/conversion, track, stations, depots, waypoints and train assembly;
- path/block signal types, directionality and reservations;
- consists, refits, orders, timetables, servicing, replacement and upgrades;
- junction, platform, congestion, lost-train, collision and crossing observations;
  and
- rail-specialist and mixed road/rail curricula.

`G17` requires native legality/cost/state parity for every rail action family,
multiple trains sharing signalled networks without unresolved deadlock or collision,
profitable passenger and freight rail, a byte-pinned qualified rail-specialist
solo baseline with preferred-package rejection retained truthfully, and all
earlier regressions. [`G17_GATE_REPORT.md`](G17_GATE_REPORT.md) records the pass:
AAAHogEx supplies the qualified rail baseline because ChooChoo remained
catalog-listed but unselectable.

### M18 — Ships and waterways

Required outputs:

- docks, ship depots, buoys, natural water, rivers and route observations;
- canals, locks and aqueducts with height/connectivity legality;
- passenger/freight ships, refits, transfers, service and replacement; and
- sparse water-region planning and stuck/unreachable-route recovery.

`G18` requires profitable natural-water and constructed-waterway routes, lock and
aqueduct traversal, multimodal transfer, full ship action/oracle parity, ShipAI
qualification, and all earlier regressions.

[`G18_GATE_REPORT.md`](G18_GATE_REPORT.md) records the pass: 16 cases and 32
exact-twin native runs cover all eight ship/water probes, and the retained
coastal scenario promotes ShipAI from M14's truthful healthy-inactive disposition
to scenario-specific active qualification with two ships across save/load.

### M19 — Aircraft and multimodal generalist

Required outputs:

- all base airport and helicopter-facility types with date availability;
- airplanes/helicopters, range, noise, capacity, runway/terminal occupancy;
- crash/disaster, service, refit, renewal and airport open/close behavior;
- unified road/rail/water/air transfer planning; and
- generalist routing between mode specialists with stable shared observations.

`G19` requires profitable air and helicopter routes, safe range/noise/footprint
masks, congested-airport recovery, at least three-mode end-to-end cargo/passenger
journeys, Lufthansa and multimodal-AI qualification, and all earlier regressions.

### M20 — Competitive companies and external-AI tournament

Required outputs:

- one RL company against one and many NoAI companies in a shared simulation;
- symmetric slot/start-delay randomization and opponent isolation;
- competitor ownership, cargo capture, ratings, subsidies, collisions, failure,
  merger/purchase and shared-map resource observations;
- opponent timeouts/crashes contained without corrupting the RL company;
- solo, head-to-head, round-robin and mixed-field runners; and
- preregistered final seeds, maps, opponents, metrics and statistical analysis.

`G20` requires deterministic manifest replay, no privileged opponent leakage,
solo competence preserved, paired multi-seed results against every qualified audit
opponent, clear uncertainty intervals and no cherry-picked missing runs. Winning
every matchup is not required; a truthful reproducible benchmark is.

### M21 — Broad base-game, Game Script, NewGRF and event coverage

Required outputs:

- all four climates, long calendar spans, engine/airport introduction and expiry;
- local-authority actions, subsidies, exclusive rights, recession/inflation,
  breakdowns and disasters;
- Game Script goals, questions, stories and league-table observation/response;
- pinned NewGRF compatibility pack for tram, cargo, industries, stations, objects,
  road and rail types, ships and aircraft; and
- capability discovery plus fail-closed handling for unknown content.

`G21` requires the base-game feature matrix and every 15.3 command disposition to
have executable acceptance or deliberate environment/presentation evidence. The
pinned content pack passes; no arbitrary-NewGRF universality claim is allowed.

### M22 — Generalist learning, scale and robustness

Required outputs:

- trusted PPO training across the full curriculum and hierarchical actions;
- recurrent/attention/graph state and exact checkpoint recovery;
- specialist-router, monolithic and non-neural architecture baselines;
- measured CPU/CUDA batching without simulation-semantic changes;
- long-horizon curriculum, catastrophic-forgetting and prior-stage retention
  tests; and
- independent final suite across modes, climates, sizes and opponents.

`G22` requires multiple training seeds, finite/stable optimization, exact recovery
at the declared boundary, meaningful improvement over random/trivial baselines,
profitable/service-capable behavior in every mode, broad generalization reporting,
and all G15–G21 competence regressions. Training reward alone is never acceptance.

### M23 — V2 package, visible play, release and publication

Required outputs:

- versioned V2 ONNX/checkpoint packages and compatibility adapters;
- native/ONNX/in-game equivalence for every architecture output and recurrent
  state;
- visible normal-game control over broad scenarios and AI opponents;
- operator controls, inspection, fallback and actionable incompatibility errors;
- full clean-host build/train/resume/evaluate/export/install/play/tournament guide;
- immutable release manifest, artifact index, model card, benchmark report and
  third-party notices; and
- two independent clean-root reproductions.

`G23` and publication pass only when the complete V2 story is reproducible, all
mandatory requirements pass, no correctness defect can invalidate results, V1
remains reproducible, and release artifacts match reviewed bytes.

## V2 definition of done

V2 is complete only when all of these claims have gate evidence:

1. V1 remains fully runnable, evaluable, package-compatible and visibly playable.
2. Native map sizes and rectangular shapes are dispositioned from 64 through 4096,
   with useful trained/evaluated scale through the declared generalization tier.
3. Passengers, mail and every base cargo/industry chain are supported in all four
   climates.
4. Road/tram, rail, ship and aircraft construction, vehicles, orders, service and
   lifecycle behavior pass native differential tests.
5. The agent can build and operate profitable multimodal networks over long
   horizons and recover from documented congestion/failure cases.
6. Every base-game gameplay domain and every executable 15.3 command has an
   accepted policy/admin/presentation disposition with non-vacuous evidence.
7. External AI packages are byte-pinned, dependency-complete, sandboxed and run in
   a fair, preregistered shared-map benchmark.
8. Competition results cover all qualified opponents and report failures and
   uncertainty without selection after final results.
9. PPO, scalable architectures, CUDA use, checkpoints, monitoring and independent
   evaluation meet or exceed V1 correctness standards.
10. Native, ONNX and in-game inference remain equivalent and fail closed on
    incompatibility.
11. A user can reproduce build through tournament and watch the V2 policy play a
    broad normal game against AIs.
12. All mandatory tests/gates pass and no open defect can invalidate training,
    evaluation, competition or deployment claims.

Passing one mode, loading a large map, beating one AI once, or documenting a
feature does not satisfy V2.

## Immediate implementation order

M18 is complete and frozen at the requested stopping point. M19 is next in the
dependency order but has not started. Its next authorized sequence is:

1. freeze airport, helicopter, range, noise, occupancy, vehicle and lifecycle
   contracts;
2. extend native observations/actions for aircraft and airport state;
3. build deterministic fixed-wing, helicopter, congestion and failure corpora;
4. prove native legality, movement, delivery, recovery and at least three-mode
   transfer accounting; and
5. retain the complete G18 water, G17 rail, G16 cargo, G15 scalable/passenger and
   V1 compatibility boundaries in every future M19 artifact.
