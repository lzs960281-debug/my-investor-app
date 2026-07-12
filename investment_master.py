import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd

# [UI 설정: 토스증권 스타일]
st.set_page_config(page_title="Toss ETF 관제탑", layout="centered")

st.markdown("""
<style>
    /* Toss Blue Color */
    :root { --toss-blue: #3182f6; }
    
    /* 둥근 카드 디자인 */
    .stApp { background-color: #f8f9fa; }
    .card { background: white; padding: 20px; border-radius: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px; }
    
    /* 폰트 및 텍스트 */
    h1, h2, h3 { color: #191f2c; font-weight: 700; }
    .big-number { font-size: 32px; font-weight: 800; color: #191f2c; }
    .sub-text { color: #8b95a1; font-size: 14px; }
    
    /* 버튼 스타일 */
    div.stButton > button { background-color: #3182f6; color: white; border-radius: 12px; height: 50px; font-weight: 700; border: none; }
</style>
""", unsafe_allow_html=True)

# [ETF 데이터]
ETF_UNIVERSE = {
    'S&P500': '360750.KS', '나스닥100': '133690.KS',
    '국고채30년': '439870.KS', '배당다우': '458730.KS',
    '테크TOP10': '441680.KS', '골드선물': '132030.KS'
}

# [엔진: 실시간 가격]
@st.cache_data(ttl=60)
def get_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="1d")
        return float(data['Close'].iloc[-1]) if not data.empty else 0
    except: return 0

# [세션 초기화]
if 'portfolio' not in st.session_state: st.session_state.portfolio = {'360750.KS': 100, '133690.KS': 50}
if 'targets' not in st.session_state: st.session_state.targets = {'360750.KS': 0.6, '133690.KS': 0.4}

# [메인 로직]
st.title("내 투자")

# 1. 자산 현황 카드
prices = {t: get_price(t) for t in ETF_UNIVERSE.values()}
total_val = sum(prices.get(t, 0) * q for t, q in st.session_state.portfolio.items())

st.markdown(f"""
<div class="card">
    <div class="sub-text">총 자산 평가금액</div>
    <div class="big-number">{total_val:,.0f} 원</div>
</div>
""", unsafe_allow_html=True)

# 2. 탭 구성
tab1, tab2 = st.tabs(["자산 현황", "포트폴리오 리밸런싱"])

with tab1:
    # 도넛 차트
    fig = go.Figure(data=[go.Pie(
        labels=list(ETF_UNIVERSE.keys()), 
        values=[prices.get(v, 0)*st.session_state.portfolio.get(v, 0) for v in ETF_UNIVERSE.values()],
        hole=.8, marker=dict(colors=['#3182f6', '#31c48d', '#f04452', '#ff9f43', '#8b5cf6', '#64748b'])
    )])
    fig.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=200)
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("### 보유 중인 ETF")
    for t, q in st.session_state.portfolio.items():
        name = next((k for k, v in ETF_UNIVERSE.items() if v == t), t)
        st.write(f"**{name}** · {q}주 · ₩{prices.get(t, 0)*q:,.0f}")

with tab2:
    st.markdown("### 🎯 목표 비중 설정")
    for name, ticker in ETF_UNIVERSE.items():
        val = st.slider(f"{name} 비중", 0, 100, int(st.session_state.targets.get(ticker, 0)*100))
        st.session_state.targets[ticker] = val / 100
        
    budget = st.number_input("오늘 투자할 금액 (원)", value=1000000, step=10000)
    
    if st.button("투자 지시서 만들기"):
        total_after = total_val + budget
        st.markdown("### 📋 오늘의 매매 지시서")
        for ticker, target in st.session_state.targets.items():
            price = prices.get(ticker, 0)
            if price > 0:
                needed = (total_after * target) - (price * st.session_state.portfolio.get(ticker, 0))
                shares = int(needed / price)
                if shares > 0:
                    st.success(f"매수: {next((k for k,v in ETF_UNIVERSE.items() if v==ticker), ticker)} {shares}주")
                elif shares < 0:
                    st.warning(f"매도: {next((k for k,v in ETF_UNIVERSE.items() if v==ticker), ticker)} {abs(shares)}주")
