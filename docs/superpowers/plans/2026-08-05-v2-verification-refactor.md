# V2 Verification Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portable, tiered V2 verification system that shortens local
feedback while preserving every frozen G22/M23/V1 invariant and keeping the
default command as the complete fail-closed release gate.

**Architecture:** `scripts/v2/verify.sh` becomes a thin public wrapper over an
importable Python inventory/runner. A shared artifact context separates offline
record validation from explicit relocated live validation. Existing validators
are migrated in bounded milestone groups, after which duplicate repository passes
and fixture construction are consolidated without changing frozen evidence.

**Tech Stack:** Bash, Python 3.12 standard library, `unittest`, `jsonschema`, Git,
existing V2 validators and immutable JSON records.

## Global Constraints

- All 86 V2 requirements remain in scope. All nine `V2-RELEASE-*` requirements
  remain `PLANNED` until actual G23 evidence passes.
- Final-v1 and follow-up-v1 remain immutable `FAIL`; follow-up-v2 remains the
  accepted G22 `PASS`. No suite may be retried, replaced, relabeled, or edited.
- Every current mutation category remains exercised with a stable label.
- Checkpoint IDs, package formats, the 48-case/580-row golden corpus, three
  runtimes, tolerances, eight campaign identities, and V1 bytes do not change.
- `scripts/v2/verify.sh` with no tier argument remains the full release gate.
- Missing live artifacts are never passing evidence: fast/contract do not
  dereference them, while full fails preflight before launching validators.
- Frozen JSON retains its recorded `/home/thecl/...` strings and canonical bytes;
  relocation affects only current-host filesystem reads.
- Fast/contract summaries never emit a G23 or release claim.
- Implementation tasks run sequentially. Every task uses a
  `gpt-5.6-sol`/`xhigh` implementer and a separate `gpt-5.6-sol`/`xhigh` reviewer.
- Do not modify `config/v1`, `scripts/v1`, accepted gate reports, checkpoint
  identities, or committed evidence/schema files.

---

## File structure

- `scripts/v2/verify_driver.py`: tier inventory, preflight, execution, exact
  expected-status handling, and summaries.
- `scripts/v2/artifact_context.py`: offline/live validation mode and safe
  current-host relocation of immutable recorded paths, plus a fail-closed map
  for live inputs that cannot be inferred from a frozen record.
- `scripts/v2/source_context.py`: explicit offline/live access to the pinned
  OpenTTD Git object repository; this remains separate from artifact relocation.
- `tests/project/v2/test_v2_verify_driver.py`: driver inventory, CLI, preflight,
  and failure-classification tests.
- `tests/project/v2/test_v2_artifact_context.py`: pure relocation and aggregate
  preflight tests.
- `tests/project/v2/test_v2_source_context.py`: pinned-object-repository
  preflight and no-hidden-Git-access tests.
- `scripts/v2/m22_evaluation_validation.py`: mechanical historical-source,
  digest, protocol, statistics, and acceptance recomputation shared by M22
  validators.
- `tests/project/v2/m22_fixture_support.py`: fresh 42-case report factories and
  named mutation harnesses.
- `tests/project/v2/m23_fixture_support.py`: immutable golden, package, and report
  test fixtures with per-mutation copies.
- `docs/project/V2_VERIFICATION.md`: tier usage, inputs, output semantics, and
  development-versus-release claims.

Existing validators and tests are changed only in the task that owns their
milestone group. No task edits another task's shared files concurrently.

## Agent execution units

Tasks 3–5 are milestone groupings, not single agent prompts. Execute these named
units sequentially; each receives its own `gpt-5.6-sol`/`xhigh` implementer,
focused tests, commit, and separate reviewer before the next unit starts:

- **3A — M15 evidence freezing:** the three `freeze_m15_*_evidence.py` modules
  their three validation-only CLIs, and action/observation/episode evidence
  tests.
- **3B — M15 runtime evidence:** native reset validator/matrix, policy,
  the native-reset-matrix validation-only CLI, cross-scale replay, competence,
  and their tests.
- **3C — M15 source and map validation:** the five M15 source validators,
  `run_m15_map_matrix.py`, the new validation-only map CLI, and their tests.
- **4A — baseline and opponents:** research baseline, setting generation/
  validation, package/runtime evidence, competition manifest, and their tests.
- **4B — M16 through M18:** cargo, rail, ship, ShipAI source/evidence modules,
  and their tests.
- **4C — M19 through M21:** air, competition, broad source/evidence/runtime
  modules, and their tests.
- **5A — M22 learning artifacts:** native corpus builder/validator, recovery,
  training, qualification validators, and their tests.
- **5B — M22 retained runtimes:** final/follow-up runtime-source validators,
  both preparation tests, and their relocated-live tests.
- **5C — M22 evaluation history:** final/follow-up/follow-up-v2 evaluation
  runners/validators and evidence tests, including prior-attempt splitting and
  historical Git-blob checks.

If a unit discovers a necessary edit owned by a later unit, record it in the
progress ledger rather than crossing the boundary. A genuinely shared API change
returns to Task 2's implementer and reviewer before dependent work resumes.

### Task 1: Fail-closed tier inventory and verification driver

**Files:**

- Create: `scripts/v2/verify_driver.py`
- Create: `tests/project/v2/test_v2_verify_driver.py`
- Modify: `scripts/v2/verify.sh`

**Interfaces:**

- Consumes: the current ordered 55-process behavior of `scripts/v2/verify.sh`
  plus the missing authoritative final-v1 evaluation validator.
- Produces: `Tier`, `CommandSpec`, `VerificationConfig`, `PreflightIssue`,
  `CommandResult`, `VerificationSummary`, `build_inventory()`,
  `select_commands()`, `preflight()`, and `run_verification()` for all later
  tasks.

- [ ] **Step 1: Write driver model and inventory tests that fail before the module exists**

Create `tests/project/v2/test_v2_verify_driver.py` with `unittest` tests named:

```python
class V2VerifyDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.python = pathlib.Path(sys.executable).resolve()

    def test_default_tier_is_full(self) -> None:
        args = driver.parse_args([
            "--root", str(self.root), "--tools-python", str(self.python),
        ])
        self.assertIs(driver.resolve_config(args, {}).tier, driver.Tier.FULL)

    def test_inventory_is_unique_ordered_and_cumulative(self) -> None:
        inventory = driver.build_inventory(self.root, self.python)
        self.assertEqual(len(inventory), 56)
        self.assertEqual(len({item.command_id for item in inventory}), 56)
        fast = driver.select_commands(inventory, driver.Tier.FAST)
        contract = driver.select_commands(inventory, driver.Tier.CONTRACT)
        full = driver.select_commands(inventory, driver.Tier.FULL)
        self.assertEqual([item.command_id for item in fast],
                         ["m22-corpus-binary", "v2-unit-tests"])
        self.assertEqual((len(fast), len(contract), len(full)), (2, 55, 56))
        self.assertEqual(full[-1].command_id, "v1-traceability")
```

Also add:

```text
test_fast_and_contract_summaries_make_no_gate_or_g23_claim
test_final_v1_exit_two_is_expected_success
test_final_v1_zero_or_different_nonzero_is_failure
test_followup_v1_exit_two_is_expected_success
test_followup_v1_zero_or_different_nonzero_is_failure
test_unexpected_status_is_retained_and_later_commands_continue
test_fast_preflight_needs_no_artifact_root_or_submodule
test_contract_preflight_requires_exact_pinned_submodule
test_full_preflight_requires_artifact_root_before_execution
test_preflight_accumulates_categories_and_exits_two
test_artifact_resolution_prefers_cli_then_environment_then_none
test_relative_artifact_environment_value_fails_closed
```

- [ ] **Step 2: Run the focused test and confirm the import failure**

Run:

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_verify_driver -v
```

Expected: `ImportError` for `verify_driver`.

- [ ] **Step 3: Implement the exact driver types and public functions**

Create `scripts/v2/verify_driver.py` with these public types:

```python
class Tier(enum.IntEnum):
    FAST = 0
    CONTRACT = 1
    FULL = 2

class CommandCategory(enum.Enum):
    TEST = "test"
    VALIDATOR = "validator"
    BUILDER = "builder"
    REGRESSION = "regression"

class Requirement(enum.Enum):
    OPENTTD_SOURCE = "openttd-source"
    ARTIFACT_ROOT = "artifact-root"

class FailureKind(enum.Enum):
    UNEXPECTED_STATUS = "unexpected-status"
    SPAWN = "spawn"
    TIMEOUT = "timeout"

@dataclasses.dataclass(frozen=True)
class CommandSpec:
    command_id: str
    minimum_tier: Tier
    category: CommandCategory
    argv: tuple[str, ...]
    expected_status: int = 0
    environment: tuple[tuple[str, str], ...] = ()
    requirements: frozenset[Requirement] = frozenset()
    timeout_seconds: float | None = None

@dataclasses.dataclass(frozen=True)
class VerificationConfig:
    repository_root: pathlib.Path
    tools_python: pathlib.Path
    tier: Tier = Tier.FULL
    artifact_root: pathlib.Path | None = None
```

Add immutable `PreflightIssue`, `CommandResult`, and `VerificationSummary`
dataclasses. `CommandResult.passed` is true only when `failure_kind is None` and
`actual_status == command.expected_status`; `VerificationSummary.passed` requires
every result to pass.

Implement these public callables with the named arguments and return values:

- `parse_tier(value: str) -> Tier`
- `parse_args(argv: list[str]) -> argparse.Namespace`
- `resolve_config(args, environ=os.environ) -> VerificationConfig`
- `build_inventory(repository_root, tools_python) -> immutable CommandSpec sequence`
- `select_commands(inventory, tier) -> immutable CommandSpec sequence`
- `preflight(config, commands) -> immutable PreflightIssue sequence`
- `execute_command(command, repository_root) -> CommandResult`
- `run_verification(config, inventory=None) -> VerificationSummary`
- `render_summary(summary) -> immutable string sequence`
- `main(argv=None) -> int`

Build the current commands in their existing relative order and insert
`m22-final-v1-evaluation` immediately before the follow-up manifests/evaluations.
Assign the inline
M22 corpus round trip and V2 unittest discovery to `FAST`; assign the 52 V2
validators/builders plus final-v1 to `CONTRACT`; assign V1 traceability to
`FULL`. Mark both `m22-final-v1-evaluation` and
`m22-followup-v1-evaluation` with `expected_status=2`. Retain the two manifest
builder commands until Task 8 proves their authoritative replacement.

Use `subprocess.run(command.argv, cwd=repository_root, text=True,
capture_output=True, check=False)` with no shell. Continue after command failures and render all
results. Fast/contract summary text must not contain `G23`, `RELEASE`, or
`V2_VERIFY_GATE`.

- [ ] **Step 4: Replace the public shell body with validated delegation**

Modify `scripts/v2/verify.sh` to parse options in any order:

```text
scripts/v2/verify.sh [--tier fast|contract|full]
                     [--tools-python /absolute/python]
                     [--artifact-root /absolute/openttd-rl-artifacts]
```

Default `tier=full`. Reject unknown, missing, duplicate, relative Python, and
relative artifact-root arguments with exit `2`; `--help` exits `0`. Delegate with:

```bash
PYTHONPATH="$repository_root/scripts/v2" exec "$tools_python" \
  "$repository_root/scripts/v2/verify_driver.py" \
  --root "$repository_root" --tier "$tier" \
  --tools-python "$tools_python" "${artifact_args[@]}"
```

- [ ] **Step 5: Run focused tests and shell checks**

Run:

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_verify_driver -v
bash -n scripts/v2/verify.sh
scripts/v2/verify.sh --help
```

Expected: all driver tests pass; Bash syntax succeeds; help prints the public
syntax and exits `0`. Do not claim the contract/full tiers are portable yet.

- [ ] **Step 6: Commit Task 1**

```bash
git add scripts/v2/verify_driver.py scripts/v2/verify.sh \
  tests/project/v2/test_v2_verify_driver.py
git commit -m "Refactor V2 verification into explicit tiers"
```

### Task 2: Shared offline/live artifact and source contexts

**Files:**

- Create: `scripts/v2/artifact_context.py`
- Create: `scripts/v2/source_context.py`
- Create: `tests/project/v2/test_v2_artifact_context.py`
- Create: `tests/project/v2/test_v2_source_context.py`

**Interfaces:**

- Consumes: explicit CLI root, `OPENTTD_RL_ARTIFACT_ROOT`, and frozen recorded
  absolute paths.
- Produces: `ValidationMode`, `ArtifactRequirement`, `RoleRequirement`,
  `ToolRequirement`,
  `ArtifactContext`, `LiveInputManifest`,
  `SourceContext`, `resolve_artifact_root()`, `add_artifact_root_argument()`, and
  `add_object_repository_argument()` used by Tasks 3–7.

- [ ] **Step 1: Write the pure context tests**

Create tests named:

```text
test_explicit_root_wins_over_environment
test_environment_root_is_used_when_explicit_root_is_absent
test_no_configured_root_returns_none
test_relative_explicit_root_is_rejected_without_environment_fallback
test_relative_environment_root_is_rejected
test_offline_context_rejects_artifact_set_access
test_offline_context_rejects_relocation
test_live_context_maps_logical_set_below_current_host_root
test_live_context_relocates_nested_recorded_path
test_relocation_does_not_mutate_recorded_json_value
test_relocation_rejects_path_outside_recorded_set
test_artifact_set_rejects_multicomponent_or_parent_name
test_preflight_reports_all_missing_sets_in_sorted_order
test_preflight_reports_all_missing_nested_files_and_directories
test_requirement_rejects_absolute_parent_or_empty_relative_path
test_role_requirement_preflights_nested_checkpoint_and_log_paths
test_tool_requirement_checks_presence_kind_and_optional_digest
test_preflight_rejects_symlinked_base_or_set
test_live_input_manifest_rejects_unknown_duplicate_relative_or_escaping_paths
test_live_input_manifest_reports_every_missing_role
test_live_input_manifest_rejects_each_wrong_frozen_executable_or_corpus_digest
test_recovery_v1_and_v2_roles_cannot_alias_incompatible_binaries
test_named_live_input_cannot_be_read_in_offline_mode
```

Create `tests/project/v2/test_v2_source_context.py` with:

```text
test_offline_context_never_resolves_an_object_repository
test_live_context_requires_an_absolute_nonsymlink_git_object_repository
test_live_context_runs_git_only_against_the_explicit_repository
test_preflight_rejects_missing_or_wrong_pinned_commit
test_cli_object_repository_wins_over_the_documented_default
```

Representative relocation assertion:

```python
recorded = "/home/thecl/.codex/artifacts/openttd-rl/v2-m22-followup-runtime-a/source"
context = ArtifactContext.live(pathlib.Path("/srv/openttd-rl"))
self.assertEqual(
    context.relocate(
        recorded,
        recorded_root="/home/thecl/.codex/artifacts/openttd-rl/v2-m22-followup-runtime-a",
    ),
    pathlib.Path("/srv/openttd-rl/v2-m22-followup-runtime-a/source"),
)
```

- [ ] **Step 2: Run and confirm the missing-module failure**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_artifact_context \
  tests.project.v2.test_v2_source_context -v
```

Expected: `ImportError` for `artifact_context` and `source_context`.

- [ ] **Step 3: Implement the pure relocation API**

Create:

```python
ARTIFACT_ROOT_ENV = "OPENTTD_RL_ARTIFACT_ROOT"

class ArtifactContextError(ValueError):
    pass

class ValidationMode(enum.StrEnum):
    OFFLINE = "offline"
    LIVE = "live"

@dataclasses.dataclass(frozen=True, slots=True)
class ArtifactContext:
    mode: ValidationMode
    artifact_root: pathlib.Path | None
```

Implement `ArtifactContext.offline()`, `ArtifactContext.live(artifact_root)`, the
`is_live` property, `artifact_set(logical_name)`,
`relocate(recorded_path, recorded_root=recorded_root)`, and
`preflight(requirements) -> None` on that immutable type.

Offline live-access methods raise exactly
`ArtifactContextError("offline validation attempted live artifact access")`.
`artifact_set()` accepts one nonempty POSIX component and rejects slash, `.`,
`..`, and parent traversal. `relocate()` performs lexical `PurePosixPath`
containment, uses the recorded root's final component as the logical set, and
never mutates the record. Define immutable
`ArtifactRequirement(logical_set, relative_path, kind, consumer,
expected_sha256=None)`. `relative_path` is a safe POSIX path below one logical
set; `kind` is file or directory. Aggregate preflight verifies every nested path,
kind, nonsymlink component, and optional digest, then sorts and de-duplicates all
failures into one error.

`ArtifactContext.resolve(requirement)` returns the already-relocated path for an
`ArtifactRequirement`. Artifact-backed live validation must enumerate the
requirement first and resolve through this method rather than joining an
unregistered path independently.

Define the parallel immutable
`RoleRequirement(role, relative_path, kind, consumer, expected_sha256=None)` for
host-manifest roots. `LiveInputManifest.preflight(requirements)` applies the same
nested-path, kind, symlink, and digest rules below the mapped role path. Artifact
sets and roles remain distinct types; `LiveInputManifest.resolve(requirement)`
returns a role-backed path only for a declared `RoleRequirement`.

Define `ToolRequirement(name, path, expected_sha256=None)` for executables that
are not retained-artifact roles. Tool preflight requires an absolute regular
nonsymlink executable and verifies the optional digest.

Implement resolution order as explicit root, environment, then `None`; reject
relative values and never infer a home directory or `.codex` path.

Add `LiveInputManifest` as an immutable runtime value loaded from the host-only
`<artifact-root>/v2-live-inputs.json`. It maps these exact roles to absolute or
artifact-root-relative paths:

```text
recovery-v1-artifacts        directory
recovery-v1-executable       file  sha256=2f26dc241b029abeb4641f1497e9347a6675a3d607b564855518fb91b391356f
recovery-v1-corpus           file  sha256=0d5aa3944241b3c00e0b1283de586e00c8fb0a5a51abe385c7e3288785369a0d
recovery-v2-artifacts        directory
training-artifacts           directory
qualification-artifacts      directory
v2-campaign-executable       file  sha256=62ed497cf6f237248a54861269e5b0ad27c8808f8e3d4d7b73d29148e84a5fc2
v2-corpus-binary             file  sha256=d6cdf022e4382a90da4b89a225eb3e1cf15833a63d9c450712aa4c9dbfbc4021
qualification-executable     file  sha256=ae5a74d890e980a6c1308cdad31154e902d0c5e40f234f98b7d34e61849f4b52
final-v1-evaluator           file  sha256=bc87f4608643b4664068381fa5136d464c44bd05dad09a66fa088bfa995b92e6
m14-openttd-executable       file  sha256=8b27f06113d08fa3a21f81c01721873194f35bf885963be2697cc9da52e1ef9a
```

Paths must resolve lexically below the configured artifact root, must not
traverse symlinks, and must exist with the declared file/directory kind. Unknown,
missing, or duplicate roles are one aggregate preflight error. This manifest is
host configuration only and is never committed, hashed into, or confused with
frozen evidence.

Create `scripts/v2/source_context.py` with immutable `SourceContext.offline()`
and `SourceContext.live(object_repository, pinned_commit)`. Its live constructor
accepts only an explicit absolute nonsymlink Git object repository and preflights
the recorded commit with `git cat-file -e <commit>^{commit}`. All Git reads use
`git -C <object_repository>`; offline mode raises
`SourceContextError("offline validation attempted live source access")`. Do not
place the checkout beneath `OPENTTD_RL_ARTIFACT_ROOT` and do not infer it inside
a validator.

- [ ] **Step 4: Run context tests and diff guards**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_artifact_context \
  tests.project.v2.test_v2_source_context -v
git diff --check
```

Expected: all context tests pass and no whitespace errors exist.

- [ ] **Step 5: Commit Task 2**

```bash
git add scripts/v2/artifact_context.py \
  scripts/v2/source_context.py tests/project/v2/test_v2_artifact_context.py \
  tests/project/v2/test_v2_source_context.py
git commit -m "Add portable V2 live validation contexts"
```
### Task 3: M15 validators and tests use explicit validation context

**Files:**

- Modify: `scripts/v2/freeze_m15_action_evidence.py`
- Modify: `scripts/v2/freeze_m15_observation_evidence.py`
- Modify: `scripts/v2/freeze_m15_episode_evidence.py`
- Create: `scripts/v2/validate_m15_action_evidence.py`
- Create: `scripts/v2/validate_m15_observation_evidence.py`
- Create: `scripts/v2/validate_m15_episode_evidence.py`
- Modify: `scripts/v2/validate_m15_native_reset_evidence.py`
- Modify: `scripts/v2/run_m15_native_reset_matrix.py`
- Create: `scripts/v2/validate_m15_native_reset_matrix.py`
- Modify: `scripts/v2/validate_m15_policy_evidence.py`
- Modify: `scripts/v2/validate_m15_cross_scale_replay_evidence.py`
- Modify: `scripts/v2/validate_m15_competence_evidence.py`
- Modify: `scripts/v2/validate_m15_native_source.py`
- Modify: `scripts/v2/validate_m15_observation_source.py`
- Modify: `scripts/v2/validate_m15_action_source.py`
- Modify: `scripts/v2/validate_m15_episode_source.py`
- Modify: `scripts/v2/validate_m15_competence_source.py`
- Modify: `scripts/v2/run_m15_map_matrix.py`
- Create: `scripts/v2/validate_m15_map_evidence.py`
- Modify: the 13 corresponding `tests/project/v2/test_v2_m15_*` modules that
  currently contain `/home/thecl` artifact lookups, plus
  `tests/project/v2/test_v2_m15_map_qualification.py`.

**Interfaces:**

- Consumes: `ArtifactContext.offline()` or one explicit live context.
- Produces: M15 validators that validate committed bytes offline and relocate
  filesystem reads live without changing any recorded path, plus exact
  `required_live_inputs(root)` inventories consumed by Task 7.

- [ ] **Step 1: Add failing offline and relocated-live boundary tests**

Add these named tests to their existing modules:

```text
M15ActionEvidenceTests.test_relocated_live_artifacts_do_not_rewrite_recorded_base
M15NativeSourceTests.test_offline_validation_does_not_open_recorded_base_source
M15PolicyEvidenceTests.test_relocated_source_and_build_use_one_artifact_context
M15MapQualificationTests.test_offline_validation_does_not_open_artifact_hint
M15MapQualificationTests.test_relocated_live_map_matrix_passes
M15MapQualificationTests.test_creation_artifact_root_is_not_a_validation_base
M15ActionEvidenceTests.test_creation_artifact_root_is_not_a_validation_base
M15ObservationEvidenceTests.test_creation_artifact_root_is_not_a_validation_base
M15EpisodeEvidenceTests.test_creation_artifact_root_is_not_a_validation_base
M15NativeResetMatrixTests.test_creation_artifact_root_is_not_a_validation_base
```

For the no-open test, patch the validator's Git/live projection helper to raise
`AssertionError("unexpected live access")`, then call the repository validator
with `ArtifactContext.offline()`. For relocation, copy the minimum valid retained
fixture under a temporary base, construct `ArtifactContext.live(base)`, validate,
and assert the original loaded JSON still contains its exact recorded
`/home/thecl/...` string.

- [ ] **Step 2: Run the focused boundary tests and confirm the signature failure**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest -v \
  tests.project.v2.test_v2_m15_action_evidence \
  tests.project.v2.test_v2_m15_native_source \
  tests.project.v2.test_v2_m15_policy_evidence
```

Expected: failure because the validators do not accept `artifact_context`.

- [ ] **Step 3: Migrate validation signatures and live guards**

Preserve each validator's existing positional `root`, config, report, and schema
arguments. Replace validation-only `artifact_base`, `artifact_root`,
`source_artifact`, and `base_source` keywords with the keyword-only parameter
`artifact_context: ArtifactContext | None = None`; the first executable line is
`context = artifact_context or ArtifactContext.offline()`.

Keep schema, canonical-byte, digest, source-inventory, ordering, and summary
checks outside the live branch. Guard every file, Git source, executable, report,
log, and save read with `if context.is_live:`. Use `context.artifact_set()` for
records that store a logical set name and `context.relocate()` for records that
store an absolute root/path pair.

Use these exact logical-set/relative-path pairs:

```text
m12-release-final-a -> composed-source/openttd
v2-m15-native-a -> source
v2-m15-observation-a -> source
v2-m15-action-a -> source
v2-m15-episode-a -> source
v2-m15-policy-a -> .
```

Do not compare a current-host path string with a frozen recorded path. Validate
the recorded path shape and logical set name, then hash the relocated path in
live mode. Newly generated evidence calls its validator with a live context
rooted at the generated set's parent, preserving output bytes.

Move the validation-only CLI for the map matrix into
`validate_m15_map_evidence.py`. It accepts the common `--artifact-root` as the
current-host base and calls `run_m15_map_matrix.validate()` with
`ArtifactContext.live(base)`. Keep `run_m15_map_matrix.py --artifact-root` solely
as the destination for creating a new matrix; its parser must reject any attempt
to mix creation and validation options. The live validator resolves
`v2-m15-map-matrix-a`, all 49 result directories, the transcript/save bodies,
and the full-tier `m14-openttd-executable` role explicitly. Offline validation proves only the
frozen schema, contract/source/executable identities, 49 rectangles, outcome
policy, and aggregates.

Until Task 7 switches the inventory, preserve the runner's root-only invocation
as an offline validation delegation with no live-path option. Task 7 then points
the authoritative command at `validate_m15_map_evidence.py`; at no point may the
creation `--artifact-root` be interpreted as a validation base.

Apply the same separation to `freeze_m15_action_evidence.py`,
`freeze_m15_observation_evidence.py`, `freeze_m15_episode_evidence.py`, and
`run_m15_native_reset_matrix.py`. Their `--artifact-root` remains a new-output
destination. The four new `validate_m15_*` CLIs own offline/live validation and
accept the common current-host `--artifact-root`. Preserve a root-only offline
delegation in the generators until Task 7 switches the authoritative inventory,
then leave generation and validation entry points unambiguous. Driver tests map
each of these five validation-only CLIs to exactly one command ID.

- [ ] **Step 4: Remove M15 test literals and use explicit contexts**

In the affected M15 tests, import `ArtifactContext` and
`resolve_artifact_root`. Offline repository and mutation tests pass
`ArtifactContext.offline()`. Live methods resolve
`OPENTTD_RL_ARTIFACT_ROOT`; when absent they call `self.skipTest` with
`"live artifact validation is outside offline mode"`. In full mode the driver
preflight added in Task 7 makes that skip unreachable.

No M15 test may construct a path from `$HOME`, `.codex`, or a recorded user-home
prefix.

- [ ] **Step 5: Run all M15 tests and the path guard**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest discover \
  -s tests/project/v2 -p 'test_v2_m15*.py' -v
rg -n '/home/thecl|\.codex/artifacts' tests/project/v2/test_v2_m15*
```

Expected: M15 tests pass with live-only methods explicitly skipped offline; `rg`
has no output and exits `1`.

- [ ] **Step 6: Commit and review units 3A, 3B, and 3C separately**

```bash
git add scripts/v2/freeze_m15_* scripts/v2/validate_m15_* \
  scripts/v2/run_m15_native_reset_matrix.py scripts/v2/run_m15_map_matrix.py \
  tests/project/v2/test_v2_m15_*
git commit -m "Separate M15 offline and live evidence validation"
```

Use a scope-specific subject for each unit; the command above is the final 3C
example. Do not combine the three units into one review.
### Task 4: Baseline, M14, and M16–M21 validators split records from live inputs

**Files:**

- Modify: `scripts/v2/validate_research_baseline.py`
- Modify: `scripts/v2/generate_setting_inventory.py`
- Modify: `scripts/v2/validate_setting_inventory.py`
- Modify: `scripts/v2/validate_opponent_package_evidence.py`
- Modify: `scripts/v2/validate_opponent_runtime_evidence.py`
- Modify: `scripts/v2/validate_competition_manifest.py`
- Modify: `scripts/v2/validate_m16_cargo_evidence.py`
- Modify: `scripts/v2/validate_m16_cargo_source.py`
- Modify: `scripts/v2/validate_m17_rail_evidence.py`
- Modify: `scripts/v2/validate_m17_rail_source.py`
- Modify: `scripts/v2/validate_m18_ship_evidence.py`
- Modify: `scripts/v2/validate_m18_ship_source.py`
- Modify: `scripts/v2/validate_m18_shipai_evidence.py`
- Modify: `scripts/v2/validate_m19_air_evidence.py`
- Modify: `scripts/v2/validate_m19_air_source.py`
- Modify: `scripts/v2/validate_m20_competition_evidence.py`
- Modify: `scripts/v2/validate_m20_competition_source.py`
- Modify: `scripts/v2/validate_m21_broad_evidence.py`
- Modify: `scripts/v2/validate_m21_broad_source.py`
- Modify: `scripts/v2/run_m21_broad_matrix.py`
- Modify: `tests/project/v2/test_v2_research_baseline.py`
- Modify: `tests/project/v2/test_v2_setting_inventory.py`
- Modify: the corresponding M16–M21 and opponent/ShipAI unit tests.

**Interfaces:**

- Consumes: the same `artifact_context: ArtifactContext | None = None` keyword as
  Task 3 plus an independent `source_context: SourceContext | None = None` for
  pinned OpenTTD Git objects.
- Produces: artifact-offline summaries that never open a retained path, explicit
  source-live summaries for the two completeness claims, and artifact-live
  summaries that rehash the relocated complete closure. Every artifact-backed
  module also produces its exact `required_live_inputs(root)` closure.

- [ ] **Step 1: Add milestone boundary tests before changing validators**

Add these exact tests:

```text
V2ResearchBaselineTests.test_offline_validation_does_not_invoke_git_on_object_repository
V2ResearchBaselineTests.test_live_validation_uses_explicit_object_repository
V2ResearchBaselineTests.test_missing_live_object_repository_is_a_preflight_failure
SettingInventoryTests.test_offline_validation_does_not_invoke_source_extraction
SettingInventoryTests.test_live_validation_uses_explicit_object_repository
OpponentPackageEvidenceTests.test_repository_evidence_passes_offline_without_retained_artifacts
OpponentPackageEvidenceTests.test_relocated_live_package_closure_passes
OpponentRuntimeEvidenceTests.test_repository_evidence_passes_offline_without_retained_artifacts
OpponentRuntimeEvidenceTests.test_relocated_live_runtime_and_package_closures_pass
CompetitionManifestTests.test_nested_runtime_authority_is_explicitly_offline
M16CargoEvidenceTests.test_repository_evidence_passes_offline_without_retained_artifacts
M17RailEvidenceTests.test_repository_evidence_passes_offline_without_retained_artifacts
M18ShipEvidenceTests.test_repository_evidence_passes_offline_without_retained_artifacts
M18ShipAIEvidenceTests.test_repository_evidence_passes_offline_without_retained_artifacts
M18ShipAIEvidenceTests.test_offline_validation_does_not_call_qualification_validator
M18ShipAIEvidenceTests.test_relocated_live_package_scenario_and_runtime_pass
M19AirEvidenceTests.test_repository_evidence_passes_offline_without_retained_artifacts
M20CompetitionEvidenceTests.test_repository_evidence_passes_offline_without_retained_artifacts
M21BroadEvidenceTests.test_repository_evidence_passes_offline_without_retained_artifacts
M16CargoEvidenceTests.test_relocated_live_report_digest_mutation_fails
M21BroadEvidenceTests.test_relocated_live_negative_log_mutation_fails
M21BroadSourceTests.test_relocated_runtime_paths_are_used_instead_of_recorded_paths
```

Patch each module's live report loader during an offline test so an absolute path
outside the repository raises `AssertionError("unexpected live read")`. Assert
the summary reports `live is False` (or `live_artifacts is False` for opponent
summary dataclasses).

- [ ] **Step 2: Run the new boundary tests and confirm current live dereferences**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest -v \
  tests.project.v2.test_v2_research_baseline \
  tests.project.v2.test_v2_setting_inventory \
  tests.project.v2.test_v2_opponent_package_evidence \
  tests.project.v2.test_v2_opponent_runtime_evidence \
  tests.project.v2.test_v2_m16_cargo_evidence \
  tests.project.v2.test_v2_m17_rail_evidence \
  tests.project.v2.test_v2_m18_ship_evidence \
  tests.project.v2.test_v2_m18_shipai_evidence \
  tests.project.v2.test_v2_m19_air_evidence \
  tests.project.v2.test_v2_m20_competition_evidence \
  tests.project.v2.test_v2_m21_broad_evidence
```

Expected: offline tests fail at current frozen absolute paths.

The baseline and setting-inventory tests also fail because their current
repository validations invoke Git extraction without an explicit live source
context.

- [ ] **Step 3: Split record checks from relocated live traversal**

Give every artifact-backed validator from opponent package through M21 the
keyword:

```python
*, artifact_context: ArtifactContext | None = None
```

and initialize `context = artifact_context or ArtifactContext.offline()`.

Always validate schemas, committed repository digests, relative-path safety,
case/twin/replicate ordering, declared statistics, acceptance projections, and
source-patch records. Only live mode may check retained report/log/save files,
executables, source Git trees, OpenGFX, runtime configuration, content, or Game
Script files.

Remove fallbacks such as:

```python
artifact_root = (artifact_root or pathlib.Path(evidence["artifact_root"])).resolve()
```

Do not replace them with existence inference. Relocate absolute records beneath
the current host's logical set.

Change the M21 runtime helper to
`validate_runtime(root: pathlib.Path, source: dict[str, Any], artifact_context:
ArtifactContext)`, returning the relocated runtime root and its named path map.

M18 ShipAI validates its committed M14 disposition, schema, projected package,
scenario metadata, and observation metadata offline. Live mode relocates the
package lock, scenario save, and qualification manifest before hashing and
semantic validation.

Opponent package/runtime summaries retain their existing dataclass shapes and
`live_artifacts` flag. Their old `artifact_base` keyword and CLI option become one
artifact context/current-host base, while `openttd` remains a separately explicit
live executable.

Change `validate_research_baseline.validate()` and
`validate_setting_inventory.validate()` to accept
`source_context: SourceContext | None = None`, defaulting to offline. Offline
baseline checks retain JSON/schema/hash, V1 source-profile identity, disposition,
map/domain/opponent, and documentation invariants. Offline setting checks retain
schema, engine/source-file policy, row order/counts, scope/disposition, and
secret classification. Live mode alone reads the pinned OpenTTD Git objects and
proves the 145-command and 20-file/435-definition completeness claims. Contract
and full pass `SourceContext.live(root / "openttd-upstream", pinned_commit)`;
fast never does. Their summaries expose `live_source` so an offline pass cannot
be described as source completeness.

Package live mode preflights and resolves all ten package artifact sets. Runtime
live mode preflights those ten plus the eight non-`PACKAGE` runtime sets. The
OpenTTD executable is the required full-tier `m14-openttd-executable` role
because the frozen records contain only its hash and size. Route that one typed
path to package acquisition, opponent runtime, M15 map, and ShipAI consumers.
Nested authority validation in
`validate_competition_manifest.py` explicitly passes
`ArtifactContext.offline()` so the direct package/runtime commands own the sole
live traversal.

- [ ] **Step 4: Migrate baseline, opponent, and M16–M21 tests**

Replace hard-coded roots with `ArtifactContext.live(configured_base)` only in
live methods. Repository/mutation tests pass `ArtifactContext.offline()`.
Preserve every existing mutation label and error regex.

Run:

```bash
PYTHONPATH=scripts/v2 python3 -m unittest -v \
  tests.project.v2.test_v2_research_baseline \
  tests.project.v2.test_v2_setting_inventory \
  tests.project.v2.test_v2_opponent_package_evidence \
  tests.project.v2.test_v2_opponent_runtime_evidence
PYTHONPATH=scripts/v2 python3 -m unittest discover \
  -s tests/project/v2 -p 'test_v2_m1[6-9]*.py' -v
PYTHONPATH=scripts/v2 python3 -m unittest discover \
  -s tests/project/v2 -p 'test_v2_m2[0-1]*.py' -v
rg -n '/home/thecl|\.codex/artifacts' \
  tests/project/v2/test_v2_m1[6-9]* tests/project/v2/test_v2_m2[0-1]*
```

Expected: offline tests pass, live-only tests explicitly skip without a configured
base, and `rg` exits `1`.

- [ ] **Step 5: Commit and review units 4A, 4B, and 4C separately**

```bash
git add scripts/v2/validate_research_baseline.py \
  scripts/v2/generate_setting_inventory.py scripts/v2/validate_setting_inventory.py \
  scripts/v2/validate_opponent_* scripts/v2/validate_competition_manifest.py \
  scripts/v2/validate_m1[6-9]_* \
  scripts/v2/validate_m2[0-1]_* scripts/v2/run_m21_broad_matrix.py \
  tests/project/v2/test_v2_research_baseline.py \
  tests/project/v2/test_v2_setting_inventory.py \
  tests/project/v2/test_v2_opponent_* tests/project/v2/test_v2_m1[6-9]* \
  tests/project/v2/test_v2_m2[0-1]*
git commit -m "Make M14 through M21 evidence validation portable"
```

Use one scope-specific commit per execution unit; the command above illustrates
the aggregate file set only.

### Task 5: M22 offline history and relocated live evidence

**Files:**

- Modify: `scripts/v2/run_m22_final_evaluation.py`
- Modify: `scripts/v2/validate_m22_final_evaluation.py`
- Modify: `scripts/v2/validate_m22_followup_evaluation.py`
- Modify: `scripts/v2/validate_m22_followup_v2_evaluation.py`
- Modify: `scripts/v2/validate_m22_final_runtime_source.py`
- Modify: `scripts/v2/validate_m22_followup_runtime_source.py`
- Modify: `scripts/v2/validate_m22_recovery_evidence.py`
- Modify: `scripts/v2/validate_m22_training_evidence.py`
- Modify: `scripts/v2/validate_m22_qualification_evidence.py`
- Modify: `scripts/v2/build_m22_native_corpus.py`
- Modify: `scripts/v2/validate_m22_native_corpus.py`
- Modify: M22 final/follow-up runtime, preparation, native-corpus,
  qualification, and evaluation evidence tests.

**Interfaces:**

- Consumes: `ArtifactContext`; immutable M22 report roots and prior-attempt record.
- Produces: offline semantic validation of all three retained evaluation suites and
  explicit relocated live rehashing, with exact `required_live_inputs(root)`
  closures for runtime, evaluation, learning, and qualification artifacts.

- [ ] **Step 1: Add failing history and relocation tests**

Add:

```text
M22FinalEvaluationSourceTests.test_offline_validation_does_not_open_prior_attempt_artifacts
M22FollowupEvaluationEvidenceTests.test_offline_validation_does_not_resolve_evaluator
M22FollowupV2EvaluationEvidenceTests.test_offline_validation_does_not_resolve_evaluator
M22FinalEvaluationSourceTests.test_offline_validation_does_not_resolve_bwrap
M22FollowupEvaluationEvidenceTests.test_offline_validation_does_not_resolve_bwrap
M22FollowupV2EvaluationEvidenceTests.test_offline_validation_does_not_resolve_bwrap
M22FollowupEvaluationEvidenceTests.test_relocated_live_root_preserves_frozen_failed_status
M22FollowupV2EvaluationEvidenceTests.test_relocated_live_root_preserves_frozen_passing_status
M22FinalRuntimeSourceTests.test_relocated_root_does_not_rewrite_retained_artifact
M22FollowupRuntimeSourceTests.test_relocated_root_does_not_rewrite_retained_artifact
M22FinalRuntimeSourceTests.test_offline_validation_never_opens_recorded_runtime_paths
M22FinalRuntimeSourceTests.test_relocated_live_runtime_and_smokes_pass
M22FinalRuntimeSourceTests.test_relocated_m21_base_is_used_for_patch_check
M22FollowupRuntimeSourceTests.test_offline_validation_never_opens_recorded_runtime_paths
M22FollowupRuntimeSourceTests.test_relocated_live_runtime_and_smokes_pass
M22FollowupRuntimeSourceTests.test_relocated_m21_base_reproduces_source_identity
M22NativeCorpusTests.test_exact_rebuild_is_offline_even_when_recorded_artifacts_exist
M22QualificationTests.test_native_corpus_revalidation_is_explicitly_offline
```

Patch `pathlib.Path.is_dir`, evaluator resolution, or the prior-attempt artifact
loader to raise on live access in offline tests. Assert exact outcomes:
final-v1 `FAIL`, follow-up-v1 `FAIL` with zero classified failures, follow-up-v2
`PASS`, all with 42 cases.

- [ ] **Step 2: Run focused M22 tests and capture the current absolute-path failure**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest -v \
  tests.project.v2.test_v2_m22_final_evaluation_source \
  tests.project.v2.test_v2_m22_followup_evaluation_evidence \
  tests.project.v2.test_v2_m22_followup_v2_evaluation_evidence \
  tests.project.v2.test_v2_m22_final_runtime_source \
  tests.project.v2.test_v2_m22_followup_runtime_source
```

Expected: offline tests fail in `validate_prior_attempt` or a recorded artifact
path.

- [ ] **Step 3: Add explicit context through final and follow-up validation**

Change all public validation entry points to accept:

```python
*, artifact_context: ArtifactContext | None = None
```

Replace evaluator literals and generic current-host roots with
`ArtifactContext` for frozen-set paths and explicit typed role-path parameters
for inputs whose authority exists only in `LiveInputManifest`. In live mode,
resolve:

```text
v2-m22-final-evaluation-a
v2-m22-final-evaluation-b
v2-m22-followup-evaluation-a
v2-m22-followup-v2-evaluation-a
v2-m22-final-runtime-c
v2-m22-followup-runtime-a
```

using logical set names from each frozen record rather than hard-coded current
host roots. `v2-m22-final-evaluation-a` is the nonexecuting prior attempt and
`v2-m22-final-evaluation-b` is the 42-case final-v1 run. Resolve the final-v1
evaluator only through the `final-v1-evaluator` host-manifest role because no
frozen record authorizes the old test literal's artifact-set name.

Move every `shutil.which("bwrap")` and tool hash behind live mode. Offline
evaluation validates only the committed bwrap identity field and never resolves
a host binary. Full receives the exact preflighted `bwrap` path as a typed tool
argument and compares its digest with the frozen identity before reading case
artifacts. Missing/wrong bwrap is therefore a full preflight failure, never a
contract dependency.

Split `run_m22_final_evaluation.validate_prior_attempt()` into record-only and
live portions. Offline still validates its schema, canonical digest, zero
case/evaluator/native executions, one manifest read, and frozen failure category;
only live checks its log/artifact files.

Preserve CLI exit statuses exactly: final-v1 and follow-up-v1 semantic `FAIL`
return `2`; follow-up-v2 returns `0`. Missing live input returns `1` after full
preflight and can never satisfy expected `2`.

For recovery-v1, pass the `recovery-v1-*` artifact/executable/corpus roles. For
recovery-v2 and training, pass their distinct artifact roots plus the shared
`v2-campaign-executable` and `v2-corpus-binary`. Qualification receives
`qualification-artifacts`, `qualification-executable`, `v2-corpus-binary`, and
derives its one selected checkpoint below `training-artifacts` from the committed
checkpoint path. Do not guess set names from relative checkpoint paths. Offline
summaries label those closures unvalidated; full requires every role in aggregate
preflight and passes the typed paths explicitly.

Update `build_m22_native_corpus.validate_sources()` to take an explicit
`ArtifactContext` and pass `ArtifactContext.offline()` to every nested G15–G21
validator. `validate_m22_native_corpus.py` and the qualification validator also
request offline nested corpus validation explicitly. Corpus construction consumes
committed projections, never retained report bodies, so it must not become live
merely because the full driver has a configured artifact root.

Qualification calls the nested training validator with no live artifact paths.
After that offline authority check, qualification alone inspects the selected
checkpoint through the typed `training-artifacts` role. Add
`M22QualificationTests.test_nested_training_validation_cannot_traverse_live_artifacts`
and assert the standalone training validator owns the only complete training-tree
traversal.

In `test_v2_m22_final_runtime_preparation.py` and
`test_v2_m22_followup_runtime_preparation.py`, replace paths derived from
`m21["source"]["path"]` with
`context.artifact_set("v2-m21-broad-a") / "source"`; classify those exact patch
application methods as live. No existence probe may be performed in an offline
test.

- [ ] **Step 4: Keep frozen source identities valid after validator refactoring**

Every affected M22 recovery, training, qualification, runtime, and evaluation
record binds source files from its historical repository commit, including
validators changed by this refactor. Change all such source validation to hash
the recorded Git blob, never the current working file:

```python
def historical_blob(root: pathlib.Path, commit: str, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=root, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    require(completed.returncode == 0, f"historical source is unavailable: {path}")
    return completed.stdout
```

For every source record, require
`sha256_bytes(historical_blob(root, commit, path)) == record["sha256"]`, then verify the recorded
commit/tree. Add mutations for commit, tree, file path/order, file digest, and
inventory digest. Do not rewrite any frozen source record to name the refactored
current files.

- [ ] **Step 5: Remove M22 test literals and run all M22 offline tests**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest discover \
  -s tests/project/v2 -p 'test_v2_m22*.py' -v
rg -n '/home/thecl|\.codex/artifacts' tests/project/v2/test_v2_m22*
```

Expected: offline M22 tests pass, live-only tests explicitly skip, frozen statuses
and all mutation labels remain, and `rg` exits `1`.

- [ ] **Step 6: Commit and review units 5A, 5B, and 5C separately**

```bash
git add scripts/v2/run_m22_final_evaluation.py \
  scripts/v2/build_m22_native_corpus.py scripts/v2/validate_m22_* \
  tests/project/v2/test_v2_m22_*
git commit -m "Separate M22 historical and live evidence validation"
```

Use one scope-specific commit per execution unit; the command above illustrates
the aggregate file set only.

### Task 6: Portable M23 patch-application tests

**Files:**

- Modify: `tests/project/v2/test_v2_m23_ingame_source.py`
- Modify: `tests/project/v2/test_v2_m23_visible_source.py`

**Interfaces:**

- Consumes: configured `ArtifactContext`.
- Produces: no host-specific V2 test path remains and the driver can preflight
  exact source directories for both live patch-application methods.

- [ ] **Step 1: Write the path-independence assertions**

Add a test in each module that patches `resolve_artifact_root` to a temporary base
and asserts the patch application source is respectively:

```text
<base>/v2-m22-followup-runtime-a/source
<base>/v2-m23-visible-runtime-baseline-a
```

Keep the existing test names
`test_patch_applies_exactly_to_retained_m22_source_when_available` and
`test_patch_applies_after_source_integrated_equivalence_foundation`.

- [ ] **Step 2: Replace both literal paths with context lookups**

Offline mode explicitly skips only these retained-source application methods.
Live mode requires the relocated source and executes the same
`git apply --check --whitespace=error-all` command. Full preflight later makes a
missing source a failure before unittest starts.

Task 7 registers exact directory requirements for
`v2-m22-followup-runtime-a/source` and
`v2-m23-visible-runtime-baseline-a`; these are test-owned live inputs rather than
standalone validator modules.

- [ ] **Step 3: Run focused M23 source tests and the global literal guard**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest -v \
  tests.project.v2.test_v2_m23_ingame_source \
  tests.project.v2.test_v2_m23_visible_source
rg -n '/home/thecl|\.codex/artifacts' tests/project/v2
```

Expected: focused tests pass with two explicit offline skips; `rg` has no output
and exits `1`.

- [ ] **Step 4: Commit Task 6**

```bash
git add tests/project/v2/test_v2_m23_ingame_source.py \
  tests/project/v2/test_v2_m23_visible_source.py
git commit -m "Make M23 source application tests relocatable"
```

### Task 7: Wire tier modes, complete artifact preflight, and validator CLIs

**Files:**

- Modify: `scripts/v2/verify_driver.py`
- Modify: `scripts/v2/artifact_context.py`
- Modify: `scripts/v2/source_context.py`
- Modify: `scripts/v2/verify.sh`
- Modify: every validator CLI migrated in Tasks 3–5.
- Modify: `tests/project/v2/test_v2_verify_driver.py`
- Modify: `tests/project/v2/test_v2_artifact_context.py`
- Modify: `tests/project/v2/test_v2_source_context.py`

**Interfaces:**

- Consumes: all migrated validator contexts and the logical artifact-set inventory.
- Produces: portable fast/contract tiers and fail-closed relocated full execution.

- [ ] **Step 1: Add failing driver integration tests**

Add:

```text
test_fast_ignores_configured_artifact_root_and_never_builds_live_context
test_contract_ignores_configured_artifact_root_and_runs_artifact_validators_offline
test_contract_passes_live_source_context_only_to_research_and_setting_inventory
test_contract_materialization_does_not_resolve_or_bind_bwrap
test_full_materializes_consumer_specific_m22_binary_roles
test_full_routes_m14_executable_to_every_recorded_consumer
test_full_never_passes_live_base_to_an_m15_generation_cli
test_full_uses_explicit_artifact_root_before_environment
test_full_uses_environment_artifact_root_when_cli_is_absent
test_full_without_artifact_root_fails_preflight_before_commands
test_full_preflight_reports_every_missing_artifact_set
test_full_preflight_reports_source_repository_and_every_named_live_input_role
test_full_preflight_reports_missing_nested_files_git_and_bwrap_before_execution
test_full_preflight_rejects_bwrap_digest_disagreement_or_mismatch
test_full_does_not_convert_missing_live_input_to_skip
```

Assert fast does not preflight the OpenTTD submodule; contract preflights the
pinned submodule but not artifacts; full preflights both before its first process.

- [ ] **Step 2: Define the complete logical live-input inventory**

Every artifact-backed validator migrated in Tasks 3–6 exports the pure function
`required_live_inputs(root) -> tuple[ArtifactRequirement | RoleRequirement, ...]`.
It parses only
committed records and enumerates the exact logical set, required relative path,
file/directory kind, consumer, and recorded digest for every live read—including
all paths derived through `relocate()`, dynamic package/runtime `artifact_dir`
values, report/save/log bodies, source Git directories, 42-case evaluation
trees, checkpoint files, OpenGFX/content assets, and both M23 patch baselines.
Live validation resolves paths only from this returned closure; it may not invent
an additional path after preflight.

The driver aggregates those functions with the object-repository commit,
every exact `LiveInputManifest` role, and immutable `ToolRequirement` records for
the configured Python, Git, and `bwrap`. The `bwrap` requirement uses the frozen
digest
`52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712`
from each evaluation identity and rejects a disagreement between records.
Sort and de-duplicate before checking every nested path, kind, symlink component,
digest, source commit, and tool. No “at minimum” or set-directory-only preflight
is permitted.

Add one registry-coverage test that enumerates every artifact-backed command and
fails if its module lacks `required_live_inputs`. Add focused coverage fixtures
for literal `artifact_set()`, `relocate()`, package/runtime record-derived paths,
role paths, and tools. Delete no coverage fixture until a mutation that adds an
unregistered live read fails this test.

- [ ] **Step 3: Pass mode and root explicitly through commands**

Fast and contract set `OPENTTD_RL_VALIDATION_MODE=offline` and do not pass an
artifact root even when the environment contains one. Contract passes the pinned
`--object-repo` only to research-baseline and setting-inventory commands so their
source-completeness claims remain honest. Full sets artifact mode `live`,
passes `--artifact-root <base>` to every artifact-backed migrated validator, and passes any
separately required executable/corpus/training path from the validated live-input
manifest.

At this task, extend `VerificationConfig` with the resolved object repository,
optional `LiveInputManifest`, and preflighted tool paths, change `execute_command` to receive the complete
config rather than only `repository_root`, and add a pure
`materialize_command(command, config)` step. Materialization appends only the CLI
arguments declared by that command's typed requirements and constructs a fresh
environment; it never mutates the inventory. Add a test proving the same
`CommandSpec` materializes offline for contract artifact checks and live for full
without retaining state between calls.

Add immutable `ArgumentBinding(option, source, key=None)` records to
`CommandSpec`, where `source` is exactly `artifact-root`, `object-repository`,
`live-role`, or `tool`. A role/tool binding names one Task 2 manifest role or
preflighted tool and its target CLI option—for example
`m14-openttd-executable -> --openttd` and
`recovery-v1-corpus -> --corpus`. Contract materializes only the two source
bindings; full materializes source, artifact, role, and tool bindings. This table, not
CLI-name heuristics, prevents a generation command from receiving a validation
base.

Map role-backed directories and tools explicitly:

```text
recovery-v1-artifacts    -> recovery-v1 --artifact-root
recovery-v2-artifacts    -> recovery-v2 --artifact-root
training-artifacts       -> training --artifact-root
qualification-artifacts  -> qualification --artifact-root
training-artifacts       -> qualification --training-artifact-root
final-v1-evaluator       -> final-v1 --evaluator
m14-openttd-executable   -> package/runtime/map/ShipAI --openttd
bwrap tool               -> final/follow-up/follow-up-v2 --bwrap
```

Bind each recovery/training/qualification executable and corpus role to its
consumer's existing `--executable`/`--corpus` options.

Standalone migrated validator CLIs use `add_artifact_root_argument()` and source
validators use `add_object_repository_argument()`. No
validator directly reads `OPENTTD_RL_ARTIFACT_ROOT`; the driver resolves it once.
Switch action, observation, episode, native-reset-matrix, and map-matrix command
IDs to the five validation-only CLIs created in Task 3. Generation CLIs never
receive a current-host live base.

The cumulative V2 unittest command is the sole exception to CLI injection: in
full, materialization sets `OPENTTD_RL_ARTIFACT_ROOT` to the already-preflighted
base and `OPENTTD_RL_VALIDATION_MODE=live` so live test methods use the same
closure. Fast/contract explicitly remove the root and set mode `offline`.
Production validators never resolve that environment variable themselves.

Replace the fast unit command with an explicit module inventory that contains
only synthetic/offline modules. Contract runs that fast inventory, each
standalone offline validator once, and remaining offline mutation modules. Full
runs contract plus live methods/native commands/V1. Inventory tests lock each
module to exactly one tier.

Keep `scripts/v1/traceability.sh` byte-for-byte unchanged. It runs only in full,
after the object-repository preflight, so its ten source-live tests cannot leak
into fast/contract. `materialize_command` starts from an allowlisted environment
and always unsets `M07_TRAINER_EXECUTABLE`, `M07_LIVE_MANIFEST`,
`M07_RECOVERY_REPORT`, `M08_CUDA_REPORT`, `M08_CPU_SMOKE_REPORT`,
`M08_CUDA_SMOKE_REPORT`, and `M08_LIVE_MANIFEST` in every tier, including full.
Those optional V1 live inputs have no typed preflight in this refactor, so ambient
host values may not expand the gate after preflight. Add a driver test that seeds
all seven variables with existing paths and proves none reaches V1 traceability;
the pinned source-live V1 tests still run in full through the preflighted
`openttd-upstream` checkout.

- [ ] **Step 4: Run tier commands**

```bash
scripts/v2/verify.sh --tier fast
scripts/v2/verify.sh --tier contract
env -u OPENTTD_RL_ARTIFACT_ROOT scripts/v2/verify.sh --tier full
```

Expected: fast and contract pass without retained artifacts; full exits `2`
before launching commands and names every missing nested artifact, role, source,
or tool input. Neither fast nor
contract output contains `G23`, `RELEASE`, or a gate status.

- [ ] **Step 5: Commit Task 7**

```bash
git add scripts/v2/verify_driver.py scripts/v2/artifact_context.py \
  scripts/v2/source_context.py scripts/v2/verify.sh scripts/v2/validate_* \
  scripts/v2/freeze_m15_* \
  scripts/v2/run_m15_native_reset_matrix.py scripts/v2/run_m21_broad_matrix.py \
  tests/project/v2/test_v2_verify_driver.py \
  tests/project/v2/test_v2_artifact_context.py \
  tests/project/v2/test_v2_source_context.py
git commit -m "Wire portable V2 verification tiers"
```
### Task 8: Remove duplicate authoritative passes

**Files:**

- Modify: `scripts/v2/verify_driver.py`
- Modify: `tests/project/v2/test_v2_verify_driver.py`
- Modify: V2 test modules containing only duplicate `test_repository_*_passes`
  methods or deterministic-builder repetitions.

**Interfaces:**

- Consumes: portable contract inventory from Task 7.
- Produces: one authoritative committed-record invocation per validator while
  retaining all mutations and live checks.

- [ ] **Step 1: Lock the authoritative command-to-test mapping**

Add `test_every_removed_repository_pass_has_one_authoritative_command` with a
table mapping each removed method's module to the exact contract command ID.
Include research/setting/opponent/competition, every M15–M21 source/evidence
validator, M22 learning/corpus/recovery/training/qualification/runtime/manifests/
evaluations, M23 release contract, and traceability.

Assert each command ID occurs once. Assert final-v1 and follow-up-v1 both still
expect `2`.

- [ ] **Step 2: Remove three redundant top-level processes**

Delete from inventory:

```text
m22-corpus-binary
m22-followup-manifest-build
m22-followup-v2-manifest-build
```

Keep `test_v2_m22_native_corpus_binary.py` as the one binary round-trip behavior
test. Both manifest validators already rebuild and byte-compare canonical output.

Update cumulative inventory counts to:

```python
self.assertEqual((len(fast), len(contract), len(full)), (1, 52, 53))
```

where fast's one command is the explicit offline unittest inventory.

- [ ] **Step 3: Delete only duplicate repository-pass methods**

Remove methods matching the reviewed mapping, including the two
`test_manifest_is_exact_deterministic_build` methods. Retain every schema,
canonicalization, mutation, error classification, live artifact, source identity,
and expected-status test.

Do not delete a method when its standalone validator does not exercise the same
repository input. Add the missing authoritative command instead.

- [ ] **Step 4: Prove mutations remain and contract invokes each validator once**

Run:

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_verify_driver -v
scripts/v2/verify.sh --tier fast
scripts/v2/verify.sh --tier contract
```

Also compare pre/post mutation method names saved in the Task 8 report. Every
removed name must be in the authoritative mapping; every non-pass mutation name
must remain.

- [ ] **Step 5: Commit Task 8**

```bash
git add scripts/v2/verify_driver.py tests/project/v2
git commit -m "Remove duplicate V2 repository validation passes"
```

### Task 9: Consolidate M22 evaluation fixtures and validation mechanics

**Files:**

- Create: `scripts/v2/m22_evaluation_validation.py`
- Create: `tests/project/v2/m22_fixture_support.py`
- Create: `tests/project/v2/test_v2_m22_evaluation_common.py`
- Modify: `scripts/v2/validate_m22_final_evaluation.py`
- Modify: `scripts/v2/validate_m22_followup_evaluation.py`
- Modify: `scripts/v2/validate_m22_followup_v2_evaluation.py`
- Modify: the three M22 evaluation-source tests, two follow-up manifest tests,
  and two follow-up evidence tests.

**Interfaces:**

- Consumes: Task 5 historical-blob and artifact-context boundaries.
- Produces: shared mechanical validation without merging distinct acceptance
  policies or statuses.

- [ ] **Step 1: Write common-mechanics tests**

Create tests for source path/order/hash/commit/tree mutations across final-v1,
follow-up-v1, and follow-up-v2, plus fixture isolation:

```python
for spec in SUITES:
    for label, mutate, pattern in SOURCE_MUTATIONS:
        with self.subTest(suite=spec.label, label=label):
            value = copy.deepcopy(spec.report["source"])
            mutate(value)
            with self.assertRaisesRegex(spec.error_type, pattern):
                common.validate_source_identity(
                    value, self.root, mechanics=spec.runner,
                    suite_label=spec.message_prefix,
                    require=spec.validator.require,
                )
```

Assert fixture reports contain exactly 42 fresh runs and a mutation never changes
the base object.

- [ ] **Step 2: Implement shared mechanical primitives**

Create typed functions `load_json_object(path, *, error_type)`,
`validate_schema(value, schema, label, *, error_type)`,
`historical_blob(root, commit, path, require)`,
`validate_source_identity(value, root, mechanics, suite_label, require)`,
`validate_report_digest(report, mechanics, suite_label, require)`, and
`validate_aggregate_records(report, cases, mechanics, suite_label, live,
require)`. The first five return the loaded object, `None`, historical bytes,
`None`, and `None`; the aggregate function returns the existing summary object.

`validate_aggregate_records` recomputes protocol, statistics, acceptance, failure
counts, and derived status. It returns the existing summary shape and does not
decide suite-specific immutable history or error messages.

Create fresh-data test support:

```python
@dataclasses.dataclass(frozen=True)
class MutationCase:
    label: str
    mutate: Callable[[dict[str, Any]], None]
    error_pattern: str
    live: bool = False
```

Add typed factories `make_case(case_id, *, private_seed)`,
`make_run(mechanics, case, ordinal)`, `make_report(mechanics, spec)`, and
`run_named_mutations(test, base, cases, reject)`. The first three return fresh
JSON objects; the last returns `None` after executing every labeled mutation.

Every factory deep-copies nested input and every mutation runs under
`subTest(label=mutation.label)`.

- [ ] **Step 3: Make validators thin without changing public results**

Move only duplicated load/schema/historical-source/digest/protocol/statistics
mechanics. Keep final-v1, follow-up-v1, and follow-up-v2 exception types,
immutable dependencies, manifest logic, failure classification, acceptance
predicate, CLI prefix, and exit status suite-local.

Preserve:

```text
final-v1: 42 cases, FAIL, exit 2
follow-up-v1: 42 cases, zero classified failures, FAIL, exit 2
follow-up-v2: 42 cases, zero failures, PASS, exit 0
one manifest read; 42 evaluator/native processes; zero retry/replacement
```

- [ ] **Step 4: Parameterize copied tests and remove superseded token assertions**

Move common fake report construction and named mutations into
`m22_fixture_support.py`. Delete source-token/order tests only after common
behavior tests cover source order, SHA, inventory SHA, commit, tree, one manifest
read, zero retry/replacement, and no post-selection.

Keep the follow-up-v2 routing-labeled multimodal positive/negative acceptance
tests; they are not common with follow-up-v1.

- [ ] **Step 5: Run focused M22 suite**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest -v \
  tests.project.v2.test_v2_m22_evaluation_common \
  tests.project.v2.test_v2_m22_final_evaluation_source \
  tests.project.v2.test_v2_m22_followup_evaluation_source \
  tests.project.v2.test_v2_m22_followup_v2_evaluation_source \
  tests.project.v2.test_v2_m22_followup_manifest \
  tests.project.v2.test_v2_m22_followup_v2_manifest \
  tests.project.v2.test_v2_m22_followup_evaluation_evidence \
  tests.project.v2.test_v2_m22_followup_v2_evaluation_evidence
```

Expected: all offline tests pass with the three immutable outcomes unchanged.

- [ ] **Step 6: Commit Task 9**

```bash
git add scripts/v2/m22_evaluation_validation.py \
  scripts/v2/validate_m22_*evaluation.py \
  tests/project/v2/m22_fixture_support.py \
  tests/project/v2/test_v2_m22_*
git commit -m "Share M22 evaluation validation and fixtures"
```

### Task 10: Cache immutable M23 golden, package, and report fixtures

**Files:**

- Create: `tests/project/v2/m23_fixture_support.py`
- Create: `tests/project/v2/test_v2_m23_fixture_support.py`
- Modify: `tests/project/v2/test_v2_m23_packages.py`
- Modify: `tests/project/v2/test_v2_m23_ingame_source.py`
- Modify: `scripts/v2/m23_ingame.py`

**Interfaces:**

- Consumes: unchanged `m23_golden` and `m23_package` public APIs.
- Produces: one immutable base per architecture/report and isolated clones for
  mutations.

- [ ] **Step 1: Write fixture immutability and cached-value tests**

Test:

```python
before = fixtures.snapshot_tree(base)
with tempfile.TemporaryDirectory() as raw:
    clone = fixtures.clone_package(base, pathlib.Path(raw))
    (clone / "INSTALL.md").write_bytes(b"mutated\n")
self.assertEqual(fixtures.snapshot_tree(base), before)
```

Patch `m23_golden.decode` to raise while validating a copied in-memory report to
prove semantic mutations do not rebuild/decode the golden.

- [ ] **Step 2: Implement shared fixture helpers**

Create typed helpers `make_golden_records(index)`, `make_golden_binary()`,
`make_package(parent, root, contract, architecture, records)`,
`clone_package(base, parent)`, `snapshot_tree(root)`, and
`make_equivalence_report(records, *, golden_sha256, runtime, model_shas)`.
They return, respectively, immutable golden records, encoded bytes, a package
path, a cloned package path, sorted path/SHA pairs, and a fresh report object.

`clone_package` uses `shutil.copytree`, never links, and requires a new target.
`snapshot_tree` returns sorted relative path/SHA pairs and rejects symlinks.

Extract `validate_equivalence_value(value, runtime, golden_sha256, records,
package_report) -> dict[str, Any]` in `m23_ingame.py`.

The existing file validator remains public and performs canonical bytes, hash,
and decode before delegating. Full validation is never cached.

- [ ] **Step 3: Convert package mutations to cloned bases**

Generate records and one base package per exact architecture in `setUpClass`.
Clone before every mutation and verify base snapshots again in `tearDownClass`.

Retain all 28 frozen rejection labels in exact order plus golden-definition,
carried-hidden, illegal-action, evaluation status/case/tolerance, and host-path
mutations.

- [ ] **Step 4: Convert in-game mutations to copied report values**

Write/decode the 48-case/580-row binary once. Keep one positive test through the
full file validator. Run semantic mutations against deep copies through
`validate_equivalence_value` with labels:

```text
runtime-identity
status
case-count
action-exact
failure-count
maximum-error
```

- [ ] **Step 5: Run correctness and timing comparison**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest -v \
  tests.project.v2.test_v2_m23_fixture_support \
  tests.project.v2.test_v2_m23_packages \
  tests.project.v2.test_v2_m23_ingame_source

for run in 1 2 3; do
  /usr/bin/time -f "run=$run wall=%e" \
    env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts/v2 \
    python3 -m unittest \
      tests.project.v2.test_v2_m23_packages \
      tests.project.v2.test_v2_m23_ingame_source
done
```

Expected: correctness passes; median wall time is at least 30% below the recorded
8.18-second baseline. Record timing but do not add a flaky timing assertion.

- [ ] **Step 6: Commit Task 10**

```bash
git add tests/project/v2/m23_fixture_support.py \
  tests/project/v2/test_v2_m23_fixture_support.py \
  tests/project/v2/test_v2_m23_packages.py \
  tests/project/v2/test_v2_m23_ingame_source.py scripts/v2/m23_ingame.py
git commit -m "Cache immutable M23 test fixtures"
```

### Task 11: Document tiers and verify the complete refactor

**Files:**

- Create: `docs/project/V2_VERIFICATION.md`
- Modify: `README.md`
- Modify: `scripts/v2/verify_driver.py`
- Modify: `tests/project/v2/test_v2_verify_driver.py`

**Interfaces:**

- Consumes: all prior task outputs.
- Produces: documented developer commands, a complete coverage inventory, and
  final evidence that no frozen project bytes changed.

- [ ] **Step 1: Add documentation-presence and inventory tests**

Test that the documentation contains exact commands for fast, contract, and full,
states full is the no-argument default, explains offline versus live, documents
`OPENTTD_RL_ARTIFACT_ROOT`, the required `v2-live-inputs.json` roles, the pinned
OpenTTD object repository, and says fast/contract cannot make G23 claims.

Add an inventory test that every V2 test module is assigned exactly once to a
tier and every standalone validator is invoked exactly once in contract/full.

- [ ] **Step 2: Write the verification guide**

Document:

```bash
./scripts/v2/verify.sh --tier fast
git submodule update --init --recursive
./scripts/v2/verify.sh --tier contract
OPENTTD_RL_ARTIFACT_ROOT=/absolute/openttd-rl-artifacts \
  ./scripts/v2/verify.sh
```

Explain that contract validates artifact records offline while the initialized
submodule proves research/setting source completeness; full relocates only
filesystem reads. Missing object repositories, manifest roles, or artifact sets
are preflight errors, and retained final-v1/follow-up-v1 exit `2` results are
expected semantic outcomes distinct from infrastructure failure.

Update README's V2 verification section to link the guide and avoid claiming a
clean clone can run live evidence without declared caches.

- [ ] **Step 3: Run final portable verification**

```bash
rg -n '/home/thecl|\.codex/artifacts' tests/project/v2
scripts/v2/verify.sh --tier fast
scripts/v2/verify.sh --tier contract
env -u OPENTTD_RL_ARTIFACT_ROOT scripts/v2/verify.sh --tier full
```

Expected: `rg` exits `1`; fast and contract pass; full exits `2` before commands
and lists all missing live inputs by category.

- [ ] **Step 4: Run quality and frozen-boundary guards**

```bash
python3 -m compileall -q scripts/v2 tests/project/v2
bash -n scripts/v2/verify.sh
git diff --check
git diff 46c4033 -- config/v1 scripts/v1 config/v2 docs/project/schema \
  'docs/project/G*_GATE_REPORT.md'
```

Expected: compilation, Bash syntax, and whitespace pass; the frozen-boundary diff
is empty.

If a complete relocated artifact tree becomes available, additionally run:

```bash
./scripts/v2/verify.sh --tier full \
  --artifact-root /absolute/openttd-rl-artifacts
```

A missing tree is not a release pass and does not block completion of the
portable refactor; it remains required for later G23 acceptance.

- [ ] **Step 5: Record final timing and test inventory**

Run three focused M23 timings, compare the median with 8.18 seconds, and record
the before/after commands and values in the task report. Record counts of fast,
contract, and full commands and skipped live-only methods. Do not claim G23.

- [ ] **Step 6: Commit Task 11**

```bash
git add docs/project/V2_VERIFICATION.md README.md \
  scripts/v2/verify_driver.py tests/project/v2/test_v2_verify_driver.py
git commit -m "Document portable V2 verification workflow"
```

## Completion audit for this plan

Before calling the refactor complete, the controller must verify every design
criterion against current state:

1. Search proves no V2 test contains a host-specific artifact lookup.
2. Fast passes without submodule or artifacts and emits no gate claim.
3. Contract passes from an initialized recursive clone without artifacts.
4. Default full fails aggregate preflight without artifacts, the pinned source
   repository, or named live-input roles and cannot skip mandatory live work.
5. Every retained mutation label and the three M22 outcomes remain exact.
6. All 28 M23 rejections and all in-game report mutations remain.
7. Authoritative validator inventory has no duplicate builder/pass executions.
8. Median focused M23 time improves by at least 30% on the same host.
9. Driver/artifact/source-context/tier/preflight behavior has direct tests, and
   the command inventory matches every literal artifact-set consumer.
10. Frozen evidence, schema, G22/M23 contract, and V1 bytes are unchanged.
11. Research/setting completeness is never claimed from an offline source
    context; M22 role-specific closures are never claimed without the live-input
    manifest; nested corpus/competition validation is explicitly offline.

After review, begin a new design/plan cycle for the persistent road-passenger
normal-command executor and save/load vertical slice. Do not expand this plan into
runtime gameplay work.
