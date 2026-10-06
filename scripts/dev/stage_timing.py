"""Opt-in stage wall times, separate from canonical gameplay/training evidence."""
from contextlib import contextmanager
import json
from pathlib import Path
import time


class StageTimings:
    """One process owns one file; disabled spans never read a clock or write data.

    Durations include synchronous work inside a span, not its logging overhead.
    They are host wall time, not CUDA-event/kernel time. Use disjoint spans when
    summing stages; an outer span includes any nested spans and must not be added.
    """
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self.stream = None
        self.sequence = 0

    def __enter__(self):
        if self.path is not None:
            self.stream = self.path.open("x", encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        return False

    @contextmanager
    def measure(self, stage, **context):
        if self.stream is None:
            yield
            return
        started = time.perf_counter_ns()
        status = "failed"
        try:
            yield
            status = "completed"
        finally:
            elapsed = time.perf_counter_ns() - started
            self.sequence += 1
            record = {"schema": "development-stage-wall-timing-v1", "sequence": self.sequence,
                      "stage": stage, "context": context, "clock": "perf_counter_ns",
                      "start_ns": started, "elapsed_ns": elapsed, "status": status}
            self.stream.write(json.dumps(record, allow_nan=False) + "\n")
