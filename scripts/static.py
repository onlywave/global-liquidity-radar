"""Parti statiche del cruscotto: riquadro segnale nell'HTML e grafici PNG.
Così la pagina mostra segnale e grafici anche se il JavaScript non parte."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BG, FG, MUT = "#03050c", "#e9eefb", "#8792ad"
BANDS = [(0, 20, "#b06cff"), (20, 40, "#cdb6ff"), (40, 60, "#4b5368"), (60, 80, "#0b6fd6"), (80, 100, "#18b6f0")]


def verdict(sig: dict) -> dict:
    s_long, s_short = sig["state"], sig["short_state"]
    if s_short == "SHORT ATTIVO":
        v, why = "SHORT", "Liquidità in calo, stress elevato e S&P 500 sotto la media a 40 settimane."
    elif s_long.startswith("LONG"):
        v, why = "LONG", f"{s_long.capitalize()} dal {sig['since']}: il GLSI sta uscendo da una fase di siccità."
    else:
        v = "NEUTRO"
        notes = []
        if s_short == "PRE-ALLERTA SHORT":
            n = sum(c["ok"] for c in sig["short_checks"])
            miss = [c["text"] for c in sig["short_checks"] if not c["ok"]]
            notes.append(f"pre-allerta short ({n}/3 condizioni; manca: {', '.join(miss).lower()})")
        if s_long == "ALLERTA LONG":
            notes.append("allerta long: score in siccità, in attesa della risalita")
        why = "Nessun segnale attivo" + (" — " + "; ".join(notes) if notes else ".")
    return dict(v=v, why=why)


def banner_html(sig: dict, latest: dict) -> str:
    vd = verdict(sig)
    return (f'<div class="verdict v-{vd["v"].lower()}" id="verdict">'
            f'<span class="vlab">SEGNALE S&amp;P 500</span>'
            f'<b id="v-main">{vd["v"]}</b>'
            f'<span id="v-why">{html.escape(vd["why"])}</span>'
            f'<span class="vmeta" id="v-meta">GLSI {latest["score"]:.1f} · {html.escape(latest["regime_it"])} · '
            f'dati al {latest["date"]}</span></div>')


def inject(index: Path, block: str):
    t = index.read_text()
    new = re.sub(r"<!--VERDICT-->.*?<!--/VERDICT-->", "<!--VERDICT-->" + block + "<!--/VERDICT-->", t, flags=re.S)
    if new != t:
        index.write_text(new)


def _ax(ax):
    ax.set_facecolor(BG)
    for s in ax.spines.values():
        s.set_color("#1a2547")
    ax.tick_params(colors=MUT, labelsize=9)
    ax.grid(color="#121b33", lw=0.6)


def charts(hist: dict, eps: dict, sig: dict):
    df = pd.DataFrame({k: hist[k] for k in ("score", "spx", "stress")}, index=pd.to_datetime(hist["dates"])).astype(float)
    df = df.loc[df.index >= df.index[-1] - pd.DateOffset(years=20)]
    # storico GLSI
    fig, ax = plt.subplots(figsize=(12, 3.6), dpi=110, facecolor=BG)
    _ax(ax)
    for lo, hi, c in BANDS:
        ax.axhspan(lo, hi, color=c, alpha=0.10, lw=0)
    sc = df["score"]
    for lo, hi, c in BANDS:
        ax.plot(sc.where((sc >= lo) & (sc < hi + 0.5)), color=c, lw=1.4)
    ax.set_ylim(0, 100)
    ax.set_xlim(df.index[0], df.index[-1])
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.tight_layout()
    fig.savefig(DATA / "hist.png", facecolor=BG)
    plt.close(fig)
    # S&P con episodi, segnali
    fig, ax = plt.subplots(figsize=(12, 5), dpi=110, facecolor=BG)
    _ax(ax)
    for e in eps["episodes"]:
        z = e.get("stress_z") or 0
        ax.axvspan(pd.Timestamp(e["start"]), pd.Timestamp(e["end"]), color="#ff5d73",
                   alpha=max(0.06, min(0.4, 0.06 + 0.12 * z)), lw=0)
    ax.plot(df["spx"], color="#18b6f0", lw=1.4)
    ax.set_yscale("log")
    for h in sig["history"]:
        d = pd.Timestamp(h["date"])
        if d < df.index[0] or h["spx"] is None:
            continue
        if h["tier"] == "CONFERMATO":
            ax.scatter(d, h["spx"], s=70, color="#38d39f", edgecolor="white", zorder=5)
        elif h["tier"] == "ANTICIPATO":
            ax.scatter(d, h["spx"], s=45, facecolor="none", edgecolor="#38d39f", lw=2, zorder=5)
        elif h["tier"] == "SHORT":
            ax.scatter(d, h["spx"], s=80, marker="x", color="#ff5d73", lw=2.5, zorder=5)
    for iv in eps.get("interventions", []):
        d = pd.Timestamp(iv["date"])
        if d >= df.index[0]:
            v = df["spx"].asof(d)
            ax.scatter(d, v * 0.93, s=22, marker="^", color="#ffb547", zorder=4)
    ax2 = ax.twinx()
    ax2.plot(df["stress"], color="#b06cff", lw=0.9, alpha=0.7)
    ax2.set_ylim(-2, 3.2)
    ax2.tick_params(colors=MUT, labelsize=9)
    ax.set_xlim(df.index[0], df.index[-1])
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", "'")))
    fig.tight_layout()
    fig.savefig(DATA / "spx.png", facecolor=BG)
    plt.close(fig)


def main():
    latest = json.loads((DATA / "latest.json").read_text())
    sig = json.loads((DATA / "signal.json").read_text())
    hist = json.loads((DATA / "history.json").read_text())
    eps = json.loads((DATA / "episodes.json").read_text())
    inject(ROOT / "index.html", banner_html(sig, latest))
    charts(hist, eps, sig)
    print("statico:", verdict(sig)["v"])


if __name__ == "__main__":
    main()
