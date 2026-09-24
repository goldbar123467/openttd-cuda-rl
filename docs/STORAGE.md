# Development artifact retention

Keep research evidence losslessly. Most storage is verbose public request logs
and tensor snapshots, not source or model weights. Compress completed development
artifacts before considering off-drive archival or checkpoint removal.

The completed 2026-09-24 cleanup records are at
`~/.local/share/openttd-rl/maintenance/storage-20260924-01`. It saves 149.65 GiB
of artifact bytes, with a 149.01 GiB observed net increase in WSL available space.
The report and preservation checks are copied into
`runs/2026-09-24/storage-cleanup-01/` in the checkout.

The maintenance command below is separate from training. It retains the existing
collector and tensor-archive defaults, so qualified collector/checkpoint source
identities remain unchanged. Run it in WSL with experiment producers stopped.
It uses at most two gzip workers and never launches training or a game.

## Retention rules

- Keep reports, configurations, registrations, failures, native transitions,
  source captures, model packages, final models, and recovery checkpoints.
- Preserve closed held-out evidence and frozen release records unchanged.
- Explicitly exclude the latest run and any run needed by a queued consumer.
- Compress only `requests.jsonl`, `tensors-*.bin`, and the explicitly selected
  `tensors-NNNNNN-observation.json` / `tensors-NNNNNN-candidates.json` metadata
  belonging to completed development runs. Failed or unmarked cases stay untouched.
- Do not prune checkpoint files without a reviewed list of required recovery
  boundaries. Do not move experiments off-drive without a named destination and
  a verified copy. No off-drive archive or checkpoint pruning has been performed.
- Never use the parent OpenTTD data directory as a cleanup root.

## Plan and execute compression

Create a fresh maintenance directory outside `runs`, then run from the checkout:

```bash
RL_ROOT=$HOME/.local/share/openttd-rl
MAINTENANCE="$RL_ROOT/maintenance/storage-new"
mkdir "$MAINTENANCE"
python3 scripts/dev/archive_completed.py plan \
  --root "$RL_ROOT/runs" \
  --exclude v2-financial-horizon256-learning-01 \
  --output "$MAINTENANCE/plan.json"
python3 scripts/dev/archive_completed.py apply \
  --plan "$MAINTENANCE/plan.json" --output "$MAINTENANCE/execution"
```

Review the plan before execution. It records exact relative paths, sizes, file
identities, completion-marker hashes, exclusions and skipped cases. The apply
command checks these again. It uses gzip level 1, verifies every decompressed
SHA-256 against both the initial and reread original, publishes the archive
without replacing existing files, and flushes a verification journal before
removing that original. A failure before verified publication retains the
original and any partial archive; already archived files remain journaled.
Existing `.gz` or `.gz.partial` files cause rejection, not replacement. A fresh
plan can handle remaining originals after an interruption; inspect conflicts
before retrying. `journal.jsonl` and `summary.json` retain actual savings.

The default plan includes request logs and binary snapshots. For the large JSON
metadata snapshots, make a separate plan with `--kind tensor_metadata`, retaining
the same root and exclusions. Execute that plan only after the earlier pass has
finished, keeping the total at two compression workers. Use `apply --batch-size
128` for many small files on the same Linux filesystem. Each file still passes
both original hashes and the decompressed hash. Linux `syncfs` makes every
archive and directory entry in the batch durable, then the verification journal
is flushed before any original is removed. A failed flush retains the originals.
This avoids five separate disk flushes per small file. The default batch size
is one; logs can use either mode. Interrupted files retain their partial/complete
archives and originals for inspection; completed journal entries identify the
finished prefix. Never relabel an interrupted full pass as completed.

## Read or restore evidence

`report_shared_v2.py` reads either the original request log or its `.jsonl.gz`
archive. The documented ONNX exporter accepts verified `.bin.gz` files.
Archived scripts and isolated worktrees remain unchanged; older consumers that
require an original log, binary, or metadata path can restore that specific file:

```bash
python3 scripts/dev/archive_completed.py restore \
  --root "$RL_ROOT/runs" --journal "$MAINTENANCE/execution/journal.jsonl" \
  --path 'RUN/worker/requests.jsonl'
```

Use the exact relative path in the journal. Restore checks the compressed hash
and decompressed hash, refuses to overwrite a file, and keeps the archive.
For ad hoc streaming analysis, use Python `gzip.open(path, "rt")` or `gzip -cd`.
Compressed bytes have a new hash; the journal retains the original-byte hash
used by historical provenance records. Do not rewrite those historical records.

Deleting verified originals frees blocks inside WSL. Windows' virtual-disk file
may not shrink automatically; this workflow does not shut down WSL or compact
its virtual disk.
