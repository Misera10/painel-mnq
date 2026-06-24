import streamlit as st
import pandas as pd
import numpy as np
import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh
import time

# Import local modules
from data_provider import (
    get_market_summary,
    get_ticker_data,
    calculate_indicators,
    calculate_daily_bias,
    get_macro_correlations,
    get_news_feed,
    get_economic_calendar,
    calculate_pivot_points
)
from risk_calculator import (
    get_mnq_specs,
    calculate_position_size,
    suggest_stops_targets,
    round_to_tick
)

# 1. PAGE CONFIGURATION
st.set_page_config(
    page_title="MNQ Trading Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inject custom CSS for premium dark-mode trading theme
st.markdown("""
<style>
    /* Dark Theme Core Styles */
    .stApp {
        background-color: #0d0f12;
        color: #e2e8f0;
    }
    
    /* Card Styles */
    .metric-card {
        background: rgba(18, 22, 28, 0.85);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 8px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.15);
        margin-bottom: 12px;
    }
    
    .metric-title {
        font-size: 0.85rem;
        color: #94a3b8;
        font-weight: 600;
        text-transform: uppercase;
        margin-bottom: 5px;
    }
    
    .metric-value {
        font-size: 1.6rem;
        font-weight: 700;
        font-family: 'Courier New', Courier, monospace;
        margin-bottom: 2px;
    }
    
    .metric-change {
        font-size: 0.85rem;
        font-weight: 600;
    }
    
    /* Bias Indicator styles */
    .bias-card {
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        margin-bottom: 15px;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.25);
    }
    
    .bias-title {
        font-size: 1rem;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #e2e8f0;
        margin-bottom: 8px;
        font-weight: 500;
    }
    
    .bias-label {
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: 0.5px;
        margin-bottom: 10px;
    }
    
    .bias-score {
        font-size: 0.95rem;
        font-weight: 600;
        opacity: 0.9;
    }
    
    /* Sidebar Styles */
    section[data-testid="stSidebar"] {
        background-color: #11141a !important;
        border-right: 1px solid rgba(255,255,255,0.05);
    }
    
    /* Table styling overrides */
    div[data-testid="stTable"] table {
        background-color: #12161c;
        color: #e2e8f0;
        border-collapse: collapse;
        border-radius: 6px;
        overflow: hidden;
    }
    
    /* Custom Headers */
    .section-header {
        font-size: 1.25rem;
        font-weight: 700;
        color: #38bdf8;
        border-bottom: 1px solid rgba(56, 189, 248, 0.2);
        padding-bottom: 5px;
        margin-top: 15px;
        margin-bottom: 12px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
</style>
""", unsafe_allow_html=True)

# 2. STATE MANAGEMENT & AUTO-REFRESH
if "refresh_counter" not in st.session_state:
    st.session_state.refresh_counter = 0

# Sidebar Settings
st.sidebar.markdown("### ⚙️ Configurações do Painel")

# Auto-refresh setup
auto_refresh_enabled = st.sidebar.checkbox("Auto-Atualizar (Tempo Real)", value=True)
if auto_refresh_enabled:
    refresh_interval = st.sidebar.selectbox(
        "Intervalo de Atualização",
        options=[10, 30, 60, 300],
        format_func=lambda x: f"{x} segundos" if x < 60 else f"{x//60} minutos",
        index=1 # 30 seconds default
    )
    st_autorefresh(interval=refresh_interval * 1000, key="market_data_refresh")
else:
    st.sidebar.info("Auto-atualização desativada.")

# Manual refresh button
if st.sidebar.button("🔄 Forçar Atualização"):
    st.session_state.refresh_counter += 1
    st.rerun()

# Display current time
current_time = datetime.datetime.now().strftime("%H:%M:%S")
st.sidebar.markdown(f"<div style='font-size:0.8rem; color:#64748b;'>Última leitura: {current_time}</div>", unsafe_allow_html=True)

# 3. LOAD DATA (NQ=F and indicators)
@st.cache_data(ttl=10)
def load_all_market_data():
    summary = get_market_summary()
    
    df_daily_nq = get_ticker_data("NQ=F", period="30d", interval="1d")
    df_15m_nq = get_ticker_data("NQ=F", period="5d", interval="15m")
    df_5m_nq = get_ticker_data("NQ=F", period="3d", interval="5m")
    
    # Calculate indicators
    df_15m_nq_ind = calculate_indicators(df_15m_nq)
    df_5m_nq_ind = calculate_indicators(df_5m_nq)
    df_daily_nq_ind = calculate_indicators(df_daily_nq)
    
    # News & Calendar
    news = get_news_feed()
    calendar = get_economic_calendar()
    corr = get_macro_correlations()
    
    # Bias
    bias = calculate_daily_bias(summary, df_daily_nq, df_15m_nq)
    
    return {
        "summary": summary,
        "df_daily_nq": df_daily_nq_ind,
        "df_15m_nq": df_15m_nq_ind,
        "df_5m_nq": df_5m_nq_ind,
        "news": news,
        "calendar": calendar,
        "corr": corr,
        "bias": bias
    }

with st.spinner("Conectando ao Yahoo Finance..."):
    try:
        data = load_all_market_data()
    except Exception as e:
        st.error(f"Erro ao carregar dados de mercado: {e}")
        st.info("Tentando reconectar...")
        time.sleep(2)
        st.rerun()

# 4. RENDER TOP METRICS BAR
summary = data["summary"]
nq_data = summary.get("NQ=F", {})
vix_data = summary.get("^VIX", {})
dxy_data = summary.get("DX-Y.NYB", {})
us10y_data = summary.get("^TNX", {})
es_data = summary.get("ES=F", {})

def get_card_html(label, price, change, pct_change, is_yield=False, points_mode=True):
    color = "#00c853" if change >= 0 else "#dd2c00"
    sign = "+" if change >= 0 else ""
    symbol = "%" if is_yield else ""
    
    if points_mode and not is_yield:
        price_str = f"{price:,.2f}"
        change_str = f"{sign}{change:,.2f}"
    else:
        price_str = f"{price:.3f}" if is_yield else f"{price:.2f}"
        change_str = f"{sign}{change:.3f}" if is_yield else f"{sign}{change:.2f}"
        
    return f"""
    <div class="metric-card">
        <div class="metric-title">{label}</div>
        <div class="metric-value">{price_str}{symbol}</div>
        <div class="metric-change" style="color: {color};">
            {change_str} ({sign}{pct_change:.2f}%)
        </div>
    </div>
    """

cols = st.columns(5)

with cols[0]:
    if nq_data:
        st.markdown(get_card_html("Nasdaq Futuros (NQ)", nq_data["price"], nq_data["change"], nq_data["pct_change"]), unsafe_allow_html=True)
with cols[1]:
    if es_data:
        st.markdown(get_card_html("S&P 500 Futuros (ES)", es_data["price"], es_data["change"], es_data["pct_change"]), unsafe_allow_html=True)
with cols[2]:
    if vix_data:
        st.markdown(get_card_html("Volatilidade (VIX)", vix_data["price"], vix_data["change"], vix_data["pct_change"], points_mode=False), unsafe_allow_html=True)
with cols[3]:
    if dxy_data:
        st.markdown(get_card_html("Dólar Index (DXY)", dxy_data["price"], dxy_data["change"], dxy_data["pct_change"], points_mode=False), unsafe_allow_html=True)
with cols[4]:
    if us10y_data:
        st.markdown(get_card_html("Juros EUA 10A (US10Y)", us10y_data["price"], us10y_data["change"], us10y_data["pct_change"], is_yield=True), unsafe_allow_html=True)


# 5. SIDEBAR CALCULATOR & RISK MANAGEMENT
st.sidebar.markdown("<div class='section-header'>🧮 Calculadora de Risco MNQ</div>", unsafe_allow_html=True)

specs = get_mnq_specs()
st.sidebar.markdown(
    f"<div style='font-size:0.75rem; background:rgba(255,255,255,0.03); padding:8px; border-radius:5px; border:1px solid rgba(255,255,255,0.05); margin-bottom:10px;'>"
    f"<b>Especificações MNQ:</b><br>"
    f"• 1 Ponto = US$ {specs['multiplier']:.2f}<br>"
    f"• Tick Mínimo = {specs['tick_size']} (US$ {specs['tick_value']:.2f})<br>"
    f"• Margem Intraday aprox. = US$ {specs['intraday_margin']:.2f}"
    f"</div>", 
    unsafe_allow_html=True
)

account_balance = st.sidebar.number_input("Saldo da Conta (USD)", min_value=100.0, value=10000.0, step=500.0, format="%.2f")
risk_pct = st.sidebar.slider("Risco por Operação (%)", min_value=0.25, max_value=5.0, value=1.0, step=0.25)

atr_value = 15.0
if not data["df_15m_nq"].empty:
    atr_value = data["df_15m_nq"]['ATR'].iloc[-1]
    
suggested_stop_points = round_to_tick(atr_value * 1.5)

st.sidebar.markdown(f"<div style='font-size:0.8rem; color:#94a3b8;'>ATR 15m atual: <b>{atr_value:.2f} pts</b><br>Stop Sugerido (1.5x ATR): <b>{suggested_stop_points:.2f} pts</b></div>", unsafe_allow_html=True)

stop_loss_input = st.sidebar.number_input("Stop Loss (Pontos)", min_value=1.0, value=float(suggested_stop_points), step=1.0, format="%.2f")

# Calculate position size
calc_results = calculate_position_size(account_balance, risk_pct, stop_loss_input)

# Display calculations
st.sidebar.markdown("#### Resultado da Gestão:")
contracts = calc_results["contracts_rounded"]

color_contracts = "#00c853" if contracts >= 1 else "#dd2c00"

st.sidebar.markdown(
    f"<div class='metric-card' style='border-left: 4px solid {color_contracts};'>"
    f"<div class='metric-title'>Tamanho de Posição Recomendado</div>"
    f"<div class='metric-value' style='color:{color_contracts};'>{contracts} Contrato(s)</div>"
    f"<div style='font-size:0.8rem; color:#94a3b8; margin-top:5px;'>"
    f"• Limite de Risco Operação: <b>US$ {calc_results['max_risk_usd']:.2f} ({risk_pct}%)</b><br>"
    f"• Perda Real Projetada: <b>US$ {calc_results['actual_risk_usd']:.2f}</b><br>"
    f"• Risco unitário contrato: <b>US$ {calc_results['risk_per_contract_usd']:.2f}</b><br>"
    f"• Margem Operacional requerida: <b>US$ {calc_results['required_intraday_margin']:.2f}</b>"
    f"</div>"
    f"</div>",
    unsafe_allow_html=True
)

if calc_results["required_intraday_margin"] > account_balance:
    st.sidebar.error("⚠️ Alerta: Margem requerida excede o saldo da conta!")

# TRADING CHECKLIST
st.sidebar.markdown("<div class='section-header'>📋 Checklist do Trader</div>", unsafe_allow_html=True)
st.sidebar.checkbox("Viés do dia está alinhado com o trade?", value=False)
st.sidebar.checkbox("Relação Risco/Retorno é favorável (min. 1:1.5)?", value=False)
st.sidebar.checkbox("Sem notícias de alto impacto nos próximos 30min?", value=False)
st.sidebar.checkbox("Stop Loss já cadastrado/posicionado?", value=False)


# 6. MAIN CONTENT SECTION 1: VIÉS DO DIA & GRÁFICOS
main_cols = st.columns([1, 2])

with main_cols[0]:
    st.markdown("<div class='section-header'>🎯 Viés do Dia (Contexto Geral)</div>", unsafe_allow_html=True)
    
    bias_info = data["bias"]
    
    st.markdown(
        f"<div class='bias-card' style='background: {bias_info['color']}22; border: 2px solid {bias_info['color']};'>"
        f"<div class='bias-title'>Viés Dominante</div>"
        f"<div class='bias-label' style='color: {bias_info['color']};'>{bias_info['label']}</div>"
        f"<div class='bias-score'>Pontuação de Força: {bias_info['score']:+d} / +11</div>"
        f"</div>",
        unsafe_allow_html=True
    )
    
    # Detail factors that led to this bias
    st.markdown("#### Fatores Ponderados:")
    for score_factor, desc in bias_info["factors"]:
        badge_color = "#00c853" if "+" in score_factor else "#dd2c00"
        st.markdown(
            f"<div style='font-size:0.85rem; padding: 4px 8px; margin-bottom:5px; background: rgba(255,255,255,0.02); border-left: 3px solid {badge_color};'>"
            f"<span style='font-weight: 700; color:{badge_color};'>{score_factor}</span> &nbsp; {desc}"
            f"</div>",
            unsafe_allow_html=True
        )
        
    # Suggested Stop/Targets Table based on current price
    st.markdown("#### Sugestões de Alvos baseados no ATR:")
    if nq_data:
        current_nq_price = nq_data["price"]
        stops_targets = suggest_stops_targets(current_nq_price, atr_value)
        
        if stops_targets:
            tab1, tab2 = st.tabs(["🟢 Compras (Long)", "🔴 Vendas (Short)"])
            
            with tab1:
                st.markdown(
                    f"**Entrada:** `{stops_targets['long']['entry']:.2f}` | "
                    f"**Stop:** `{stops_targets['long']['stop_loss']:.2f}` ( {stops_targets['stop_loss_points']:.2f} pts | US$ {stops_targets['stop_loss_usd_per_contract']:.2f}/contr.)"
                )
                tgt_df = pd.DataFrame([
                    {"Relação R:R": rr, "Preço do Alvo": details["price"], "Pontos": details["points"], "Lucro por Contrato": f"US$ {details['profit_usd_per_contract']:.2f}"}
                    for rr, details in stops_targets["long"]["targets"].items()
                ])
                st.table(tgt_df)
                
            with tab2:
                st.markdown(
                    f"**Entrada:** `{stops_targets['short']['entry']:.2f}` | "
                    f"**Stop:** `{stops_targets['short']['stop_loss']:.2f}` ( {stops_targets['stop_loss_points']:.2f} pts | US$ {stops_targets['stop_loss_usd_per_contract']:.2f}/contr.)"
                )
                tgt_df_short = pd.DataFrame([
                    {"Relação R:R": rr, "Preço do Alvo": details["price"], "Pontos": details["points"], "Lucro por Contrato": f"US$ {details['profit_usd_per_contract']:.2f}"}
                    for rr, details in stops_targets["short"]["targets"].items()
                ])
                st.table(tgt_df_short)

with main_cols[1]:
    st.markdown("<div class='section-header'>📈 Gráfico Interativo Nasdaq Futuro (NQ)</div>", unsafe_allow_html=True)
    
    tf_col, view_col = st.columns([1, 2])
    with tf_col:
        tf_option = st.selectbox("Tempo Gráfico", options=["5m", "15m", "1h", "Diário"], index=1)
    with view_col:
        chart_overlays = st.multiselect("Sobreposições Técnicas", options=["Médias EMAs (9, 21, 50)", "Bandas de Bollinger", "Canais de Pivot"], default=["Médias EMAs (9, 21, 50)"])
        
    if tf_option == "5m":
        df_chart = data["df_5m_nq"].copy()
    elif tf_option == "1h":
        df_chart = get_ticker_data("NQ=F", period="15d", interval="1h")
        df_chart = calculate_indicators(df_chart)
    elif tf_option == "Diário":
        df_chart = data["df_daily_nq"].copy()
    else:
        df_chart = data["df_15m_nq"].copy()
        
    df_plot = df_chart.tail(80)
    
    if not df_plot.empty:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                             vertical_spacing=0.06, 
                             row_heights=[0.75, 0.25])
        
        # Add Candlesticks
        fig.add_trace(go.Candlestick(
            x=df_plot.index,
            open=df_plot['Open'],
            high=df_plot['High'],
            low=df_plot['Low'],
            close=df_plot['Close'],
            name="NQ=F",
            increasing_line_color='#26a69a', decreasing_line_color='#ef5350',
            increasing_fillcolor='#26a69a', decreasing_fillcolor='#ef5350'
        ), row=1, col=1)
        
        if "Médias EMAs (9, 21, 50)" in chart_overlays and "EMA9" in df_plot.columns:
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['EMA9'], name="EMA 9", line=dict(color='#38bdf8', width=1.2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['EMA21'], name="EMA 21", line=dict(color='#fbbf24', width=1.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['EMA50'], name="EMA 50", line=dict(color='#ec4899', width=1.8)), row=1, col=1)
            
        if "Bandas de Bollinger" in chart_overlays:
            sma20 = df_plot['Close'].rolling(window=20).mean()
            std20 = df_plot['Close'].rolling(window=20).std()
            upper_band = sma20 + (2 * std20)
            lower_band = sma20 - (2 * std20)
            fig.add_trace(go.Scatter(x=df_plot.index, y=upper_band, name="Banda Superior", line=dict(color='rgba(255,255,255,0.25)', dash='dash')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_plot.index, y=lower_band, name="Banda Inferior", line=dict(color='rgba(255,255,255,0.25)', dash='dash'), fill='tonexty', fillcolor='rgba(255,255,255,0.02)'), row=1, col=1)

        if "Canais de Pivot" in chart_overlays:
            pivots = calculate_pivot_points(data["df_daily_nq"])
            if pivots:
                for level, val in pivots.items():
                    color_pivot = '#64748b'
                    if level.startswith('R'): color_pivot = 'rgba(239, 83, 80, 0.4)'
                    elif level.startswith('S'): color_pivot = 'rgba(38, 166, 154, 0.4)'
                    
                    fig.add_trace(go.Scatter(
                        x=[df_plot.index[0], df_plot.index[-1]],
                        y=[val, val],
                        mode="lines",
                        name=level,
                        line=dict(color=color_pivot, width=1, dash='dot')
                    ), row=1, col=1)

        # Volume Bar Chart
        colors = ['#26a69a' if df_plot['Close'].iloc[i] >= df_plot['Open'].iloc[i] else '#ef5350' for i in range(len(df_plot))]
        fig.add_trace(go.Bar(
            x=df_plot.index,
            y=df_plot['Volume'],
            name="Volume",
            marker_color=colors,
            opacity=0.5
        ), row=2, col=1)
        
        # Layout tuning
        fig.update_layout(
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            height=460,
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            paper_bgcolor="#0d0f12",
            plot_bgcolor="#0d0f12"
        )
        fig.update_yaxes(gridcolor='rgba(255,255,255,0.03)', zeroline=False)
        fig.update_xaxes(gridcolor='rgba(255,255,255,0.03)')
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Aguardando carregamento de velas de mercado...")


# 7. SECTION 2: MICRO & MACRO ANALYSIS
sec2_cols = st.columns([1, 1])

with sec2_cols[0]:
    st.markdown("<div class='section-header'>🔬 Análise Micro & Níveis Técnicos</div>", unsafe_allow_html=True)
    
    micro_tab1, micro_tab2 = st.tabs(["📍 Pontos de Pivô Diários", "📊 Alinhamento de Tendência"])
    
    with micro_tab1:
        pivots = calculate_pivot_points(data["df_daily_nq"])
        if pivots and nq_data:
            current_nq = nq_data["price"]
            
            pivots_data = [
                {"Nível": "Resistência 3 (R3)", "Preço": f"{pivots['R3']:.2f}", "Status": "Acima" if current_nq < pivots['R3'] else "Rompido"},
                {"Nível": "Resistência 2 (R2)", "Preço": f"{pivots['R2']:.2f}", "Status": "Acima" if current_nq < pivots['R2'] else "Rompido"},
                {"Nível": "Resistência 1 (R1)", "Preço": f"{pivots['R1']:.2f}", "Status": "Acima" if current_nq < pivots['R1'] else "Rompido"},
                {"Nível": "Pivot Point (PP)", "Preço": f"{pivots['PP']:.2f}", "Status": "Acima" if current_nq < pivots['PP'] else "Abaixo"},
                {"Nível": "Suporte 1 (S1)", "Preço": f"{pivots['S1']:.2f}", "Status": "Abaixo" if current_nq > pivots['S1'] else "Rompido"},
                {"Nível": "Suporte 2 (S2)", "Preço": f"{pivots['S2']:.2f}", "Status": "Abaixo" if current_nq > pivots['S2'] else "Rompido"},
                {"Nível": "Suporte 3 (S3)", "Preço": f"{pivots['S3']:.2f}", "Status": "Abaixo" if current_nq > pivots['S3'] else "Rompido"}
            ]
            p_df = pd.DataFrame(pivots_data)
            
            def color_pivots(row):
                val = row["Nível"]
                if "R" in val:
                    return ["color: #ef5350"] * len(row)
                elif "S" in val:
                    return ["color: #26a69a"] * len(row)
                else:
                    return ["color: #fbbf24; font-weight: 700"] * len(row)
            
            st.table(p_df)
            st.markdown(
                f"<div style='font-size:0.8rem; color:#94a3b8; text-align:center;'>Preço Atual: <b>{current_nq:,.2f}</b> | "
                f"Distância do Pivot: <b>{current_nq - pivots['PP']:.2f} pts</b></div>",
                unsafe_allow_html=True
            )
            
    with micro_tab2:
        m5_latest = data["df_5m_nq"].iloc[-1]
        m15_latest = data["df_15m_nq"].iloc[-1]
        daily_latest = data["df_daily_nq"].iloc[-1]
        
        df_1h_temp = get_ticker_data("NQ=F", period="10d", interval="1h")
        df_1h_temp = calculate_indicators(df_1h_temp)
        h1_latest = df_1h_temp.iloc[-1] if not df_1h_temp.empty else None
        
        trend_status = []
        
        def eval_trend(close, ema9, ema21, ema50):
            if close > ema9 > ema21 > ema50:
                return "FORTE ALTA 🟢", "#00c853"
            elif close > ema21:
                return "ALTA 📈", "#aeea00"
            elif close < ema9 < ema21 < ema50:
                return "FORTE BAIXA 🔴", "#dd2c00"
            elif close < ema21:
                return "BAIXA 📉", "#ff6d00"
            else:
                return "LATERAL / NEUTRO 🟡", "#ffd600"
                
        t_5m, c_5m = eval_trend(m5_latest['Close'], m5_latest['EMA9'], m5_latest['EMA21'], m5_latest['EMA50'])
        t_15m, c_15m = eval_trend(m15_latest['Close'], m15_latest['EMA9'], m15_latest['EMA21'], m15_latest['EMA50'])
        
        if h1_latest is not None:
            t_1h, c_1h = eval_trend(h1_latest['Close'], h1_latest['EMA9'], h1_latest['EMA21'], h1_latest['EMA50'])
        else:
            t_1h, c_1h = "Sem Dados", "#808080"
            
        t_d1, c_d1 = eval_trend(daily_latest['Close'], daily_latest['EMA9'], daily_latest['EMA21'], daily_latest['EMA50'])
        
        st.markdown(
            f"<div style='font-size:0.9rem; margin-bottom: 10px;'>"
            f"<b>Alinhamento de Médias Exponenciais:</b>"
            f"</div>"
            f"<div style='display: grid; grid-template-columns: 1fr 1fr; gap: 8px;'>"
            f"<div class='metric-card' style='border-left:4px solid {c_5m}; margin-bottom:0;'>Grafico 5 Minutos (M5):<br><span style='font-weight:700; color:{c_5m};'>{t_5m}</span></div>"
            f"<div class='metric-card' style='border-left:4px solid {c_15m}; margin-bottom:0;'>Grafico 15 Minutos (M15):<br><span style='font-weight:700; color:{c_15m};'>{t_15m}</span></div>"
            f"<div class='metric-card' style='border-left:4px solid {c_1h}; margin-bottom:0;'>Grafico 1 Hora (H1):<br><span style='font-weight:700; color:{c_1h};'>{t_1h}</span></div>"
            f"<div class='metric-card' style='border-left:4px solid {c_d1}; margin-bottom:0;'>Grafico Diario (D1):<br><span style='font-weight:700; color:{c_d1};'>{t_d1}</span></div>"
            f"</div>",
            unsafe_allow_html=True
        )
        
        st.markdown("##### Indicadores Auxiliares (15m):")
        rsi_val = m15_latest['RSI']
        macd_val = m15_latest['MACD_Hist']
        
        rsi_color = "#ffd600"
        if rsi_val > 70: rsi_color = "#dd2c00"
        elif rsi_val < 30: rsi_color = "#00c853"
        elif 50 <= rsi_val <= 70: rsi_color = "#aeea00"
        
        macd_color = "#00c853" if macd_val > 0 else "#dd2c00"
        
        st.markdown(
            f"<div style='display:flex; justify-content: space-around; margin-top:10px;'>"
            f"<div style='text-align:center;'>RSI (14): <br><b style='color:{rsi_color}; font-size:1.2rem;'>{rsi_val:.2f}</b></div>"
            f"<div style='text-align:center;'>Hist. MACD: <br><b style='color:{macd_color}; font-size:1.2rem;'>{macd_val:.2f}</b></div>"
            f"</div>",
            unsafe_allow_html=True
        )

with sec2_cols[1]:
    st.markdown("<div class='section-header'>🌐 Análise Macro, Notícias & Calendário</div>", unsafe_allow_html=True)
    
    macro_tab1, macro_tab2, macro_tab3 = st.tabs(["📰 Notícias de Impacto", "📅 Calendário Econômico", "🔗 Correlação Macro"])
    
    with macro_tab1:
        news_items = data["news"]
        if news_items:
            for item in news_items:
                st.markdown(
                    f"<div style='margin-bottom: 12px; font-size: 0.85rem; border-bottom: 1px solid rgba(255,255,255,0.03); padding-bottom:6px;'>"
                    f"<span style='color: #64748b;'>[{item['time']}] {item['publisher']}</span><br>"
                    f"<a href='{item['link']}' target='_blank' style='color: #e2e8f0; font-weight: 600; text-decoration: none;'>{item['title']}</a>"
                    f"</div>",
                    unsafe_allow_html=True
                )
        else:
            st.info("Nenhuma notícia macroeconômica relevante encontrada.")
            
    with macro_tab2:
        calendar_events = data["calendar"]
        if calendar_events:
            for event in calendar_events:
                impact = event["impact"]
                badge_color = "rgba(239, 83, 80, 0.25)" if "Alta" in impact or "Máxima" in impact else "rgba(251, 191, 36, 0.25)"
                border_color = "#ef5350" if "Alta" in impact or "Máxima" in impact else "#fbbf24"
                
                st.markdown(
                    f"<div style='display: flex; align-items: center; justify-content: space-between; font-size: 0.85rem; padding: 6px 10px; margin-bottom: 6px; background: rgba(255,255,255,0.01); border-left: 3px solid {border_color};'>"
                    f"<div>"
                    f"<span style='color: #94a3b8; font-weight:500;'>{event['day']} ({event['time']})</span><br>"
                    f"<span style='color: #e2e8f0; font-weight:600;'>{event['event']}</span>"
                    f"</div>"
                    f"<div style='background: {badge_color}; border: 1px solid {border_color}; border-radius: 4px; padding: 2px 6px; font-size:0.7rem; font-weight: 700; color:#e2e8f0;'>"
                    f"{impact.upper()}"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
        else:
            st.info("Nenhum evento econômico agendado.")
            
    with macro_tab3:
        corr_matrix = data["corr"]
        if not corr_matrix.empty:
            st.markdown("<p style='font-size:0.8rem; color:#94a3b8;'>Matriz de correlação linear diária dos últimos 30 dias (Nasdaq futures vs Drivers Macro). Valores próximos de -1 indicam correlação invertida; próximos de +1 indicam correlação direta.</p>", unsafe_allow_html=True)
            
            def highlight_corr(val):
                if val == 1.0:
                    return 'background-color: rgba(255, 255, 255, 0.1); color: #fff;'
                elif val < -0.5:
                    return 'background-color: rgba(239, 83, 80, 0.2); color: #ef5350; font-weight: 600;'
                elif val > 0.5:
                    return 'background-color: rgba(38, 166, 154, 0.2); color: #26a69a; font-weight: 600;'
                return ''
                
            styler = corr_matrix.style
            if hasattr(styler, "map"):
                styled_corr = styler.map(highlight_corr).format("{:.2f}")
            else:
                styled_corr = styler.applymap(highlight_corr).format("{:.2f}")
            st.dataframe(styled_corr, use_container_width=True)
        else:
            st.info("Aguardando carregamento de dados históricos macro para calcular correlações.")

# Footer info
st.markdown("<hr style='border-color: rgba(255,255,255,0.05); margin-top:25px;'>", unsafe_allow_html=True)
st.markdown("<div style='text-align: center; color: #64748b; font-size: 0.75rem; margin-bottom: 20px;'>MNQ Trading Dashboard v1.0.0 • Projetado para auxílio à leitura de contexto de trade em Micro E-mini Nasdaq-100 • Use com cautela e siga sua gestão de risco.</div>", unsafe_allow_html=True)
