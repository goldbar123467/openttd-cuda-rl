"""Optional public-planner curriculum; every proposed action remains a native primitive."""
import hashlib
import json

from local import ROOT, write_json
from service_v2 import ServicePolicy

GUIDANCE = "one-bus-public-plan-v1"
WAIT_GUIDANCE = "one-bus-public-plan-v2"
BORROW_GUIDANCE = "one-bus-public-plan-v3"
GUIDANCES = (GUIDANCE, WAIT_GUIDANCE, BORROW_GUIDANCE)


class PublicPlanGuide:
    def __init__(self, observation, output, *, guidance=GUIDANCE):
        if guidance not in GUIDANCES:
            raise ValueError("Unsupported public planner guidance version")
        self.guidance = guidance
        self.policy = ServicePolicy(observation, repay=False, planner="graph", minimum_length=12, site_checks=True)
        contract = json.loads((ROOT / "config/v2/m15-scalable-contract.json").read_text())
        self.families = contract["action"]["families"]
        self.proposal = None
        self.next_stage = None
        self.next_actions = None
        write_json(output / "planner-guide.json", {"guidance": self.guidance, "plan": self.policy.plan,
            "claim": "Planner supplies route construction choices; neural policy controls execution timing and debt repayment and, in v3, optional first-bus borrowing recovery"})

    def prepare(self, observation, candidate_path, records, native_mask):
        # A time-limit bootstrap has physical candidates in TENSORS but no ACT
        # candidates in OBSERVE. Rebuild only those current legal descriptors.
        exposed = [{"key": value["stable_key"], "family": self.families[value["family_index"]],
                    "parameters": value["parameters"], "cost": value["cost"]} for value in records.values()]
        preview = {**observation, "candidates": exposed}
        stage = self.policy.stage
        next_actions = None
        blocked = False
        try:
            try:
                proposal = self.policy.choose(preview)
                next_stage = self.policy.stage
            except RuntimeError as exc:
                unavailable_service = (self.guidance in (WAIT_GUIDANCE, BORROW_GUIDANCE) and
                    str(exc) == "Planned service continuation has no exposed legal candidate" and
                    stage >= len(self.policy.plan["actions"]))
                if not (unavailable_service or str(exc).startswith("Planned primitive is no longer exposed/legal at stage ")):
                    raise
                # The native bounded candidate set can change after repayment
                # even when a planned tile is still clear. Use another exposed
                # primitive from the same plan; never submit a hidden command.
                # In v2, an unavailable post-construction service action also
                # waits. This preserves a legal game when, for example, the
                # company cannot afford a bus; it adds no cash or borrowing.
                index = {(c["family"], tuple(c["parameters"][1:4])): c for c in exposed}
                remaining = self.policy.plan["actions"]
                available = next((i for i in range(stage, len(remaining))
                                  if (remaining[i][0], tuple(remaining[i][1])) in index), None)
                if available is None:
                    proposal = next(c for c in exposed if c["family"] == "WAIT")
                    next_stage, blocked = stage, True
                else:
                    family, params = remaining[available]
                    proposal = index[(family, tuple(params))]
                    next_actions = list(remaining)
                    next_actions[stage], next_actions[available] = next_actions[available], next_actions[stage]
                    next_stage = stage + 1
        finally:
            # Evaluating the next value or choosing WAIT must not advance the
            # construction plan. Commit only the actual chosen proposal.
            self.policy.stage = stage
        # Expose recovery as a choice only after first-bus construction.
        # The low-cash threshold is below the existing repayment threshold,
        # so the policy never has indistinguishable borrow/repay alternatives.
        borrowing_recovery = (self.guidance == BORROW_GUIDANCE and blocked and
            stage >= len(self.policy.plan["actions"]) and not observation["vehicles"] and
            observation["economy"]["balance"] < 10000)
        allowed = {proposal["key"]}
        for candidate in exposed:
            if candidate["family"] == "WAIT" or (candidate["family"] == "MANAGE_LOAN" and
                candidate["parameters"][1:3] == [2, 10000] and observation["economy"]["balance"] >= 20000 and
                observation["economy"]["loan"] >= 10000):
                allowed.add(candidate["key"])
            elif (borrowing_recovery and candidate["family"] == "MANAGE_LOAN" and
                  candidate["parameters"][1:3] == [1, 10000]):
                allowed.add(candidate["key"])
        present = {value["stable_key"] for value in records.values()}
        if not allowed <= present:
            raise ValueError("Planner proposed an unexposed native action")
        mask = bytes(int(row in records and records[row]["stable_key"] in allowed) for row in range(4096))
        if not any(mask) or any(value and not native_mask[row] for row, value in enumerate(mask)):
            raise ValueError("Planner mask must be a nonempty subset of native legality")
        original = candidate_path.read_bytes()
        if len(original) != 790528 or original[-4096:] != native_mask:
            raise ValueError("Native candidate bytes/mask differ before curriculum filtering")
        guided = original[:-4096] + mask
        path = candidate_path.with_name(candidate_path.stem + "-guided-one-bus.bin")
        if path.exists():
            if path.read_bytes() != guided:
                raise ValueError("A repeated physical snapshot produced a different planner mask")
        else:
            with path.open("xb") as stream:
                stream.write(guided)
        self.proposal, self.next_stage, self.next_actions = proposal["key"], next_stage, next_actions
        info = {"guidance": self.guidance, "stage": stage, "proposed_key": self.proposal,
            "construction_blocked": blocked, "construction_reordered": next_actions is not None,
            "allowed_keys": sorted(allowed), "native_legal_count": sum(native_mask), "sampling_legal_count": sum(mask),
            "sampling_binary": str(path), "sampling_binary_sha256": hashlib.sha256(guided).hexdigest(),
            "native_binary_sha256": hashlib.sha256(original).hexdigest()}
        if self.guidance == BORROW_GUIDANCE:
            info["borrowing_recovery_eligible"] = borrowing_recovery
        return path, mask, info

    def commit(self, candidate_key):
        if self.proposal is None:
            raise ValueError("No planner proposal was prepared")
        if candidate_key == self.proposal:
            self.policy.stage = self.next_stage
            if self.next_actions is not None:
                self.policy.plan["actions"] = self.next_actions
