"""Radar B3: digite o código do ativo e veja valuation, dividendos, FII e sinais técnicos."""
import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis import (HORIZONS, PIVOT_FREQ, TIMEFRAMES, to_timeframe, _r as fmt_ratio, confluences, dividends_analysis, fii_analysis,
                      fmt_brl as brl, fmt_num as num, fmt_pct as pct, is_fii, market_summary, scan_swing,
                      technical, valuation)
from data import MAIN_TICKERS, load, load_hourly, load_market, load_ohlc_many

st.set_page_config(page_title="Radar B3", layout="wide")

ICON = {"ok": "✅", "warn": "⚠️", "bad": "❌", "na": "➖"}
FAVORABLE = ("bull", "bull-weak", "up")
UNFAVORABLE = ("bear", "bear-weak", "down")


@st.cache_data(ttl=3600, show_spinner="Buscando dados...")
def get(ticker, period):
    return load(ticker, period)


@st.cache_data(ttl=900, show_spinner="Buscando candles de 1 hora...")
def get_hourly(ticker):
    return load_hourly(ticker)


@st.cache_data(ttl=600, show_spinner="Buscando o mercado...")
def get_market(tickers):
    close, vol = load_market(list(tickers) + ["^BVSP"])
    return market_summary(close, vol)


@st.cache_data(ttl=1800, show_spinner="Buscando candles dos ativos...")
def get_ohlc(tickers):
    return load_ohlc_many(list(tickers), "3y")


# ============================================================================
# BARRA LATERAL
# ============================================================================
st.sidebar.title("Radar B3")
ticker = st.sidebar.text_input("Código do ativo", "PETR4").strip().upper()
kind_opt = st.sidebar.selectbox("Tipo do ativo", ["Automático", "Ação", "FII"],
                                help="Se um fundo imobiliário não for reconhecido sozinho, escolha FII.")
tf = st.sidebar.selectbox("Tempo gráfico", TIMEFRAMES, index=0,
                          help="Vale para o gráfico e a análise técnica. Semanal e mensal usam o histórico diário "
                               "(prefira 5y ou 10y); 1 hora vem do Yahoo, que entrega até ~2 anos.")
period = st.sidebar.selectbox("Histórico", ["2y", "3y", "5y", "10y"], index=2)
order = st.sidebar.slider("Sensibilidade de topos/fundos", 3, 12, 5,
                          help="Candles de cada lado para confirmar um topo/fundo. "
                               "Menor = mais pivôs (curto prazo); maior = só pivôs relevantes.")

st.sidebar.subheader("Pivôs e Fibonacci")
piv_period = st.sidebar.selectbox("Pivôs calculados sobre", list(PIVOT_FREQ), index=0,
                                  help="Semanal serve para swing trade; mensal, para posições mais longas; "
                                       "diário, para o gráfico de 1 hora.")
piv_variant = st.sidebar.selectbox("Fórmula dos pivôs", ["Clássico", "Fibonacci"],
                                   help="Clássico: P, R1-R3 e S1-S3 pelo high/low/close do período anterior. "
                                        "Fibonacci: níveis a 38,2%, 61,8% e 100% da amplitude.")
show_piv = st.sidebar.checkbox("Mostrar pivôs no gráfico", True)
piv_detail = st.sidebar.selectbox("Níveis de pivô no gráfico", ["P, R1-R2, S1-S2", "Todos (com R3 e S3)"],
                                  help="O primeiro deixa o gráfico mais limpo; R3 e S3 ficam longe do preço.")
show_fib = st.sidebar.checkbox("Mostrar alvos de projeção Fibonacci (61,8%, 100%, 161,8%)", True)
show_retr = st.sidebar.checkbox("Mostrar também as retrações", False,
                                help="Retrações de 38,2% a 78,6% da última perna. Ficam só nas tabelas se desligado.")

st.sidebar.subheader("Premissas de ações")
ke = st.sidebar.slider("Custo do capital próprio (Ke)", 0.08, 0.22, 0.14, 0.005, format="%.3f")
g_high = st.sidebar.slider("Crescimento do FCL (5 anos)", 0.0, 0.20, 0.08, 0.005, format="%.3f")
g_term = st.sidebar.slider("Crescimento perpétuo", 0.0, 0.08, 0.05, 0.005, format="%.3f",
                           help="Damodaran: nunca acima da taxa livre de risco da moeda.")
bz = st.sidebar.slider("Yield mínimo (Bazin)", 0.04, 0.12, 0.06, 0.005, format="%.3f")

st.sidebar.subheader("Premissas de FII")
vp_in = st.sidebar.number_input("VP por cota (R$)", min_value=0.0, value=0.0, step=0.01,
                                help="Valor patrimonial por cota, do relatório gerencial. "
                                     "Deixe 0 para tentar usar o dado do Yahoo.")
cdi = st.sidebar.slider("Renda fixa de referência (CDI, a.a.)", 0.05, 0.20, 0.12, 0.005, format="%.3f",
                        help="Atualize para o CDI atual. Usado para comparar o rendimento do fundo.")


# ============================================================================
# TRECHOS REUTILIZÁVEIS
# ============================================================================
PIV_COLOR = {"R": "#d6453d", "S": "#1a9e6e", "P": "#f2a900"}


def make_chart(tec, trade=None):
    """Candles + médias + topos/fundos + pivôs clássicos + Fibonacci (retração e projeção) + entrada/stop/alvo."""
    d = tec["df"]
    hourly = len(d) > 2 and d.index.to_series().diff().median() < pd.Timedelta(hours=20)
    x_end = d.index[-1] + pd.Timedelta(days=2 if hourly else 12)
    fig = go.Figure()
    fig.add_candlestick(x=d.index, open=d.Open, high=d.High, low=d.Low, close=d.Close, name="Preço",
                        increasing_line_color="#1a9e6e", decreasing_line_color="#d6453d")
    for col, color in (("SMA20", "#f2a900"), ("SMA50", "#3b82f6"), ("SMA200", "#8b5cf6")):
        fig.add_scatter(x=d.index, y=d[col], name=col.replace("SMA", "Média "), line=dict(color=color, width=1.4))
    if tec["highs"]:
        fig.add_scatter(x=[d.index[i] for i, _ in tec["highs"]], y=[p for _, p in tec["highs"]], mode="markers",
                        name="Topos", marker=dict(symbol="triangle-down", size=9, color="#d6453d"))
    if tec["lows"]:
        fig.add_scatter(x=[d.index[i] for i, _ in tec["lows"]], y=[p for _, p in tec["lows"]], mode="markers",
                        name="Fundos", marker=dict(symbol="triangle-up", size=9, color="#1a9e6e"))

    drawn = []

    def hline(y, color, label, x0=None, dash="dot", width=1.1):
        drawn.append(y)
        fig.add_shape(type="line", x0=x0 if x0 is not None else d.index[0], x1=x_end, y0=y, y1=y,
                      line=dict(color=color, width=width, dash=dash))
        fig.add_annotation(x=x_end, y=y, text=label, showarrow=False, xanchor="right", yanchor="bottom",
                           font=dict(size=10, color=color))

    piv = tec.get("piv")
    if show_piv and piv:
        variant = "classic" if piv_variant == "Clássico" else "fib"
        keep = ("R2", "R1", "P", "S1", "S2") if piv_detail.startswith("P,") else ("R3", "R2", "R1", "P", "S1", "S2", "S3")
        for k, v in piv[variant].items():
            if v > 0 and k in keep:
                hline(v, PIV_COLOR[k[0]], f"{k} {num(v)}", x0=piv["start"],
                      dash="solid" if k == "P" else "dash", width=1.4 if k == "P" else 1.0)

    fib = tec.get("fib")
    if show_fib and fib:
        fig.add_scatter(x=[d.index[i] for i, _ in fib["pts"]], y=[p for _, p in fib["pts"]], mode="lines+markers+text",
                        text=[f"Ponto {k}" for k in range(1, len(fib["pts"]) + 1)], textposition="top center",
                        textfont=dict(size=10, color="#9ca3af"),
                        name="Pontos 1-2-3 (Fibonacci)", line=dict(color="#6b7280", width=1.2, dash="dot"),
                        marker=dict(size=5, color="#6b7280"))
        if len(fib["pts"]) == 3:  # confirmação do pivô: rompimento do Ponto 2
            i2, p2 = fib["pts"][1]
            hline(p2, "#9ca3af", f"Confirmação do pivô · {num(p2)}", x0=d.index[i2], width=0.9)
        x0 = d.index[fib["pts"][-1][0]]
        pct_ = lambda r: f"{r * 100:g}".replace(".", ",") + "%"  # noqa: E731
        for r, p in fib["proj"]:
            hline(p, "#a855f7", f"Alvo {pct_(r)} · {num(p)}", x0=x0, width=1.4)
        if show_retr:
            for r, p in fib["retr"]:
                hline(p, "#0ea5e9", f"Ret. {pct_(r)} · {num(p)}", x0=x0, width=0.8)

    if trade:
        hline(trade["Entrada"], "#3b82f6", f"Entrada {num(trade['Entrada'])}")
        hline(trade["Stop"], "#d6453d", f"Stop {num(trade['Stop'])}")
        hline(trade["Alvo"], "#1a9e6e", f"Alvo {num(trade['Alvo'])}")
    else:
        for s in tec["setups"]:
            if s["Entrada"]:
                hline(s["Entrada"], "#3b82f6", f"Entrada · {s['Setup']}")
                hline(s["Stop"], "#d6453d", "Stop")
                hline(s["Alvo"], "#1a9e6e", "Alvo")
                break
    fig.update_layout(height=640, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10),
                      legend=dict(orientation="h", y=1.02),
                      xaxis=dict(rangebreaks=[dict(bounds=["sat", "mon"])]
                                 + ([dict(bounds=[17, 10], pattern="hour")] if hourly else [])))
    fig.update_xaxes(range=[d.index[-min(len(d), 320)], x_end])
    vis = d.iloc[-min(len(d), 320):]
    lo_, hi_ = min([float(vis.Low.min())] + drawn), max([float(vis.High.max())] + drawn)
    pad = (hi_ - lo_) * 0.04
    fig.update_yaxes(range=[lo_ - pad, hi_ + pad])
    return fig


def render_levels(tec):
    piv, fib, d = tec["piv"], tec["fib"], tec["df"]
    last = float(d.Close.iloc[-1])
    dist = lambda v: (v / last - 1) * 100  # noqa: E731

    st.subheader("Pivôs clássicos")
    with st.expander("O que são pivôs clássicos?"):
        st.markdown(
            "Também chamados de *floor pivots* (pivôs de pregão): níveis de suporte e resistência calculados "
            "com a **máxima (H), mínima (L) e fechamento (C) do período anterior**. Valem para o período atual.\n\n"
            "- **P** = (H + L + C) / 3: o ponto central. Acima dele o viés é de alta; abaixo, de baixa.\n"
            "- **R1** = 2P − L · **S1** = 2P − H\n"
            "- **R2** = P + (H − L) · **S2** = P − (H − L)\n"
            "- **R3** = H + 2(P − L) · **S3** = L − 2(H − P)\n\n"
            "A **variante Fibonacci** mantém o P e põe os níveis a 38,2%, 61,8% e 100% da amplitude (H − L): "
            "R1/S1 = P ± 0,382·(H−L), R2/S2 = P ± 0,618·(H−L), R3/S3 = P ± 1,0·(H−L).\n\n"
            "Para swing trade use os pivôs **semanais**; para posições mais longas, os **mensais** "
            "(troque na barra lateral)."
        )
    if piv is None:
        st.info("Histórico curto demais para calcular pivôs.")
    else:
        st.caption(f"Base: período anterior ({piv['prev_start']:%d/%m/%Y}) com máxima {brl(piv['H'])}, "
                   f"mínima {brl(piv['L'])} e fechamento {brl(piv['C'])}. Valem desde {piv['start']:%d/%m/%Y}.")
        rows = [{"Nível": k, "Clássico": piv["classic"][k], "Dist. (%)": dist(piv["classic"][k]),
                 "Fibonacci": piv["fib"][k], "Dist. Fib (%)": dist(piv["fib"][k])}
                for k in ("R3", "R2", "R1", "P", "S1", "S2", "S3")]
        st.dataframe(pd.DataFrame(rows), hide_index=True, column_config={
            "Clássico": st.column_config.NumberColumn(format="%.2f"),
            "Fibonacci": st.column_config.NumberColumn(format="%.2f"),
            "Dist. (%)": st.column_config.NumberColumn(format="%+.1f"),
            "Dist. Fib (%)": st.column_config.NumberColumn(format="%+.1f")})

    st.subheader("Fibonacci sobre topos e fundos")
    if fib is None:
        st.info("Ainda não há dois pivôs confirmados para traçar Fibonacci. Diminua a sensibilidade na barra lateral.")
    else:
        (_, pa), (_, pb), (_, pc) = (fib["pts"][-3:] if len(fib["pts"]) == 3 else [(0, 0)] + fib["pts"])
        st.caption(
            f"Pontos 1-2-3: {brl(pa)} → {brl(pb)} → {brl(pc)}. Última perna (2→3): **{fib['dir_last']}**. Retração = até onde o preço pode voltar "
            "dessa perna. " + (f"Projeção = repete a perna anterior ({brl(pa)} → {brl(pb)}, **{fib['dir_proj']}**) "
                               f"a partir de {brl(pc)}: alvos em 61,8%, 100% e 161,8%." if fib["proj"] else ""))
        a, b = st.columns(2)
        a.markdown("**Retrações**")
        a.dataframe(pd.DataFrame([{"Razão": fmt_ratio(r), "Preço": p, "Dist. (%)": dist(p)} for r, p in fib["retr"]]),
                    hide_index=True, column_config={"Preço": st.column_config.NumberColumn(format="%.2f"),
                                                    "Dist. (%)": st.column_config.NumberColumn(format="%+.1f")})
        b.markdown("**Projeções**")
        if fib["proj"]:
            b.dataframe(pd.DataFrame([{"Razão": fmt_ratio(r), "Preço": p, "Dist. (%)": dist(p)} for r, p in fib["proj"]]),
                        hide_index=True, column_config={"Preço": st.column_config.NumberColumn(format="%.2f"),
                                                        "Dist. (%)": st.column_config.NumberColumn(format="%+.1f")})
        else:
            b.caption("São necessários três pivôs para projetar.")

    conf = confluences(tec, "classic" if piv_variant == "Clássico" else "fib")
    st.subheader("Confluências")
    if conf:
        st.dataframe(pd.DataFrame(conf), hide_index=True,
                     column_config={"Zona": st.column_config.NumberColumn(format="%.2f")})
        st.caption("Zonas onde pivô, Fibonacci e/ou média móvel caem a menos de meio ATR uma da outra: "
                   "tendem a ser suportes/resistências mais relevantes.")
    else:
        st.caption("Nenhuma confluência perto agora.")
    st.caption("Níveis mecânicos e educacionais. Não são recomendação de investimento.")


def render_swing():
    st.subheader("Ações boas para swing trade: tendência de alta e de baixa")
    c1, c2 = st.columns(2)
    hz_key = c1.radio("Horizonte", list(HORIZONS), format_func=lambda k: HORIZONS[k]["nome"], horizontal=True,
                      help="Swing: pivôs semanais e topos/fundos de curto prazo. "
                           "Longo prazo: pivôs mensais, topos/fundos mais relevantes e stops mais largos.")
    min_liq = c2.number_input("Liquidez mínima (R$ milhões/dia)", 0.0, 500.0, 5.0, 1.0,
                              help="Média de volume financeiro dos últimos 60 pregões.")
    txt = st.text_area("Ativos analisados (separe por vírgula ou espaço; pode editar)", ", ".join(MAIN_TICKERS),
                       height=90, key="swing_txt")
    if st.button("Buscar oportunidades", key="swing_go"):
        tks = tuple(dict.fromkeys(t for t in re.split(r"[,\s;]+", txt.upper()) if t))
        try:
            data_ = get_ohlc(tks)
            table, skipped = scan_swing(data_, hz_key)
            st.session_state["swing"] = {"table": table, "skipped": skipped, "data": data_, "hz": hz_key}
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
    res = st.session_state.get("swing")
    if res is None:
        st.info("Clique em **Buscar oportunidades** para analisar a lista (leva alguns segundos).")
        return
    if res["hz"] != hz_key:
        st.warning("O horizonte mudou: clique em **Buscar oportunidades** de novo para recalcular.")
    hz, table = HORIZONS[res["hz"]], res["table"]
    if table.empty:
        st.warning("Nenhum ativo com histórico suficiente (precisa de mais de 230 pregões).")
        return
    table = table[table["Liquidez (R$ mi/dia)"] >= min_liq]
    min_score = st.slider("Score mínimo", 0, 10, 6, help="Soma de pontos: tendência pelas médias, topos/fundos, "
                          "IFR, proximidade de suporte/resistência (médias, pivôs, Fibonacci) e alvo técnico.")
    good = table[table["Score"] >= min_score]
    up, dn = good[good["Direção"] == "Alta"], good[good["Direção"] == "Queda"]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Analisados", len(table))
    k2.metric("Alta (compra)", len(up))
    k3.metric("Queda (venda)", len(dn))
    k4.metric("Fora da lista", len(res["skipped"]), help=", ".join(res["skipped"]) or None)

    cols = ["Ativo", "Score", "Médias 20/50/200", "Sinal do gráfico", "Preço", "IFR", "Stop", "Risco (%)", "Alvo",
            "R/R", "Alvo em", "Motivos"]
    cfg = {"Score": st.column_config.ProgressColumn(min_value=0, max_value=10, format="%d"),
           "Preço": st.column_config.NumberColumn(format="%.2f"), "IFR": st.column_config.NumberColumn(format="%.0f"),
           "Stop": st.column_config.NumberColumn(format="%.2f"), "Alvo": st.column_config.NumberColumn(format="%.2f"),
           "R/R": st.column_config.NumberColumn(format="%.1f"),
           "Risco (%)": st.column_config.NumberColumn(format="%.1f")}
    t_up, t_dn, t_all = st.tabs(["Alta (compra)", "Queda (venda)", "Todas"])
    with t_up:
        st.caption("Tendência de alta: entrada em recuo a suporte (média, pivô, Fibonacci) com stop abaixo dele.")
        st.dataframe(up.sort_values("Score", ascending=False)[cols], hide_index=True, column_config=cfg)
    with t_dn:
        st.caption("Tendência de baixa: repique até resistência com stop acima. Vender a descoberto exige aluguel "
                   "de ações (BTC) e tem risco ilimitado; sem isso, use como lista de ativos a evitar.")
        st.dataframe(dn.sort_values("Score", ascending=False)[cols], hide_index=True, column_config=cfg)
    with t_all:
        st.dataframe(table.sort_values("Score", ascending=False)[["Direção"] + cols], hide_index=True, column_config=cfg)

    pick_pool = good if len(good) else table
    st.markdown("**Ver gráfico com pivôs, Fibonacci, entrada, stop e alvo**")
    pick = st.selectbox("Ativo", list(pick_pool.sort_values("Score", ascending=False)["Ativo"]))
    row = table[table["Ativo"] == pick].iloc[0]
    tec_p = technical(res["data"][pick], hz["order"], hz["freq"])
    st.plotly_chart(make_chart(tec_p, {"Entrada": row["Entrada (ref.)"], "Stop": row["Stop"], "Alvo": row["Alvo"]}))
    st.markdown(f"**{pick} · {row['Direção']}** · score {row['Score']}/10 · stop em {row['Stop em']} · "
                f"alvo em {row['Alvo em']} · R/R {num(row['R/R'], 1)}")
    for m in row["Motivos"].split("; "):
        if m:
            st.markdown(f"- {m}")
    st.caption("Triagem mecânica e educacional: o score mede alinhamento de sinais, não garante resultado. "
               "Confira notícias, resultados e liquidez antes de operar. Não é recomendação de investimento.")


def render_market():
    st.subheader("Mercado hoje: principais ações")
    txt = st.text_area("Ativos do painel (separe por vírgula ou espaço; pode editar)",
                       ", ".join(MAIN_TICKERS), height=100)
    if st.button("Carregar / atualizar painel"):
        tks = tuple(dict.fromkeys(t for t in re.split(r"[,\s;]+", txt.upper()) if t))
        try:
            st.session_state["mkt"] = get_market(tks)
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
    res = st.session_state.get("mkt")
    if res is None:
        st.info("Clique em **Carregar / atualizar painel** para buscar os fechamentos (leva alguns segundos).")
        return
    table, ref_date = res
    ibov = table[table["Ativo"] == "^BVSP"]
    tbl = table[table["Ativo"] != "^BVSP"].reset_index(drop=True)
    if tbl.empty:
        st.warning("Nenhum ativo retornou dados.")
        return

    st.caption(f"Último pregão nos dados: {ref_date:%d/%m/%Y}. Fechamentos como cotados na bolsa. "
               "Se o pregão de hoje ainda não fechou, o painel mostra o último candle disponível.")
    k1, k2, k3, k4 = st.columns(4)
    if len(ibov):
        k1.metric("Ibovespa", num(ibov["Fechamento (R$)"].iloc[0], 0), f"{ibov['Var. dia (%)'].iloc[0]:+.2f}%")
    k2.metric("Ativos em alta", int((tbl["Var. dia (%)"] > 0).sum()))
    k3.metric("Ativos em queda", int((tbl["Var. dia (%)"] < 0).sum()))
    k4.metric("Ativos no painel", len(tbl))

    cfg = {
        "Fechamento (R$)": st.column_config.NumberColumn(format="%.2f"),
        "Var. dia (%)": st.column_config.NumberColumn(format="%+.2f"),
        "Var. 5 dias (%)": st.column_config.NumberColumn(format="%+.2f"),
        "vs máx. 52s (%)": st.column_config.NumberColumn(format="%.1f"),
        "vs mín. 52s (%)": st.column_config.NumberColumn(format="%.1f"),
        "Volume (R$ mi)": st.column_config.NumberColumn(format="%.1f"),
    }
    cols = ["Ativo", "Fechamento (R$)", "Var. dia (%)", "Var. 5 dias (%)", "Volume (R$ mi)"]
    a, b = st.columns(2)
    a.subheader("Maiores altas do dia")
    a.dataframe(tbl.nlargest(10, "Var. dia (%)")[cols], hide_index=True, column_config=cfg)
    b.subheader("Maiores quedas do dia")
    b.dataframe(tbl.nsmallest(10, "Var. dia (%)")[cols], hide_index=True, column_config=cfg)

    top = pd.concat([tbl.nlargest(8, "Var. dia (%)"), tbl.nsmallest(8, "Var. dia (%)")]) \
        .drop_duplicates("Ativo").sort_values("Var. dia (%)")
    fig_m = go.Figure(go.Bar(x=top["Var. dia (%)"], y=top["Ativo"], orientation="h",
                             marker_color=np.where(top["Var. dia (%)"] >= 0, "#1a9e6e", "#d6453d")))
    fig_m.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10), xaxis_title="Variação no dia (%)")
    st.plotly_chart(fig_m)

    st.subheader("Perto da máxima e da mínima de 52 semanas")
    c1, c2 = st.columns(2)
    cols2 = ["Ativo", "Fechamento (R$)", "vs máx. 52s (%)", "vs mín. 52s (%)"]
    c1.markdown("**Mais perto da máxima do ano**")
    c1.dataframe(tbl.nlargest(8, "vs máx. 52s (%)")[cols2], hide_index=True, column_config=cfg)
    c2.markdown("**Mais perto da mínima do ano**")
    c2.dataframe(tbl.nsmallest(8, "vs mín. 52s (%)")[cols2], hide_index=True, column_config=cfg)

    with st.expander("Tabela completa"):
        st.dataframe(tbl.sort_values("Var. dia (%)", ascending=False), hide_index=True, column_config=cfg)


def render_dividends(da, fii):
    if da is None:
        st.info("Sem histórico de proventos nos dados carregados para este ativo.")
        return
    st.subheader("Proventos")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Yield 12 meses", pct(da["yield12"]))
    m2.metric("Proventos 12 meses", brl(da["div12"]) + (" /cota" if fii else " /ação"))
    if fii:
        m3.metric("Média por mês", brl(da["div12"] / 12))
    else:
        m3.metric("Payout", pct(da["payout"], 0) if da["payout"] is not None else "—")
    m4.metric("Último pagamento", brl(da["last_value"]), f"{da['last_date']:%d/%m/%Y}", delta_color="off")
    m5.metric("Pagamentos em 12m", da["n12"])

    by_year = da["by_year"].tail(10)
    labels = [f"{y}" + (" (parcial)" if y == da["cur_year"] else "") for y in by_year.index]
    fig_y = go.Figure(go.Bar(x=labels, y=by_year.values, marker_color="#1a9e6e"))
    fig_y.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10), title="Proventos por ano (R$ por cota/ação)")
    st.plotly_chart(fig_y)

    if fii:
        mo = da["monthly"].tail(24)
        fig_mo = go.Figure(go.Bar(x=[str(p) for p in mo.index], y=mo.values, marker_color="#3b82f6"))
        fig_mo.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10),
                             title="Proventos por mês (últimos 24 meses)")
        st.plotly_chart(fig_mo)

    st.subheader("Leitura")
    for status, text in da["readings"]:
        st.markdown(f"{ICON[status]} {text}")
    if da["avg5_yield"] is not None:
        st.caption(f"Média anual dos últimos anos fechados sobre o preço de hoje: {pct(da['avg5_yield'])}. "
                   "Proventos passados não garantem os futuros.")

    st.subheader("Últimos pagamentos")
    last = da["last"].rename("Valor (R$)").reset_index()
    last.columns = ["Data", "Valor (R$)"]
    last["Data"] = pd.to_datetime(last["Data"]).dt.strftime("%d/%m/%Y")
    st.dataframe(last, hide_index=True,
                 column_config={"Valor (R$)": st.column_config.NumberColumn(format="%.4f")})
    st.caption("Datas e valores do Yahoo Finance (data ex). Inclui juros sobre capital próprio (valores brutos).")


def render_fii(fa):
    st.subheader("Vale a pena comprar este FII?")
    box = {"good": st.success, "mid": st.warning, "bad": st.error}[fa["tone"]]
    box(f"**{fa['verdict']}** · {fa['score']} de {fa['max']} pontos possíveis")
    mt = fa["metrics"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("P/VP", num(mt["pvp"]) if mt["pvp"] else "—",
              f"{mt['premio'] * 100:+.0f}% vs patrimônio" if mt["premio"] is not None else None,
              delta_color="inverse")
    c2.metric("Yield 12m", pct(mt["dy12"]), f"CDI líq. {pct(mt['cdi_liq'])}", delta_color="off")
    c3.metric("Média por mês", brl(mt["avg_month"]) + " /cota" if mt["avg_month"] else "—")
    c4.metric("Volatilidade anual", pct(mt["vol"], 0))

    rows = pd.DataFrame([{"": ICON[c["Status"]], "Critério": c["Critério"], "Valor": c["Valor"],
                          "Leitura": c["Comentário"], "Pontos": f"{c['Pontos']:+d} / {c['Máx.']}"}
                         for c in fa["criteria"]])
    st.dataframe(rows, hide_index=True)

    st.markdown("**O que este app não enxerga: confira no relatório gerencial mais recente**")
    st.markdown(
        "- **Tipo do fundo:** tijolo (imóveis), papel (CRIs/recebíveis) ou fundo de fundos; o risco muda muito.\n"
        "- **Vacância e inadimplência:** vacância física/financeira alta ou crescente é sinal de alerta.\n"
        "- **Concentração:** poucos imóveis, inquilinos ou devedores em grande parte da receita.\n"
        "- **Vencimento dos contratos e reajustes:** contratos longos (atípicos) dão previsibilidade.\n"
        "- **Alavancagem e liquidez do portfólio**, **taxas de gestão** e **resultado recorrente vs. "
        "não recorrente** (ganhos de capital pontuais inflam o dividendo).\n"
        "- **Valor patrimonial real:** o P/VP depende de o VP refletir o valor de mercado dos ativos."
    )
    st.caption("Pontuação mecânica para triagem. Não é recomendação de investimento.")


# ============================================================================
# CARREGA O ATIVO
# ============================================================================
try:
    data = get(ticker, period)
except Exception as e:  # noqa: BLE001
    st.error(str(e))
    st.divider()
    t_sw, t_mk = st.tabs(["Swing trade", "Mercado hoje"])
    with t_sw:
        render_swing()
    with t_mk:
        render_market()
    st.stop()

df, info, divs = data["df"], data["info"], data["divs"]
price = float(df.Close.iloc[-1])
last_date = df.index[-1]

fii = {"FII": True, "Ação": False}.get(kind_opt, None)
if fii is None:
    fii = is_fii(ticker, info, divs, last_date)

vp = vp_in if vp_in > 0 else (info.get("bookValue") or info.get("navPrice") if fii else None)
try:
    df_tf = get_hourly(ticker) if tf == "1 hora" else to_timeframe(df, tf)
except Exception as e:  # noqa: BLE001
    st.warning(f"{e} Mostrando o diário.")
    df_tf, tf = df, "Diário"
tec = technical(df_tf, order, PIVOT_FREQ[piv_period])
al = tec["align"]
val = None if fii else valuation(price, info, divs, last_date, ke, g_high, g_term, bz)
da = dividends_analysis(divs, price, info.get("trailingEps") if not fii else None, last_date)
fa = fii_analysis(price, divs, df, last_date, vp, cdi, tec["tone"]) if fii else None

st.title(f"{ticker} · {info.get('longName', '')}")
st.caption(f"{'Fundo imobiliário (FII)' if fii else info.get('sector', '')} · último candle: {last_date:%d/%m/%Y}"
           + (" · tipo detectado automaticamente" if kind_opt == "Automático" else "")
           + f" · gráfico: {tf.lower()}")
if len(df_tf) < 200:
    st.caption(f"Só {len(df_tf)} candles no tempo gráfico {tf.lower()}: a média de 200 não aparece. "
               "Aumente o histórico na barra lateral.")

# ============================================================================
# RESUMO
# ============================================================================
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Preço", brl(price))
if fii:
    c2.metric("FII", fa["verdict"].split(" – ")[0], f"{fa['score']}/{fa['max']} pontos", delta_color="off")
else:
    c2.metric("Valuation", val["label"],
              f"{pct(val['margin'], 0)} vs preço justo" if val["margin"] is not None else None)
c3.metric("Gráfico", tec["verdict"])
c4.metric("Médias 20/50/200",
          {"alta": "Alta clara", "baixa": "Baixa clara", "misto": "Misturadas"}[al["estado"]])
c5.metric("Topos/fundos", tec["ctx"]["Estrutura de topos/fundos"])

if fii:
    if fa["tone"] == "good" and tec["tone"] in FAVORABLE:
        st.success("Fundamentos atrativos pela triagem e gráfico favorável.")
    elif fa["tone"] == "good" and tec["tone"] in UNFAVORABLE:
        st.warning("Triagem boa, mas o gráfico está em queda: considere esperar sinal de reversão.")
    elif fa["tone"] == "bad":
        st.error("A triagem não achou atrativos suficientes agora (preço, renda ou constância).")
    else:
        st.info("Triagem neutra: veja o detalhamento na aba do FII e confira o relatório gerencial.")
else:
    cheap = val["margin"] is not None and val["margin"] >= 0.10
    dear = val["margin"] is not None and val["margin"] <= -0.10
    if cheap and tec["tone"] in FAVORABLE:
        st.success("Barata e com gráfico favorável (tendência de alta ou sinais de fundo): candidata a observação de entrada.")
    elif cheap and tec["tone"] in UNFAVORABLE:
        st.warning("Barata, mas o gráfico ainda está em baixa: o risco é a 'barata que fica mais barata'. "
                   "Aguarde confirmação de reversão.")
    elif dear and tec["tone"] in ("bear", "bear-weak"):
        st.error("Cara e com sinais de topo/reversão de baixa: cenário de cautela.")
    elif dear:
        st.warning("Cara pelos métodos usados, mesmo com gráfico favorável: cuidado com preço.")
    else:
        st.info("Sem alinhamento claro entre valuation e gráfico.")

if fii:
    tabs = st.tabs(["FII: vale a pena?", "Dividendos", "Pontos de entrada", "Análise técnica",
                    "Pivôs e Fibonacci", "Swing trade", "Dados", "Mercado hoje"])
    tab_fii, tab_div, tab_res, tab_tec, tab_lvl, tab_swing, tab_dados, tab_mkt = tabs
    tab_val = None
else:
    tabs = st.tabs(["Pontos de entrada", "Valuation", "Dividendos", "Análise técnica",
                    "Pivôs e Fibonacci", "Swing trade", "Dados", "Mercado hoje"])
    tab_res, tab_val, tab_div, tab_tec, tab_lvl, tab_swing, tab_dados, tab_mkt = tabs
    tab_fii = None

# ---------------- gráfico (compartilhado) ----------------
fig = make_chart(tec)

# ---------------- pontos de entrada ----------------
with tab_res:
    st.plotly_chart(fig)
    st.subheader("Possíveis pontos de entrada")
    st.dataframe(pd.DataFrame(tec["setups"])[["Setup", "Entrada", "Stop", "Alvo", "R/R", "Obs"]], hide_index=True)
    st.caption("Sugestões mecânicas e educacionais, baseadas em topos/fundos, médias e ATR. "
               "Não são recomendação de investimento.")
    l1, l2 = st.columns(2)
    fmt = lambda v: f"{v[0]}: {num(v[1])}" if isinstance(v, tuple) else num(v)  # noqa: E731
    l1.markdown("**Suportes:** " + (" · ".join(fmt(v) for v in tec["levels"]["suportes"]) or "—"))
    l2.markdown("**Resistências:** " + (" · ".join(fmt(v) for v in tec["levels"]["resistências"]) or "—"))

# ---------------- valuation (ações) ----------------
if tab_val is not None:
    with tab_val:
        st.subheader("Preço justo por método")
        rows = pd.DataFrame(val["rows"])
        rows["Preço justo"] = rows["Preço justo"].map(brl)
        rows["Margem vs preço"] = rows["Margem vs preço"].map(lambda x: pct(x, 0))
        st.dataframe(rows, hide_index=True)
        st.markdown(f"**Consenso (mediana de {val['n_methods']} método(s)):** {brl(val['consensus'])} "
                    f"→ **{val['label']}**")
        st.subheader("Indicadores")
        m = val["metrics"]
        fm = {"P/L": num, "P/VP": num, "EV/EBITDA": num, "ROE": pct, "Margem líquida": pct,
              "Dividend yield 12m": pct, "Earnings yield (1/PL)": pct, "Dívida líquida/EBITDA": num}
        st.dataframe(pd.DataFrame({"Indicador": list(m), "Valor": [fm[k](v) for k, v in m.items()]}),
                     hide_index=True)
        st.caption("Graham e Bazin não servem bem para empresas sem lucro ou sem dividendos. O DCF usa o fluxo "
                   "de caixa livre atual; para bancos e seguradoras ele não é confiável (use P/VP e ROE). "
                   "Ajuste as premissas na barra lateral: o resultado é muito sensível a elas.")

# ---------------- FII ----------------
if tab_fii is not None:
    with tab_fii:
        render_fii(fa)

# ---------------- dividendos ----------------
with tab_div:
    render_dividends(da, fii)

# ---------------- análise técnica ----------------
with tab_tec:
    st.subheader("Tendência pelas médias 20, 50 e 200")
    if al["estado"] == "alta":
        st.success(f"**Tendência de ALTA clara:** média 20 acima da 50 e a 50 acima da 200, "
                   f"alinhadas há {al['sequencia']} candles. A média 20 está {pct(al['spread_20_200'])} acima da 200.")
    elif al["estado"] == "baixa":
        st.error(f"**Tendência de BAIXA clara:** média 20 abaixo da 50 e a 50 abaixo da 200, "
                 f"alinhadas há {al['sequencia']} candles. A média 20 está {pct(abs(al['spread_20_200']))} abaixo da 200.")
    elif not al["valid"]:
        st.info("Histórico curto demais para calcular a média de 200. Escolha um período maior na barra lateral.")
    else:
        st.info("**Médias misturadas, sem tendência clara.** Alta clara = 20 > 50 > 200; baixa clara = 20 < 50 < 200.")
    ma = pd.DataFrame({"Média": ["20", "50", "200"],
                       "Valor": [brl(al["SMA20"]), brl(al["SMA50"]), brl(al["SMA200"])],
                       "Preço vs média": [pct(tec["ctx"]["vs SMA20"]), pct(tec["ctx"]["vs SMA50"]),
                                          pct(tec["ctx"]["vs SMA200"])]})
    st.dataframe(ma, hide_index=True)

    ca, cb = st.columns(2)
    ca.subheader(f"Sinais de reversão de ALTA (pontos: {tec['bull_score']})")
    for t, w in tec["bull"]:
        ca.markdown(f"- {t} *(+{w})*")
    if not tec["bull"]:
        ca.caption("Nenhum sinal no momento.")
    cb.subheader(f"Sinais de reversão de BAIXA (pontos: {tec['bear_score']})")
    for t, w in tec["bear"]:
        cb.markdown(f"- {t} *(+{w})*")
    if not tec["bear"]:
        cb.caption("Nenhum sinal no momento.")
    st.subheader("Contexto")
    x = tec["ctx"]
    st.dataframe(pd.DataFrame({
        "Medida": ["Máx. 52 sem.", "Mín. 52 sem.", "Dist. da máxima", "Dist. da mínima", "IFR(14)"],
        "Valor": [brl(x["Máx. 52 sem."]), brl(x["Mín. 52 sem."]), pct(x["Distância da máxima"]),
                  pct(x["Distância da mínima"]), num(x["IFR(14)"], 1)]}), hide_index=True)
    st.caption("Reversão de alta = quebra de topo descendente, fundo ascendente, cruzamento de médias, "
               "divergência de IFR. A pontuação soma esses sinais; ≥4 pontos vira 'possível fundo/topo'. "
               "Uma tendência clara pelas médias só é rebaixada se houver 2+ pontos de sinais contrários.")

# ---------------- pivôs e Fibonacci ----------------
with tab_lvl:
    render_levels(tec)

# ---------------- swing trade ----------------
with tab_swing:
    render_swing()

# ---------------- dados ----------------
with tab_dados:
    st.dataframe(df.tail(60).iloc[::-1])
    st.caption("Fonte: Yahoo Finance via yfinance. Dados fundamentalistas do Yahoo para ativos brasileiros "
               "podem estar incompletos ou defasados; confira nos RI das empresas e nos relatórios dos fundos.")

# ---------------- mercado ----------------
with tab_mkt:
    render_market()
