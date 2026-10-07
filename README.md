# Radar B3

Digite o código de uma ação ou FII da B3 (ex.: PETR4, VALE3, HGLG11) e veja:

- **Valuation (ações):** preço justo por Graham, Bazin e DCF simplificado (estilo Damodaran), consenso e classificação (barata / justa / cara), mais P/L, P/VP, EV/EBITDA, ROE, dividend yield.
- **FII: vale a pena?** Checklist com P/VP, rendimento vs CDI líquido, constância dos pagamentos, tendência do dividendo, liquidez e momento do gráfico, com veredito. Informe o VP por cota na barra lateral para o P/VP.
- **Dividendos:** yield, payout, histórico por ano e por mês, crescimento, anos seguidos pagando e últimos pagamentos.
- **Análise técnica:** candles, médias de 20/50/200, topos e fundos, sinais de reversão e **tendência clara pelas médias** (20 > 50 > 200 = alta; 20 < 50 < 200 = baixa).
- **Tempo gráfico:** diário, semanal, mensal e 1 hora (barra lateral). Vale para o gráfico e para a análise técnica; semanal e mensal são montados a partir do histórico diário (use 5y ou 10y) e o de 1 hora vem do Yahoo, que entrega até cerca de 2 anos.
- **Pontos de entrada:** rompimento e pullback, com stop, alvo e relação risco/retorno.
- **Pivôs clássicos e Fibonacci:** pivôs clássicos (*floor pivots*: P, R1–R3, S1–S3, calculados com máxima, mínima e fechamento da semana ou do mês anterior) e a variante Fibonacci (38,2%, 61,8% e 100% da amplitude), desenhados no gráfico. Também traça Fibonacci sobre os topos e fundos: **retrações** da última perna e **projeções** (AB=CD) com três alvos: 61,8%, 100% e 161,8% (as retrações ficam nas tabelas e podem ser ligadas no gráfico), mais as **confluências** entre pivôs, Fibonacci e médias.
- **Gráfico limpo:** escala logarítmica (ligada por padrão), eixos de tempo e preço com zoom livre (arraste para ampliar, role o mouse, duplo clique restaura). Por padrão mostra só os candles, a linha azul de entrada, a vermelha de stop e os alvos de Fibonacci (61,8%, 100% e 161,8%). Médias móveis, topos/fundos, pivôs e retrações são opcionais na barra lateral.
- **Swing trade:** triagem de uma lista de ações em **tendência de alta (compra)** e **de baixa (venda)**, para swing trade ou longo prazo. Cada ativo recebe um score de 0 a 10 (médias 20/50/200, topos e fundos, IFR, proximidade de suporte/resistência, alvo técnico) e uma sugestão de entrada, stop e alvo, com gráfico completo.
- **Mercado hoje:** painel das principais ações com maiores altas e quedas do dia, Ibovespa e ativos perto da máxima/mínima de 52 semanas. A lista de ativos é editável.

## Como rodar

```
pip install -r requirements.txt
streamlit run app.py
```

No Windows, se `pip` ou `streamlit` não forem reconhecidos, use `py -m pip install -r requirements.txt` e `py -m streamlit run app.py`.

Para testar sem internet com dados simulados: `DEMO=1 streamlit run app.py` (no Windows: `set DEMO=1` e depois o comando).

## Observações

- Dados via Yahoo Finance (yfinance). Os fundamentos de ativos brasileiros no Yahoo podem estar incompletos; confira nos RI das empresas e nos relatórios gerenciais dos fundos.
- O tipo (ação ou FII) é detectado sozinho; se errar, escolha na barra lateral.
- O DCF não serve para bancos e seguradoras. Use P/VP e ROE nesses casos.
- A análise de FII não enxerga vacância, inadimplência, tipo de fundo nem concentração: confira no relatório gerencial.
- Vender a descoberto (aba Swing trade, lado de queda) exige aluguel de ações e tem risco ilimitado; sem isso, use a lista de queda como ativos a evitar.
- Os pontos de entrada e as pontuações são mecânicos e educacionais, não recomendação de investimento.
