"""Valuation, análise técnica, dividendos, FIIs e painel de mercado."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# FORMATAÇÃO (pt-BR)
# ----------------------------------------------------------------------------

def _na(x):
    return x is None or (isinstance(x, (float, np.floating)) and np.isnan(x))


def _sep(s):
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_brl(x):
    return "—" if _na(x) else _sep(f"R$ {x:,.2f}")


def fmt_pct(x, d=1):
    return "—" if _na(x) else _sep(f"{x * 100:,.{d}f}%")


def fmt_num(x, d=2):
    return "—" if _na(x) else _sep(f"{x:,.{d}f}")


# ----------------------------------------------------------------------------
# VALUATION
# ----------------------------------------------------------------------------

def graham(eps, bvps):
    """Preço justo de Graham: raiz(22,5 x LPA x VPA)."""
    if eps and bvps and eps > 0 and bvps > 0:
        return math.sqrt(22.5 * eps * bvps)
    return None


def bazin(div_12m, yield_min=0.06):
    """Preço teto de Bazin: dividendos dos últimos 12m / yield mínimo exigido."""
    if div_12m and div_12m > 0:
        return div_12m / yield_min
    return None


def dcf(fcf, shares, net_debt, g_high=0.08, g_term=0.05, ke=0.14, years=5):
    """DCF simplificado em 2 estágios, no estilo Damodaran.

    Cresce o fluxo de caixa livre a `g_high` por `years` anos, depois perpetuidade
    a `g_term` (deve ficar abaixo do custo de capital). Subtrai dívida líquida.
    """
    if not fcf or not shares or fcf <= 0 or shares <= 0 or ke <= g_term:
        return None
    pv = 0.0
    cf = fcf
    for t in range(1, years + 1):
        cf *= 1 + g_high
        pv += cf / (1 + ke) ** t
    terminal = cf * (1 + g_term) / (ke - g_term) / (1 + ke) ** years
    equity = pv + terminal - (net_debt or 0.0)
    if equity <= 0:
        return None
    return equity / shares


def classify_margin(m):
    if m is None:
        return "Sem dados"
    if m >= 0.30:
        return "Muito barata"
    if m >= 0.10:
        return "Barata"
    if m > -0.10:
        return "Preço justo"
    if m > -0.30:
        return "Cara"
    return "Muito cara"


def valuation(price, info, divs, last_date, ke=0.14, g_high=0.08, g_term=0.05, bazin_yield=0.06):
    eps = info.get("trailingEps")
    bvps = info.get("bookValue")
    shares = info.get("sharesOutstanding")
    fcf = info.get("freeCashflow")
    net_debt = (info.get("totalDebt") or 0) - (info.get("totalCash") or 0)

    if divs is not None and len(divs):
        div12 = float(divs[divs.index >= last_date - pd.Timedelta(days=365)].sum())
    else:
        div12 = 0.0

    methods = {
        "Graham": graham(eps, bvps),
        "Bazin": bazin(div12, bazin_yield),
        "DCF simplificado": dcf(fcf, shares, net_debt, g_high, g_term, ke),
    }
    rows = []
    for name, fair in methods.items():
        margin = (fair / price - 1) if fair else None
        rows.append({"Método": name, "Preço justo": fair, "Margem vs preço": margin,
                     "Leitura": classify_margin(margin)})
    valid = [r["Preço justo"] for r in rows if r["Preço justo"]]
    consensus = float(np.median(valid)) if valid else None
    cons_margin = (consensus / price - 1) if consensus else None

    dy = div12 / price if price else None
    pl = info.get("trailingPE") or (price / eps if eps and eps > 0 else None)
    metrics = {
        "P/L": pl,
        "P/VP": info.get("priceToBook") or (price / bvps if bvps and bvps > 0 else None),
        "EV/EBITDA": info.get("enterpriseToEbitda"),
        "ROE": info.get("returnOnEquity"),
        "Margem líquida": info.get("profitMargins"),
        "Dividend yield 12m": dy,
        "Earnings yield (1/PL)": (1 / pl) if pl and pl > 0 else None,
        "Dívida líquida/EBITDA": (net_debt / info["ebitda"]) if info.get("ebitda") else None,
    }
    return {"rows": rows, "consensus": consensus, "margin": cons_margin,
            "label": classify_margin(cons_margin), "metrics": metrics, "div12": div12,
            "n_methods": len(valid)}


# ----------------------------------------------------------------------------
# ANÁLISE TÉCNICA
# ----------------------------------------------------------------------------

def sma(s, n):
    return s.rolling(n).mean()


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def atr(df, n=14):
    tr = pd.concat([df.High - df.Low,
                    (df.High - df.Close.shift()).abs(),
                    (df.Low - df.Close.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def find_pivots(df, order=5):
    """Topos e fundos confirmados (precisam de `order` candles depois para valer)."""
    h, l = df.High.values, df.Low.values
    highs, lows = [], []
    for i in range(order, len(df) - order):
        if h[i] > h[i - order:i].max() and h[i] >= h[i + 1:i + order + 1].max():
            highs.append((i, float(h[i])))
        if l[i] < l[i - order:i].min() and l[i] <= l[i + 1:i + order + 1].min():
            lows.append((i, float(l[i])))
    return highs, lows


def _crossed_above(a, b, lookback):
    x = (a.shift(1) <= b.shift(1)) & (a > b)
    return bool(x.tail(lookback).any())


def _crossed_below(a, b, lookback):
    x = (a.shift(1) >= b.shift(1)) & (a < b)
    return bool(x.tail(lookback).any())


def _streak(mask):
    """Quantos candles seguidos (até o último) a condição está verdadeira."""
    v = mask.values[::-1]
    if len(v) == 0:
        return 0
    if v.all():
        return int(len(v))
    return int(np.argmin(v))


def _structure(highs, lows):
    if len(highs) < 2 or len(lows) < 2:
        return "indefinida"
    hh = highs[-1][1] > highs[-2][1]
    hl = lows[-1][1] > lows[-2][1]
    if hh and hl:
        return "alta"
    if not hh and not hl:
        return "baixa"
    return "transição"


def ma_alignment(d):
    """Tendência clara pelas médias: 20 > 50 > 200 (alta) ou 20 < 50 < 200 (baixa)."""
    s20, s50, s200 = (float(d[c].iloc[-1]) for c in ("SMA20", "SMA50", "SMA200"))
    last = float(d.Close.iloc[-1])
    up = (d.SMA20 > d.SMA50) & (d.SMA50 > d.SMA200)
    dn = (d.SMA20 < d.SMA50) & (d.SMA50 < d.SMA200)
    valid = not any(np.isnan(v) for v in (s20, s50, s200))
    if valid and bool(up.iloc[-1]):
        estado, run = "alta", _streak(up)
    elif valid and bool(dn.iloc[-1]):
        estado, run = "baixa", _streak(dn)
    else:
        estado, run = "misto", 0
    return {"estado": estado, "sequencia": run, "valid": valid,
            "SMA20": s20, "SMA50": s50, "SMA200": s200,
            "spread_20_200": (s20 / s200 - 1) if valid else None,
            "preco_vs_20": (last / s20 - 1) if not np.isnan(s20) else None}


# ----------------------------------------------------------------------------
# PIVÔS CLÁSSICOS (floor pivots) E FIBONACCI
# ----------------------------------------------------------------------------

PIVOT_FREQ = {"Semanal": "W-FRI", "Mensal": "M", "Diário": "D"}
TIMEFRAMES = ["Diário", "Semanal", "Mensal", "1 hora"]


def to_timeframe(df, tf):
    """Converte candles diários em semanais/mensais. Diário e 1 hora já vêm prontos da fonte."""
    if tf not in ("Semanal", "Mensal"):
        return df
    per = df.index.to_period("W-FRI" if tf == "Semanal" else "M")
    g = df.groupby(per).agg(Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"),
                            Close=("Close", "last"), Volume=("Volume", "sum"))
    g.index = df.index.to_series().groupby(per).max().values  # data do último pregão de cada período
    return g
RETR = (0.382, 0.5, 0.618, 0.786)
PROJ = (0.618, 1.0, 1.618)


def _r(x):
    """Razão de Fibonacci em pt-BR (0,618 / 1,272)."""
    return _sep(f"{x:.3f}").rstrip("0").rstrip(",")


def classic_pivots(df, freq="W-FRI"):
    """Pivôs clássicos (floor pivots) do período atual, calculados com máx., mín. e fechamento do anterior.

    P = (H+L+C)/3; R1 = 2P-L; S1 = 2P-H; R2 = P+(H-L); S2 = P-(H-L);
    R3 = H+2(P-L); S3 = L-2(H-P). A variante Fibonacci usa P ± 0,382/0,618/1,0 x (H-L).
    """
    if len(df) < 10:
        return None
    per = df.index.to_period(freq)
    g = df.groupby(per).agg(High=("High", "max"), Low=("Low", "min"), Close=("Close", "last"))
    starts = df.index.to_series().groupby(per).min()
    if len(g) < 2:
        return None
    prev = g.iloc[-2]
    H, L, C = float(prev.High), float(prev.Low), float(prev.Close)
    P, rng = (H + L + C) / 3, H - L
    classic = {"R3": H + 2 * (P - L), "R2": P + rng, "R1": 2 * P - L, "P": P,
               "S1": 2 * P - H, "S2": P - rng, "S3": L - 2 * (H - P)}
    fib = {"R3": P + 1.0 * rng, "R2": P + 0.618 * rng, "R1": P + 0.382 * rng, "P": P,
           "S1": P - 0.382 * rng, "S2": P - 0.618 * rng, "S3": P - 1.0 * rng}
    return {"freq": freq, "start": starts.iloc[-1], "prev_start": starts.iloc[-2],
            "H": H, "L": L, "C": C, "classic": classic, "fib": fib}


def _alt_swings(highs, lows):
    """Topos e fundos em sequência alternada (se houver dois seguidos do mesmo tipo, fica o mais extremo)."""
    pts = sorted([(i, p, "H") for i, p in highs] + [(i, p, "L") for i, p in lows])
    seq = []
    for pt in pts:
        if seq and seq[-1][2] == pt[2]:
            if (pt[2] == "H" and pt[1] > seq[-1][1]) or (pt[2] == "L" and pt[1] < seq[-1][1]):
                seq[-1] = pt
        else:
            seq.append(pt)
    return seq


STOP_BUFFER_ATR = 0.1  # folga do stop além do Ponto 3 (fração do ATR)


def _ponto3(d, highs, lows, up):
    """Ponto 3 do pivô: menor mínima (compra) ou maior máxima (venda) desde o último topo/fundo confirmado.

    Na compra é o fundo do recuo depois do Ponto 2 (último topo); na venda, o topo do repique depois do último fundo.
    Vale mesmo que o recuo ainda não tenha sido confirmado como fundo pelo filtro de sensibilidade.
    """
    ref = highs if up else lows
    if not ref:
        return None
    seg = (d.Low if up else d.High).iloc[ref[-1][0] + 1:]
    if len(seg) == 0:
        return None
    return float(seg.min() if up else seg.max())


def fib_levels(highs, lows, d=None):
    """Retração da última perna (B->C) e projeção AB=CD a partir de C, em razões de Fibonacci.

    A, B, C = três últimos pivôs alternados. Retração: onde o preço pode parar ao voltar
    parte da perna B->C. Projeção: C + razão x (B - A), na direção da perna A->B.
    """
    seq = _alt_swings(highs, lows)
    if d is not None and seq:
        # Ponto 3 provisório: extremo desde o último pivô confirmado, se o preço já reagiu pelo menos 1 ATR
        i0, p0, t0 = seq[-1]
        atr_v, last = float(d.ATR.iloc[-1]), float(d.Close.iloc[-1])
        seg = (d.Low if t0 == "H" else d.High).iloc[i0 + 1:]
        if len(seg):
            j = i0 + 1 + int(np.argmin(seg.values) if t0 == "H" else np.argmax(seg.values))
            p = float(seg.min() if t0 == "H" else seg.max())
            if t0 == "H" and p < p0 and last - p >= atr_v:
                seq.append((j, p, "L"))
            elif t0 == "L" and p > p0 and p - last >= atr_v:
                seq.append((j, p, "H"))
    if len(seq) < 2:
        return None
    b, c = seq[-2], seq[-1]
    leg = c[1] - b[1]
    retr = [(r, c[1] - r * leg) for r in RETR]
    proj, dir_proj = [], None
    if len(seq) >= 3:
        a = seq[-3]
        ab = b[1] - a[1]
        dir_proj = "alta" if ab > 0 else "baixa"
        proj = [(r, c[1] + r * ab) for r in PROJ]
    return {"pts": [(i, p) for i, p, _ in seq[-3:]], "dir_last": "alta" if leg > 0 else "queda",
            "dir_proj": dir_proj, "retr": [x for x in retr if x[1] > 0],
            "proj": [x for x in proj if x[1] > 0]}


def confluences(tec, variant="classic"):
    """Zonas onde pivôs, Fibonacci e médias caem próximos (até 0,5 ATR): suportes/resistências mais fortes."""
    d, piv, fib = tec["df"], tec.get("piv"), tec.get("fib")
    tol = 0.5 * float(d.ATR.iloc[-1])
    lv = []
    if piv:
        lv += [(f"Pivô {k}", v, "pivô") for k, v in piv[variant].items() if v > 0]
    if fib:
        lv += [(f"Fib {_r(r)} ret.", p, "fib") for r, p in fib["retr"]]
        lv += [(f"Fib {_r(r)} proj.", p, "fib") for r, p in fib["proj"]]
    for c in ("SMA20", "SMA50", "SMA200"):
        v = d[c].iloc[-1]
        if not np.isnan(v):
            lv.append((c.replace("SMA", "Média "), float(v), "média"))
    lv.sort(key=lambda x: x[1])
    groups, cur = [], []
    for x in lv:
        if cur and x[1] - cur[0][1] > tol:
            groups.append(cur)
            cur = []
        cur.append(x)
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        if len(g) >= 2 and len({x[2] for x in g}) >= 2:
            out.append({"Zona": float(np.mean([x[1] for x in g])), "Níveis": " + ".join(x[0] for x in g)})
    return out


def _clean_ohlc(df):
    """Corrige candles ruins do Yahoo (mínima/máxima zeradas ou vazias) antes de qualquer conta."""
    d = df.copy()
    d = d[d.Close > 0]
    d["Open"] = d.Open.where(d.Open > 0, d.Close)
    lo, hi = d[["Open", "Close"]].min(axis=1), d[["Open", "Close"]].max(axis=1)
    d["Low"] = d.Low.where(d.Low > 0, lo)
    d["High"] = d.High.where(d.High > 0, hi)
    return d


def _vs(a, b):
    """a / b - 1, ou None se b for zero/vazio (evita ZeroDivisionError)."""
    try:
        b = float(b)
    except (TypeError, ValueError):
        return None
    return (float(a) / b - 1) if np.isfinite(b) and b > 0 else None


def technical(df, order=5, pivot_freq="W-FRI"):
    d = _clean_ohlc(df)
    d["SMA20"], d["SMA50"], d["SMA200"] = sma(d.Close, 20), sma(d.Close, 50), sma(d.Close, 200)
    d["RSI"], d["ATR"] = rsi(d.Close), atr(d)
    close = d.Close
    last = float(close.iloc[-1])
    highs, lows = find_pivots(d, order)
    structure = _structure(highs, lows)
    align = ma_alignment(d)

    bull, bear = [], []  # (descrição, peso)

    # --- estrutura de topos e fundos ---
    if len(lows) >= 3 and lows[-3][1] > lows[-2][1] < lows[-1][1]:
        bull.append(("Fundo ascendente após um novo fundo (possível fim da queda)", 2))
    if len(lows) >= 2 and abs(lows[-1][1] / lows[-2][1] - 1) <= 0.025 and structure != "alta":
        bull.append(("Fundo duplo (dois fundos na mesma região)", 1))
    if len(highs) >= 2 and len(lows) >= 1 and highs[-1][1] < highs[-2][1]:
        lvl = highs[-1][1]
        if last > lvl and _crossed_above(close, pd.Series(lvl, index=close.index), 15):
            bull.append((f"Rompeu o último topo descendente ({lvl:.2f}): quebra de estrutura de alta", 3))

    if len(highs) >= 3 and highs[-3][1] < highs[-2][1] > highs[-1][1]:
        bear.append(("Topo descendente após um novo topo (possível fim da alta)", 2))
    if len(highs) >= 2 and abs(highs[-1][1] / highs[-2][1] - 1) <= 0.025 and structure != "baixa":
        bear.append(("Topo duplo (dois topos na mesma região)", 1))
    if len(lows) >= 2 and lows[-1][1] > lows[-2][1]:
        lvl = lows[-1][1]
        if last < lvl and _crossed_below(close, pd.Series(lvl, index=close.index), 15):
            bear.append((f"Perdeu o último fundo ascendente ({lvl:.2f}): quebra de estrutura de baixa", 3))

    # --- médias móveis (20, 50, 200) ---
    if _crossed_above(close, d.SMA20, 10) and last > d.SMA20.iloc[-1]:
        bull.append(("Preço cruzou para cima da média de 20", 1))
    if _crossed_above(d.SMA20, d.SMA50, 20):
        bull.append(("Média de 20 cruzou para cima da de 50", 2))
    if _crossed_above(close, d.SMA200, 20):
        bull.append(("Preço retomou a média de 200", 2))
    if _crossed_below(close, d.SMA20, 10) and last < d.SMA20.iloc[-1]:
        bear.append(("Preço cruzou para baixo da média de 20", 1))
    if _crossed_below(d.SMA20, d.SMA50, 20):
        bear.append(("Média de 20 cruzou para baixo da de 50", 2))
    if _crossed_below(close, d.SMA200, 20):
        bear.append(("Preço perdeu a média de 200", 2))

    # --- divergência de IFR (RSI) nos dois últimos fundos/topos ---
    if len(lows) >= 2:
        (i1, p1), (i2, p2) = lows[-2], lows[-1]
        r1, r2 = d.RSI.iloc[i1], d.RSI.iloc[i2]
        if p2 < p1 and r2 > r1 and r1 < 40:
            bull.append(("Divergência altista no IFR: preço fez fundo mais baixo, IFR mais alto", 2))
    if len(highs) >= 2:
        (i1, p1), (i2, p2) = highs[-2], highs[-1]
        r1, r2 = d.RSI.iloc[i1], d.RSI.iloc[i2]
        if p2 > p1 and r2 < r1 and r1 > 60:
            bear.append(("Divergência baixista no IFR: preço fez topo mais alto, IFR mais baixo", 2))

    bs, es = sum(w for _, w in bull), sum(w for _, w in bear)
    s50, s200 = d.SMA50.iloc[-1], d.SMA200.iloc[-1]
    above200 = (not np.isnan(s200)) and last > s200

    if bs >= 4 and bs > es:
        verdict, tone = "Possível FUNDO – reversão de alta", "bull"
    elif es >= 4 and es > bs:
        verdict, tone = "Possível TOPO – reversão de baixa", "bear"
    elif align["estado"] == "alta" and not (es >= 2 and es > bs):
        verdict, tone = "Tendência de ALTA clara (20 > 50 > 200)", "up"
    elif align["estado"] == "baixa" and not (bs >= 2 and bs > es):
        verdict, tone = "Tendência de BAIXA clara (20 < 50 < 200)", "down"
    elif bs >= 2 and bs > es:
        verdict, tone = "Fundo em formação (ainda sem confirmação)", "bull-weak"
    elif es >= 2 and es > bs:
        verdict, tone = "Topo em formação (ainda sem confirmação)", "bear-weak"
    elif structure == "alta" and last > (s50 if not np.isnan(s50) else last):
        verdict, tone = "Tendência de alta", "up"
    elif structure == "baixa" and last < (s50 if not np.isnan(s50) else last):
        verdict, tone = "Tendência de baixa", "down"
    else:
        verdict, tone = "Lateral / sem sinal claro", "neutral"

    yr = d[d.index >= d.index[-1] - pd.Timedelta(days=365)]  # 52 semanas, em qualquer tempo gráfico
    hi52, lo52 = float(yr.High.max()), float(yr.Low.min())
    ctx = {
        "Preço": last, "Estrutura de topos/fundos": structure,
        "Máx. 52 sem.": hi52, "Mín. 52 sem.": lo52,
        "Distância da máxima": _vs(last, hi52), "Distância da mínima": _vs(last, lo52),
        "vs SMA20": _vs(last, d.SMA20.iloc[-1]),
        "vs SMA50": _vs(last, s50),
        "vs SMA200": _vs(last, s200),
        "IFR(14)": float(d.RSI.iloc[-1]), "ATR(14)": float(d.ATR.iloc[-1]),
        "acima200": above200,
    }
    levels = _levels(d, highs, lows, last)
    setups = entry_points(d, highs, lows, last, tone, levels)
    piv = classic_pivots(d, pivot_freq)
    fib = fib_levels(highs, lows, d)
    return {"df": d, "piv": piv, "fib": fib, "highs": highs, "lows": lows, "bull": bull, "bear": bear,
            "bull_score": bs, "bear_score": es, "verdict": verdict, "tone": tone,
            "ctx": ctx, "levels": levels, "setups": setups, "align": align}


def _levels(d, highs, lows, last):
    sup = sorted({round(p, 2) for _, p in lows if p < last}, key=lambda p: last - p)[:3]
    res = sorted({round(p, 2) for _, p in highs if p > last}, key=lambda p: p - last)[:3]
    for c in ("SMA20", "SMA50", "SMA200"):
        v = d[c].iloc[-1]
        if not np.isnan(v):
            (sup if v < last else res).append((c, round(float(v), 2)))
    return {"suportes": sup, "resistências": res}


def entry_points(d, highs, lows, last, tone, levels):
    """Sugestões didáticas de entrada, stop e alvo (não são recomendação)."""
    atr_v = float(d.ATR.iloc[-1])
    setups = []
    if tone in ("bear", "down", "bear-weak"):
        if highs:
            trig = highs[-1][1]
            setups.append({"Setup": "Aguardar (tendência contra)",
                           "Gatilho": f"Fechamento acima de {trig:.2f} (último topo)",
                           "Entrada": None, "Stop": None, "Alvo": None, "R/R": None,
                           "Obs": "Só vira candidato a compra se rompeu o último topo descendente."})
        return setups

    # candidato a pullback: suporte numérico mais próximo abaixo do preço (até 10%)
    sup_vals = [p if not isinstance(p, tuple) else p[1] for p in levels["suportes"]]
    sup_vals = [p for p in sup_vals if 0 < last / p - 1 <= 0.10]
    res_vals = [p if not isinstance(p, tuple) else p[1] for p in levels["resistências"]]

    if highs and last < highs[-1][1]:
        entry = highs[-1][1] * 1.005
        p3 = _ponto3(d, highs, lows, True)
        stop = (p3 if p3 is not None else (lows[-1][1] if lows else last - 2 * atr_v)) - STOP_BUFFER_ATR * atr_v
        nxt = [r for r in res_vals if r > entry * 1.01]
        target = nxt[0] if nxt else entry + 2 * (entry - stop)
        setups.append(_mk("Rompimento do último topo", entry, stop, target,
                          "Entrada por confirmação: compra se fechar acima do topo recente."))
    if sup_vals:
        entry = max(sup_vals)
        stop = entry - 1.0 * atr_v
        target = highs[-1][1] if highs and highs[-1][1] > entry * 1.03 else entry + 2 * (entry - stop)
        setups.append(_mk("Pullback no suporte / média", entry, stop, target,
                          "Entrada em recuo até o suporte mais próximo, com stop curto abaixo dele."))
    if not setups:
        setups.append({"Setup": "Sem setup claro", "Gatilho": "Aguardar recuo a suporte ou rompimento",
                       "Entrada": None, "Stop": None, "Alvo": None, "R/R": None, "Obs": ""})
    return setups


def _mk(name, entry, stop, target, obs):
    risk, reward = entry - stop, target - entry
    return {"Setup": name, "Gatilho": obs, "Entrada": round(entry, 2), "Stop": round(stop, 2),
            "Alvo": round(target, 2), "R/R": round(reward / risk, 2) if risk > 0 else None, "Obs": obs}


# ----------------------------------------------------------------------------
# DIVIDENDOS
# ----------------------------------------------------------------------------

def dividends_analysis(divs, price, eps, last_date):
    """Resumo do histórico de proventos. `divs` = série de valores por ação/cota."""
    if divs is None or len(divs) == 0:
        return None
    s = divs[divs > 0].sort_index()
    if s.empty:
        return None
    last12 = s[s.index >= last_date - pd.Timedelta(days=365)]
    prev12 = s[(s.index < last_date - pd.Timedelta(days=365)) &
               (s.index >= last_date - pd.Timedelta(days=730))]
    div12 = float(last12.sum())
    by_year = s.groupby(s.index.year).sum()
    cur = int(last_date.year)
    full = by_year[by_year.index < cur]
    last5 = full.tail(5)

    cagr = None
    if len(last5) >= 3 and last5.iloc[0] > 0 and last5.iloc[-1] > 0:
        cagr = float((last5.iloc[-1] / last5.iloc[0]) ** (1 / (len(last5) - 1)) - 1)

    yrs, y = 0, cur - 1
    while y in by_year.index and by_year[y] > 0:
        yrs += 1
        y -= 1

    payout = (div12 / eps) if (eps and eps > 0) else None
    yield12 = div12 / price if price else None
    avg5_yield = float(last5.mean() / price) if len(last5) and price else None
    chg12 = (div12 / float(prev12.sum()) - 1) if len(prev12) and prev12.sum() > 0 else None
    monthly = s.groupby(s.index.to_period("M")).sum()

    readings = []
    if yield12 is not None:
        readings.append(("ok" if yield12 >= 0.06 else "warn" if yield12 >= 0.03 else "bad",
                         f"Yield dos últimos 12 meses: {fmt_pct(yield12)}"))
    if payout is not None:
        readings.append(("bad" if payout > 1 else "warn" if payout > 0.8 else "ok",
                         f"Payout (dividendos / lucro por ação): {fmt_pct(payout, 0)}"
                         + (" – paga mais do que lucra, difícil de sustentar" if payout > 1 else "")))
    elif eps is not None and eps <= 0:
        readings.append(("bad", "Lucro por ação não positivo: dividendos não estão cobertos pelo lucro"))
    if cagr is not None:
        readings.append(("ok" if cagr >= 0.03 else "warn" if cagr >= -0.03 else "bad",
                         f"Crescimento anual composto dos proventos (últimos {len(last5)} anos fechados): {fmt_pct(cagr)}"))
    readings.append(("ok" if yrs >= 5 else "warn" if yrs >= 3 else "bad",
                     f"Pagou proventos em {yrs} ano(s) seguido(s) até o ano passado"))
    if chg12 is not None:
        readings.append(("ok" if chg12 >= 0.03 else "warn" if chg12 >= -0.10 else "bad",
                         f"Proventos dos últimos 12m vs 12m anteriores: {fmt_pct(chg12)}"))

    return {"div12": div12, "yield12": yield12, "payout": payout, "cagr": cagr,
            "years_paid": yrs, "avg5_yield": avg5_yield, "n12": int(len(last12)),
            "last_date": s.index[-1], "last_value": float(s.iloc[-1]),
            "by_year": by_year, "cur_year": cur, "monthly": monthly, "last": s.tail(12)[::-1],
            "readings": readings}


# ----------------------------------------------------------------------------
# FUNDOS IMOBILIÁRIOS
# ----------------------------------------------------------------------------

# Units de ações que também terminam em 11 (não são FIIs)
_UNITS = {"KLBN11", "TAEE11", "SANB11", "ALUP11", "BPAC11", "SAPR11", "ENGI11", "SULA11", "IGTI11",
          "CPLE11", "AESB11", "BRBI11", "SAPR11", "CSMG11", "TRPL11"}
_FII_WORDS = ("FII", "IMOB", "REAL ESTATE", "FUNDO DE INVEST", "FDO INV", "REIT")


def is_fii(ticker, info, divs=None, last_date=None):
    t = ticker.strip().upper().replace(".SA", "")
    if not t.endswith("11") or t in _UNITS:
        return False
    name = f"{info.get('longName', '')} {info.get('shortName', '')} {info.get('sector', '')}".upper()
    if any(w in name for w in _FII_WORDS) and "ISHARES" not in name and "ETF" not in name:
        return True
    # FIIs pagam quase todo mês e não têm lucro por ação
    if divs is not None and len(divs) and last_date is not None and not info.get("trailingEps"):
        d12 = divs[divs.index >= last_date - pd.Timedelta(days=365)]
        return d12.index.to_period("M").nunique() >= 9
    return False


def fii_analysis(price, divs, df, last_date, vp=None, cdi=0.12, tone="neutral", ir=0.15):
    """Checklist quantitativo: P/VP, renda vs renda fixa, constância, tendência, liquidez, gráfico."""
    s = divs[divs > 0].sort_index() if divs is not None and len(divs) else pd.Series(dtype=float)
    last12 = s[s.index >= last_date - pd.Timedelta(days=365)]
    div12 = float(last12.sum())
    dy12 = div12 / price if price else None
    months_paid = int(last12.index.to_period("M").nunique()) if len(last12) else 0
    m = s.groupby(s.index.to_period("M")).sum().tail(12)
    recent = float(m.tail(3).mean()) if len(m) >= 6 else None
    prior = float(m.head(len(m) - 3).mean()) if len(m) >= 6 else None
    trend = (recent / prior) if recent and prior and prior > 0 else None
    pvp = (price / vp) if vp and vp > 0 else None
    liq = float((df.Close * df.Volume).tail(60).mean())
    cdi_liq = cdi * (1 - ir)
    vol = float(df.Close.pct_change().tail(252).std() * np.sqrt(252))

    crit = []  # critério, valor, status, comentário, pontos, máximo

    def add(nome, valor, status, comentario, pts, mx):
        crit.append({"Critério": nome, "Valor": valor, "Status": status, "Comentário": comentario,
                     "Pontos": pts, "Máx.": mx})

    # 1) P/VP
    if pvp is None:
        add("P/VP (preço / valor patrimonial)", "—", "na",
            "Informe o VP por cota na barra lateral (relatório gerencial do fundo).", 0, 0)
    else:
        if pvp < 0.95:
            st_, pts, c = "ok", 2, f"Desconto de {fmt_pct(1 - pvp, 0)} sobre o patrimônio."
        elif pvp <= 1.05:
            st_, pts, c = "warn", 1, "Preço próximo do valor patrimonial."
        elif pvp <= 1.15:
            st_, pts, c = "warn", 0, f"Ágio de {fmt_pct(pvp - 1, 0)} sobre o patrimônio."
        else:
            st_, pts, c = "bad", -1, f"Ágio alto de {fmt_pct(pvp - 1, 0)}: pouca margem de segurança."
        add("P/VP (preço / valor patrimonial)", fmt_num(pvp), st_, c, pts, 2)

    # 2) Renda vs renda fixa
    if dy12 is not None and dy12 > 0:
        r = dy12 / cdi_liq if cdi_liq > 0 else 0
        if r >= 1.0:
            st_, pts = "ok", 2
        elif r >= 0.85:
            st_, pts = "warn", 1
        elif r >= 0.70:
            st_, pts = "warn", 0
        else:
            st_, pts = "bad", -1
        add("Renda 12m vs renda fixa", f"{fmt_pct(dy12)} (CDI líq. {fmt_pct(cdi_liq)})", st_,
            f"Dividendos são isentos de IR para pessoa física; equivale a {fmt_pct(dy12 / (1 - ir))} bruto de renda fixa.",
            pts, 2)
    else:
        add("Renda 12m vs renda fixa", "—", "bad", "Sem proventos nos últimos 12 meses.", -1, 2)

    # 3) Constância
    if months_paid >= 11:
        st_, pts = "ok", 2
    elif months_paid >= 9:
        st_, pts = "warn", 1
    else:
        st_, pts = "bad", -1
    add("Constância dos pagamentos", f"{months_paid} de 12 meses", st_,
        "Fundos de tijolo costumam pagar todo mês; falhas indicam vacância ou caixa fraco.", pts, 2)

    # 4) Tendência do dividendo
    if trend is None:
        add("Tendência do dividendo", "—", "na", "Histórico insuficiente.", 0, 0)
    else:
        if trend >= 1.03:
            st_, pts = "ok", 2
        elif trend >= 0.97:
            st_, pts = "ok", 1
        elif trend >= 0.90:
            st_, pts = "warn", 0
        else:
            st_, pts = "bad", -1
        add("Tendência do dividendo", f"{fmt_pct(trend - 1)} (últ. 3 meses vs 9 anteriores)", st_,
            "Média dos 3 últimos pagamentos comparada à dos 9 anteriores.", pts, 2)

    # 5) Liquidez
    if liq >= 1_000_000:
        st_, pts, c = "ok", 1, "Boa liquidez para entrar e sair."
    elif liq >= 300_000:
        st_, pts, c = "warn", 0, "Liquidez moderada; use ordens limitadas."
    else:
        st_, pts, c = "bad", -1, "Liquidez baixa: difícil sair sem perder preço."
    add("Liquidez diária (média 60 pregões)", fmt_brl(liq), st_, c, pts, 1)

    # 6) Momento do gráfico
    if tone in ("up", "bull", "bull-weak"):
        st_, pts, c = "ok", 1, "Gráfico favorável."
    elif tone in ("down", "bear", "bear-weak"):
        st_, pts, c = "bad", -1, "Gráfico desfavorável: pode valer esperar reversão."
    else:
        st_, pts, c = "warn", 0, "Gráfico sem direção clara."
    names = {"up": "Tendência de alta", "bull": "Possível fundo", "bull-weak": "Fundo em formação",
             "down": "Tendência de baixa", "bear": "Possível topo", "bear-weak": "Topo em formação",
             "neutral": "Lateral"}
    add("Momento do gráfico", names.get(tone, tone), st_, c, pts, 1)

    score = sum(c["Pontos"] for c in crit)
    mx = sum(c["Máx."] for c in crit)
    ratio = score / mx if mx else 0
    if ratio >= 0.65:
        verdict, vtone = "Atrativo – vale acompanhar para compra", "good"
    elif ratio >= 0.35:
        verdict, vtone = "Neutro – depende do seu objetivo e do preço", "mid"
    else:
        verdict, vtone = "Pouco atrativo no momento", "bad"
    if pvp is None:
        verdict += " (parcial: faltou o VP)"

    return {"criteria": crit, "score": score, "max": mx, "verdict": verdict, "tone": vtone,
            "metrics": {"pvp": pvp, "vp": vp, "dy12": dy12, "div12": div12,
                        "avg_month": div12 / 12 if div12 else None,
                        "last_div": float(s.iloc[-1]) if len(s) else None,
                        "months_paid": months_paid, "liq": liq, "cdi_liq": cdi_liq, "vol": vol,
                        "premio": (pvp - 1) if pvp else None}}


# ----------------------------------------------------------------------------
# PAINEL DO MERCADO
# ----------------------------------------------------------------------------

def market_summary(close, vol=None):
    """Tabela com fechamento, variação do dia e do período, distância da máx./mín. de 52 semanas."""
    rows = []
    for c in close.columns:
        s = close[c].dropna()
        if len(s) < 2:
            continue
        last, prev = float(s.iloc[-1]), float(s.iloc[-2])
        ref5 = float(s.iloc[-6]) if len(s) >= 6 else float(s.iloc[0])
        w = s.tail(252)
        v = vol[c].dropna() if vol is not None and c in vol.columns else pd.Series(dtype=float)
        fin = float(v.iloc[-1]) * last / 1e6 if len(v) else np.nan
        rows.append({"Ativo": c, "Fechamento (R$)": last,
                     "Var. dia (%)": (last / prev - 1) * 100,
                     "Var. 5 dias (%)": (last / ref5 - 1) * 100,
                     "vs máx. 52s (%)": (last / float(w.max()) - 1) * 100,
                     "vs mín. 52s (%)": (last / float(w.min()) - 1) * 100,
                     "Volume (R$ mi)": fin})
    table = pd.DataFrame(rows)
    ref_date = close.dropna(how="all").index[-1] if len(close) else None
    return table, ref_date


# ----------------------------------------------------------------------------
# SWING TRADE: ações em tendência de alta (compra) ou de baixa (venda)
# ----------------------------------------------------------------------------

HORIZONS = {
    "swing": {"nome": "Swing trade (dias a semanas)", "freq": "W-FRI", "order": 5,
              "rmin": 1.0, "rmax": 2.5, "fallback": 2.0, "rr_min": 1.5},
    "longo": {"nome": "Longo prazo (meses)", "freq": "M", "order": 10,
              "rmin": 1.5, "rmax": 4.0, "fallback": 3.0, "rr_min": 2.0},
}


def _level_list(tec):
    """Níveis do gráfico como (nome, preço, tipo). Tipo 'proj' = alvo de projeção (não vale como suporte)."""
    d = tec["df"]
    lv = []
    for c in ("SMA20", "SMA50", "SMA200"):
        v = d[c].iloc[-1]
        if not np.isnan(v):
            lv.append((c.replace("SMA", "Média "), float(v), "lvl"))
    if tec.get("piv"):
        lv += [(f"Pivô {k}", float(v), "lvl") for k, v in tec["piv"]["classic"].items()]
    if tec.get("fib"):
        lv += [(f"Fib {_r(r)} ret.", float(p), "retr") for r, p in tec["fib"]["retr"]]
        lv += [(f"Fib {_r(r)} proj.", float(p), "proj") for r, p in tec["fib"]["proj"]]
    lv += [("Topo recente", float(p), "lvl") for _, p in tec["highs"][-3:]]
    lv += [("Fundo recente", float(p), "lvl") for _, p in tec["lows"][-3:]]
    lv.append(("Máx. 52 sem.", float(d.High.tail(252).max()), "lvl"))
    lv.append(("Mín. 52 sem.", float(d.Low.tail(252).min()), "lvl"))
    return [x for x in lv if x[1] > 0]


def _swing_side(side, tec, hz):
    """Pontua (0 a 10) um lado do swing: side=+1 compra em tendência de alta, side=-1 venda em baixa."""
    d = tec["df"]
    last, atr_v, rsi_v = float(d.Close.iloc[-1]), float(d.ATR.iloc[-1]), float(d.RSI.iloc[-1])
    al, tone, struct = tec["align"], tec["tone"], tec["ctx"]["Estrutura de topos/fundos"]
    s200 = d.SMA200.iloc[-1]
    up = side > 0
    pts, why = 0, []

    if al["estado"] == ("alta" if up else "baixa"):
        pts += 3
        why.append("Médias 20/50/200 alinhadas " + ("em alta" if up else "em baixa"))
    elif tone == ("bull" if up else "bear"):
        pts += 2
        why.append("Possível fundo (reversão de alta)" if up else "Possível topo (reversão de baixa)")
    elif tone == ("bull-weak" if up else "bear-weak"):
        pts += 1
        why.append("Fundo em formação" if up else "Topo em formação")
    if struct == ("alta" if up else "baixa"):
        pts += 2
        why.append("Topos e fundos " + ("ascendentes" if up else "descendentes"))
    if not np.isnan(s200) and ((last > s200) if up else (last < s200)):
        pts += 1
        why.append("Preço " + ("acima" if up else "abaixo") + " da média de 200")

    if up:
        if 40 <= rsi_v <= 62:
            pts += 2
            why.append(f"IFR {rsi_v:.0f}: zona de pullback saudável")
        elif 62 < rsi_v <= 72:
            pts += 1
        elif rsi_v > 75:
            pts -= 2
            why.append(f"IFR {rsi_v:.0f}: esticado, risco de correção")
    else:
        if 38 <= rsi_v <= 60:
            pts += 2
            why.append(f"IFR {rsi_v:.0f}: repique dentro da baixa")
        elif 28 <= rsi_v < 38:
            pts += 1
        elif rsi_v < 25:
            pts -= 2
            why.append(f"IFR {rsi_v:.0f}: sobrevendido, risco de repique")

    opp = tec["bear_score"] if up else tec["bull_score"]
    if opp >= 2:
        pts -= 2
        why.append(f"Sinais contrários no gráfico ({opp} pts)")

    levels = _level_list(tec)
    base = [x for x in levels if x[2] != "proj"]
    if up:
        near = [x for x in base if x[1] <= last * 1.003]
        near = max(near, key=lambda x: x[1]) if near else None
        close_enough = near and (last - near[1]) <= 1.0 * atr_v
    else:
        near = [x for x in base if x[1] >= last * 0.997]
        near = min(near, key=lambda x: x[1]) if near else None
        close_enough = near and (near[1] - last) <= 1.0 * atr_v
    if close_enough:
        pts += 2
        why.append(f"Perto de {near[0]} ({fmt_num(near[1])}): {'suporte' if up else 'resistência'} para a entrada")

    # stop: logo depois do nível mais próximo que dê um risco razoável (em ATR); senão, stop por volatilidade
    stop, stop_nome = None, None
    p3 = _ponto3(d, tec["highs"], tec["lows"], up)
    if p3 is not None:
        stop = p3 - STOP_BUFFER_ATR * atr_v if up else p3 + STOP_BUFFER_ATR * atr_v
        stop_nome = "Ponto 3 (fundo do recuo)" if up else "Ponto 3 (topo do repique)"
    cands = sorted([x for x in base if (x[1] < last if up else x[1] > last)],
                   key=lambda x: -x[1] if up else x[1])
    for nome, p, _ in (cands if stop is None else []):
        s = p - 0.3 * atr_v if up else p + 0.3 * atr_v
        risk = (last - s) if up else (s - last)
        if hz["rmin"] * atr_v <= risk <= hz["rmax"] * atr_v:
            stop, stop_nome = s, nome
            break
    if stop is None:
        stop = last - hz["fallback"] * atr_v if up else last + hz["fallback"] * atr_v
        stop_nome = f"{hz['fallback']:g} ATR"
    risk = abs(last - stop)

    # alvo: primeiro nível na direção do trade que pague pelo menos rr_min vezes o risco
    tg = sorted([x for x in levels if (x[1] > last * 1.005 if up else x[1] < last * 0.995)],
                key=lambda x: x[1] if up else -x[1])
    target, target_nome = None, None
    for nome, p, _ in tg:
        if abs(p - last) >= hz["rr_min"] * risk:
            target, target_nome = p, nome
            break
    if target is None:
        target = last + 2 * risk if up else last - 2 * risk
        target_nome = "2R (mecânico)"
    else:
        pts += 1
        why.append(f"Alvo técnico em {target_nome}")
    rr = abs(target - last) / risk if risk > 0 else None

    return {"score": int(min(10, max(0, pts))), "why": why, "stop": float(stop), "stop_nome": stop_nome,
            "target": float(target), "target_nome": target_nome, "rr": rr}


def swing_row(ticker, tec, hz):
    d = tec["df"]
    last = float(d.Close.iloc[-1])
    lg, sh = _swing_side(+1, tec, hz), _swing_side(-1, tec, hz)
    if lg["score"] == sh["score"]:
        direction, best = "Neutro", lg
    elif lg["score"] > sh["score"]:
        direction, best = "Alta", lg
    else:
        direction, best = "Queda", sh
    est = {"alta": "Alta clara", "baixa": "Baixa clara", "misto": "Misturadas"}[tec["align"]["estado"]]
    return {"Ativo": ticker, "Direção": direction, "Score": best["score"], "Médias 20/50/200": est,
            "Sinal do gráfico": tec["verdict"], "Preço": last, "IFR": float(d.RSI.iloc[-1]),
            "Entrada (ref.)": last, "Stop": best["stop"], "Alvo": best["target"], "R/R": best["rr"],
            "Alvo em": best["target_nome"], "Stop em": best["stop_nome"],
            "Risco (%)": abs(last - best["stop"]) / last * 100,
            "Liquidez (R$ mi/dia)": float((d.Close * d.Volume).tail(60).mean()) / 1e6,
            "Motivos": "; ".join(best["why"])}


def scan_swing(data, horizon="swing"):
    """Roda a análise em vários ativos. `data` = {ticker: DataFrame OHLCV}. Devolve (tabela, ignorados)."""
    hz = HORIZONS[horizon]
    rows, skipped = [], []
    for t, df in data.items():
        try:
            if df is None or len(df) < 230:
                skipped.append(t)
                continue
            tec = technical(df, hz["order"], hz["freq"])
            rows.append(swing_row(t, tec, hz))
        except Exception:  # noqa: BLE001 - um ativo ruim não derruba o painel
            skipped.append(t)
    return pd.DataFrame(rows), skipped
