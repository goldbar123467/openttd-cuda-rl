"""Label the frozen short training-device probe without changing its execution."""


def run_probe(evaluate, *args):
    result = dict(evaluate(*args))
    # The frozen evaluator reads the current-quarter snapshot counter. Its
    # value must not be presented as lifetime income from a complete episode.
    result["quarter_income"] = result.pop("income")
    result["claim"] = "not an evaluation"
    return result
