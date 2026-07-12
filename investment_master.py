import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from groq import Groq
import concurrent.futures
import os

# [앱 설정]
st.set_page_config(page_title="ETF 자산 관제탑", layout="centered")

# [보안/에러 방지] 
ETF_LIST = {
    '미국S&P500(TIGER)': '360750.KS', '미국나스닥100(TIGER)': '133690.KS',
    '국고채30년(KODEX)': '439870.KS', '미국배당다우(TIGER)': '458730.KS',
    '미국테크TOP10(TIGER)': '441680.KS', '골드선물(KODEX)': '132030.KS'
}

# [데이터 엔진: 절대 죽지 않도록 설계]
def get_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="1d")
        if data.empty: return 0
        return float(data['Close'].iloc[-1])
    except: return 0

# [메인 로직]
st.title("🛡️ ETF 자산 관제탑")
if 'portfolio' not in st.session_state: st.session_state.portfolio = {'360750.KS': 100, '133690.KS': 50}
if 'targets' not in st.session_state: st.session_state.targets = {'360750.KS': 0.6, '133690.KS': 0.4}

tab1, tab2, tab3 = st.tabs(["🏠 내 자산", "⚖️ 리밸런싱", "🤖 AI 전략"])

# 1. 내 자산 (홈)
with tab1:
    prices = {t: get_price(t) for t in st.session_state.portfolio.keys()}
    total = sum(prices.get(t, 0) * q for t, q in st.session_state.portfolio.items())
    
    st.metric("총 평가금액", f"{total:,.0f} 원")
    st.divider()
    for t, q in st.session_state.portfolio.items():
        name = next((k for k, v in ETF_LIST.items() if v == t), t)
        st.write(f"**{name}** : {q}주 / 약 {prices.get(t, 0)*q:,.0f}원")

# 2. 리밸런싱 (자동 매수 계산)
with tab2:
    budget = st.number_input("월 투자 가능 금액", value=1000000, step=10000)
    st.info("목표 비중을 설정하면 자동으로 매수 수량을 계산합니다.")
    
    for name, ticker in ETF_LIST.items():
        val = st.slider(f"{name} 목표 비중", 0, 100, int(st.session_state.targets.get(ticker, 0)*100))
        st.session_state.targets[ticker] = val / 100
        
    if st.button("자동 주문서 생성"):
        total_after = total + budget
        for t, target in st.session_state.targets.items():
            price = prices.get(t, 0)
            if price > 0: # 0원인 종목은 건너뜀 (ZeroDivision 방지)
                current_val = prices.get(t, 0) * st.session_state.portfolio.get(t, 0)
                needed = (total_after * target) - current_val
                if needed > 0:
                    buy_shares = int(needed / price)
                    st.success(f"매수: {t} {buy_shares}주")

# 3. AI 전략
with tab3:
    if st.button("AI 시장 진단 시작"):
        api_key = st.secrets.get("GROQ_API_KEY")
        if not api_key:
            st.error("Secrets에 GROQ_API_KEY가 없습니다.")
        else:
            try:
                client = Groq(api_key=api_key)
                res = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": "ETF 기반 자산 배분 전략을 제시해줘."}]
                )
                st.write(res.choices[0].message.content)
            except Exception as e:
                st.error(f"연결 실패: {e}")
