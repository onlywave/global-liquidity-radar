"""Commento automatico del giorno: breve (3–7 gg), medio (1 mese), lungo (12 mesi),
considerazioni pratiche con i precedenti storici più simili a oggi."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _r(x, nd=1):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), nd)


def _pct(a, b):
    return (a / b - 1) * 100 if a and b else np.nan


def _sgn(x, nd=1, suf=""):
    return "n.d." if x is None or pd.isna(x) else f"{x:+.{nd}f}{suf}".replace(".", ",")


def _f(x, nd=1):
    return "n.d." if x is None or pd.isna(x) else f"{x:.{nd}f}".replace(".", ",")


def daily_block(raw: dict) -> dict:
    """Variazioni sugli ultimi 5 giorni di borsa dai dati giornalieri."""
    out = {}
    for sid, key in (("VIXCLS", "vix"), ("BAMLH0A0HYM2", "hy"), ("SP500", "spx")):
        s = raw.get(sid, pd.Series(dtype=float)).dropna()
        if len(s) < 7:
            out[key] = None
            continue
        out[key] = dict(last=float(s.iloc[-1]), d5=float(s.iloc[-6]), date=s.index[-1].strftime("%Y-%m-%d"),
                        max20=float(s.tail(20).max()), min20=float(s.tail(20).min()))
    return out


def analogs(df: pd.DataFrame, events: dict, k: int = 5) -> list[dict]:
    """Settimane passate più simili a oggi per score, liquidità, stress e variazione dello score a 4 settimane."""
    X = pd.DataFrame({"score": df["score"] / 10, "liq": df["liq"], "stress": df["stress"],
                      "d4": (df["score"] - df["score"].shift(4)) / 10}).dropna()
    if len(X) < 200:
        return []
    now = X.iloc[-1]
    cand = X.loc[:X.index[-1] - pd.Timedelta(weeks=52)]
    d = np.sqrt(((cand - now) ** 2).sum(axis=1)).sort_values()
    spx = df["spx"]
    names = events.get("episodes", [])
    picked = []
    for t, dist in d.items():
        if any(abs((t - p).days) < 26 * 7 for p, _ in picked):
            continue
        picked.append((t, dist))
        if len(picked) == k:
            break
    res = []
    for t, dist in picked:
        v0 = spx.get(t)
        def fw(w):
            x = spx.asof(t + pd.Timedelta(weeks=w))
            return _r(_pct(x, v0))
        win = spx.loc[t:t + pd.Timedelta(weeks=13)].dropna()
        ep = next((e["name"] for e in names if pd.Timestamp(e["from"]) <= t <= pd.Timestamp(e["to"])), None)
        res.append(dict(date=t.strftime("%Y-%m-%d"), dist=_r(dist, 2), score=_r(df.loc[t, "score"]),
                        liq=_r(df.loc[t, "liq"], 2), stress=_r(df.loc[t, "stress"], 2), episode=ep,
                        r1m=fw(4), r3m=fw(13), r12m=fw(52),
                        mdd3m=_r(_pct(win.min(), v0)) if len(win) else None))
    return res


def conditional(df: pd.DataFrame, band: float = 5.0) -> dict:
    sc, spx = df["score"], df["spx"]
    cur = sc.dropna().iloc[-1]
    m = (sc - cur).abs() <= band
    m.iloc[-52:] = False
    out = {}
    for w, k in ((4, "1m"), (13, "3m"), (52, "12m")):
        f = ((spx.shift(-w) / spx - 1) * 100)[m].dropna()
        base = ((spx.shift(-w) / spx - 1) * 100)[sc.notna()].dropna()
        out[k] = dict(n=int(len(f)), mean=_r(f.mean()), pos=_r((f > 0).mean() * 100, 0),
                      base_mean=_r(base.mean()), base_pos=_r((base > 0).mean() * 100, 0))
    return out


def build_commentary(df: pd.DataFrame, latest: dict, sig: dict, raw: dict, events: dict, active_eps: list) -> dict:
    sc = df["score"].dropna()
    cur = sc.iloc[-1]
    st, lq = df["stress"].dropna(), df["liq"].dropna()
    dly = daily_block(raw)
    an = analogs(df, events)
    cond = conditional(df)

    # ---------- breve 3–7 giorni
    pts, press = [], 0
    if dly.get("vix"):
        v = dly["vix"]; ch = v["last"] - v["d5"]
        press += 1 if ch > 1.5 else (-1 if ch < -1.5 else 0)
        pts.append(f"VIX a {_f(v['last'])} ({_sgn(ch)} punti in 5 sedute; massimo a 20 sedute {_f(v['max20'])})")
    if dly.get("hy"):
        h = dly["hy"]; ch = (h["last"] - h["d5"]) * 100
        press += 1 if ch > 10 else (-1 if ch < -10 else 0)
        pts.append(f"spread high yield {_f(h['last'], 2)}% ({_sgn(ch, 0)} pb in 5 sedute)")
    if dly.get("spx"):
        s = dly["spx"]; ch = _pct(s["last"], s["d5"])
        press += 1 if ch < -2 else (-1 if ch > 2 else 0)
        pts.append(f"S&P 500 {_sgn(ch, 1, '%')} in 5 sedute")
    dst = st.iloc[-1] - st.iloc[-2] if len(st) > 1 else 0
    press += 1 if dst > 0.15 else (-1 if dst < -0.15 else 0)
    tone_b = "in aumento" if press >= 2 else ("in calo" if press <= -2 else "stabile o mista")
    breve = dict(
        title="Breve (3–7 giorni)",
        tone={"in aumento": "neg", "in calo": "pos"}.get(tone_b, "neu"),
        headline=f"Pressione di mercato {tone_b}",
        text=(("; ".join(pts) + ". " if pts else "") + f"Stress composito settimanale {_sgn(dst, 2)} sull'ultima settimana. "
              "Su questo orizzonte i dati di liquidità non hanno capacità previsiva: conta l'umore di mercato."
              + (" Lo stress è a un passo dalla soglia del segnale short: un nuovo rialzo di VIX o spread lo farebbe scattare."
                 if sig["short_state"] == "PRE-ALLERTA SHORT" and not sig["short_checks"][1]["ok"] else "")))

    # ---------- medio 1 mese
    d4 = cur - sc.iloc[-5]
    dl4 = lq.iloc[-1] - lq.iloc[-5]
    ds4 = st.iloc[-1] - st.iloc[-5]
    if d4 <= -8:
        hm = "Deterioramento in corso"; tm = "neg"
    elif d4 >= 8:
        hm = "Miglioramento in corso"; tm = "pos"
    else:
        hm = "Quadro senza una direzione netta"; tm = "neu"
    c1 = cond["1m"]
    medio = dict(
        title="Medio (1 mese)", tone=tm, headline=hm,
        text=(f"Score {_sgn(d4)} punti in 4 settimane (liquidità z {_sgn(dl4, 2)}, stress z {_sgn(ds4, 2)}). "
              f"Liquidità netta globale {_sgn(latest.get('gnl_4w'), 1, '%')} in 4 settimane e {_sgn(latest.get('gnl_13w'), 1, '%')} in 13. "
              f"Nelle settimane passate con uno score simile (±5 punti, {c1['n']} casi) l'S&P a 1 mese ha fatto in media "
              f"{_sgn(c1['mean'], 1, '%')} ({_f(c1['pos'], 0)}% positivi), contro {_sgn(c1['base_mean'], 1, '%')} di tutte le settimane."))

    # ---------- lungo 12 mesi
    c12 = cond["12m"]
    if sig["state"].startswith("LONG"):
        hl, tl = "Contesto storicamente favorevole", "pos"
    elif sig["short_state"] == "SHORT ATTIVO":
        hl, tl = "Rischio elevato, ma i 12 mesi restano incerti", "neg"
    elif c12["mean"] is not None and c12["mean"] > c12["base_mean"] + 3:
        hl, tl = "Storicamente sopra la media", "pos"
    elif c12["mean"] is not None and c12["mean"] < c12["base_mean"] - 3:
        hl, tl = "Storicamente sotto la media", "neg"
    else:
        hl, tl = "In linea con la media storica, con esiti molto dispersi", "neu"
    lungo = dict(
        title="Lungo (12 mesi)", tone=tl, headline=hl,
        text=(f"Con score intorno a {_f(cur)} ({c12['n']} settimane simili dal 2003) l'S&P a 12 mesi ha fatto in media "
              f"{_sgn(c12['mean'], 1, '%')} ({_f(c12['pos'], 0)}% positivi), contro {_sgn(c12['base_mean'], 1, '%')} di media generale. "
              "Lo score da solo, a questo livello, non dà un vantaggio sull'anno: decide come evolvono liquidità e stress. "
              "Se lo score scende sotto 20 e poi risale, storicamente l'anno successivo è stato molto buono; "
              "se la stretta si prolunga come nel 2008 o nel 2022, no."))

    # ---------- considerazioni pratiche
    pr = []
    if sig["short_state"] == "SHORT ATTIVO":
        pr.append("Segnale short attivo: storicamente conveniva ridurre l'esposizione o coprirsi, non necessariamente vendere allo scoperto.")
    elif sig["short_state"] == "PRE-ALLERTA SHORT":
        miss = [c["text"].lower() for c in sig["short_checks"] if not c["ok"]]
        pr.append(f"Pre-allerta short: manca solo «{miss[0]}». È il momento di decidere in anticipo le coperture, non di inseguire il mercato.")
    if sig["state"] == "ALLERTA LONG":
        pr.append("Score in siccità: storicamente zona da preparare una lista acquisti, ma comprando a rate e solo alla prima risalita dello score.")
    elif sig["state"].startswith("LONG"):
        pr.append(f"{sig['state'].capitalize()}: nei casi passati l'S&P a 12 mesi è stato sempre positivo; il rischio principale è un falso inizio.")
    elif cur < 40:
        pr.append("Nessun segnale long: i rimbalzi in fase di stretta, senza miglioramento della liquidità, sono stati spesso fragili.")
    if an:
        r12 = [a["r12m"] for a in an if a["r12m"] is not None]
        m3 = [a["mdd3m"] for a in an if a["mdd3m"] is not None]
        lst = ", ".join(f"{a['date'][:7]}{' (' + a['episode'] + ')' if a['episode'] else ''}" for a in an[:3])
        pr.append(f"I precedenti più simili a oggi sono {lst}. In questi {len(an)} casi l'S&P a 12 mesi ha fatto in media "
                  f"{_sgn(np.mean(r12) if r12 else None, 1, '%')}, ma con un calo massimo medio di {_sgn(np.mean(m3) if m3 else None, 1, '%')} nei 3 mesi successivi.")
    if active_eps:
        e = active_eps[0]
        pr.append(f"Episodio di stress in corso: «{e['name']}», drawdown S&P finora {_sgn(e.get('spx_dd'), 1, '%')}; "
                  "per questo episodio non c'è ancora un intervento di banca centrale in catalogo; negli episodi passati la svolta è arrivata quasi sempre dopo un intervento.")
    pratico = dict(title="Considerazioni pratiche", tone="neu", headline="Cosa suggerisce lo storico", text=" ".join(pr))

    return dict(date=latest["date"], generated=latest["generated"], kind="auto",
                blocks=[breve, medio, lungo, pratico], analogs=an, conditional=cond,
                note="Commento generato automaticamente dai dati a ogni aggiornamento. Non è consulenza finanziaria.")
