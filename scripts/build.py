#!/usr/bin/env python3
"""Global Liquidity & Stress Radar — costruzione dati.

Scarica le serie ufficiali (FRED / Fed St. Louis, che ripubblica Fed, BCE, BoJ,
Chicago Fed, ICE, CBOE), calcola l'indice GLSI settimanale, gli episodi di
stress, gli alert e scrive i JSON letti dalla pagina.

Score = 100 × Φ(½·Liquidità − ½·Stress), scala 0–100.
Liquidità e Stress sono medie di z-score (finestra mobile 10 anni).

Uso: python scripts/build.py            (scarica dal web)
     GLSI_CACHE=dir python scripts/build.py   (legge CSV locali id.csv, per test)
"""
from __future__ import annotations

import io
import json
import math
import os
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CFG = ROOT / "config"
UA = {"User-Agent": "Mozilla/5.0 (GLSI radar; github.com/onlywave)"}

# ---------------------------------------------------------------- serie
SERIES = {
    # liquidità — livelli
    "WALCL": dict(name="Fed — attivo totale", unit="mln $", src="Federal Reserve H.4.1"),
    "WTREGEN": dict(name="Tesoro USA — conto TGA", unit="mld $", src="Federal Reserve H.4.1"),
    "RRPONTSYD": dict(name="Fed — reverse repo overnight", unit="mld $", src="NY Fed"),
    "WRESBAL": dict(name="Riserve bancarie USA", unit="mld $", src="Federal Reserve H.4.1"),
    "ECBASSETSW": dict(name="BCE — attivo totale", unit="mln €", src="BCE"),
    "JPNASSETS": dict(name="BoJ — attivo totale", unit="100 mln ¥", src="Bank of Japan"),
    "M2SL": dict(name="M2 USA", unit="mld $", src="Federal Reserve H.6"),
    "DTWEXBGS": dict(name="Dollaro — indice ampio", unit="indice", src="Federal Reserve H.10"),
    "DEXUSEU": dict(name="Cambio USD per EUR", unit="$", src="Federal Reserve H.10"),
    "DEXJPUS": dict(name="Cambio JPY per USD", unit="¥", src="Federal Reserve H.10"),
    # stress
    "NFCI": dict(name="Chicago Fed NFCI", unit="indice (0 = media)", src="Chicago Fed"),
    "STLFSI4": dict(name="St. Louis Fed Financial Stress", unit="indice (0 = media)", src="St. Louis Fed"),
    "VIXCLS": dict(name="VIX", unit="punti", src="CBOE"),
    "BAMLH0A0HYM2": dict(name="Spread high yield USA (OAS)", unit="%", src="ICE BofA"),
    # mercato
    "SP500": dict(name="S&P 500 (FRED, 10 anni)", unit="punti", src="S&P Dow Jones Indices"),
}

BANDS = [(0, 20, "Drought", "Siccità"), (20, 40, "Tightening", "Stretta"),
         (40, 60, "Neutral", "Neutrale"), (60, 80, "Easing", "Allentamento"),
         (80, 100.01, "Flood", "Abbondanza")]

ZWIN, ZMIN = 520, 104          # finestra z-score: 10 anni, minimo 2 anni (settimane)
EP_THRESHOLD = 1.0             # soglia episodio di stress (z composito)


def fred_url(sid: str) -> str:
    return f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=1990-01-01"


def get(url: str, tries: int = 3, **kw) -> requests.Response:
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=45, **kw)
            if r.status_code == 200 and r.content:
                return r
            last = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = str(e)
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def parse_csv(text: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip() for c in df.columns]
    dcol = df.columns[0]
    vcol = df.columns[-1]
    s = pd.Series(pd.to_numeric(df[vcol], errors="coerce").values,
                  index=pd.to_datetime(df[dcol], errors="coerce"))
    return s[s.index.notna()].dropna().sort_index()


def load(sid: str) -> pd.Series:
    cache = os.environ.get("GLSI_CACHE")
    if cache:
        p = Path(cache) / f"{sid}.csv"
        return parse_csv(p.read_text()) if p.exists() else pd.Series(dtype=float)
    return parse_csv(get(fred_url(sid)).text)


def load_spx_long() -> tuple[pd.Series, str]:
    """S&P 500 settimanale ~25 anni: Yahoo, poi Stooq, poi FRED (10 anni)."""
    cache = os.environ.get("GLSI_CACHE")
    if cache:
        p = Path(cache) / "SPX_LONG.csv"
        if p.exists():
            return parse_csv(p.read_text()), "cache"
    try:
        r = get("https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=30y&interval=1wk")
        j = r.json()["chart"]["result"][0]
        ts = pd.to_datetime(j["timestamp"], unit="s")
        cl = j["indicators"]["quote"][0]["close"]
        s = pd.Series(cl, index=ts, dtype=float).dropna()
        if len(s) > 500:
            return s.sort_index(), "Yahoo Finance (^GSPC)"
    except Exception as e:  # noqa: BLE001
        print("Yahoo SPX non disponibile:", e, file=sys.stderr)
    try:
        s = parse_csv(get("https://stooq.com/q/d/l/?s=%5Espx&i=w").text)
        if len(s) > 500:
            return s, "Stooq (^SPX)"
    except Exception as e:  # noqa: BLE001
        print("Stooq SPX non disponibile:", e, file=sys.stderr)
    return pd.Series(dtype=float), ""


# ---------------------------------------------------------------- calcolo
def rz(s: pd.Series) -> pd.Series:
    m = s.rolling(ZWIN, min_periods=ZMIN).mean()
    sd = s.rolling(ZWIN, min_periods=ZMIN).std()
    return ((s - m) / sd).clip(-3, 3)


def phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def band(score: float):
    for lo, hi, en, it in BANDS:
        if lo <= score < hi:
            return en, it, lo, hi
    return BANDS[-1][2], BANDS[-1][3], 80, 100


def r1(x, nd=2):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), nd)


def build():
    raw, meta = {}, {}
    for sid in SERIES:
        try:
            s = load(sid)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] {sid}: {e}", file=sys.stderr)
            s = pd.Series(dtype=float)
        raw[sid] = s
        meta[sid] = dict(SERIES[sid], id=sid,
                         url=f"https://fred.stlouisfed.org/series/{sid}",
                         last_date=s.index[-1].strftime("%Y-%m-%d") if len(s) else None,
                         last_value=r1(s.iloc[-1], 3) if len(s) else None,
                         ok=bool(len(s)))
    if not meta["WALCL"]["ok"] or not meta["NFCI"]["ok"]:
        raise SystemExit("Serie essenziali mancanti (WALCL/NFCI): interrompo senza sovrascrivere i dati.")

    end = max(s.index[-1] for s in raw.values() if len(s))
    idx = pd.date_range("1996-01-03", end + pd.Timedelta(days=6), freq="W-WED")

    def wk(sid, limit=None):
        s = raw[sid]
        if not len(s):
            return pd.Series(np.nan, index=idx)
        s = s[~s.index.duplicated(keep="last")]
        u = s.reindex(s.index.union(idx)).ffill(limit=limit)
        return u.reindex(idx)

    walcl = wk("WALCL", 20) / 1000.0                     # mld $
    tga = wk("WTREGEN", 20)
    rrp = wk("RRPONTSYD", 30).fillna(0.0)
    eur = wk("DEXUSEU", 30)
    jpy = wk("DEXJPUS", 30)
    ecb = wk("ECBASSETSW", 20) / 1000.0 * eur            # mld $
    boj = wk("JPNASSETS", 400) * 0.1 / jpy               # mld $ (100 mln ¥ → mld ¥ /10)
    fed_net = walcl - tga - rrp
    gnl = fed_net + ecb.fillna(0) + boj.fillna(0)
    gnl[walcl.isna() | tga.isna()] = np.nan

    m2 = wk("M2SL", 400)
    dxy = wk("DTWEXBGS", 20)

    L = pd.DataFrame({
        "gnl_13w": rz(gnl.pct_change(13, fill_method=None) * 100),
        "gnl_52w": rz(gnl.pct_change(52, fill_method=None) * 100),
        "m2_52w": rz(m2.pct_change(52, fill_method=None) * 100),
        "usd_13w": -rz(dxy.pct_change(13, fill_method=None) * 100),
    })
    S = pd.DataFrame({
        "nfci": rz(wk("NFCI", 10)),
        "stlfsi": rz(wk("STLFSI4", 10)),
        "vix": rz(wk("VIXCLS", 10)),
        "hy": rz(wk("BAMLH0A0HYM2", 10)),
    })
    liq = L.mean(axis=1, skipna=True)
    liq[L.notna().sum(axis=1) < 2] = np.nan
    stress = S.mean(axis=1, skipna=True)
    stress[S.notna().sum(axis=1) < 2] = np.nan
    score = (0.5 * liq - 0.5 * stress).apply(lambda x: np.nan if pd.isna(x) else 100 * phi(x))

    spx_long, spx_src = load_spx_long()
    spx_fred = wk("SP500", 10)
    if len(spx_long):
        s = spx_long[~spx_long.index.duplicated(keep="last")]
        spx = s.reindex(s.index.union(idx)).ffill(limit=10).reindex(idx)
        spx = spx.fillna(spx_fred)
    else:
        spx, spx_src = spx_fred, "FRED SP500 (solo ultimi 10 anni)"

    df = pd.DataFrame({"score": score, "liq": liq, "stress": stress, "gnl": gnl,
                       "fed_net": fed_net, "ecb": ecb, "boj": boj, "spx": spx,
                       "nfci": wk("NFCI", 10), "stlfsi": wk("STLFSI4", 10),
                       "vix": wk("VIXCLS", 10), "hy": wk("BAMLH0A0HYM2", 10),
                       "dxy": dxy})
    last_i = df["score"].last_valid_index()
    df = df.loc[:last_i]
    return df, L.loc[:last_i], S.loc[:last_i], meta, spx_src


# ---------------------------------------------------------------- episodi
def episodes(df: pd.DataFrame, events: dict) -> list[dict]:
    """Episodi = finestre del catalogo + episodi trovati nei dati (stress z > soglia)
    che non ricadono in nessuna finestra. Livelli e date sempre calcolati dai dati."""
    st = df["stress"]
    hot = st > EP_THRESHOLD
    runs, start, prev = [], None, None
    for d, h in hot.items():
        if h and start is None:
            start = d
        if h:
            prev = d
        if not h and start is not None and prev is not None and (d - prev).days > 56:
            runs.append((start, prev)); start = None
    if start is not None:
        runs.append((start, prev))
    since = pd.Timestamp("2006-01-01")
    runs = [(a, b) for a, b in runs if (b - a).days >= 7 and b >= since]

    names = events.get("episodes", [])
    wins = [(pd.Timestamp(e["from"]), min(pd.Timestamp(e["to"]), df.index[-1]), e["name"], True)
            for e in names if pd.Timestamp(e["from"]) <= df.index[-1]]
    for a, b in runs:
        if not any(wa <= b and wb >= a for wa, wb, _, _ in wins):
            wins.append((a, b, "Episodio non catalogato", False))
    wins.sort()

    inter = sorted(events.get("interventions", []), key=lambda x: x["date"])
    spx = df["spx"]
    out = []
    for a, b, nm, cat in wins:
        seg = df.loc[a:b]
        if seg["stress"].notna().sum() == 0:
            continue
        pk = seg["stress"].idxmax()
        pre_hi = spx.loc[a - pd.Timedelta(weeks=26):b].max()
        sw = spx.loc[a:b + pd.Timedelta(weeks=8)].dropna()
        trough_d = sw.idxmin() if len(sw) else None
        dd = (sw.min() / pre_hi - 1) * 100 if len(sw) and pre_hi else np.nan

        def fwd(weeks):
            t = pk + pd.Timedelta(weeks=weeks)
            if t > df.index[-1]:
                return None
            v0, v1 = spx.get(pk), spx.asof(t)
            return r1((v1 / v0 - 1) * 100, 1) if v0 and v1 and not pd.isna(v0) and not pd.isna(v1) else None

        win_a, win_b = a - pd.Timedelta(weeks=3), b + pd.Timedelta(weeks=8)
        ivs = [i for i in inter if win_a <= pd.Timestamp(i["date"]) <= win_b]
        hot_w = int((seg["stress"] > EP_THRESHOLD).sum())
        out.append(dict(
            name=nm, catalogued=cat,
            start=a.strftime("%Y-%m-%d"), end=b.strftime("%Y-%m-%d"),
            peak=pk.strftime("%Y-%m-%d"), hot_weeks=hot_w,
            stress_z=r1(seg.loc[pk, "stress"]), score_min=r1(seg["score"].min(), 1),
            stlfsi=r1(seg["stlfsi"].max()), nfci=r1(seg["nfci"].max()),
            vix=r1(seg["vix"].max(), 1), hy=r1(seg["hy"].max()),
            spx_peak=r1(spx.get(pk), 0), spx_dd=r1(dd, 1),
            spx_trough_date=trough_d.strftime("%Y-%m-%d") if trough_d is not None else None,
            fwd_3m=fwd(13), fwd_6m=fwd(26), fwd_12m=fwd(52),
            interventions=ivs,
            first_response_days=((pd.Timestamp(ivs[0]["date"]) - a).days if ivs else None),
            ongoing=bool(b >= df.index[-2]),
        ))
    return out


# ---------------------------------------------------------------- alert
def make_alerts(df: pd.DataFrame, gnl_chg4: float) -> list[dict]:
    a = []
    s = df["score"].dropna()
    cur, prev = s.iloc[-1], s.iloc[-2]
    d = s.index[-1].strftime("%Y-%m-%d")
    ben, bit, lo, hi = band(cur)
    pen, pit, *_ = band(prev)
    if ben != pen:
        up = cur > prev
        a.append(dict(level="alta", code="REGIME", date=d,
                      text=f"Cambio di regime: {pit} → {bit} (score {prev:.1f} → {cur:.1f})",
                      dir="up" if up else "down"))
    for th in (20, 40, 60, 80):
        if abs(cur - th) < 2 and band(cur)[0] == ben and not (abs(prev - th) < 2):
            a.append(dict(level="media", code="SOGLIA", date=d,
                          text=f"Score {cur:.1f} a meno di 2 punti dalla soglia {th}"))
    if len(s) > 4 and abs(cur - s.iloc[-5]) >= 10:
        a.append(dict(level="media", code="MOMENTUM", date=d,
                      text=f"Score {'+' if cur > s.iloc[-5] else ''}{cur - s.iloc[-5]:.1f} punti in 4 settimane"))
    vix = df["vix"].dropna()
    if len(vix) and vix.iloc[-1] >= 30 and vix.iloc[-2] < 30:
        a.append(dict(level="alta", code="VIX", date=d, text=f"VIX sopra 30 ({vix.iloc[-1]:.1f})"))
    nf = df["nfci"].dropna()
    if len(nf) and nf.iloc[-1] > 0 and nf.iloc[-2] <= 0:
        a.append(dict(level="alta", code="NFCI", date=d,
                      text=f"NFCI sopra zero ({nf.iloc[-1]:.2f}): condizioni più strette della media storica"))
    stz = df["stress"].dropna()
    if len(stz) and stz.iloc[-1] > EP_THRESHOLD and stz.iloc[-2] <= EP_THRESHOLD:
        a.append(dict(level="alta", code="EPISODIO", date=d,
                      text=f"Inizio episodio di stress (z composito {stz.iloc[-1]:.2f} > {EP_THRESHOLD})"))
    if gnl_chg4 is not None and gnl_chg4 <= -2:
        a.append(dict(level="media", code="DRENAGGIO", date=d,
                      text=f"Liquidità netta globale {gnl_chg4:.1f}% in 4 settimane"))
    return a


def notify(new: list[dict], latest: dict):
    if not new:
        return
    site = os.environ.get("SITE_URL", "https://onlywave.github.io/global-liquidity-radar/")
    title = f"GLSI {latest['score']:.1f} ({latest['regime_it']}) — " + "; ".join(x["code"] for x in new)
    body = "\n".join(f"- [{x['level']}] {x['text']}" for x in new)
    body += f"\n\nScore {latest['score']:.1f} · Liquidità z {latest['liq']:+.2f} · Stress z {latest['stress']:+.2f}\nDati al {latest['date']}\n{site}"
    tok, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if tok and repo:
        try:
            requests.post(f"https://api.github.com/repos/{repo}/issues", timeout=30,
                          headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"},
                          json={"title": title, "body": body, "labels": ["alert"]})
        except Exception as e:  # noqa: BLE001
            print("issue:", e, file=sys.stderr)
    tb, tc = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if tb and tc:
        try:
            requests.post(f"https://api.telegram.org/bot{tb}/sendMessage", timeout=30,
                          json={"chat_id": tc, "text": f"{title}\n\n{body}"})
        except Exception as e:  # noqa: BLE001
            print("telegram:", e, file=sys.stderr)
    su, sp, to = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS"), os.environ.get("ALERT_EMAIL_TO")
    if su and sp and to:
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"], msg["From"], msg["To"] = title, su, to
            with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.gmail.com"), 465, timeout=30) as s:
                s.login(su, sp); s.send_message(msg)
        except Exception as e:  # noqa: BLE001
            print("email:", e, file=sys.stderr)


# ---------------------------------------------------------------- main
def main():
    DATA.mkdir(exist_ok=True)
    events = json.loads((CFG / "events.json").read_text())
    df, L, S, meta, spx_src = build()

    last = df["score"].last_valid_index()
    cur = df.loc[last]
    ben, bit, lo, hi = band(cur["score"])
    g = df["gnl"].dropna()

    def chg(s, n):
        s = s.dropna()
        return r1((s.iloc[-1] / s.iloc[-1 - n] - 1) * 100, 2) if len(s) > n else None

    comp_names = {"gnl_13w": "Liquidità netta globale, var. 13 sett.",
                  "gnl_52w": "Liquidità netta globale, var. 52 sett.",
                  "m2_52w": "M2 USA, var. annua", "usd_13w": "Dollaro (invertito), var. 13 sett.",
                  "nfci": "Chicago Fed NFCI", "stlfsi": "St. Louis Fed FSI",
                  "vix": "VIX", "hy": "Spread high yield"}
    latest = dict(
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        date=last.strftime("%Y-%m-%d"),
        score=r1(cur["score"], 1), liq=r1(cur["liq"]), stress=r1(cur["stress"]),
        regime=ben, regime_it=bit, band_lo=lo, band_hi=min(hi, 100),
        to_up=r1(min(hi, 100) - cur["score"], 1) if hi <= 100 else None,
        to_down=r1(cur["score"] - lo, 1),
        to_neutral=r1(40 - cur["score"], 1) if cur["score"] < 40 else (r1(cur["score"] - 60, 1) if cur["score"] > 60 else 0),
        chg_1w=r1(cur["score"] - df["score"].dropna().iloc[-2], 1),
        chg_4w=r1(cur["score"] - df["score"].dropna().iloc[-5], 1),
        chg_13w=r1(cur["score"] - df["score"].dropna().iloc[-14], 1),
        percentile=r1((df["score"].dropna() <= cur["score"]).mean() * 100, 0),
        gnl=r1(g.iloc[-1], 0), gnl_4w=chg(g, 4), gnl_13w=chg(g, 13), gnl_52w=chg(g, 52),
        fed_net=r1(cur["fed_net"], 0), ecb=r1(cur["ecb"], 0), boj=r1(cur["boj"], 0),
        components=[dict(key=k, name=comp_names[k], group="Liquidità", z=r1(L[k].loc[last]))
                    for k in L.columns] +
                   [dict(key=k, name=comp_names[k], group="Stress", z=r1(S[k].loc[last]))
                    for k in S.columns],
        series=list(meta.values()), spx_source=spx_src,
        method="Score = 100 × Φ(½·Liquidità − ½·Stress); z-score su finestra mobile di 10 anni, limitati a ±3.",
    )

    hist = df.loc["2003-01-01":]
    history = dict(
        dates=[d.strftime("%Y-%m-%d") for d in hist.index],
        **{k: [r1(v, 2 if k in ("liq", "stress", "nfci", "stlfsi", "hy") else 1) for v in hist[k]]
           for k in ("score", "liq", "stress", "spx", "gnl", "vix", "nfci", "stlfsi", "hy")}
    )

    eps = episodes(df, events)
    # transizioni di regime storiche (per il log)
    sc = df["score"].dropna()
    regs, prevb = [], None
    for d, v in sc.items():
        b = band(v)[1]
        if prevb and b != prevb:
            regs.append(dict(date=d.strftime("%Y-%m-%d"), frm=prevb, to=b, score=r1(v, 1)))
        prevb = b

    # alert operativi con log persistente
    ap = DATA / "alerts.json"
    log = json.loads(ap.read_text()) if ap.exists() else {"log": []}
    new = make_alerts(df, latest["gnl_4w"])
    seen = {(x["date"], x["code"]) for x in log["log"]}
    fresh = [x for x in new if (x["date"], x["code"]) not in seen]
    log["log"] = (fresh + log["log"])[:500]
    log["active"] = new
    log["regime_changes"] = regs[-200:][::-1]

    (DATA / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=1))
    (DATA / "history.json").write_text(json.dumps(history, ensure_ascii=False, separators=(",", ":")))
    (DATA / "episodes.json").write_text(json.dumps(dict(threshold=EP_THRESHOLD, episodes=eps[::-1],
                                                        interventions=events["interventions"]),
                                                   ensure_ascii=False, indent=1))
    ap.write_text(json.dumps(log, ensure_ascii=False, indent=1))
    if os.environ.get("GLSI_NOTIFY", "1") == "1":
        notify(fresh, latest)
    print(f"GLSI {latest['score']} {latest['regime_it']} al {latest['date']} · episodi {len(eps)} · nuovi alert {len(fresh)}")


if __name__ == "__main__":
    main()
