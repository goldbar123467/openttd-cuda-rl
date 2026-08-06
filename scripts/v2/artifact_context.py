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
    "verify_driver": "8277d33d215b6ef1af339d7535c39095a9fd61d6f2feae505f4ff3a494bc8bf6",
})
LIVE_COMMAND_REGISTRY_SHA256: Mapping[str, str] = MappingProxyType({
    "opponent-package-evidence": "adf4a34ebaec4d05d95dcaf27aea2ff64b532cc52efebcdc3983dd7113e7cf50",
    "opponent-runtime-evidence": "0fc172ecfe8f8f76e66124b98de51cebcef43b158c53cccd31d81dc97e070aec",
    "m15-policy-evidence": "0892ebb2b2f2cb590777cb40cca64f2dfc043993d25bb22f48a4d2904d082f93",
    "m15-map-matrix": "83e020c5935c700555effc6fbe22a8e0f8397cb510430852282d3b4a484fd666",
    "m15-native-source": "a3d492105868a9624b74a30acc4c88e89437d654cef2394fc6086f3e33732871",
    "m15-native-reset-evidence": "8e12c6ba4d6a717658cbc9a73fadf5d7937602b0f2569f9f030e428aef9d4434",
    "m15-native-reset-matrix": "618f2230dcbed483ed3ffd3cc4a5cdb2aac5c6ce6a9c5b0c178b80974c1ecc05",
    "m15-observation-source": "ab508925ead864f07c50b75713f2afce4aad73d0b26711526aac5741670a4be8",
    "m15-observation-evidence": "825d4b63396b6848dc3b1b12948d36a6e232f7704503c9278c4d5d2b932cb3d0",
    "m15-action-source": "c42d8e0ce68dee38f74f6510ed2fa94feb52989b23b328839c1b7cedfabb56f1",
    "m15-action-evidence": "721c695f3f5035a81c0bc6e7a90799c11ce2638ff69a218c47e156db4d2f6107",
    "m15-episode-source": "db38366e03ff03f2687474467794b34a5da2864b5ea8dd2525f1b36ac1088753",
    "m15-episode-evidence": "6bba1d323f06cf0ee6b8a6a338e2f884f7a256897671eab33da781e652707ff0",
    "m15-cross-scale-replay-evidence": "e7ee1de939c16dc3a0ad00e7714280028b29c4cb9d8041fb978c5d932377198a",
    "m15-competence-source": "8363b95b9c21ac26ad1d77de0d255122ba12e3d9ff699350e44e9a213b5d7383",
    "m15-competence-evidence": "3e3b8205eadfe46c88d0693aa5c0b5bf23a6c37181ebae1e09d1b5045079b399",
    "m16-cargo-source": "bf903543c7df60576581b9008029f94a8b738b01bc56af05aa92dda10727f69b",
    "m16-cargo-evidence": "510519f0ab77a5d234c94a995c0851e96b45a5d5ad245a4dc9dc5150aa146df7",
    "m17-rail-source": "c9db439dffc1745647a62e6ff3c47a5438d24f354f2071bba061d2def2a421fa",
    "m17-rail-evidence": "9b330cfbd70bdb7b5019923b812000045fc558452f19b375fbbd1d4d993a65e0",
    "m18-ship-source": "656576ac8f00d65d291d8f4ca3ddfddf570fc098b10ae961a705c8dd24147ecc",
    "m18-shipai-evidence": "b4ac4cfac5f5400bb070c3afc57494a5089d4d26560a9198ee93983090504529",
    "m18-ship-evidence": "5b8015a4982aacd2e24e466aa5283c530202b1457f99d9e35b386c5d3a512be9",
    "m19-air-source": "6341a81dab40f3f69d5b5564393e359a1260092e0a039eeb2c42ca9737cd3b21",
    "m19-air-evidence": "46655168223b95c07364a2d5cccfc780d371cfe755740b902af3c58d49c8bf04",
    "m20-competition-source": "eb0333147db592cec6db2c2c8109ef406c44cea45fcecd593f75fb1993665cd5",
    "m20-competition-evidence": "2dea7f121375e90f92808a6cb22fd5d3ec48e9e8c427978c815cebe9906cb1e8",
    "m21-broad-source": "3204c4eb110ece1713070277e864dbdd7ac35e15e0e83824a0aace7f0bdbc23e",
    "m21-broad-evidence": "4b83351a9e3cd9b0d0ba0632598a42821973632ee5f07a3771cf4bc8bccf0b14",
    "m22-recovery-v1-evidence": "79eec7199500de3fc8cf0dea7eb3b144ee854769a0efe31e0cee3b5e25cb3013",
    "m22-recovery-v2-evidence": "3e97bb5ec9a4e9bb1605c2f8bd87bc3d1a1c36c9a857384dc8836f2a17e73f34",
    "m22-training-evidence": "37c4451010e05013f824d1935ecaebb2357f6ac9b87941a4e9d7bf29f01d3b58",
    "m22-qualification-evidence": "f17086c73a03b933ccc481d9ab789e403260a38a6f6bdd160b2a462055d3e64e",
    "m22-final-runtime-source": "cc1af719fe6d3a18bab6a8b170aa9caf39e420dbfe4458ff2fa096314fc66c11",
    "m22-followup-runtime-source": "999a9a4b861b7fd6ea3a37f61003cc3114f20a45df5857c3e855ea95aa49bdf9",
    "m22-final-v1-evaluation": "0e17ab2f4fb8ad596649d351b40acfd6860954ff0b2e0ce878303132eef9e28b",
    "m22-followup-v1-evaluation": "6c7e03742152a9cb0eb551578b6e9c4a189017cdc7ab57491c7af8d0fa6cb158",
    "m22-followup-v2-evaluation": "e6f00c27038a29f3fce80a4f792e942941c1b29364d0578a10572243136e2e8e",
    "v2-unit-tests": "3e39e7e256eeaa1aeae53470577428f11cebde678b4547a21fb871295d1fbdd3",
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
