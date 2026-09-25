"""Native trainer checkpoints with deterministic, synchronized game resets.

The existing collector still owns all rollout and PPO inputs. A scoped factory
tracks its current environments; checkpoints publish only at an actual reset.
"""
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

from local import ROOT
import run_m07_cpu_ppo as m07
from m08_trainer_client import TrainerClient


def start_trainer(executable, *, deterministic_cudnn=False, entropy_coefficient=0.01, gae_lambda=0.95, **configuration):
    if not math.isfinite(entropy_coefficient) or entropy_coefficient < 0:
        raise ValueError("Entropy coefficient must be finite and nonnegative")
    if not math.isfinite(gae_lambda) or not 0 <= gae_lambda <= 1:
        raise ValueError("GAE lambda must be finite and in [0,1]")
    if not deterministic_cudnn and entropy_coefficient == 0.01 and gae_lambda == 0.95:
        return TrainerClient.start(executable, **configuration)
    # The release client's wire implementation is reused unchanged. Only this
    # development launch adds a kernel-selection option for exact CNN recovery.
    command = [str(executable), "--deterministic-cudnn", "1" if deterministic_cudnn else "0"]
    # Omit the default option so previously built development binaries remain
    # usable. A nondefault request fails explicitly on an older trainer.
    if entropy_coefficient != 0.01:
        command.extend(["--entropy-coefficient", str(entropy_coefficient)])
    if gae_lambda != 0.95:
        command.extend(["--gae-lambda", str(gae_lambda)])
    for name, value in configuration.items():
        command.extend(["--" + name.replace("_", "-"), str(value)])
    return TrainerClient(subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def state_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def compatibility(record, templates):
    # Bind executable semantics and collection/reward code; documentation edits
    # need not invalidate a recoverable run. Full source identity stays in run.json.
    scripts = sorted((ROOT / "scripts/v1").glob("*.py")) + [
        ROOT / "scripts/dev" / name for name in
        ("train_live.py", "training_environment.py", "training_reward.py", "bridge_validation.py", "live_checkpoint.py", "credit_trace.py", "policy_inputs.py", "trainer_diagnostics.py")]
    return {"configuration": {key: record[key] for key in
            ("architecture", "device", "seed", "episode_action_horizon", "training_reward", "rollout_length",
             "environments", "minibatch_size", "epochs", "trainer_sha256", "openttd_sha256", "deterministic_cudnn", "entropy_coefficient", "gae_lambda")}
            | {"spatial_validation": record.get("spatial_validation", "reference"),
               "spatial_validation_numpy": record.get("spatial_validation_numpy")},
            "templates": {path.name: digest(path) for path in templates},
            "collector_sources": {str(path.relative_to(ROOT)): digest(path) for path in scripts}}


def read_checkpoint(path, expected):
    path = Path(path).resolve()
    manifest = json.loads((path / "checkpoint.json").read_text())
    if manifest.get("format") != "openttd-rl-live-reset-checkpoint-1":
        raise ValueError("Unsupported live checkpoint format")
    if manifest["compatibility"] != expected:
        raise ValueError("Checkpoint runtime, configuration, templates or collection source differs")
    if manifest["trainer_sha256"] != digest(path / "trainer.pt"):
        raise ValueError("Checkpoint trainer payload digest mismatch")
    if len(manifest["environments"]) != expected["configuration"]["environments"]:
        raise ValueError("Checkpoint environment count differs")
    ids = [entry["environment_id"] for entry in manifest["environments"]]
    if ids != list(range(len(ids))) or any(entry["episode_index"] < 0 for entry in manifest["environments"]):
        raise ValueError("Checkpoint environment identities invalid")
    return manifest


def native_request(client, kind, path):
    response = client._request(kind, client._pack_string(str(Path(path).resolve())))
    if response:
        raise RuntimeError("Native checkpoint returned an unexpected payload")


class CheckpointClient:
    def __init__(self, client, environments, root, expected, interval, source, resume=None):
        self.client, self.environments, self.root = client, environments, root
        self.expected, self.interval, self.source = expected, interval, source
        self.resume = resume
        self.saved = []

    def act(self, *args, **kwargs):
        return self.client.act(*args, **kwargs)

    def update(self, transitions):
        metrics = self.client.update(transitions)
        if self.interval and metrics.update % self.interval == 0:
            self.save(metrics)
        return metrics

    def save(self, metrics):
        environments = [self.environments[index] for index in range(len(self.environments))]
        if len(environments) != self.expected["configuration"]["environments"] or any(
                environment.episode_length != 0 for environment in environments):
            # Early native terminals can desynchronize the workers. Do not label
            # a mid-game save as recoverable from a reset.
            self.saved.append({"update": metrics.update, "status": "skipped", "reason": "workers not all at reset"})
            return
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / f"update-{metrics.update:06d}"
        temporary = self.root / f".update-{metrics.update:06d}-partial"
        if target.exists():
            raise ValueError("Checkpoint already exists; refusing overwrite")
        temporary.mkdir(exist_ok=False)
        native_request(self.client, 5, temporary / "trainer.pt")
        manifest = {"format": "openttd-rl-live-reset-checkpoint-1", "recovery_boundary": "all-workers-at-native-reset",
                    "update": metrics.update, "samples": metrics.samples, "compatibility": self.expected,
                    "source": self.source, "parent_checkpoint": str(self.resume) if self.resume else None,
                    "trainer_sha256": digest(temporary / "trainer.pt"),
                    "environments": [{"environment_id": e.environment_id, "episode_index": e.episode_index,
                                      "template_id": e.template.stem,
                                      "observation_sha256": state_digest(e.observation),
                                      "mask_sha256": state_digest(e.mask)} for e in environments]}
        with (temporary / "checkpoint.json").open("x") as stream:
            json.dump(manifest, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        for directory in (temporary, self.root):
            descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            if directory == temporary:
                temporary.rename(target)
        self.saved.append({"update": metrics.update, "status": "saved", "path": str(target)})


@contextmanager
def checkpoint_collection(client, root, expected, interval, source, resume=None):
    horizon = expected["configuration"]["episode_action_horizon"]
    rollout = expected["configuration"]["rollout_length"]
    if interval < 0 or (interval and interval % (horizon // rollout)):
        raise ValueError("Checkpoint interval must be a multiple of updates per full training episode")
    manifest = read_checkpoint(resume, expected) if resume else None
    if resume:
        native_request(client, 6, Path(resume) / "trainer.pt")
    original = m07.start_environment
    environments = {}

    def start(executable, templates, artifact_root, contract, environment_id, episode_index, timeout, phase):
        entry = None
        if phase == "train" and environment_id not in environments and manifest:
            entry = manifest["environments"][environment_id]
            episode_index = entry["episode_index"]
        environment = original(executable, templates, artifact_root, contract, environment_id, episode_index, timeout, phase)
        if phase == "train":
            if entry and (entry["template_id"] != environment.template.stem or
                          entry["observation_sha256"] != state_digest(environment.observation) or
                          entry["mask_sha256"] != state_digest(environment.mask)):
                environment.controller.abort()
                raise ValueError("Recreated checkpoint environment differs from saved reset state")
            environments[environment_id] = environment
        return environment

    adapter = CheckpointClient(client, environments, root, expected, interval, source, resume)
    m07.start_environment = start
    try:
        yield adapter
    except BaseException:
        # The frozen collector constructs its initial worker list before its
        # own cleanup block. A reset verification failure must still release
        # any earlier workers that were successfully created.
        for environment in environments.values():
            if environment.controller.worker.process.poll() is None:
                try:
                    environment.controller.abort()
                except Exception:
                    pass  # Preserve the primary restore/collection failure.
        raise
    finally:
        m07.start_environment = original
