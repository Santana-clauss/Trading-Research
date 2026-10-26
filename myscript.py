"""
XAU candidate-zone research harness (Python port of the Pine indicator + research confirmations).

Run locally:  pip install yfinance pandas numpy  &&  python xau_zone_research.py
Data limits (Yahoo): 15m = last ~60 days, 60m = last ~730 days.
  - GC=F (COMEX gold futures) has real volume but trades ~23h/day with a daily break.
  - XAUUSD=X (spot proxy) has NO volume -> volume filters are automatically skipped.
Nothing here is financial advice; it measures whether each rule adds expectancy out-of-sample.

Research basis for the added confirmations
  Osler (2003, J. Finance; NY Fed SR125/SR150): take-profit orders cluster AT round numbers,
  stop-loss orders cluster just BEYOND them. => (a) zone edges near round numbers get more
  reversal interest; (b) a wick through a round number that closes back = stop-run absorbed.
  Cont/Kukanov/Stoikov (2014): order-flow imbalance, not raw volume, drives price changes, and
  OFI needs book data. OHLCV can only give a weak proxy (relative volume, close-location).
"""
import sys
import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None

# ----------------------------- parameters (mirror Pine defaults) -----------------------------
P = dict(
    left=3, right=3, ema_len=50, bias_life=48, search_bars=10, full_candle=True,
    require_departure=True, departure_atr=1.0, zone_life=96, max_zones=12,
    first_only=True, confirm_bars=3, atr_len=14, stop_atr=0.1, stop_ticks=1,
    target_r=1.5, min_r=1.0, tick=0.1, horizon=96,
)


# ----------------------------- data -----------------------------
def load(symbol="GC=F", interval="15m", period="60d"):
    if yf is None:
        sys.exit("pip install yfinance")
    df = yf.download(symbol, interval=interval, period=period, auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()
    df.index = pd.to_datetime(df.index, utc=True)
    return df


# ----------------------------- structure (port of f_structure) -----------------------------
def structure(df, l, r):
    h, lo, c = df["high"].values, df["low"].values, df["close"].values
    n = len(df)
    direction = np.zeros(n, int); event = np.zeros(n, int)
    sh_a = np.full(n, np.nan); sl_a = np.full(n, np.nan)
    contraction = np.zeros(n, bool); age = np.full(n, 100000)
    sh = sl = psh = psl = np.nan
    hi_used = lo_used = False
    d = 0; last_break = None
    for i in range(n):
        up = (not np.isnan(sh)) and (not hi_used) and c[i] > sh
        dn = (not np.isnan(sl)) and (not lo_used) and c[i] < sl
        ev = 0
        if up and not dn:
            ev = 2 if d == -1 else 1; d = 1; hi_used = True; last_break = i
        if dn and not up:
            ev = -2 if d == 1 else -1; d = -1; lo_used = True; last_break = i
        if i >= l + r:  # pivot at i-r confirmed now (strict max/min like ta.pivothigh)
            w_h = h[i - l - r:i + 1]; w_l = lo[i - l - r:i + 1]
            if h[i - r] == w_h.max() and (w_h == h[i - r]).sum() == 1:
                psh, sh, hi_used = sh, h[i - r], False
            if lo[i - r] == w_l.min() and (w_l == lo[i - r]).sum() == 1:
                psl, sl, lo_used = sl, lo[i - r], False
        direction[i] = d; event[i] = ev; sh_a[i] = sh; sl_a[i] = sl
        contraction[i] = (not np.isnan(psh)) and (not np.isnan(psl)) and sh <= psh and sl >= psl
        age[i] = 100000 if last_break is None else i - last_break
    return pd.DataFrame(dict(dir=direction, ev=event, sh=sh_a, sl=sl_a, rng=contraction, age=age), index=df.index)


def htf_bias(df15, htf="60min"):
    """Completed-HTF bias, available only from the NEXT HTF bar open (no look-ahead)."""
    o = df15.resample(htf, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    s = structure(o, P["left"], P["right"])
    ema = o["close"].ewm(span=P["ema_len"], adjust=False).mean()
    bias = np.where((s.age > P["bias_life"]) | s.rng | s.sh.isna() | s.sl.isna(), 0, s.dir)
    bias = np.where((bias == 1) & (o["close"] <= ema), 0, bias)
    bias = np.where((bias == -1) & (o["close"] >= ema), 0, bias)
    b = pd.Series(bias, index=o.index).shift(1)            # value known from next HTF bar on
    return b.reindex(df15.index, method="ffill").fillna(0).astype(int)


# ----------------------------- research confirmations -----------------------------
def nearest_round(x, step):
    return np.round(x / step) * step

def near_round(price, step, tol):
    return abs(price - nearest_round(price, step)) <= tol

def swept_round(row, direction, step):
    """Osler stop-run: wick pierces a round number against the trade, bar closes back through it."""
    if direction == 1:   # long: dipped below a round level, closed above it
        lvl = nearest_round(row.low, step)
        return row.low < lvl <= row.close and lvl <= row.high
    lvl = nearest_round(row.high, step)
    return row.high > lvl >= row.close and lvl >= row.low


# ----------------------------- signal generation (port of the Pine entry loop) -----------------------------
def generate(df, cfg):
    s = structure(df, P["left"], P["right"])
    htf = htf_bias(df)
    tr = pd.concat([df.high - df.low, (df.high - df.close.shift()).abs(), (df.low - df.close.shift()).abs()], axis=1).max(axis=1)
    atr_prior = tr.ewm(alpha=1 / P["atr_len"], adjust=False).mean().shift(1)   # RMA(prior)
    vol_prior = df.volume.rolling(20).mean().shift(1)
    has_vol = df.volume.sum() > 0
    O, H, L, C = (df[k].values for k in ("open", "high", "low", "close"))
    idx = df.index
    zones, sigs = [], []
    for i in range(30, len(df)):
        a = atr_prior.iloc[i]
        if not a or np.isnan(a):
            continue
        took = False
        for z in reversed(zones):
            if not z["active"]:
                continue
            broken = C[i] < z["bot"] if z["d"] == 1 else C[i] > z["top"]
            if broken or i - z["born"] > P["zone_life"]:
                z["active"] = False
                continue
            overlap = i > z["born"] and H[i] >= z["bot"] and L[i] <= z["top"]
            new_visit = overlap and not z["inside"]
            if new_visit:
                z["touches"] += 1; z["touch_bar"] = i
            z["inside"] = overlap
            if took or z["touches"] == 0 or (P["first_only"] and z["touches"] != 1):
                continue
            d = z["d"]
            if not (htf.iloc[i] == d and s.dir.iloc[i] == d and not s.rng.iloc[i]):
                continue
            directional = C[i] > O[i] if d == 1 else C[i] < O[i]
            after = z["touch_bar"] is not None and 0 < i - z["touch_bar"] <= P["confirm_bars"]
            a_cand = cfg["A"] and new_visit and not z["sA"]
            b_cand = cfg["B"] and after and directional and not z["sB"]
            if not (a_cand or b_cand):
                continue
            # ---- research confirmations (all optional) ----
            near_edge = z["top"] if d == 1 else z["bot"]
            if cfg["round_zone"] and not (near_round(near_edge, cfg["round_step"], cfg["round_tol"]) or
                                          near_round(z["top"], cfg["round_step"], cfg["round_tol"]) or
                                          near_round(z["bot"], cfg["round_step"], cfg["round_tol"])):
                continue
            row = df.iloc[i]
            if cfg["sweep"] and not swept_round(row, d, cfg["round_step"]):
                continue
            if cfg["rel_vol"] and has_vol and not (vol_prior.iloc[i] > 0 and df.volume.iloc[i] / vol_prior.iloc[i] >= cfg["rel_vol"]):
                continue
            if cfg["close_loc"]:   # closes in the favourable 1/3 of its range (cheap OFI proxy)
                rg = H[i] - L[i]
                loc = (C[i] - L[i]) / rg if rg > 0 else 0.5
                if (d == 1 and loc < 0.67) or (d == -1 and loc > 0.33):
                    continue
            # ---- levels ----
            buf = max(a * P["stop_atr"], P["tick"] * P["stop_ticks"])
            entry = C[i]
            stop = np.floor((z["bot"] - buf) / P["tick"]) * P["tick"] if d == 1 else np.ceil((z["top"] + buf) / P["tick"]) * P["tick"]
            risk = (entry - stop) * d
            if risk < P["tick"] or (d == 1 and L[i] <= stop) or (d == -1 and H[i] >= stop):
                continue
            tgt = entry + d * risk * P["target_r"]
            if (tgt - entry) * d / risk < P["min_r"]:
                continue
            z["sB" if b_cand else "sA"] = True
            took = True
            sigs.append(dict(i=i, t=idx[i], d=d, entry=entry, stop=stop, tgt=tgt, risk=risk,
                             model="B" if b_cand else "A"))
        # ---- new zone ----
        ev = s.ev.iloc[i]
        if ev != 0 and (abs(C[i] - O[i]) >= P["departure_atr"] * a) and ((C[i] > O[i]) == (ev > 0)):
            d = 1 if ev > 0 else -1
            f = next((o for o in range(1, P["search_bars"] + 1) if (C[i - o] < O[i - o] if d == 1 else C[i - o] > O[i - o])), None)
            if f:
                top = H[i - f] if P["full_candle"] else max(O[i - f], C[i - f])
                bot = L[i - f] if P["full_candle"] else min(O[i - f], C[i - f])
                if top > bot and ((C[i] > top) if d == 1 else (C[i] < bot)):
                    zones.append(dict(top=top, bot=bot, d=d, born=i, active=True, touches=0, touch_bar=None,
                                      inside=False, sA=False, sB=False))
                    zones = zones[-P["max_zones"]:]
    return pd.DataFrame(sigs), atr_prior, htf, s


# ----------------------------- outcome evaluation (conservative: stop first on ambiguous bars) -----------------------------
def evaluate(df, sigs, tgt_r=None, horizon=None):
    horizon = horizon or P["horizon"]
    H, L, C = df.high.values, df.low.values, df.close.values
    out = []
    for r in sigs.itertuples():
        res, exit_i = None, None
        for j in range(r.i + 1, min(r.i + 1 + horizon, len(df))):
            hit_stop = L[j] <= r.stop if r.d == 1 else H[j] >= r.stop
            hit_tgt = H[j] >= r.tgt if r.d == 1 else L[j] <= r.tgt
            if hit_stop:               # includes the ambiguous both-hit bar -> stop first
                res = -1.0; exit_i = j; break
            if hit_tgt:
                res = P["target_r"]; exit_i = j; break
        if res is None:               # time stop at close
            j = min(r.i + horizon, len(df) - 1)
            res = (C[j] - r.entry) * r.d / r.risk
            exit_i = j
        out.append((res, exit_i - r.i))
    sigs = sigs.copy()
    sigs["R"] = [o[0] for o in out]
    sigs["bars"] = [o[1] for o in out]
    return sigs


def summarize(name, ev, cost_r=0.0):
    if ev is None or len(ev) == 0:
        return dict(variant=name, n=0)
    r = ev.R - cost_r
    t = r.mean() / (r.std(ddof=1) / np.sqrt(len(r))) if len(r) > 2 and r.std() > 0 else np.nan
    half = len(r) // 2
    return dict(variant=name, n=len(r), win=round((r > 0).mean(), 3), avgR=round(r.mean(), 3),
                t=round(t, 2), firstHalfR=round(r.iloc[:half].mean(), 3) if half else np.nan,
                secondHalfR=round(r.iloc[half:].mean(), 3) if half else np.nan)


# ----------------------------- baseline: same direction rule, random timing -----------------------------
def random_baseline(df, htf, s, atr_prior, n_draw=400, seed=7):
    rng = np.random.default_rng(seed)
    cand = [i for i in range(60, len(df) - P["horizon"] - 1)
            if htf.iloc[i] != 0 and s.dir.iloc[i] == htf.iloc[i] and not np.isnan(atr_prior.iloc[i])]
    if not cand:
        return None
    pick = rng.choice(cand, size=min(n_draw, len(cand)), replace=False)
    rows = []
    for i in pick:
        d = int(htf.iloc[i]); risk = max(atr_prior.iloc[i], P["tick"])
        e = df.close.iloc[i]
        rows.append(dict(i=i, t=df.index[i], d=d, entry=e, stop=e - d * risk, tgt=e + d * risk * P["target_r"], risk=risk))
    return evaluate(df, pd.DataFrame(rows))


# ----------------------------- variants -----------------------------
BASE = dict(A=True, B=True, round_zone=False, sweep=False, rel_vol=0.0, close_loc=False, round_step=10.0, round_tol=1.5)
VARIANTS = {
    "base A+B": {},
    "B only": dict(A=False),
    "A only": dict(B=False),
    "B + zone near $10 round": dict(A=False, round_zone=True, round_step=10.0),
    "B + zone near $50 round": dict(A=False, round_zone=True, round_step=50.0, round_tol=3.0),
    "B + round-number sweep": dict(A=False, sweep=True, round_step=10.0),
    "A + round-number sweep": dict(B=False, sweep=True, round_step=10.0),
    "B + rel volume>=1.5": dict(A=False, rel_vol=1.5),
    "B + close-location": dict(A=False, close_loc=True),
    "B + $10 round + close-loc": dict(A=False, round_zone=True, close_loc=True),
}


def main(symbol="GC=F", interval="15m", period="60d", cost_r=0.05):
    df = load(symbol, interval, period)
    print(f"{symbol} {interval}: {len(df)} bars, {df.index[0]} -> {df.index[-1]}  (cost per trade = {cost_r}R)")
    rows, base_sigs = [], None
    for name, over in VARIANTS.items():
        cfg = {**BASE, **over}
        sigs, atr_p, htf, s = generate(df, cfg)
        if base_sigs is None:
            base_atr, base_htf, base_s = atr_p, htf, s
        ev = evaluate(df, sigs) if len(sigs) else None
        rows.append(summarize(name, ev, cost_r))
    rb = random_baseline(df, base_htf, base_s, base_atr)
    rows.append(summarize("RANDOM-TIME baseline (same bias, ATR stop)", rb, cost_r))
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nRead it like this: a confirmation is only worth keeping if avgR beats 'base' AND the baseline,"
          "\nt > ~2, and BOTH halves are positive. With n < ~100 treat every row as noise.")


if __name__ == "__main__":
    main(*(sys.argv[1:4] if len(sys.argv) > 1 else []))