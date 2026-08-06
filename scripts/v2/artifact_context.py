#!/usr/bin/env python3
"""Pure offline/live path contexts for V2 verification inputs."""

from __future__ import annotations

import argparse
import dataclasses
import enum
import hashlib
import json
import os
import pathlib
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType
from typing import Any


ARTIFACT_ROOT_ENV = "OPENTTD_RL_ARTIFACT_ROOT"
LIVE_INPUT_MANIFEST = "v2-live-inputs.json"
LIVE_INPUT_SCHEMA_VERSION = "openttd-rl-v2-live-inputs-1"

# Reviewed Task 7 registry snapshots.  The values are populated beside the
# registry implementation so provider source and command closure drift fail
# before any verification command runs.
LIVE_PROVIDER_AST_SHA256: Mapping[str, str] = MappingProxyType({
    "validate_m15_action_evidence": "a8298f04d28509ca04cc2164eb5c738a3cdec8e41bd857137b5446e75b6c74ce",
    "validate_m15_action_source": "45c21f50ad7b5e79663e6b651dde30c01cde7f949e277b72d264ea5d04c5d6ee",
    "validate_m15_competence_evidence": "68a24af0cab13b21e8a9248152aeff2ae58e2bad59ae1c164f03f955016e01d7",
    "validate_m15_competence_source": "03e02a6d4b4847270dee9ad1be42cf168163a01e9784a0e685ba2058dd4a6e42",
    "validate_m15_cross_scale_replay_evidence": "d4898c6180c04ddb7b991d31f00005018531bf7d92d2c282915076b6fd0de544",
    "validate_m15_episode_evidence": "c69d6c6b6538763765f7c35b42800549f4355530ab8bee18cb378ce019c38ec8",
    "validate_m15_episode_source": "ae08275eb1bcbb9e6be40ef01791a1dacef2fdb2f88c5d42d6dfc69450227e23",
    "validate_m15_map_evidence": "49b4b1ed5bd5b84be4e9d39782ed5d3e81be25145028f03ff75c920257a70d80",
    "validate_m15_native_reset_evidence": "92c69ed87c8d8a572b11f3057d55c381ea8a12d0de61852f4d4642c17f5bf900",
    "validate_m15_native_reset_matrix": "745de0db14d78bc89c99971e0ef9e72785d50d1bfb9ce48ba0e1388e6654126a",
    "validate_m15_native_source": "d961c6f6a6e2b0a35437379525eb08a90a97923539612ea9b07294d62c8bc25a",
    "validate_m15_observation_evidence": "eac04b52b3f45599159012f56878faae5a7a756f7719cd61ffa668eac56329c4",
    "validate_m15_observation_source": "4371fcd1fb928ffb38080319d876e67999fbe5ad101a9b5b28fc7c5e1597d1b2",
    "validate_m15_policy_evidence": "1581d709f350e34ee4f9042e15111e1d63479f918792d3e43537fc7c7c28f32b",
    "validate_m16_cargo_evidence": "ba506aec5e165f4f34af124cf95ca56ea01cd070039da8cf1ac0727ba288bac2",
    "validate_m16_cargo_source": "4ce68e52d6faef94c727daf00820f17d8e48d9157947810b50fe90410d97486d",
    "validate_m17_rail_evidence": "57ade1231c26124eee4da161544abe72926a90d1269586c0d40b931f1ab23735",
    "validate_m17_rail_source": "5d4e3e2c64b8c3e431979080bd502c452604f6bcd136aad88faf769c12383ceb",
    "validate_m18_ship_evidence": "89340dfe86fc120a3b603381bf8a2436c61067320ab9fe902287dc0ec4e9f7f6",
    "validate_m18_ship_source": "dd02ff6f8072f0a5eaaf53a3d3f19150763fef05091fd97b8a7b12ef889f6aa3",
    "validate_m18_shipai_evidence": "b9ed51c60b5472b4d6e940d4c89e11457e16d9292750f5e806296ca637c970af",
    "validate_m19_air_evidence": "d6c610531bb76d0281f02156d60d686e9d1c364d3a834aec0db6f5a8b3d1b4c3",
    "validate_m19_air_source": "13290ea4914229164e96011a755b220ded844dab0a10f476e2f7c1248fe46680",
    "validate_m20_competition_evidence": "2575ed7b981aea85400252d0a6860d46a99a81626d5c1aa6a2746771e87363a9",
    "validate_m20_competition_source": "7dc06fb588893612d775515676b6cde0724367172823fe3d39d5be26769fe5e8",
    "validate_m21_broad_evidence": "7449adca3676790c85deeb8962ee10289f34a3b1d8f8bd57a0243a55a24c3ea0",
    "validate_m21_broad_source": "059c0e39a5fc4de27b16b8dd39ca52d798b9032430d7179f6aca5e02cd787dd4",
    "validate_m22_final_evaluation": "b998493839d5536a6cd7cba36aef6ee9f29d6a27c2529720cb3d0442ee0ebaa1",
    "validate_m22_final_runtime_source": "72ce0512e75604e6d3e71de54938f6bb971c2252f52ef01acd11bc026479a085",
    "validate_m22_followup_evaluation": "38aac5c73aa33978a24fb7df0dd049be7ecd6c816e322f3a204554b1cbaf3276",
    "validate_m22_followup_runtime_source": "0e3a6722748c948c3ff8eedc9df8451a79b8c0aec5b54a119c88c1bcb0e649aa",
    "validate_m22_followup_v2_evaluation": "762814bc55ea20bccca8128a288a10e9e14062636f525958fc2abb85e3d58c25",
    "validate_m22_qualification_evidence": "bdc1bc0e861915f093d2d1bca79ceddb96e3d939d234df7a2034d0d9a472b445",
    "validate_m22_recovery_evidence": "94c85eca6665d641830a445b8d11edc8269e82e9422f323a74fd09fd3b819a84",
    "validate_m22_training_evidence": "50d1a80a74e9f793894cb7f43ebe68fcba47b4702178658e1a057c7c3cf980ab",
    "validate_opponent_package_evidence": "b1f1fa08b106058b53bf55ba693877c281ee5754516313e024e5b9c6b6d1e804",
    "validate_opponent_runtime_evidence": "ac153e12608c81129005fe64218c7f34f5bd997762ba4abb869bfae9ca754af3",
    "verify_driver": "ad7b955929ed1a210300bcd5e85ad8929cc292ccdd85adce2312ef4dc3e0d8af",
})
LIVE_COMMAND_REGISTRY_SHA256: Mapping[str, str] = MappingProxyType({
    "opponent-package-evidence": "c59947ab2c41b4de3905a349c695deea8d5daffe55f239bf072fdd893539e5ce",
    "opponent-runtime-evidence": "eb3536dd8c11358443418a3614b62ee0482a7763b22d0b796f1894262c55e0b6",
    "m15-policy-evidence": "ebe09a895dffec0b2431daa4343e5a809a7a30e5aeb58446e53263db45ef9112",
    "m15-map-matrix": "5ba2b12e2465c2fb59b041bf47801c4792f3520e989ff7e88b8e11e11f8baa1e",
    "m15-native-source": "6c03e8b8dbcf16407f36f5e307d91cc392e03ca292f0304faead3a69450de504",
    "m15-native-reset-evidence": "35a1d2221abb85d1cab7740d22cab01a6bbc2e06f8e11b4ce8cd9a62efc23509",
    "m15-native-reset-matrix": "2bb76d4b22e7b3306a5692a77c6262ad8f7d731da855a4dbe43b311107a30d5b",
    "m15-observation-source": "b3eda22a627afc7f60b5938db66617d3edc07f8cdd27a21e00dc28721765d4d9",
    "m15-observation-evidence": "f3973d7949fc961ae80eb952087eca22751857922fca5fc0a6f0df163c6b09b7",
    "m15-action-source": "30c02d216690181521dff83e693a935e308f0022d2c2a7b8e36806798fdfafb2",
    "m15-action-evidence": "5d92c1e58834b7f80bb486f1ea2bc85500134ace04ad65b31715dd587b56f744",
    "m15-episode-source": "29bc6ac4c3edeb6873cca8d235667ece3c891e442cc8e94d602363257a6ff18b",
    "m15-episode-evidence": "bedcb5f9b6142db5e47432f2a45dfd9704e5e80fbd823cdd75d9756a9625c210",
    "m15-cross-scale-replay-evidence": "8757a00128b8261a9a8f699b5c78438ed2504e20272a0fe040468ae310262cc1",
    "m15-competence-source": "1ffe5ddbc135d3a6f19159533c35699c8b3efc50790cba118417d8f373552a36",
    "m15-competence-evidence": "b15fce9e9931f7610f57f46a935143d527b623f77f7702e31fbe3ce36f1010d5",
    "m16-cargo-source": "88ae9fd15094bc38c941ecd7536224b44a055f68df509072ce8c03008f6517ae",
    "m16-cargo-evidence": "11906330e4f5406134b58cf33df5dfaeb0c1164f4a94b73c497a1260256ebc28",
    "m17-rail-source": "2ed28809734337f4a9d04e7623e109de6c2a994081a0b3175131fbb248bdace8",
    "m17-rail-evidence": "9404810313a26b4e79c9c43e6fbcc95bad5a9c44610e26f8dd61607d39a729d3",
    "m18-ship-source": "3c8447e28fec1316f2f38c3183858fc842fa0789885029bb882491658267d173",
    "m18-shipai-evidence": "e695ec4c9fe6b7743969c4caa38d8b6c66d6a72c2bae4cf5b08831844693a7e0",
    "m18-ship-evidence": "9e55b21645b2c91f8cbaae3c7efb3d37da9ff53a4ff57c9588cc26734d349bb4",
    "m19-air-source": "0b0ed0f173dcc555283dd91a2bf1d87b8666e4f83a5c64ca82f5b91a2dc1bce6",
    "m19-air-evidence": "6da34b8c12f6984d2affd74d50e41fd9383f79667aae8fe3905d0fabf84e6670",
    "m20-competition-source": "155d3169e199dee030f1fa9b7f48ce834044ec40367c6fad6327264409dab611",
    "m20-competition-evidence": "1f75ec5fc38b40ccbb874a784b3a749c729a9b118039a53803e643846a6889af",
    "m21-broad-source": "7e3ecd858b494b01907555eb4ca2bdd65c0e0f431889bd14240451bb12b875bf",
    "m21-broad-evidence": "bd05336af973236fbe682c8afef10b4f7b0f13b72d268f76b81d8f58bce311d4",
    "m22-recovery-v1-evidence": "07dca54af64ceb3a41b976ca5aea69766c3679d1bf524d285fb41ef26ea76a06",
    "m22-recovery-v2-evidence": "e6896a57a9b7418c56f56e752337a6afcdfdd326effe9da34bb9d82be2aca163",
    "m22-training-evidence": "09fc96d31d8cda98644d373f3d5300ca70b1d373e0d104892f05406e4b71ac8d",
    "m22-qualification-evidence": "703512ec600320572a25ff5c748e16dd6c58bc91f28e82aa9d866f910b618d4b",
    "m22-final-runtime-source": "c17e4fc54179af24aa16247ab87eda0cb69de27376baccb18740c2948372b15b",
    "m22-followup-runtime-source": "e8824dce0a29ce0c59593a2de5ca6ff905ad3371ae343ba4533aafc4391fa9f0",
    "m22-final-v1-evaluation": "8ee54401a239246f7b9c6f4996910b7ece07ef1899c672f52c0bc23811f50287",
    "m22-followup-v1-evaluation": "e91b39b76353e655c32182311f0d11f87684f4804ea97dbb59e00c0e3a0ecece",
    "m22-followup-v2-evaluation": "7fa1d559d196e3a2f7916e416a7e403b273636c19fd28b44c69c9994867c64cc",
    "v2-unit-tests": "e6bc213001556f3c15e1f8fe906d3182646a01e69bec880a3272846e4093b5a9",
})


class ArtifactContextError(ValueError):
    """A live artifact input is absent, unsafe, or inconsistent."""


class ValidationMode(enum.StrEnum):
    OFFLINE = "offline"
    LIVE = "live"


_KINDS = frozenset({"file", "directory"})
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _raise_issues(issues: Iterable[str]) -> None:
    failures = sorted(set(issues))
    if failures:
        raise ArtifactContextError("\n".join(failures))


def _validate_component(value: str, *, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        raise ArtifactContextError(f"{label} must be one nonempty POSIX path component: {value!r}")


def _relative_parts(
    value: str,
    *,
    label: str,
    allow_root_selector: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ArtifactContextError(f"{label} must be a safe nonempty relative POSIX path: {value!r}")
    if value == ".":
        if allow_root_selector:
            return ()
        raise ArtifactContextError(
            f"{label} must be a safe nonempty relative POSIX path: {value!r}"
        )
    parts = value.split("/")
    if value.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise ArtifactContextError(f"{label} must be a safe nonempty relative POSIX path: {value!r}")
    return tuple(parts)


def _absolute_parts(value: str, *, label: str) -> tuple[str, ...]:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or "\x00" in value
    ):
        raise ArtifactContextError(f"{label} must be an unambiguous absolute POSIX path: {value!r}")
    parts = value[1:].split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ArtifactContextError(f"{label} must be an unambiguous absolute POSIX path: {value!r}")
    return tuple(parts)


def _validate_kind_and_digest(kind: str, expected_sha256: str | None) -> None:
    if kind not in _KINDS:
        raise ArtifactContextError(f"requirement kind must be file or directory: {kind!r}")
    if expected_sha256 is not None:
        if kind != "file":
            raise ArtifactContextError("only file requirements may declare a SHA-256 digest")
        if _SHA256.fullmatch(expected_sha256) is None:
            raise ArtifactContextError("expected SHA-256 must be 64 lowercase hexadecimal characters")


@dataclasses.dataclass(frozen=True, slots=True)
class ArtifactRequirement:
    logical_set: str
    relative_path: str
    kind: str
    consumer: str
    expected_sha256: str | None = None

    def __post_init__(self) -> None:
        _validate_component(self.logical_set, label="logical artifact set")
        _relative_parts(
            self.relative_path,
            label="artifact relative path",
            allow_root_selector=True,
        )
        _validate_kind_and_digest(self.kind, self.expected_sha256)


@dataclasses.dataclass(frozen=True, slots=True)
class DeferredArtifactRequirement:
    """A statically named file whose digest comes from authenticated evidence."""

    logical_set: str
    relative_path: str
    kind: str
    consumer: str
    authority: ArtifactRequirement

    def __post_init__(self) -> None:
        _validate_component(self.logical_set, label="logical artifact set")
        _relative_parts(
            self.relative_path,
            label="artifact relative path",
            allow_root_selector=True,
        )
        _validate_kind_and_digest(self.kind, None)
        if not isinstance(self.authority, ArtifactRequirement):
            raise ArtifactContextError(
                "deferred artifact authority must be an ArtifactRequirement"
            )
        if (
            self.authority.kind != "file"
            or self.authority.expected_sha256 is None
        ):
            raise ArtifactContextError(
                "deferred artifact authority must be a digest-bound file"
            )


@dataclasses.dataclass(frozen=True, slots=True)
class RoleRequirement:
    role: str
    relative_path: str
    kind: str
    consumer: str
    expected_sha256: str | None = None

    def __post_init__(self) -> None:
        _validate_component(self.role, label="live-input role")
        _relative_parts(
            self.relative_path,
            label="role relative path",
            allow_root_selector=True,
        )
        _validate_kind_and_digest(self.kind, self.expected_sha256)


@dataclasses.dataclass(frozen=True, slots=True)
class ToolRequirement:
    name: str
    path: pathlib.Path
    expected_sha256: str | None = None

    def __post_init__(self) -> None:
        _validate_component(self.name, label="tool name")
        object.__setattr__(self, "path", pathlib.Path(self.path))
        if self.expected_sha256 is not None and _SHA256.fullmatch(self.expected_sha256) is None:
            raise ArtifactContextError("expected SHA-256 must be 64 lowercase hexadecimal characters")


def _first_symlink(path: pathlib.Path) -> pathlib.Path | None:
    candidates = (path, *path.parents)
    for candidate in reversed(candidates):
        if candidate.is_symlink():
            return candidate
    return None


def _sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_issues(
    path: pathlib.Path,
    *,
    kind: str,
    label: str,
    expected_sha256: str | None = None,
) -> list[str]:
    issues: list[str] = []
    symlink = _first_symlink(path)
    if symlink is not None:
        return [f"{label}: symlink traversal is forbidden: {symlink}"]
    if not path.exists():
        return [f"{label}: missing {kind}: {path}"]
    if kind == "file" and not path.is_file():
        issues.append(f"{label}: expected regular file: {path}")
    elif kind == "directory" and not path.is_dir():
        issues.append(f"{label}: expected directory: {path}")
    if expected_sha256 is not None and path.is_file():
        try:
            actual = _sha256_file(path)
        except OSError as exc:
            issues.append(f"{label}: cannot hash {path}: {exc}")
        else:
            if actual != expected_sha256:
                issues.append(
                    f"{label}: SHA-256 mismatch for {path}: expected {expected_sha256}, got {actual}"
                )
    return issues


def resolve_artifact_root(
    explicit_root: pathlib.Path | str | None,
    environ: Mapping[str, str] = os.environ,
) -> pathlib.Path | None:
    """Resolve CLI, then environment configuration without filesystem inference."""

    configured: pathlib.Path | str | None = explicit_root
    if configured is None:
        configured = environ.get(ARTIFACT_ROOT_ENV) or None
    if configured is None:
        return None
    root = pathlib.Path(configured)
    if not root.is_absolute():
        raise ArtifactContextError("artifact root must be an absolute path")
    return root


def add_artifact_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--artifact-root", type=pathlib.Path)


@dataclasses.dataclass(frozen=True, slots=True)
class ArtifactContext:
    mode: ValidationMode
    artifact_root: pathlib.Path | None

    @classmethod
    def offline(cls) -> ArtifactContext:
        return cls(ValidationMode.OFFLINE, None)

    @classmethod
    def live(cls, artifact_root: pathlib.Path | str) -> ArtifactContext:
        root = pathlib.Path(artifact_root)
        if not root.is_absolute():
            raise ArtifactContextError("artifact root must be an absolute path")
        return cls(ValidationMode.LIVE, root)

    @property
    def is_live(self) -> bool:
        return self.mode is ValidationMode.LIVE

    def _live_root(self) -> pathlib.Path:
        if not self.is_live or self.artifact_root is None:
            raise ArtifactContextError("offline validation attempted live artifact access")
        return self.artifact_root

    def artifact_set(self, logical_name: str) -> pathlib.Path:
        root = self._live_root()
        _validate_component(logical_name, label="logical artifact set")
        return root / logical_name

    def relocate(
        self,
        recorded_path: pathlib.Path | str,
        *,
        recorded_root: pathlib.Path | str,
    ) -> pathlib.Path:
        self._live_root()
        path = pathlib.PurePosixPath(str(recorded_path))
        root = pathlib.PurePosixPath(str(recorded_root))
        if not path.is_absolute() or not root.is_absolute() or root.name in {"", ".", ".."}:
            raise ArtifactContextError("recorded path and root must be absolute POSIX paths")
        try:
            relative = path.relative_to(root)
        except ValueError as exc:
            raise ArtifactContextError("recorded path is outside recorded root") from exc
        if any(part == ".." for part in relative.parts):
            raise ArtifactContextError("recorded path is outside recorded root")
        destination = self.artifact_set(root.name)
        if relative != pathlib.PurePosixPath("."):
            destination = destination.joinpath(*relative.parts)
        return destination

    def resolve(self, requirement: ArtifactRequirement) -> pathlib.Path:
        if not isinstance(requirement, ArtifactRequirement):
            raise TypeError("artifact resolution requires an ArtifactRequirement")
        relative = _relative_parts(
            requirement.relative_path,
            label="artifact relative path",
            allow_root_selector=True,
        )
        return self.artifact_set(requirement.logical_set).joinpath(*relative)

    def preflight(self, requirements: Sequence[ArtifactRequirement]) -> None:
        root = self._live_root()
        issues = _path_issues(root, kind="directory", label="artifact root")
        for requirement in requirements:
            if not isinstance(requirement, ArtifactRequirement):
                raise TypeError("artifact preflight requires ArtifactRequirement values")
            artifact_set = self.artifact_set(requirement.logical_set)
            issues.extend(_path_issues(
                artifact_set,
                kind="directory",
                label=f"artifact set {requirement.logical_set}",
            ))
            if artifact_set.exists() and _first_symlink(artifact_set) is None:
                issues.extend(_path_issues(
                    self.resolve(requirement),
                    kind=requirement.kind,
                    label=(
                        f"artifact requirement {requirement.logical_set}/"
                        f"{requirement.relative_path} for {requirement.consumer}"
                    ),
                    expected_sha256=requirement.expected_sha256,
                ))
        _raise_issues(issues)


@dataclasses.dataclass(frozen=True, slots=True)
class _RoleSpec:
    kind: str
    expected_sha256: str | None = None


LIVE_INPUT_ROLE_SPECS: Mapping[str, _RoleSpec] = MappingProxyType({
    "recovery-v1-artifacts": _RoleSpec("directory"),
    "recovery-v1-executable": _RoleSpec(
        "file", "2f26dc241b029abeb4641f1497e9347a6675a3d607b564855518fb91b391356f",
    ),
    "recovery-v1-corpus": _RoleSpec(
        "file", "0d5aa3944241b3c00e0b1283de586e00c8fb0a5a51abe385c7e3288785369a0d",
    ),
    "recovery-v2-artifacts": _RoleSpec("directory"),
    "training-artifacts": _RoleSpec("directory"),
    "qualification-artifacts": _RoleSpec("directory"),
    "v2-campaign-executable": _RoleSpec(
        "file", "62ed497cf6f237248a54861269e5b0ad27c8808f8e3d4d7b73d29148e84a5fc2",
    ),
    "v2-corpus-binary": _RoleSpec(
        "file", "d6cdf022e4382a90da4b89a225eb3e1cf15833a63d9c450712aa4c9dbfbc4021",
    ),
    "qualification-executable": _RoleSpec(
        "file", "ae5a74d890e980a6c1308cdad31154e902d0c5e40f234f98b7d34e61849f4b52",
    ),
    "final-v1-evaluator": _RoleSpec(
        "file", "bc87f4608643b4664068381fa5136d464c44bd05dad09a66fa088bfa995b92e6",
    ),
    "m14-openttd-executable": _RoleSpec(
        "file", "8b27f06113d08fa3a21f81c01721873194f35bf885963be2697cc9da52e1ef9a",
    ),
})


class _ObjectPairs(list[tuple[str, Any]]):
    pass


def _load_pairs(path: pathlib.Path) -> _ObjectPairs:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_ObjectPairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactContextError(f"cannot load live-input manifest {path}: {exc}") from exc
    if not isinstance(value, _ObjectPairs):
        raise ArtifactContextError(f"live-input manifest root is not an object: {path}")
    return value


def _duplicate_issues(pairs: _ObjectPairs, *, label: str) -> list[str]:
    return [
        f"{label}: duplicate JSON key {key!r}"
        for key, count in sorted(Counter(key for key, _ in pairs).items())
        if count > 1
    ]


def _manifest_role_path(root: pathlib.Path, value: str) -> pathlib.Path:
    if value.startswith("/"):
        candidate = pathlib.Path("/").joinpath(*_absolute_parts(value, label="live-input path"))
        try:
            relative = candidate.relative_to(root)
        except ValueError as exc:
            raise ArtifactContextError(
                f"live-input path is outside artifact root: {value}"
            ) from exc
        if relative == pathlib.Path("."):
            raise ArtifactContextError(f"live-input path must be below artifact root: {value}")
        return candidate
    parts = _relative_parts(value, label="live-input path")
    return root.joinpath(*parts)


def _bound_role_path(
    root: pathlib.Path,
    value: pathlib.Path | str,
) -> pathlib.Path:
    if not isinstance(value, (pathlib.Path, str)):
        raise ArtifactContextError(f"live-input binding must be a path: {value!r}")
    raw = str(value)
    candidate = pathlib.Path("/").joinpath(
        *_absolute_parts(raw, label="live-input binding")
    )
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ArtifactContextError(
            f"live-input binding is outside artifact root: {raw}"
        ) from exc
    if relative == pathlib.Path("."):
        raise ArtifactContextError(
            f"live-input binding must be below artifact root: {raw}"
        )
    return candidate


@dataclasses.dataclass(frozen=True, slots=True)
class LiveInputManifest:
    mode: ValidationMode
    artifact_root: pathlib.Path | None
    _roles: Mapping[str, pathlib.Path]

    @classmethod
    def offline(cls) -> LiveInputManifest:
        return cls(ValidationMode.OFFLINE, None, MappingProxyType({}))

    @classmethod
    def bind(
        cls,
        context: ArtifactContext,
        bindings: Mapping[str, pathlib.Path | str],
    ) -> LiveInputManifest:
        """Bind a validated subset of known live roles through one context."""

        if not isinstance(context, ArtifactContext):
            raise TypeError("live-input binding requires an ArtifactContext")
        root = context._live_root()
        if root != pathlib.Path("/"):
            _absolute_parts(str(root), label="artifact root")
        _raise_issues(_path_issues(root, kind="directory", label="artifact root"))
        if not isinstance(bindings, Mapping):
            raise TypeError("live-input bindings must be a mapping")

        issues: list[str] = []
        roles: dict[str, pathlib.Path] = {}
        for role, value in bindings.items():
            if role not in LIVE_INPUT_ROLE_SPECS:
                issues.append(f"live-input bindings: unknown role {role!r}")
                continue
            try:
                roles[role] = _bound_role_path(root, value)
            except ArtifactContextError as exc:
                issues.append(f"live-input role {role}: {exc}")

        aliases: dict[pathlib.Path, list[str]] = {}
        for role, path in roles.items():
            spec = LIVE_INPUT_ROLE_SPECS[role]
            if spec.expected_sha256 is not None:
                aliases.setdefault(path, []).append(role)
            issues.extend(_path_issues(
                path,
                kind=spec.kind,
                label=f"live-input role {role}",
                expected_sha256=spec.expected_sha256,
            ))
        for path, names in aliases.items():
            digests = {LIVE_INPUT_ROLE_SPECS[name].expected_sha256 for name in names}
            if len(names) > 1 and len(digests) > 1:
                issues.append(
                    f"incompatible live-input roles alias {path}: "
                    f"{', '.join(sorted(names))}"
                )
        _raise_issues(issues)
        return cls(ValidationMode.LIVE, root, MappingProxyType(dict(roles)))

    @classmethod
    def load(cls, artifact_root: pathlib.Path | str) -> LiveInputManifest:
        root = pathlib.Path(artifact_root)
        if not root.is_absolute():
            raise ArtifactContextError("artifact root must be an absolute path")
        root_issues = _path_issues(root, kind="directory", label="artifact root")
        _raise_issues(root_issues)
        manifest_path = root / LIVE_INPUT_MANIFEST
        manifest_issues = _path_issues(manifest_path, kind="file", label="live-input manifest")
        _raise_issues(manifest_issues)

        top_pairs = _load_pairs(manifest_path)
        issues = _duplicate_issues(top_pairs, label="live-input manifest")
        top_keys = [key for key, _ in top_pairs]
        for key in sorted(set(top_keys) - {"schema_version", "roles"}):
            issues.append(f"live-input manifest: unknown top-level key {key!r}")
        for key in sorted({"schema_version", "roles"} - set(top_keys)):
            issues.append(f"live-input manifest: missing top-level key {key!r}")
        top = dict(top_pairs)
        if top.get("schema_version") != LIVE_INPUT_SCHEMA_VERSION:
            issues.append(
                "live-input manifest: schema_version must be "
                f"{LIVE_INPUT_SCHEMA_VERSION!r}"
            )

        role_pairs = top.get("roles")
        if not isinstance(role_pairs, _ObjectPairs):
            issues.append("live-input manifest: roles is not an object")
            role_pairs = _ObjectPairs()
        issues.extend(_duplicate_issues(role_pairs, label="live-input roles"))
        role_names = [key for key, _ in role_pairs]
        configured = set(role_names)
        expected = set(LIVE_INPUT_ROLE_SPECS)
        for role in sorted(configured - expected):
            issues.append(f"live-input roles: unknown role {role!r}")
        for role in sorted(expected - configured):
            issues.append(f"live-input roles: missing role {role!r}")

        roles: dict[str, pathlib.Path] = {}
        for role, value in role_pairs:
            if role not in LIVE_INPUT_ROLE_SPECS or role in roles:
                continue
            if not isinstance(value, str):
                issues.append(f"live-input role {role}: path must be a string")
                continue
            try:
                roles[role] = _manifest_role_path(root, value)
            except ArtifactContextError as exc:
                issues.append(f"live-input role {role}: {exc}")

        aliases: dict[pathlib.Path, list[str]] = {}
        for role, path in roles.items():
            spec = LIVE_INPUT_ROLE_SPECS[role]
            if spec.expected_sha256 is not None:
                aliases.setdefault(path, []).append(role)
        for path, names in aliases.items():
            digests = {LIVE_INPUT_ROLE_SPECS[name].expected_sha256 for name in names}
            if len(names) > 1 and len(digests) > 1:
                issues.append(
                    f"incompatible live-input roles alias {path}: {', '.join(sorted(names))}"
                )

        for role, path in roles.items():
            spec = LIVE_INPUT_ROLE_SPECS[role]
            issues.extend(_path_issues(
                path,
                kind=spec.kind,
                label=f"live-input role {role}",
                expected_sha256=spec.expected_sha256,
            ))
        _raise_issues(issues)
        return cls(ValidationMode.LIVE, root, MappingProxyType(dict(roles)))

    @property
    def is_live(self) -> bool:
        return self.mode is ValidationMode.LIVE

    @property
    def roles(self) -> frozenset[str]:
        self._require_live()
        return frozenset(self._roles)

    def _require_live(self) -> None:
        if not self.is_live or self.artifact_root is None:
            raise ArtifactContextError("offline validation attempted live artifact access")

    def resolve(self, requirement: RoleRequirement) -> pathlib.Path:
        self._require_live()
        if not isinstance(requirement, RoleRequirement):
            raise TypeError("role resolution requires a RoleRequirement")
        try:
            base = self._roles[requirement.role]
        except KeyError as exc:
            raise ArtifactContextError(f"live-input role is not declared: {requirement.role}") from exc
        relative = _relative_parts(
            requirement.relative_path,
            label="role relative path",
            allow_root_selector=True,
        )
        return base.joinpath(*relative)

    def role_path(self, role: str) -> pathlib.Path:
        """Return one already-bound role root without inventing a nested read."""

        self._require_live()
        _validate_component(role, label="live-input role")
        try:
            return self._roles[role]
        except KeyError as exc:
            raise ArtifactContextError(f"live-input role is not declared: {role}") from exc

    def preflight(self, requirements: Sequence[RoleRequirement]) -> None:
        self._require_live()
        issues: list[str] = []
        for requirement in requirements:
            if not isinstance(requirement, RoleRequirement):
                raise TypeError("role preflight requires RoleRequirement values")
            if requirement.role not in self._roles:
                issues.append(f"live-input role is not declared: {requirement.role}")
                continue
            issues.extend(_path_issues(
                self.resolve(requirement),
                kind=requirement.kind,
                label=(
                    f"role requirement {requirement.role}/"
                    f"{requirement.relative_path} for {requirement.consumer}"
                ),
                expected_sha256=requirement.expected_sha256,
            ))
        _raise_issues(issues)


def preflight_tools(requirements: Sequence[ToolRequirement]) -> None:
    issues: list[str] = []
    for requirement in requirements:
        if not isinstance(requirement, ToolRequirement):
            raise TypeError("tool preflight requires ToolRequirement values")
        path = requirement.path
        label = f"tool {requirement.name}"
        if not path.is_absolute():
            issues.append(f"{label}: path must be absolute: {path}")
            continue
        issues.extend(_path_issues(
            path,
            kind="file",
            label=label,
            expected_sha256=requirement.expected_sha256,
        ))
        if path.is_file() and _first_symlink(path) is None and not os.access(path, os.X_OK):
            issues.append(f"{label}: path is not executable: {path}")
    _raise_issues(issues)
