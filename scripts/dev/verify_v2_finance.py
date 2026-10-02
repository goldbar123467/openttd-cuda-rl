#!/usr/bin/env python3
"""Check opt-in finance tensors against native public state and legacy execution."""
import argparse
import hashlib
import json
from pathlib import Path

from finance_observation_v2 import SCHEMA, FIELDS, expected_features, validate_finance
from live_v2 import LiveV2
from local import capture_source, host, source_identity, write_json


def legacy_view(value):
    if isinstance(value, dict):
        return {key: legacy_view(item) for key, item in value.items() if key != "finance"}
    if isinstance(value, list):
        return [legacy_view(item) for item in value]
    return value


def read_tensor(path):
    metadata = json.loads(path.read_text())
    filename = metadata["binary"]["file"]
    if Path(filename).name != filename:
        raise ValueError("Tensor binary is not a local basename")
    data = (path.parent / filename).read_bytes()
    if len(data) != metadata["binary"]["bytes"] or hashlib.sha256(data).hexdigest() != metadata["binary"]["sha256"]:
        raise ValueError("Native tensor size/hash differs")
    return metadata, data


def capture(engine, output, *, finance):
    kwargs = {"observation_mode": "finance-v1"} if finance else {}
    client = LiveV2(engine, output, decisions=26, ticks=128, **kwargs)
    snapshots, tensors, transitions = [], [], []
    try:
        for step in range(27):
            observation = client.request("OBSERVE")["observation"]
            snapshots.append(observation)
            response = client.request("TENSORS")
            if response["status"] != "OK" or response["tensors"]["token"] != observation["token"]:
                raise ValueError("Finance tensor request differs from observation boundary")
            metadata, data = read_tensor(Path(response["tensors"]["observation"]))
            _, candidates = read_tensor(Path(response["tensors"]["candidates"]))
            if finance:
                validate_finance(observation, metadata, data)
            elif metadata["observation_schema_id"] != "v2-m15-public-development-v2" or \
                    "finance_observation" in metadata or "finance" in observation["economy"] or any(data[16 * 4:23 * 4]):
                raise ValueError("Legacy mode acquired finance fields")
            tensors.append((data, candidates))
            if step == 26:
                break
            if step < 2:
                wanted = [1 if step == 0 else 2, 10000]
                candidate = next(item for item in observation["candidates"]
                                 if item["family"] == "MANAGE_LOAN" and item["parameters"][1:3] == wanted)
            else:
                candidate = next(item for item in observation["candidates"] if item["family"] == "WAIT")
            action = client.request("ACT", token=observation["token"], candidate=candidate["key"])
            if action["status"] != "OK" or action["action"]["status"] not in ("SUCCESS", "NO_OP"):
                raise ValueError("Finance verification native action failed")
            if step < 2:
                # Inspect immediately after the command, before STEP can apply
                # interest/running costs. This separates principal from earnings.
                command_after = client.request("OBSERVE")["observation"]["economy"]
                command_before = observation["economy"]
                amount = 10000 if step == 0 else -10000
                if any(command_after[name] - command_before[name] != amount for name in ("balance", "loan")):
                    raise ValueError("Native loan command cash/principal change differs")
                if any(command_after[name] != command_before[name] for name in ("income", "expenses", "operating_profit")):
                    raise ValueError("Native principal movement was counted as operating earnings")
                if finance and (command_after["finance"]["maximum_loan"] != command_before["finance"]["maximum_loan"] or
                        command_after["finance"]["borrowing_headroom"] != command_before["finance"]["borrowing_headroom"] - amount):
                    raise ValueError("Loan command changed effective limit or inconsistent headroom")
            transitions.append(client.request("STEP")["transition"])
        client.close()
    finally:
        client.abort()
    return snapshots, tensors, transitions


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {"kind": "development-v2-finance-observation-verification", "status": "running",
              "source": source_identity(), "host": host(), "engine": str(args.openttd.resolve()),
              "engine_sha256": hashlib.sha256(args.openttd.read_bytes()).hexdigest(),
              "claim": "Native observation and financing correctness; no neural learning result"}
    capture_source(output / "source")
    write_json(output / "verification.json", record)
    try:
        legacy, legacy_tensors, legacy_transitions = capture(args.openttd, output / "legacy", finance=False)
        finance, finance_tensors, finance_transitions = capture(args.openttd, output / "finance", finance=True)
        if legacy_view(finance) != legacy or legacy_view(finance_transitions) != legacy_transitions:
            raise ValueError("Opt-in finance observations changed native gameplay or legacy public fields")
        for (old, old_candidates), (new, new_candidates) in zip(legacy_tensors, finance_tensors, strict=True):
            expected = bytearray(old)
            expected[16 * 4:23 * 4] = new[16 * 4:23 * 4]
            expected[1181696 + 16:1181696 + 20] = new[1181696 + 16:1181696 + 20]
            if bytes(expected) != new or old_candidates != new_candidates:
                raise ValueError("Finance mode changed tensors outside its declared own-finance slots")
        first, borrowed, repaid, last = [finance[index]["economy"] for index in (0, 1, 2, -1)]
        if borrowed["loan"] != first["loan"] + 10000 or repaid["loan"] != first["loan"]:
            raise ValueError("Native borrow/repay principal changes differ")
        if borrowed["finance"]["borrowing_headroom"] != first["finance"]["borrowing_headroom"] - 10000:
            raise ValueError("Borrowing did not consume borrowing capacity")
        if last["finance"]["year_interest_paid"] <= first["finance"]["year_interest_paid"]:
            raise ValueError("Bounded native wait did not expose an actual interest payment")
        record.update(status="passed", snapshots=len(finance), checks={
            "legacy_state_and_transitions_unchanged": True, "only_declared_tensor_slots_changed": True,
            "all_finance_tensors_match_public_values": True, "borrow_repay_cash_principal_limit_headroom": True,
            "principal_not_counted_as_operating_earnings": True,
            "actual_interest_payment": last["finance"]["year_interest_paid"] - first["finance"]["year_interest_paid"]},
            initial_finance=first, final_finance=last)
    except BaseException as error:
        record.update(status="failed", error=str(error))
        raise
    finally:
        write_json(output / "verification.json", record)
    print(json.dumps({"status": record["status"], "output": str(output)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openttd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
