"""Opt-in vectorized checks for spatial arrays decoded from native JSON."""
from contextlib import contextmanager


def vectorized_spatial(observation):
    import numpy as np
    tensor = observation["spatial"]
    values = tensor["data"]
    if (tensor["shape"] != [32, 32, 32] or tensor["logical_order"] != "channel-y-x" or
            len(values) != 32768):
        raise ValueError("M04 spatial shape/order drifted")
    # Do not request a floating dtype: that could silently coerce JSON strings.
    # JSON provides bool/int/float scalars; nested, string, null and object values
    # must still fail. Return the original list so native float32 inputs are
    # unchanged. This optimization does not cache or skip repeated validation.
    array = np.asarray(values)
    if (array.shape != (32768,) or array.dtype.kind not in "biuf" or
            not np.isfinite(array).all() or (array < 0).any() or (array > 1).any()):
        raise ValueError("M04 spatial values left the frozen finite [0,1] range")
    return values


@contextmanager
def spatial_validation(collector, mode):
    if mode not in ("reference", "vectorized"):
        raise ValueError("Unknown spatial validation mode")
    original = collector.spatial
    if mode == "vectorized":
        import numpy  # Fail before collection if the opt-in dependency is absent.
        collector.spatial = vectorized_spatial
    try:
        yield
    finally:
        collector.spatial = original
