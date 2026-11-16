"""A tiny moving-average backtest over a fixed price history (a test fixture)."""

import argparse
import csv
import json
from pathlib import Path

PRICES = [10, 11, 12, 11, 10, 9, 10, 12, 13, 14, 13, 12, 11, 12, 14, 15, 16, 15, 14, 13]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    window = json.loads(Path(args.input).read_text(encoding="utf-8"))["parameters"]["window"]
    out = Path(args.output)
    cash, held, trades = 100.0, 0.0, []
    for day in range(window, len(PRICES)):
        avg = sum(PRICES[day - window : day]) / window
        price = PRICES[day]
        if price > avg and held == 0:
            held, cash = cash / price, 0.0
            trades.append((day, "buy", price))
        elif price < avg and held > 0:
            cash, held = held * price, 0.0
            trades.append((day, "sell", price))
    final = cash + held * PRICES[-1]
    with (out / "trades.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["day", "side", "price"])
        w.writerows(trades)
    (out / "output.json").write_text(json.dumps({"trades": len(trades), "return_pct": round(final - 100.0, 2)}), encoding="utf-8")


if __name__ == "__main__":
    main()
