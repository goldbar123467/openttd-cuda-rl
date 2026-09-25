"""Exact state comparison for native C++ checkpoints with pointer-keyed Adam.

LibTorch serializes Adam slot keys as process-local parameter addresses in an
unordered map. Archive bytes therefore cannot establish equality across native
processes. Resolve each slot through the serialized parameter-group ordering;
compare every model tensor, slot, option, counter and RNG byte without tolerance.
Only use this reader on our own hash-identified qualification artifacts.
"""
import hashlib
import json


def checkpoint_state(path):
    import torch
    checkpoint = torch.jit.load(str(path), map_location="cpu")
    if {n for n, _ in checkpoint.named_children()} != {"model", "optimizer"}:
        raise ValueError("Unknown native checkpoint module layout")
    state = dict(checkpoint.named_buffers(recurse=False))
    required = {"identity", "rng_0", "rng_1", "rng_2", "hidden", "counters", "torch_cpu_rng"}
    if not required <= state.keys() or state.keys() - (required | {"torch_cuda_rng"}):
        raise ValueError("Unknown native checkpoint state layout")
    parameters = list(checkpoint.model.named_parameters())
    state.update({"model." + key: value for key, value in parameters})
    state.update({"model.buffer." + key: value for key, value in checkpoint.model.named_buffers()})
    groups = checkpoint.optimizer.param_groups
    count = getattr(groups, "param_groups/size").item()
    if count != 1:
        raise ValueError("Expected the native trainer's single Adam parameter group")
    group = getattr(groups, "param_groups/0")
    if getattr(group, "params/size").item() != len(parameters):
        raise ValueError("Adam group and model parameter counts differ")
    slots = dict(checkpoint.optimizer.state.named_children())
    visited = []
    for i, (name, _) in enumerate(parameters):
        pointer = str(getattr(group, "params/" + str(i)))
        visited.append(pointer)
        slot = slots[pointer]
        # C++ Adam writes IValue tensor attributes, not registered buffers.
        moments = {key: getattr(slot, key) for key in ("exp_avg", "exp_avg_sq")}
        if any(not isinstance(v, torch.Tensor) for v in moments.values()) or slot._c.hasattr("max_exp_avg_sq"):
            raise ValueError("Unknown Adam moment layout")
        for key, value in moments.items():
            state[f"adam.{name}.{key}"] = value
        state[f"adam.{name}.step"] = slot.step
    if len(visited) != len(set(visited)) or set(visited) != slots.keys():
        raise ValueError("Adam parameter binding is missing, duplicated or unclaimed")
    for key in ("lr", "betas", "eps", "weight_decay", "amsgrad"):
        state["adam.options." + key] = getattr(group.options, key)
    return state


def fingerprint(state):
    import torch
    result = hashlib.sha256()
    for key, value in sorted(state.items()):
        result.update(key.encode() + b"\0")
        if isinstance(value, torch.Tensor):
            result.update(json.dumps([str(value.dtype), list(value.shape)]).encode() + b"\0")
            result.update(value.detach().cpu().contiguous().numpy().tobytes())
        else:
            result.update(json.dumps(value, allow_nan=False).encode())
        result.update(b"\0")
    return result.hexdigest()


def compare(left, right):
    import torch
    a, b = checkpoint_state(left), checkpoint_state(right)
    if a.keys() != b.keys():
        raise ValueError("Native checkpoint state fields differ")
    for key in a:
        if isinstance(a[key], torch.Tensor):
            equal = (isinstance(b[key], torch.Tensor) and a[key].dtype == b[key].dtype and
                     a[key].shape == b[key].shape and torch.equal(a[key], b[key]))
        else:
            equal = type(a[key]) is type(b[key]) and a[key] == b[key]
        if not equal:
            raise ValueError("Native checkpoint state differs: " + key)
    return {"status": "passed", "exact_state_sha256": fingerprint(a), "state_fields": len(a),
            "normalization": "Adam process-local pointer keys are resolved through parameter-group order; no numerical tolerance"}
