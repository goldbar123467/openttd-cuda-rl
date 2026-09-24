"""Economic accounting separates vehicle resale, financing, and operating income."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from service_v2 import summarize


class EconomicsTests(unittest.TestCase):
    def test_buy_sell_and_borrow_reconcile_without_counting_principal_as_profit(self):
        first = {"balance": 100000, "loan": 100000, "operating_profit": 0, "delivered_passengers": 0}
        # Buy for 6000, earn 500, sell for 4000, and borrow 10000.
        end = {"balance": 108500, "loan": 110000, "operating_profit": 500, "delivered_passengers": 32}
        rows = [{"decision": i + 1, "before": first, "after": end,
                 "action": {"family": family, "status": "SUCCESS", "native_commands": [
                     {"phase": "EXECUTE", "status": "SUCCESS", "cost": cost},
                     {"phase": "TEST", "status": "SUCCESS", "cost": cost}]}}
                for i, (family, cost) in enumerate((("BUY_BUS", 6000), ("SELL_VEHICLE", -4000), ("MANAGE_LOAN", 0)))]
        result = summarize(rows, {"economy": first, "tick": 1280},
                           {"economy": end, "tick": 1664, "terminal": False, "vehicles": [], "stations": []})
        self.assertEqual(result["capital_spend"], 6000)
        self.assertEqual(result["vehicle_sale_proceeds"], 4000)
        self.assertEqual(result["net_capital_spend"], 2000)
        self.assertEqual(result["operating_profit_less_capital"], -1500)
        self.assertEqual(result["balance_change"], result["operating_profit_less_capital"] + result["loan_change"])
        self.assertEqual(result["cash_result_excluding_financing"], -1500)
        self.assertEqual(result["other_cash_flow"], 0)
        end["balance"] -= 25  # Native EXPENSES_OTHER is excluded from cur_economy.expenses.
        other = summarize(rows, {"economy": first, "tick": 1280},
                          {"economy": end, "tick": 1664, "terminal": False, "vehicles": [], "stations": []})
        self.assertEqual(other["operating_profit"], 500)
        self.assertEqual(other["cash_result_excluding_financing"], -1525)
        self.assertEqual(other["other_cash_flow"], -25)
        self.assertEqual(other["cash_result_before_capital"], 475)


if __name__ == "__main__":
    unittest.main()
