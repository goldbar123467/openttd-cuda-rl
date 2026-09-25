# Portable single-GPU registered study

**Qualification status:** the full local and container correctness bundles passed, including
historical equivalence, A0/guide-v3/recovery CPU/CUDA agreement at the unchanged
.0001 limit, probe neutrality and exact CPU/CUDA checkpoint resume. Protocol 2
uses the qualified FP64 clipping-norm mode. The pinned image built successfully,
and its native engine, current trainer and historical reference were compiled
and exercised inside the container. The launcher reruns its
complete qualification on the target and refuses registration on failed or
mismatched results.

This package builds the existing native OpenTTD engine and C++/LibTorch trainer,
runs the minimum correctness gates, then registers and executes A0 through A3.
It retains three training seeds per arm, 8,192 decisions per seed, eight training
maps, the frozen training-only early stop, and full 512-decision development games.
No credentials or provider API are required by the runner. Provisioning, publishing
an image/source revision, and payment remain separate operator actions.

The immutable scientific protocol is
[`v2-recovery-study-protocol-2.json`](../../config/dev/v2-recovery-study-protocol-2.json).
It preserves protocol 1 and adds FP64 norm accumulation for clipping in all arms;
the model, gradients and Adam remain float32. Historical clipping remains an
explicit reference mode. The [numerical investigation](../../docs/V2_GRADIENT_NORM_2026-09-25.md)
records the reason and unchanged scientific settings/acceptance thresholds.
A4/A5 require a later prospective registration. Engineering checks do not establish
that any policy learned to play better.

## Capacity and runtime

Use a Linux x86-64 host with one exposed NVIDIA GPU (at least 8 GB nominal VRAM),
at least 16 GB host RAM, four CPU threads, and a driver supporting CUDA 12.8.
The image pins CUDA 12.8.1 Ubuntu 24.04 by digest and Torch 2.9.1+cu128. Native
compilation targets the detected GPU. Each instance must pass its own CPU/CUDA
checks; there is no CPU fallback. Builds use two workers to limit RAM pressure.

Allocate **1,500 GB of persistent volume storage**, mounted at `/data`, and at
least **50 GB of container disk** for the image/runtime. The initial launcher
requires 1,250,000,000,000 free bytes on the study volume. The retained cost
estimate is [in the repository](../../config/dev/v2-recovery-cost-estimate-2.json):
about 704 GB for the mandatory matrix with verified control reuse, plus roughly
160 GB for conditional held-out confirmation, build/qualification artifacts,
and headroom. These are estimates from older local runs, not a storage guarantee.
Before each training segment the runner requires 32 GiB plus a 20 GiB reserve;
before each evaluation it requires 4 GiB plus that reserve. Low space stops work
with all artifacts preserved; it never deletes old attempts to manufacture space.

The historical mandatory runtime estimate is approximately 41-42 hours with
control reuse, excluding builds, correctness gates, reporting/hash verification,
and the conditional held-out run. It does not measure the new norm accumulation's
overhead. GPU type alone does not predict this workload's
wall time. More interrupted attempts can require more space and time.

[Vast volumes](https://docs.vast.ai/guides/instances/storage/volumes) survive
instance deletion but are tied to a physical host and have fixed capacity.
[Container storage](https://docs.vast.ai/guides/instances/storage/types) is deleted
with the instance. The launcher requires a non-root mount containing the study;
the operator must select an actual persistent volume rather than a temporary bind.
Copy results off the host before releasing storage.

## Build a reviewable image

From the committed repository, on a Docker-equipped Linux host:

```bash
revision=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"
docker build --platform linux/amd64 --tag openttd-study:$revision deployment/vast
docker image inspect openttd-study:$revision --format '{{.Id}}'
```

The build context contains only this deployment directory. Large local runs,
models, personal OpenTTD data, and credentials cannot enter the image through it.
The image fetches the source at the exact 40-character `RL_REVISION`, checks a clean
checkout, and requires its entrypoint to match that committed revision. The chosen
commit must be available from the repository before a fresh remote launch. Publish
the reviewed source and image only when ready; use the resulting image digest in
the instance template. The image's apt dependencies are resolved at build time;
the built image digest and recorded runtime identify that concrete environment.
Keep pre-recovery reference commit `e5f69435ab53fa85dbfb2a50f03f57bec2f7a405`
available in the published Git history. The bootstrap checks out that exact
ancestor to build its historical comparison trainer.

Local container execution on an already provisioned GPU machine:

```bash
docker run --rm --gpus 'device=0' \
  --mount type=bind,src=/your/persistent-volume,dst=/data \
  --env RL_REVISION=$revision --env RL_DATA_ROOT=/data/openttd-study \
  openttd-study:$revision
```

## Vast template

Use the reviewed image, one GPU, and attach the 1,500 GB volume at `/data`. Set
`RL_REVISION` to the full commit and `RL_DATA_ROOT=/data/openttd-study`. Keep this
path fixed on restart: artifact paths are intentionally part of registration.
Use **SSH launch mode** for access to logs and copying retained evidence. Set its
on-start script to:

```bash
mkdir -p /data/openttd-study
nohup /opt/openttd-venv/bin/python /opt/openttd-entrypoint.py >> /data/openttd-study/launcher.log 2>&1 &
```

Vast's [template settings](https://docs.vast.ai/guides/templates/template-settings)
replace the image entrypoint in SSH/Jupyter modes, so this on-start command is
necessary. The image's normal ENTRYPOINT also works in ENTRYPOINT mode, but that
mode adds no SSH access. Duplicate starts are rejected by a volume lock.

No running instance, paid job, image publication, or Git push is performed by
these instructions or by the package. An instance continues to incur provider
charges after the runner exits until the operator stops it; there is no automatic
instance deletion or shutdown API call.

## Execution, interruption and results

The launcher proceeds through source composition, native/reference builds,
Python and portable checks, native CPU/CUDA CTest gates, held-out refusal tests,
exact default equivalence, recovery/probe neutrality, and exact CPU/CUDA reset
resume. Registration binds the passing bundle, source, code, engine, trainer,
policy, content, and host runtime before learning begins.

Training is sequential. Development controls can be reused only under identical
source/runtime/content/guide identities. Each failed or early-stopped seed remains
in its arm and cannot be replaced. All four mandatory arms finish before selecting
the first eligible arm in the frozen order. If no arm qualifies, no held-out game
opens. Otherwise, a separate immutable registration permits exactly the 160
specified generalization cases (three models plus two matched controls). The final
split stays closed. A reserved held-out case interrupted during execution is a
failure and is never repeated or used to tune settings.

Restart the same image/revision on the same mounted directory to continue. Training
resumes at the latest published episode-reset checkpoint, including optimizer and
RNG state; incomplete work after that checkpoint remains retained. An interruption
before any checkpoint restarts the same seed with its discarded attempt identified.
Development resumes completed/failed cases and retries incomplete infrastructure
attempts. Builds/qualification allow three attempts; training allows sixteen
segments; development allows three interrupted attempts per case. Repeated errors
stop for inspection rather than consuming compute indefinitely. No process watches
or automatically re-rents instances.

Read `/data/openttd-study/study.json`, `REPORT.md`, `artifact-index.json`, and
`launcher.log`. Build/qualification logs, registrations, training segments, native
traces, weights, development cases, held-out receipts and failed attempts are all
under this directory. A completed run can legitimately report no eligible arm.
Copy the **entire directory**, not only the report or final weights. To rerun
verification after transferring it, restore the registered absolute mount path
and matching environment. Preserve the image digest alongside the copied archive.

The local validation record and remaining limitations are in
[`REFACTOR_2026-09-25_STATUS.md`](../../docs/REFACTOR_2026-09-25_STATUS.md).
The container bundle passed 189 Python tests (four additional MCP-environment
skips), 136 portable checks, 19 native CPU/CUDA tests, held-out refusal, exact
historical comparisons, CPU/CUDA agreement, probe neutrality and exact reset
resume. The local image ID is
`sha256:02fa976708fea6c80868bb029de591dd283b41d85fe25f5b10a84f6d66ba361b`;
this is a local image identity, not a published registry reference.
Testing used WSL2's RTX 2070 driver bindings. Actual Vast provisioning, its GPU
runtime and volume attachment remain untested; the selected host must pass its
own complete bundle before registration. The full learning study has not run.
