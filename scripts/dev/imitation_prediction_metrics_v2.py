"""Tie-aware metrics shared by native human import and retention reports."""
import math

from audit_action_inputs_v2 import PROBABILITY_TOLERANCE, prediction_result


def prediction_metrics(prediction, label):
    result = prediction_result(prediction, label)
    return {**result,
            "unique_exact": result["unique_greedy_target"],
            "target_tied": len(label["legal_rows"]) > 1 and abs(result["target_margin"]) <= PROBABILITY_TOLERANCE}


def prediction_summary(items):
    if not items:
        raise ValueError("Imitation prediction summary requires examples")
    probabilities = [item["target_probability"] for item in items]
    exact = sum(item["exact_row"] for item in items)
    unique = sum(item["unique_exact"] for item in items)
    return {"examples": len(items), "exact_rows": exact, "accuracy": exact / len(items),
            "unique_exact_rows": unique, "unique_exact_accuracy": unique / len(items),
            "all_unique_exact": unique == len(items),
            "tied_target_count": sum(item["target_tied"] for item in items),
            "minimum_target_margin": min(item["target_margin"] for item in items),
            "mean_target_probability": sum(probabilities) / len(items),
            "zero_target_probabilities": sum(value == 0 for value in probabilities),
            "mean_negative_log_likelihood": (-sum(map(math.log, probabilities)) / len(items)
                                              if all(probabilities) else None)}
