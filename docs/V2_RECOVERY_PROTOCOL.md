# V2 recovery protocol frozen before tuning

[The versioned protocol](../config/dev/v2-recovery-study-protocol-1.json) fixes
the report-08 A0-A3 settings, three training seeds, training-only failure rule,
development matrix, controls, advancement and held-out selection before new
recovery tuning. No new recovery arm or held-out game has been run.

Each trained model is evaluated on all eight development maps, with one greedy
and three sampled full 512-decision games per map. Uniform and public-scripted
controls use the identical guide, engine, sources and simulation budget. The
uniform greedy diagnostic breaks equal-probability ties by candidate-row order;
scripted repetitions remain deterministic. Neither is counted as an independent
trained model. Existing v1-guide controls cannot stand in for v2/v4 controls.

The training reset probe is checked at updates 32, 40, 48, and every eight updates
thereafter. Two consecutive checks with proposal probability below .1 on at least
six maps stop that seed as a recorded failure. This makes the review's checkpoint
timing explicit. It never selects a convenient earlier checkpoint.

Advancement requires all three seeds to finish, no invalid actions or bankruptcy,
greedy sustained service on at least seven maps for every seed, and positive
paired sampled operating-profit **and** cash differences against same-guide
uniform for at least two seeds and in the pooled mean. Nested intervals retain
training seed as their outer sampling unit. Three seeds remain imprecise.

If several arms qualify, select the first eligible arm in the fixed A0-A5 order,
not the arm with the largest noisy observed effect. All mandatory arms still run;
A4/A5 require their evidence-dependent registrations before execution. If no arm
qualifies, do not access held-out games.

The eight **generalization** seeds are reserved for one final confirmation of
the selected arm's three final models, under the same full matrix and acceptance
criteria. The `final` split remains untouched. A separate immutable execution
registration must bind models, source, binaries, runtime and this protocol's
hash before access. Results cannot be used for further selection or tuning.
This is a test on unseen maps of the same size, not a claim about larger maps.

The execution-registration schema and exact-arm/matrix validators are tested.
The native evidence reader now checks explicit run/reset identities, native
reset projection, state/economics continuity, full boundaries and final weights.
Uniform controls support explicit sampled/greedy modes; the ordinary neural
launcher defaults to development. The prospective driver must still supply and
verify every map explicitly. Report integration and offline power/cost estimates
are available; estimates show storage reduction is needed before the large matrix.
The access implementation, execution driver and refusal tests are still being
built. Ordinary launchers continue to reject held-out splits; this
protocol file alone grants no access. Every execution registration must cite the
offline cost estimate and exact protocol identity. Any setup amendment must be
explicit, retain its parent's hash, and precede both new tuning and held-out use;
acceptance thresholds cannot be amended after observing study outcomes.
