"""Optional scalar audit of the exact transitions submitted to native GAE/PPO."""
import json


class CreditTrace:
    def __init__(self, client, path, rollout_length, environments):
        self.client = client
        self.path = path
        self.rollout_length = rollout_length
        self.environments = environments
        # Reserve the name before any collection; each accepted update appends.
        with path.open("x"):
            pass

    def act(self, *args, **kwargs):
        return self.client.act(*args, **kwargs)

    def update(self, transitions):
        if len(transitions) != self.rollout_length * self.environments:
            raise ValueError("Credit trace requires the registered time/environment layout")
        rows = [{key: getattr(t, key) for key in (
            "action", "old_log_probability", "old_value", "reward", "next_value", "bootstrap", "continuation")}
            for t in transitions]
        metrics = self.client.update(transitions)
        with self.path.open("a") as output:
            output.write(json.dumps({"update": metrics.update, "samples": metrics.samples,
                "rollout_length": self.rollout_length, "environments": self.environments,
                "layout": "time-major-environment-minor", "transitions": rows}, allow_nan=False) + "\n")
        return metrics
