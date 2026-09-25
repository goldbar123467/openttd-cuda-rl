"""Development-only queries; frozen ACT/UPDATE response layouts stay unchanged."""
import math
import struct

from m08_trainer_client import M08TrainerClientError


def backend_info(client, build, device):
    try:
        payload = client._request(7, b"")
    except M08TrainerClientError as exc:
        if str(exc) != "unknown M08 trainer request type":
            raise
        # Compatibility with previously built development binaries. A missing or
        # ambiguous configure flag is unknown, never guessed from the filename.
        flags = [arg for arg in build.get("configure", []) if arg.startswith("-DRL_DEV_FUSED_POLICY=")]
        if flags not in (["-DRL_DEV_FUSED_POLICY=ON"], ["-DRL_DEV_FUSED_POLICY=OFF"]):
            raise ValueError("Old trainer needs an explicit ACT backend in its build record") from exc
        return {"act_distribution": "fused-cuda" if device == "cuda:0" and flags[0].endswith("=ON") else "reference",
                "provenance": "trainer_build.configure", "behavior_replay_query": False}
    if len(payload) < 8:
        raise ValueError("Truncated native development INFO")
    version, size = struct.unpack_from("<II", payload)
    if version != 1 or len(payload) != 8 + size:
        raise ValueError("Unsupported native development INFO")
    backend = payload[8:].decode("ascii")
    if backend not in ("reference", "fused-cuda") or (backend == "fused-cuda" and device != "cuda:0"):
        raise ValueError("Native ACT backend disagrees with requested runtime")
    return {"act_distribution": backend, "provenance": "native-info-v1", "behavior_replay_query": True}


class AuditedClient:
    def __init__(self, client, records):
        self.client, self.records = client, records

    def __getattr__(self, name):
        return getattr(self.client, name)

    def update(self, transitions):
        result = self.client.update(transitions)
        payload = self.client._request(8, b"")
        if len(payload) != struct.calcsize("<Idq"):
            raise ValueError("Invalid native behavior replay response length")
        version, error, samples = struct.unpack("<Idq", payload)
        if version != 1 or not math.isfinite(error) or not 0 <= error <= 1e-4 or samples != len(transitions):
            raise ValueError("Native behavior replay failed its reported bound or coverage")
        self.records.append({"update": result.update, "samples": samples, "max_abs_log_probability_error": error})
        return result
