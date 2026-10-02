"""Independent validation of the opt-in native public finance tensor projection."""
import math
import struct

SCHEMA = "v2-m15-public-development-finance-v1"
FIELDS = ("maximum_loan", "borrowing_headroom", "interest_rate_percent", "quarter_income",
          "quarter_expenses", "quarter_operating_profit", "year_interest_paid")
MAXIMUM_LOAN_ENCODING = "own-row-column-4-effective-GetMaxLoan-divided-by-1e9"


def field_descriptions():
    return [{"index": 16 + index, "name": name,
             "encoding": "percent/100" if name == "interest_rate_percent" else "signed-log1p-clipped-1e9"}
            for index, name in enumerate(FIELDS)]


def expected_features(finance):
    def signed_log(value):
        return math.copysign(math.log1p(min(abs(value), 1e9)) / math.log1p(1e9), value)
    return tuple(finance[name] / 100 if name == "interest_rate_percent" else signed_log(finance[name])
                 for name in FIELDS)


def validate_finance(observation, metadata, data, *, schema=SCHEMA):
    if metadata.get("observation_schema_id") != schema or len(data) != 2182927:
        raise ValueError("Finance observation schema or tensor size differs")
    description = metadata.get("finance_observation", {})
    if (description.get("mode") != "finance-v1" or description.get("structured") != field_descriptions() or
            description.get("company_maximum_loan") != MAXIMUM_LOAN_ENCODING or
            description.get("quarter_expenses_sign") != "native-negative-expense"):
        raise ValueError("Finance metadata field names or encodings differ")
    economy = observation.get("economy", {})
    finance = economy.get("finance", {})
    if (set(finance) != set(FIELDS) or any(type(finance[name]) is not int for name in FIELDS) or
            type(economy.get("loan")) is not int):
        raise ValueError("Finance raw fields must be native integer amounts and rate")
    if description.get("values") != finance:
        raise ValueError("Finance metadata and public state differ")
    if finance["borrowing_headroom"] != max(0, finance["maximum_loan"] - economy["loan"]):
        raise ValueError("Borrowing headroom differs from effective limit and debt")
    if finance["quarter_operating_profit"] != finance["quarter_income"] + finance["quarter_expenses"]:
        raise ValueError("Current-quarter finance income and expenses do not reconcile")
    actual = struct.unpack_from("<7f", data, 16 * 4)
    if any(not math.isclose(a, b, rel_tol=2e-7, abs_tol=1e-8) for a, b in zip(actual, expected_features(finance), strict=True)):
        raise ValueError("Finance tensor differs from independent public-state projection")
    maximum = struct.unpack_from("<f", data, 1181696 + 4 * 4)[0]
    if not math.isclose(maximum, min(max(finance["maximum_loan"] / 1e9, 0), 1), rel_tol=2e-7, abs_tol=1e-10):
        raise ValueError("Own-company tensor does not contain the effective maximum loan")
