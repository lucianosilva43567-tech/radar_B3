"""Carrega preços e dados fundamentalistas de ativos da B3."""
import os

import numpy as np
import pandas as pd

# Lista editável (no app) das principais ações. Códigos podem mudar com o tempo;
# os que o Yahoo não encontrar são ignorados automaticamente.
MAIN_TICKERS = [
    "PETR4", "PETR3", "VALE3", "ITUB4", "BBDC4", "BBAS3", "B3SA3", "ABEV3", "WEGE3", "RENT3",
    "SUZB3", "JBSS3", "GGBR4", "CSNA3", "USIM5", "ELET3", "ELET6", "EQTL3", "CMIG4", "CPLE6",
    "SBSP3", "TAEE11", "VIVT3", "TIMS3", "RADL3", "RDOR3", "HAPV3", "LREN3", "MGLU3", "ASAI3",
    "PRIO3", "CSAN3", "UGPA3", "RAIZ4", "KLBN11", "BRFS3", "MRFG3", "BEEF3", "CMIN3", "EMBR3",
    "RAIL3", "MULT3", "CYRE3", "MRVE3", "BBSE3", "SANB11", "BPAC11", "ITSA4", "VBBR3", "TOTS3",
    "HYPE3", "ENEV3", "ALOS3", "AZZA3", "NATU3", "AURE3", "ISAE4", "CXSE3", "COGN3", "CVCB3",
]


def normalize(ticker: str) -> str:
    t = ticker.strip().upper()
    return t if (t.startswith("^") or t.endswith(".SA")) else t + ".SA"


def _naive(idx):
    idx = pd.to_datetime(idx)
    return idx.tz_localize(None) if getattr(idx, "tz", None) is not None else idx


def _demo(ticker: str) -> dict:
    """Dados sintéticos só para testar o app sem internet (DEMO=1)."""
    rng = np.random.default_rng(7)
    n = 1250
    drift = np.concatenate([
        np.full(500, 0.0008), np.full(400, -0.0012), np.full(250, 0.0016), np.full(100, 0.0003)
    ])
    ret = drift + rng.normal(0, 0.014, n)
    close = 30 * np.exp(np.cumsum(ret))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.003, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.006, n)))
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    df = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                       "Volume": rng.integers(1_000_000, 9_000_000, n)}, index=idx)
    if ticker.upper().endswith("11"):  # simula um FII que paga todo mês
        pay_idx = idx[[i for i in range(n - 520, n, 21)]]
        divs = pd.Series(np.round(0.08 + rng.normal(0, 0.004, len(pay_idx)), 3), index=pay_idx)
        info = {"longName": f"FII {ticker.upper()} (DADOS SIMULADOS)", "sector": "Real Estate"}
    else:
        divs = pd.Series([0.45, 0.50, 0.55, 0.60], index=idx[[-300, -210, -120, -30]])
        info = {
            "longName": f"{ticker.upper()} (DADOS SIMULADOS)", "sector": "Demo",
            "trailingEps": 3.2, "bookValue": 22.0, "freeCashflow": 4.0e9,
            "totalDebt": 6.0e9, "totalCash": 2.0e9, "sharesOutstanding": 1.0e9,
            "trailingPE": 9.1, "priceToBook": 1.3, "enterpriseToEbitda": 5.2,
            "returnOnEquity": 0.18, "profitMargins": 0.14, "ebitda": 8.0e9,
            "marketCap": float(close[-1]) * 1.0e9,
        }
    return {"df": df, "info": info, "divs": divs}


def _today_from_intraday(tk):
    """Candle do pregão mais recente montado com candles de 5/15 minutos (Yahoo)."""
    for interval in ("5m", "15m"):
        try:
            h = tk.history(period="5d", interval=interval, auto_adjust=True)
        except Exception:
            continue
        if h is None or h.empty:
            continue
        h.index = _naive(h.index)
        h = h[(h[["Open", "High", "Low", "Close"]] > 0).all(axis=1)]  # descarta zeros e vazios
        if h.empty:
            continue
        day = h.index[-1].normalize()
        h = h[h.index.normalize() == day]
        return day, [float(h.Open.iloc[0]), float(h.High.max()), float(h.Low.min()), float(h.Close.iloc[-1]),
                     float(h.Volume.sum())]
    return None


def _repair_today(tk, df):
    """O Yahoo às vezes devolve o candle de hoje zerado, vazio ou ausente: reconstrói pelos candles intradiários."""
    if df.empty:
        return df
    cols = ["Open", "High", "Low", "Close"]
    last = df.iloc[-1]
    bad_last = bool(last[cols].isna().any() or (last[cols] <= 0).any())
    last_day = df.index[-1].normalize()
    if not bad_last and last_day >= pd.Timestamp.today().normalize():
        return df  # candle de hoje já veio bom
    got = _today_from_intraday(tk)
    if got is None:
        return df
    day, row = got
    if day > last_day:
        df = df.copy()
        df.loc[day] = row  # o Yahoo ainda não trouxe o candle desse dia
    elif day == last_day and bad_last:
        df = df.copy()
        df.loc[df.index[-1]] = row  # candle do dia veio zerado
    return df


def load(ticker: str, period: str = "5y") -> dict:
    if os.environ.get("DEMO") == "1":
        return _demo(ticker)

    import yfinance as yf

    tk = yf.Ticker(normalize(ticker))
    df = tk.history(period=period, auto_adjust=True)
    if df is None or df.empty:
        raise ValueError(f"Nenhum dado encontrado para '{ticker}'. Confira o código (ex.: PETR4, VALE3, HGLG11).")
    df.index = _naive(df.index)
    df = _repair_today(tk, df[["Open", "High", "Low", "Close", "Volume"]]).dropna()

    try:
        info = tk.get_info() or {}
    except Exception:
        info = {}
    try:
        divs = tk.dividends
        divs.index = _naive(divs.index)
    except Exception:
        divs = pd.Series(dtype=float)
    return {"df": df, "info": info, "divs": divs}


def load_market(tickers, period: str = "1y"):
    """Fechamentos e volumes de vários ativos de uma vez (uma única chamada)."""
    tickers = [t.strip().upper().replace(".SA", "") for t in tickers if t.strip()]
    if os.environ.get("DEMO") == "1":
        rng = np.random.default_rng(11)
        n = 260
        idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
        close = pd.DataFrame({t: 20 * np.exp(np.cumsum(rng.normal(0.0003, 0.016, n))) for t in tickers}, index=idx)
        vol = pd.DataFrame(rng.integers(1_000_000, 10_000_000, (n, len(tickers))), index=idx, columns=tickers)
        return close, vol

    import yfinance as yf

    syms = [normalize(t) for t in tickers]
    # auto_adjust=False: o fechamento fica igual ao cotado na bolsa (inclusive em dia ex-dividendo)
    raw = yf.download(syms, period=period, auto_adjust=False, progress=False, threads=True, group_by="column")
    if raw is None or raw.empty:
        raise ValueError("O Yahoo Finance não devolveu dados. Tente de novo em instantes.")
    close, vol = raw["Close"], raw["Volume"]
    if isinstance(close, pd.Series):
        close, vol = close.to_frame(syms[0]), vol.to_frame(syms[0])
    for frame in (close, vol):
        frame.index = _naive(frame.index)
        frame.columns = [str(c).replace(".SA", "") for c in frame.columns]
    close = close.dropna(how="all", axis=1)
    return close, vol.reindex(columns=close.columns)


def _seed(t: str) -> int:
    return sum(ord(c) * (i + 1) for i, c in enumerate(t))


def _synth_ohlc(seed: int, n: int = 750) -> pd.DataFrame:
    """OHLC sintético com regimes de alta/baixa diferentes (só para DEMO=1)."""
    rng = np.random.default_rng(seed)
    cuts = sorted(rng.choice(np.arange(150, n - 100), 2, replace=False))
    parts = np.split(np.arange(n), cuts)
    drift = np.concatenate([np.full(len(p), rng.choice([-0.0014, -0.0005, 0.0004, 0.0012, 0.0018])) for p in parts])
    ret = drift + rng.normal(0, rng.uniform(0.012, 0.02), n)
    close = rng.uniform(8, 60) * np.exp(np.cumsum(ret))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.003, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.006, n)))
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                         "Volume": rng.integers(1_000_000, 9_000_000, n)}, index=idx)


def load_ohlc_many(tickers, period: str = "3y") -> dict:
    """Candles (OHLCV ajustados) de vários ativos numa única chamada: {ticker: DataFrame}."""
    tickers = list(dict.fromkeys(t.strip().upper().replace(".SA", "") for t in tickers if t.strip()))
    if os.environ.get("DEMO") == "1":
        return {t: _synth_ohlc(_seed(t)) for t in tickers}

    import yfinance as yf

    syms = [normalize(t) for t in tickers]
    raw = yf.download(syms, period=period, auto_adjust=True, progress=False, threads=True, group_by="ticker")
    if raw is None or raw.empty:
        raise ValueError("O Yahoo Finance não devolveu dados. Tente de novo em instantes.")
    out = {}
    for t, s in zip(tickers, syms):
        try:
            sub = raw[s] if isinstance(raw.columns, pd.MultiIndex) else raw
            sub = sub[["Open", "High", "Low", "Close", "Volume"]].dropna()
        except KeyError:
            continue
        if len(sub):
            sub.index = _naive(sub.index)
            out[t] = sub
    return out


def _synth_hourly(seed: int, days: int = 260) -> pd.DataFrame:
    """Candles de 1 hora sintéticos (10h às 16h) só para DEMO=1."""
    rng = np.random.default_rng(seed)
    days_idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    idx = pd.DatetimeIndex([d + pd.Timedelta(hours=h) for d in days_idx for h in range(10, 17)])
    n = len(idx)
    close = 30 * np.exp(np.cumsum(rng.normal(0.00005, 0.004, n)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.0015, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.0015, n)))
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                         "Volume": rng.integers(100_000, 2_000_000, n)}, index=idx)


def load_hourly(ticker: str) -> pd.DataFrame:
    """Candles de 1 hora (o Yahoo entrega no máximo ~2 anos)."""
    if os.environ.get("DEMO") == "1":
        return _synth_hourly(_seed(ticker))
    import yfinance as yf

    df = yf.Ticker(normalize(ticker)).history(period="730d", interval="1h", auto_adjust=True)
    if df is None or df.empty:
        raise ValueError(f"Sem candles de 1 hora para '{ticker}' no Yahoo Finance.")
    df.index = _naive(df.index)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
