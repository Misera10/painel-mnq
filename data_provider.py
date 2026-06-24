import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import requests
from bs4 import BeautifulSoup
import traceback

def get_ticker_data(ticker_symbol, period="30d", interval="1d"):
    """
    Fetch historical data for a ticker using yfinance.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period=period, interval=interval)
        return df
    except Exception as e:
        print(f"Error fetching data for {ticker_symbol}: {e}")
        return pd.DataFrame()

def get_market_summary():
    """
    Fetch current cotações and daily stats for NQ=F and macro indicators.
    Tickers:
      - NQ=F: E-mini Nasdaq 100 Futures (proxy for MNQ)
      - ^VIX: CBOE Volatility Index
      - DX-Y.NYB: US Dollar Index
      - ^TNX: US 10-Year Treasury Yield (multiplied by 10 in symbol, i.e. 4.25% is shown as 4.25)
      - ES=F: E-mini S&P 500 Futures
    """
    symbols = {
        "Nasdaq Futuro (NQ)": "NQ=F",
        "S&P 500 Futuro (ES)": "ES=F",
        "Índice VIX (^VIX)": "^VIX",
        "Dólar Index (DXY)": "DX-Y.NYB",
        "Juros 10 Anos (US10Y)": "^TNX"
    }
    
    summary = {}
    
    for label, sym in symbols.items():
        try:
            # Fetch 5 days to ensure we have the current and previous day's close
            df = get_ticker_data(sym, period="5d", interval="1d")
            if not df.empty:
                current_price = df['Close'].iloc[-1]
                prev_price = df['Close'].iloc[-2] if len(df) > 1 else current_price
                daily_change = current_price - prev_price
                pct_change = (daily_change / prev_price) * 100 if prev_price != 0 else 0.0
                
                # For US10Y, display as percentage
                display_price = current_price
                if sym == "^TNX":
                    display_price = current_price / 10.0
                    prev_price_display = prev_price / 10.0
                    daily_change = display_price - prev_price_display
                
                summary[sym] = {
                    "label": label,
                    "price": display_price,
                    "change": daily_change,
                    "pct_change": pct_change,
                    "high": df['High'].iloc[-1] / (10.0 if sym == "^TNX" else 1.0),
                    "low": df['Low'].iloc[-1] / (10.0 if sym == "^TNX" else 1.0),
                    "prev_close": prev_price / (10.0 if sym == "^TNX" else 1.0)
                }
            else:
                summary[sym] = {"label": label, "price": 0.0, "change": 0.0, "pct_change": 0.0, "high": 0.0, "low": 0.0, "prev_close": 0.0}
        except Exception as e:
            print(f"Error summarising {label} ({sym}): {e}")
            summary[sym] = {"label": label, "price": 0.0, "change": 0.0, "pct_change": 0.0, "high": 0.0, "low": 0.0, "prev_close": 0.0}
            
    return summary

def calculate_pivot_points(df_daily):
    """
    Calculate Daily Pivot Points using standard formula from the last completed trading session.
    """
    if len(df_daily) < 2:
        return {}
    
    yesterday = df_daily.iloc[-2]
    
    high = yesterday['High']
    low = yesterday['Low']
    close = yesterday['Close']
    
    pp = (high + low + close) / 3.0
    
    r1 = 2 * pp - low
    s1 = 2 * pp - high
    
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    
    r3 = high + 2 * (pp - low)
    s3 = low - 2 * (high - pp)
    
    return {
        "PP": pp,
        "R1": r1,
        "S1": s1,
        "R2": r2,
        "S2": s2,
        "R3": r3,
        "S3": s3
    }

def calculate_indicators(df, prefix=""):
    """
    Calculate technical indicators for a given dataframe (intraday or daily):
    - EMAs (9, 21, 50, 200)
    - RSI (14)
    - ATR (14)
    - MACD (12, 26, 9)
    """
    df = df.copy()
    if df.empty:
        return df
        
    # EMAs
    df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).copy()
    loss = (-delta.where(delta < 0, 0)).copy()
    
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    
    # Wilder's smoothing technique for RSI
    for i in range(14, len(df)):
        avg_gain.iloc[i] = (avg_gain.iloc[i-1] * 13 + gain.iloc[i]) / 14
        avg_loss.iloc[i] = (avg_loss.iloc[i-1] * 13 + loss.iloc[i]) / 14
        
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    df['RSI'] = df['RSI'].fillna(50)  # Neutral fallback
    
    # ATR (Average True Range)
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    
    # Rolling mean for ATR
    df['ATR'] = true_range.ewm(alpha=1/14, adjust=False).mean()
    df['ATR'] = df['ATR'].bfill()
    
    # MACD
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    
    return df

def calculate_daily_bias(market_summary, df_daily_nq, df_15m_nq):
    """
    Calculate daily bias based on multiple factors (Trend, VIX, DXY, Pivot).
    Returns a score (-10 to +10) and a label in Portuguese.
    """
    score = 0
    factors = []
    
    if df_daily_nq.empty or df_15m_nq.empty or not market_summary:
        return {"score": 0, "label": "Neutro/Sem Dados", "color": "#808080", "factors": []}
        
    # Calculate indicators for daily and 15m
    daily_ind = calculate_indicators(df_daily_nq)
    m15_ind = calculate_indicators(df_15m_nq)
    
    last_daily = daily_ind.iloc[-1]
    last_15m = m15_ind.iloc[-1]
    
    # 1. Daily Trend (Weight: 2)
    if last_daily['Close'] > last_daily['EMA21']:
        score += 2
        factors.append(("+2", "Preço acima da EMA 21 no Diário"))
    else:
        score -= 2
        factors.append(("-2", "Preço abaixo da EMA 21 no Diário"))
        
    if last_daily['EMA9'] > last_daily['EMA21']:
        score += 1
        factors.append(("+1", "Média rápida (EMA 9) acima da média lenta (EMA 21) no Diário"))
    else:
        score -= 1
        factors.append(("-1", "Média rápida (EMA 9) abaixo da média lenta (EMA 21) no Diário"))
        
    # 2. Intraday Trend (15m) (Weight: 2)
    if last_15m['Close'] > last_15m['EMA21']:
        score += 2
        factors.append(("+2", "Preço acima da EMA 21 no gráfico de 15m"))
    else:
        score -= 2
        factors.append(("-2", "Preço abaixo da EMA 21 no gráfico de 15m"))
        
    if last_15m['EMA9'] > last_15m['EMA21']:
        score += 1
        factors.append(("+1", "EMA 9 acima da EMA 21 no gráfico de 15m"))
    else:
        score -= 1
        factors.append(("-1", "EMA 9 abaixo da EMA 21 no gráfico de 15m"))

    # 3. Daily Pivot Point Position (Weight: 2)
    pivot_data = calculate_pivot_points(df_daily_nq)
    if pivot_data and "PP" in pivot_data:
        pp = pivot_data["PP"]
        current_nq = last_15m['Close']
        if current_nq > pp:
            score += 2
            factors.append(("+2", f"Preço atual ({current_nq:.2f}) acima do Pivot Point Diário ({pp:.2f})"))
        else:
            score -= 2
            factors.append(("-2", f"Preço atual ({current_nq:.2f}) abaixo do Pivot Point Diário ({pp:.2f})"))

    # 4. VIX Daily Trend (Weight: 2)
    vix = market_summary.get("^VIX", {})
    if vix and vix.get("pct_change", 0) != 0:
        vix_pct = vix["pct_change"]
        if vix_pct < 0:
            score += 2
            factors.append(("+2", f"VIX está em queda no dia ({vix_pct:.2f}%) - Apetite ao Risco"))
        else:
            score -= 2
            factors.append(("-2", f"VIX está em alta no dia (+{vix_pct:.2f}%) - Aversão ao Risco"))

    # 5. DXY Daily Trend (Weight: 1)
    dxy = market_summary.get("DX-Y.NYB", {})
    if dxy and dxy.get("pct_change", 0) != 0:
        dxy_pct = dxy["pct_change"]
        if dxy_pct < 0:
            score += 1
            factors.append(("+1", f"Dólar Index (DXY) em queda ({dxy_pct:.2f}%) - Positivo para Ativos de Risco"))
        else:
            score -= 1
            factors.append(("-1", f"Dólar Index (DXY) em alta (+{dxy_pct:.2f}%) - Pressão sobre Ações"))

    # Map score to label
    if score >= 6:
        label = "FORTE ALTA"
        color = "#00c853"
    elif 2 <= score < 6:
        label = "ALTA"
        color = "#aeea00"
    elif -2 < score < 2:
        label = "NEUTRO / LATERAL"
        color = "#ffd600"
    elif -6 < score <= -2:
        label = "BAIXA"
        color = "#ff6d00"
    else:
        label = "FORTE BAIXA"
        color = "#dd2c00"
        
    return {
        "score": score,
        "label": label,
        "color": color,
        "factors": factors
    }

def get_macro_correlations(period="30d"):
    """
    Fetch closing prices for key assets and calculate a 30-day correlation matrix.
    """
    tickers = {
        "Nasdaq (NQ)": "NQ=F",
        "S&P 500 (ES)": "ES=F",
        "VIX (^VIX)": "^VIX",
        "Dólar (DXY)": "DX-Y.NYB",
        "Juros (US10Y)": "^TNX"
    }
    
    data = {}
    for name, sym in tickers.items():
        try:
            df = get_ticker_data(sym, period=period, interval="1d")
            if not df.empty:
                data[name] = df['Close']
        except Exception as e:
            print(f"Error correlation for {name}: {e}")
            
    if len(data) > 1:
        df_corr = pd.DataFrame(data).dropna().corr()
        return df_corr
    return pd.DataFrame()

def get_news_feed():
    """
    Fetch news articles related to NQ=F and format them.
    """
    try:
        ticker = yf.Ticker("NQ=F")
        news = ticker.news
        formatted_news = []
        
        for item in news[:8]:
            pub_time = datetime.datetime.fromtimestamp(item.get("providerPublishTime", 0))
            formatted_news.append({
                "title": item.get("title", "No Title"),
                "publisher": item.get("publisher", "Unknown Publisher"),
                "link": item.get("link", "#"),
                "time": pub_time.strftime("%d/%m/%Y %H:%M"),
                "summary": item.get("summary", "")
            })
        return formatted_news
    except Exception as e:
        print(f"Error fetching news: {e}")
        return []

def get_economic_calendar():
    """
    Return economic events.
    """
    events = [
        {"day": "Segunda-feira", "time": "11:00", "event": "Discursos de Membros do FOMC (Varia)", "impact": "Média"},
        {"day": "Terça-feira", "time": "09:30", "event": "Índice de Preços ao Produtor (PPI)", "impact": "Alta"},
        {"day": "Terça-feira", "time": "11:00", "event": "Vendas de Novas Moradias", "impact": "Média"},
        {"day": "Quarta-feira", "time": "09:30", "event": "Licenças de Construção / Estoques de Petróleo", "impact": "Média"},
        {"day": "Quarta-feira", "time": "14:00", "event": "Decisão de Taxa de Juros do Fed (FOMC)", "impact": "Alta (Máxima)"},
        {"day": "Quarta-feira", "time": "14:30", "event": "Coletiva de Imprensa do Presidente do Fed", "impact": "Alta (Máxima)"},
        {"day": "Quinta-feira", "time": "09:30", "event": "Pedidos Iniciais por Seguro-Desemprego", "impact": "Alta"},
        {"day": "Quinta-feira", "time": "09:30", "event": "Índice de Preços ao Consumidor (CPI - Inflação)", "impact": "Alta (Máxima)"},
        {"day": "Quinta-feira", "time": "09:30", "event": "PIB Trimestral dos EUA", "impact": "Alta"},
        {"day": "Sexta-feira", "time": "09:30", "event": "Relatório de Empregos NFP (Non-Farm Payrolls)", "impact": "Alta (Máxima)"},
        {"day": "Sexta-feira", "time": "09:30", "event": "Taxa de Desemprego nos EUA", "impact": "Alta"},
        {"day": "Sexta-feira", "time": "11:00", "event": "Índice de Confiança do Consumidor Michigan", "impact": "Média"}
    ]
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get("https://www.dailyfx.com/feeds/forex-market-news", headers=headers, timeout=5)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'xml')
            items = soup.find_all('item')
            rss_events = []
            for item in items[:6]:
                title = item.title.text if item.title else ""
                is_macro = any(kw in title.lower() for kw in ["fed", "fomc", "cpi", "inflation", "payrolls", "jobs", "gdp", "rates", "interest", "juros", "powell"])
                if is_macro:
                    pub_date = item.pubDate.text if item.pubDate else ""
                    rss_events.append({
                        "day": "Notícia Macro",
                        "time": pub_date.split(" ")[4] if len(pub_date.split(" ")) > 4 else pub_date,
                        "event": title,
                        "impact": "Alta"
                    })
            if rss_events:
                return rss_events + events
    except Exception as e:
        print(f"Error fetching RSS macro news: {e}")
        
    return events
