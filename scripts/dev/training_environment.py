"""Development-only episode diagnostics and native time-limit curriculum.

The frozen collector has no factory hook. This scoped controller adapter lets it
keep owning collection, masks, behavior probabilities, and GAE boundary flags.
Use one training run per process; the original controller is always restored.
"""
from contextlib import contextmanager
import json
from pathlib import Path

from local import write_json
import run_m06_reward_trajectory as bridge
from run_m09_evaluation import M09_COMPATIBILITY_SHA256
from training_reward import service_potential


@contextmanager
def training_episodes(record_root: Path, horizon: int, reward_adapter=None):
    if horizon not in (128, 256, 512):
        raise ValueError("Development training horizon must be 128, 256 or 512")
    record_root.mkdir(parents=True, exist_ok=False)
    original = bridge.Controller
    observer = getattr(reward_adapter, "observe_transition", None)

    class RecordingController(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._potential = 0.0  # All supported M02 resets start without infrastructure/buses.
            self._record = {"status": "running", "run_id": self.run_id,
                            "template_id": self.instance_value["template_id"], "action_horizon": horizon,
                            "actions": 0, "return": 0., "passengers": 0, "operating_profit": 0,
                            "capital_spend": 0, "native_rejections": 0, "idle_bus_ticks": 0,
                            "vehicle_losses": 0, "bankruptcy": False, "termination": None}
            self._trace = (record_root / f"{self.run_id}.jsonl").open("x")
            self._summary = record_root / f"{self.run_id}.json"
            write_json(self._summary, self._record)

        def reset(self, *, observe=False):
            if self.instance_value["split"] != "training":
                raise ValueError("Training curriculum may only reset a training scenario")
            if horizon == 512:
                return super().reset(observe=observe)
            # Reuse the already implemented bounded native reset variation. It
            # changes actual engine limits, not synthetic termination labels.
            return super().reset_evaluation(evaluation_contract_sha256=M09_COMPATIBILITY_SHA256,
                                            starting_balance=100_000, action_horizon=horizon, observe=observe)

        def step(self, action_index, **kwargs):
            mask = self.last_mask
            result = super().step(action_index, **kwargs)
            if "reward" not in result:
                raise RuntimeError("Training controller received an unaccepted action")
            raw = result["reward"]["raw"]
            row = {"step": self.transition, "action": action_index, "mask": mask,
                   "reward": result["reward"], "outcome": result["action_outcome"],
                   "snapshot": result["snapshot"], "termination": result["termination"]}
            if observer is not None:
                after = service_potential(result["snapshot"], result["reward"]["source"]["post"],
                                          terminal=result["termination"]["terminal"])
                row["training_adjustment"] = observer(action_index, result["reward"]["scalar"], self._potential, after,
                                                      reward_details=result["reward"])
                self._potential = after
            self._trace.write(json.dumps(row, allow_nan=False) + "\n")
            self._trace.flush()
            record = self._record
            record["actions"] += 1
            record["return"] += result["reward"]["scalar"]
            for name, source in (("passengers", "delivered_passengers_delta"),
                                 ("operating_profit", "operating_profit_delta"),
                                 ("capital_spend", "capital_spend"), ("native_rejections", "native_rejected"),
                                 ("idle_bus_ticks", "idle_bus_ticks"), ("vehicle_losses", "vehicle_loss_count")):
                record[name] += raw[source]
            record["bankruptcy"] = bool(raw["bankruptcy"])
            record["termination"] = result["termination"]
            record["final_company"] = result["snapshot"]["company"]
            record["final_service"] = result["reward"]["source"]["post"]
            if result["termination"]["reason"] != "NONE":
                record["status"] = "completed" if result["termination"]["trainable"] else "failed"
            write_json(self._summary, record)
            return result

        def close(self, timeout):
            try:
                result = super().close(timeout)
                if self._record["status"] == "running":
                    self._record["status"] = "partial"
                return result
            except BaseException as exc:
                self._record.update(status="failed", error=str(exc))
                raise
            finally:
                self._trace.close()
                write_json(self._summary, self._record)

        def abort(self):
            try:
                return super().abort()
            finally:
                self._trace.close()
                self._record["status"] = "aborted"
                write_json(self._summary, self._record)

    bridge.Controller = RecordingController
    try:
        yield
    finally:
        bridge.Controller = original
