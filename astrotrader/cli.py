"""astrotrader CLI: build context, decide, mirror, backtest, calibrate."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click
import pandas as pd

from .backtest.ablation import (
    STANDARD_ABLATIONS,
    print_comparison,
    run_ablation,
)
from .backtest.report import print_summary, summarize
from .backtest.walk_forward import walk_forward
from .calibration.calibrator import (
    IsotonicCalibrator,
    PlattCalibrator,
    auto_load,
    default_path,
    load_calibrator,
    save_calibrator,
)
from .pipeline import AstrotradeContext, decide


def _resolve_calibrator(use: str | None, symbol: str, horizon: int):
    """Translate --use-calibrator argument into a Calibrator (or None)."""
    if not use:
        return None
    if use == "auto":
        cal = auto_load(symbol, horizon)
        if cal is None:
            raise click.ClickException(
                f"--use-calibrator auto: no calibrator at {default_path(symbol, horizon)}. "
                f"Run `astrotrader calibrate --symbol {symbol} --horizon {horizon}` first."
            )
        return cal
    return load_calibrator(use)


@click.group()
def main() -> None:
    """ASTROTRADE — Time Intelligence Engine."""


@main.command()
@click.option("--symbol", default="SPY")
@click.option("--start", default=None)
@click.option("--end", default=None)
@click.option("--refresh", is_flag=True, default=False)
@click.option("--horizon", type=int, default=5)
@click.option("--top-n", type=int, default=None)
@click.option("--date", default=None, help="Query date YYYY-MM-DD (default: most recent).")
@click.option("--show-mirror/--no-mirror", default=True)
@click.option(
    "--use-calibrator",
    default=None,
    help='Path to calibrator joblib, or "auto" for the default cache location.',
)
def decide_cmd(
    symbol, start, end, refresh, horizon, top_n, date, show_mirror, use_calibrator
) -> None:
    """Run a full decide cycle and print the score + mirror panel."""
    ctx = AstrotradeContext.build(symbol=symbol, start=start, end=end, refresh=refresh)
    cal = _resolve_calibrator(use_calibrator, symbol, horizon)
    if cal is not None:
        ctx = ctx.attach_calibrator(cal)
        click.echo(
            f"using calibrator: method={cal.method} n_train={cal.n_train} "
            f"horizon={cal.horizon} symbol={cal.symbol}"
        )
    decision = decide(ctx, query_date=date, primary_horizon=horizon, top_n=top_n)

    s = decision.score
    click.echo(f"\n=== ASTROTRADE :: {ctx.symbol} :: {decision.query_date.date()} ===")
    click.echo(f"horizon: {s.horizon}d   bias: {s.bias.upper()}")
    if s.calibrated:
        click.echo(f"P(up):   {s.p_up:.3f}    P(down): {s.p_down:.3f}    [calibrated; raw={s.p_up_raw:.3f}]")
    else:
        click.echo(f"P(up):   {s.p_up:.3f}    P(down): {s.p_down:.3f}")
    click.echo(f"E[ret]:  {s.expected_logret*100:+.2f}%   E[realvol]: {s.expected_realvol:.2%}")
    click.echo(f"confidence: {s.confidence:.2f}   N: {s.sample_size}   ESS: {s.effective_sample_size:.1f}")
    click.echo("\ncomponent contributions (probability points vs uniform baseline):")
    for c in s.components:
        click.echo(f"  {c.name:<8} {c.contribution:+6.2f}   {c.detail}")

    click.echo("\nhorizon distribution table:")
    rows = []
    for h in decision.bundle.horizons:
        rows.append({
            "h": h.horizon,
            "n": h.n,
            "mean_ret": f"{h.mean_logret*100:+.2f}%",
            "p_up": f"{h.p_up:.2f}",
            "q05": f"{h.quantiles['q05']*100:+.2f}%",
            "q50": f"{h.quantiles['q50']*100:+.2f}%",
            "q95": f"{h.quantiles['q95']*100:+.2f}%",
            "E[maxdd]": f"{h.expected_maxdd*100:+.2f}%",
            "E[maxup]": f"{h.expected_maxup*100:+.2f}%",
        })
    click.echo(pd.DataFrame(rows).to_string(index=False))

    if show_mirror:
        click.echo("\nmirror — top 10 most similar past states:")
        top = decision.similarity.matches[:10]
        mrows = []
        for m in top:
            mrows.append({
                "date": m.date.date(),
                "sim": f"{m.similarity:+.3f}",
                "astro": f"{m.per_group_similarity['astro']:+.2f}",
                "market": f"{m.per_group_similarity['market']:+.2f}",
                "regime": f"{m.per_group_similarity['regime']:+.2f}",
            })
        click.echo(pd.DataFrame(mrows).to_string(index=False))


@main.command("export-json")
@click.option("--symbol", default="SPY")
@click.option("--horizon", type=int, default=5)
@click.option("--date", default=None)
def export_json(symbol, horizon, date) -> None:
    """Print decision as JSON (for piping into the UI / API consumers)."""
    ctx = AstrotradeContext.build(symbol=symbol)
    decision = decide(ctx, query_date=date, primary_horizon=horizon)
    payload = {
        "symbol": symbol,
        "query_date": str(decision.query_date.date()),
        "score": asdict(decision.score),
        "horizons": [asdict(h) for h in decision.bundle.horizons],
        "matches": [
            {
                "date": str(m.date.date()),
                "similarity": m.similarity,
                "per_group": m.per_group_similarity,
            }
            for m in decision.similarity.matches[:25]
        ],
    }
    click.echo(json.dumps(payload, indent=2, default=str))


@main.command()
@click.option("--symbol", default="SPY")
@click.option("--horizon", type=int, default=5)
@click.option("--start", default="2018-01-01")
@click.option("--end", default=None)
@click.option("--top-n", type=int, default=50)
@click.option("--stride", type=int, default=1, help="Evaluate every k-th trading day.")
@click.option("--confidence-threshold", type=float, default=0.2)
@click.option(
    "--use-calibrator",
    default=None,
    help='Path to calibrator joblib, or "auto" for the default cache location.',
)
@click.option("--save-rows", default=None, help="Optional CSV path to dump per-day rows.")
@click.option("--save-equity", default=None, help="Optional CSV path to dump equity curve.")
def backtest(
    symbol,
    horizon,
    start,
    end,
    top_n,
    stride,
    confidence_threshold,
    use_calibrator,
    save_rows,
    save_equity,
) -> None:
    """Walk-forward calibration & strategy backtest."""
    click.echo(f"building context for {symbol}…")
    ctx = AstrotradeContext.build(symbol=symbol)
    cal = _resolve_calibrator(use_calibrator, symbol, horizon)
    if cal is not None:
        ctx = ctx.attach_calibrator(cal)
        click.echo(
            f"using calibrator: method={cal.method} n_train={cal.n_train} "
            f"horizon={cal.horizon} symbol={cal.symbol}"
        )

    n_dates = (
        (ctx.state_matrix.dates >= pd.Timestamp(start))
        & (ctx.forward[f"fwd_logret_{horizon}"].reindex(ctx.state_matrix.dates).notna())
    ).sum()
    n_dates = max(int(n_dates // max(stride, 1)), 1)

    with click.progressbar(length=n_dates, label="walk-forward") as bar:
        rows = walk_forward(
            ctx,
            horizon=horizon,
            start=start,
            end=end,
            top_n=top_n,
            stride=stride,
            progress_callback=lambda done, total: bar.update(1),
        )

    if rows.empty:
        click.echo("no rows produced — check date range / horizon vs available history.")
        return

    summary = summarize(rows, horizon=horizon, confidence_threshold=confidence_threshold)
    print_summary(summary)

    # When a calibrator was used, also print metrics on the RAW probabilities so
    # the user sees exactly how much calibration moved the numbers.
    if rows["calibrated"].any():
        from .backtest.metrics import (
            brier_score,
            expected_calibration_error,
            log_loss,
        )
        p_raw = rows["p_up_raw"].to_numpy()
        actual = rows["actual_up"].to_numpy()
        click.echo(
            "\nraw (uncalibrated) baseline on the same window:"
            f"\n  Brier raw: {brier_score(p_raw, actual):.4f}"
            f"\n  Log loss raw: {log_loss(p_raw, actual):.4f}"
            f"\n  ECE raw: {expected_calibration_error(p_raw, actual):.4f}"
        )

    if save_rows:
        rows.to_csv(save_rows, index=False)
        click.echo(f"\nsaved {len(rows)} rows to {save_rows}")
    if save_equity:
        summary.equity.to_csv(save_equity, index=False)
        click.echo(f"saved equity curve to {save_equity}")


# Per-symbol calibration windows. The training window is chosen to leave at
# least one year of clean out-of-sample data for evaluation. Asset classes with
# shallower history (crypto, NSE) get tighter windows.
CALIBRATION_MANIFEST: dict[str, tuple[str, str]] = {
    # US ETFs — long history, comfortable 2010–2018 train
    "SPY":       ("2010-01-01", "2018-12-31"),
    "QQQ":       ("2010-01-01", "2018-12-31"),
    "IWM":       ("2010-01-01", "2018-12-31"),
    "GLD":       ("2010-01-01", "2018-12-31"),
    "USO":       ("2010-01-01", "2018-12-31"),
    # XAUUSD via GC=F has yfinance data only from 2018; state matrix lands ~2019.
    "XAUUSD":    ("2019-06-01", "2023-12-31"),
    # NSE — yfinance India history is shallow; train on what we have through 2020
    "NIFTY":     ("2010-01-01", "2020-12-31"),
    "BANKNIFTY": ("2010-01-01", "2020-12-31"),
    "RELIANCE":  ("2010-01-01", "2020-12-31"),
    "TCS":       ("2010-01-01", "2020-12-31"),
    "HDFCBANK":  ("2010-01-01", "2020-12-31"),
    # Crypto — BTC starts 2014, ETH starts 2017
    "BTCUSD":    ("2015-01-01", "2022-12-31"),
    "ETHUSD":    ("2018-01-01", "2023-12-31"),
}


@main.command("calibrate-all")
@click.option("--horizon", type=int, default=5)
@click.option("--method", type=click.Choice(["isotonic", "platt"]), default="platt")
@click.option("--top-n", type=int, default=50)
@click.option("--stride", type=int, default=2)
@click.option(
    "--symbols",
    default=None,
    help="Comma-separated subset. Default: every symbol in CALIBRATION_MANIFEST.",
)
def calibrate_all(horizon, method, top_n, stride, symbols):
    """Fit a calibrator for every symbol using sensible per-symbol train windows.

    Idempotent: skips symbols whose calibrator already exists.
    """
    chosen = list(CALIBRATION_MANIFEST.keys())
    if symbols:
        wanted = {s.strip().upper() for s in symbols.split(",")}
        chosen = [s for s in chosen if s in wanted]

    summary: list[dict] = []
    for sym in chosen:
        train_start, train_end = CALIBRATION_MANIFEST[sym]
        out = default_path(sym, horizon, method)
        if out.exists():
            click.echo(f"[{sym}] skip — calibrator exists at {out.name}")
            summary.append({"symbol": sym, "status": "skipped", "path": str(out)})
            continue

        click.echo(f"\n=== [{sym}] {train_start} → {train_end}  method={method} ===")
        try:
            ctx = AstrotradeContext.build(symbol=sym)
        except Exception as e:
            click.echo(f"[{sym}] FAIL building context: {e}")
            summary.append({"symbol": sym, "status": "fail_build", "error": str(e)})
            continue

        try:
            rows = walk_forward(
                ctx,
                horizon=horizon,
                start=train_start,
                end=train_end,
                top_n=top_n,
                stride=stride,
            )
        except Exception as e:
            click.echo(f"[{sym}] FAIL walk_forward: {e}")
            summary.append({"symbol": sym, "status": "fail_walk", "error": str(e)})
            continue

        if rows.empty:
            click.echo(f"[{sym}] FAIL — empty training rows")
            summary.append({"symbol": sym, "status": "empty"})
            continue

        if method == "isotonic":
            cal = IsotonicCalibrator.fit(
                rows["p_up_raw"].to_numpy(),
                rows["actual_up"].to_numpy(),
                horizon=horizon,
                symbol=sym,
            )
        else:
            cal = PlattCalibrator.fit(
                rows["p_up_raw"].to_numpy(),
                rows["actual_up"].to_numpy(),
                horizon=horizon,
                symbol=sym,
            )
        save_calibrator(cal, out)
        click.echo(f"[{sym}] OK  N={cal.n_train}  saved {out.name}")
        summary.append({
            "symbol": sym, "status": "ok",
            "n_train": cal.n_train, "path": str(out),
        })

    click.echo("\n=== SUMMARY ===")
    click.echo(pd.DataFrame(summary).to_string(index=False))


@main.command()
@click.option("--symbol", default="SPY")
@click.option("--horizon", type=int, default=5)
@click.option("--train-start", default="2010-01-01")
@click.option("--train-end", default="2018-12-31")
@click.option("--method", type=click.Choice(["isotonic", "platt"]), default="isotonic")
@click.option("--top-n", type=int, default=50)
@click.option("--stride", type=int, default=1)
@click.option("--out", default=None, help="Output joblib path (default: cache_dir/calibrator_*).")
@click.option("--save-rows", default=None, help="Optional CSV of training rows.")
def calibrate(symbol, horizon, train_start, train_end, method, top_n, stride, out, save_rows):
    """Fit a probability calibrator on a TRAINING window walk-forward.

    Important: the test window for evaluation MUST be disjoint from [train-start, train-end].
    Run `astrotrader backtest --start <after-train-end> --use-calibrator auto` to evaluate.
    """
    click.echo(f"building context for {symbol}…")
    ctx = AstrotradeContext.build(symbol=symbol)

    fwd_col = f"fwd_logret_{horizon}"
    n_dates = (
        (ctx.state_matrix.dates >= pd.Timestamp(train_start))
        & (ctx.state_matrix.dates <= pd.Timestamp(train_end))
        & (ctx.forward[fwd_col].reindex(ctx.state_matrix.dates).notna())
    ).sum()
    n_dates = max(int(n_dates // max(stride, 1)), 1)

    click.echo(f"running walk-forward over training window {train_start} → {train_end}…")
    with click.progressbar(length=n_dates, label="train walk-forward") as bar:
        rows = walk_forward(
            ctx,
            horizon=horizon,
            start=train_start,
            end=train_end,
            top_n=top_n,
            stride=stride,
            progress_callback=lambda done, total: bar.update(1),
        )

    if rows.empty:
        raise click.ClickException("no training rows produced.")

    p_raw = rows["p_up_raw"].to_numpy()
    actual = rows["actual_up"].to_numpy()

    if method == "isotonic":
        cal = IsotonicCalibrator.fit(p_raw, actual, horizon=horizon, symbol=symbol)
    else:
        cal = PlattCalibrator.fit(p_raw, actual, horizon=horizon, symbol=symbol)

    out_path = Path(out) if out else default_path(symbol, horizon, method)
    save_calibrator(cal, out_path)

    # In-sample diagnostics — confirm the fit moved metrics in the right direction.
    # (Real evaluation must be on the disjoint test window.)
    from .backtest.metrics import brier_score, expected_calibration_error, log_loss
    p_cal = cal.transform(p_raw)
    click.echo(f"\nfit complete. method={method} symbol={symbol} horizon={horizon} N={cal.n_train}")
    click.echo(
        "in-sample (training-window) metrics — for sanity only, not an evaluation:\n"
        f"  Brier raw → cal:    {brier_score(p_raw, actual):.4f} → {brier_score(p_cal, actual):.4f}\n"
        f"  Log loss raw → cal: {log_loss(p_raw, actual):.4f} → {log_loss(p_cal, actual):.4f}\n"
        f"  ECE raw → cal:      {expected_calibration_error(p_raw, actual):.4f} → "
        f"{expected_calibration_error(p_cal, actual):.4f}"
    )
    click.echo(f"saved: {out_path}")
    click.echo(
        "\nNEXT: evaluate out-of-sample with\n"
        f"  astrotrader backtest --symbol {symbol} --horizon {horizon} "
        f"--start {pd.Timestamp(train_end) + pd.Timedelta(days=1):%Y-%m-%d} "
        f"--use-calibrator auto"
    )

    if save_rows:
        rows.to_csv(save_rows, index=False)
        click.echo(f"saved training rows to {save_rows}")


@main.command()
@click.option("--symbol", default="SPY")
@click.option("--horizon", type=int, default=5)
@click.option("--train-start", default="2010-01-01")
@click.option("--train-end", default="2018-12-31")
@click.option("--test-start", default="2019-01-01")
@click.option("--test-end", default=None)
@click.option("--top-n", type=int, default=50)
@click.option("--stride", type=int, default=1, help="Evaluate every k-th day (speed knob).")
@click.option("--method", type=click.Choice(["isotonic", "platt"]), default="platt")
@click.option(
    "--configs",
    default=None,
    help="Comma-separated subset of ablation names. Default: full set.",
)
@click.option("--save-csv", default=None)
def ablate(
    symbol,
    horizon,
    train_start,
    train_end,
    test_start,
    test_end,
    top_n,
    stride,
    method,
    configs,
    save_csv,
) -> None:
    """Feature-group ablation study.

    Per ablation: rebuild similarity engine with that weighting, fit a fresh
    calibrator on the training window, evaluate honestly on the test window.
    Compare Brier deltas vs the 'full' baseline to see which groups carry signal.
    """
    click.echo(f"building context for {symbol}…")
    ctx = AstrotradeContext.build(symbol=symbol)

    selected = STANDARD_ABLATIONS
    if configs:
        wanted = {c.strip() for c in configs.split(",")}
        selected = [c for c in STANDARD_ABLATIONS if c.name in wanted]
        if not selected:
            raise click.ClickException(
                f"no ablations matched {wanted!r}. Available: "
                f"{[c.name for c in STANDARD_ABLATIONS]}"
            )

    state = {"current": None}

    def cb(name, phase, done, total):
        if state["current"] != (name, phase):
            click.echo(f"  [{name}] {phase}: 0/{total}")
            state["current"] = (name, phase)
        # Print only at 25/50/75/100% to avoid flooding the terminal.
        if total > 0 and done in {total // 4, total // 2, (3 * total) // 4, total}:
            click.echo(f"  [{name}] {phase}: {done}/{total}")

    click.echo(
        f"running {len(selected)} ablations: "
        f"{[c.name for c in selected]}\n"
        f"train: {train_start}→{train_end}  test: {test_start}→{test_end or 'latest'}  "
        f"horizon={horizon}  stride={stride}  method={method}"
    )

    df = run_ablation(
        ctx,
        train_start=train_start,
        train_end=train_end,
        test_start=test_start,
        test_end=test_end,
        horizon=horizon,
        top_n=top_n,
        stride=stride,
        method=method,
        configs=selected,
        progress_callback=cb,
    )

    print_comparison(df)

    if save_csv:
        df.to_csv(save_csv, index=False)
        click.echo(f"\nsaved comparison to {save_csv}")


if __name__ == "__main__":
    main()
