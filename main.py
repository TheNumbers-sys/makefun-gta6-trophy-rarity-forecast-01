"""Forecast trophy earn-rate quantiles from the case's recorded page history."""
import json
import math
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
NORMAL_Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
LAUNCH = datetime(2026, 11, 19, tzinfo=timezone.utc)
TIER_CAP = {"platinum": 0.10, "gold": 0.28, "silver": 0.65, "bronze": 1.10}


def bounded(value, low, high):
    return min(high, max(low, value))


def probability_logit(rate):
    p = bounded(float(rate), 0.01, 99.99) / 100.0
    return math.log(p / (1.0 - p))


def inverse_logit(value):
    if value >= 0:
        e = math.exp(-value)
        return 100.0 / (1.0 + e)
    e = math.exp(value)
    return 100.0 * e / (1.0 + e)


def parse_time(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("timestamp has no UTC offset")
    return stamp.astimezone(timezone.utc)


def distinct_reads(history):
    result = []
    previous = None
    for read in history:
        signature = (read.get("players_tracked"), tuple(read.get("rates", [])))
        if signature != previous:
            result.append(read)
            previous = signature
    return result


def line_fit(xs, ys):
    if len(xs) < 2:
        return 0.0, ys[-1], 0.0
    xbar = sum(xs) / len(xs)
    ybar = sum(ys) / len(ys)
    denom = sum((x - xbar) ** 2 for x in xs)
    slope = 0.0 if denom == 0 else sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denom
    intercept = ybar - slope * xbar
    rms = math.sqrt(sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys)) / len(xs))
    return slope, intercept, rms


def rounding4(number):
    return float(Decimal(str(number)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def forecast(case):
    if case.get("schema") != "makefun/gta6-trophies-case/v1":
        raise ValueError("unsupported or missing case schema")
    if case.get("levels") != LEVELS:
        raise ValueError("case quantile levels do not match the competition")
    history = case.get("history")
    trophies = case.get("trophies")
    if not isinstance(history, list) or not history or not isinstance(trophies, list) or not trophies:
        raise ValueError("case needs a nonempty history and trophy list")
    for position, read in enumerate(history):
        if not isinstance(read.get("rates"), list) or len(read["rates"]) != len(trophies):
            raise ValueError(f"history row {position} has the wrong number of rates")
        if not isinstance(read.get("players_tracked"), (int, float)) or read["players_tracked"] <= 0:
            raise ValueError(f"history row {position} has an invalid player count")
        parse_time(read["at"])
    epochs = distinct_reads(history)
    last = epochs[-1]
    if len(last.get("rates", [])) != len(trophies):
        raise ValueError("last history row has the wrong number of rates")

    checkpoint = parse_time(case["at"])
    target = parse_time(case["target"])
    launch_hours = lambda read: max(0.0, (parse_time(read["at"]) - LAUNCH).total_seconds() / 3600.0)
    xs = [math.log1p(launch_hours(read)) for read in epochs]
    horizon_days = max(0.0, (target - checkpoint).total_seconds() / 86400.0)
    future_x = math.log1p(max(0.0, (target - LAUNCH).total_seconds() / 3600.0))

    player_values = [math.log(max(1, float(r["players_tracked"]))) for r in epochs]
    player_slope, player_intercept, _ = line_fit(xs, player_values)
    player_slope = bounded(player_slope, -0.25, 0.8)
    projected = math.exp(bounded(player_intercept + player_slope * future_x, math.log(1), math.log(1e15)))
    dilution = bounded(float(last["players_tracked"]) / projected, 0.02, 1.0)

    # A page with no observed refresh still has a meaningful chance of a large denominator jump.
    flat_weight = bounded((4.0 - len(epochs)) / 3.0, 0.0, 1.0)
    refresh_factor = 0.2208 + 0.7792 * (1.0 - math.exp(-horizon_days / 2.0))
    refresh_weight = flat_weight * bounded(horizon_days / 0.0625, 0.0, 1.0)
    rows = []
    for index, trophy in enumerate(trophies):
        observed = [r["rates"][index] for r in epochs if r["rates"][index] is not None]
        if not observed:
            raise ValueError(f"trophy {trophy.get('id')} has no observed rate")
        latest = float(observed[-1])
        if latest >= 99.5:
            center = 99.99
            spread = 0.035
        else:
            valid = [(math.log1p(launch_hours(read)), probability_logit(read["rates"][index]))
                     for read in epochs if read["rates"][index] is not None]
            slope, intercept, residual = line_fit([p[0] for p in valid], [p[1] for p in valid])
            cap = TIER_CAP.get(trophy.get("tier"), 0.55)
            slope = bounded(slope, -min(0.20, cap), cap)
            slope *= min(1.0, max(0.0, (len(valid) - 1) / 2.0))
            projected_logit = intercept + slope * future_x
            trend_rate = inverse_logit(projected_logit)
            prior_blend = refresh_weight
            center = trend_rate * dilution * ((1.0 - prior_blend) + prior_blend * refresh_factor)
            center = bounded(center, 0.01, 99.99)
            residual = max(0.15, residual)
            refresh_uncertainty = 0.90 * flat_weight + 0.35 * (1.0 - flat_weight)
            spread = math.sqrt((0.5 * math.sqrt(horizon_days)) ** 2 + residual ** 2 + refresh_uncertainty ** 2)
            spread = bounded(spread, 0.15, 1.6)
        values = [bounded(rounding4(inverse_logit(probability_logit(center) + z * spread)), 0.01, 99.99)
                  for z in NORMAL_Z]
        for j in range(1, len(values)):
            values[j] = max(values[j], values[j - 1])
        rows.append({"id": trophy["id"], "q": values})
    return {"trophies": rows}


def main():
    input_dir = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
    output_dir = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))
    files = sorted(input_dir.glob("*.in"))
    if not files:
        raise ValueError(f"no .in case files in {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    for source in files:
        try:
            case = json.loads(source.read_text(encoding="utf-8"))
            result = forecast(case)
            encoded = json.dumps(result, separators=(",", ":"), allow_nan=False) + "\n"
            if len(encoded.encode("utf-8")) > 65536:
                raise ValueError("forecast exceeds the 65,536-byte limit")
            (output_dir / f"{source.stem}.out").write_text(encoded, encoding="utf-8")
        except Exception as exc:
            raise ValueError(f"{source.name}: {exc}") from exc


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"forecast error: {error}", file=sys.stderr)
        sys.exit(1)
