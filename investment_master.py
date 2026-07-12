import streamlit as st
import yfinance as yf
import pandas as pd

# 1. ETF 설정 (지수 추종 위주)
ETF_UNIVERSE = {
    'S&P500(TIGER)': '360750.KS', '나스닥100(TIGER)': '133690.KS',
    '국고채30년(KODEX)': '439870.KS', '미국배당다우(TIGER)': '458730.KS',
    '미국테크TOP10(TIGER)': '441680.KS', '골드선물(KODEX)': '132030.KS'
}

# 2. 실시간 가격 엔진
@st.cache_data(ttl=60)
def get_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="1d")
        return float(data['Close'].iloc[-1]) if not data.empty else 0
    except: return 0

# 3. 레이아웃 (토스증권 스타일)
st.title("💰 ETF 자산 관제탑 v18")

# 사용자 데이터 입력 (실제 운영 시 DB에서 불러올 부분)
if 'portfolio' not in st.session_state: st.session_state.portfolio = {'360750.KS': 100, '133690.KS': 50}
if 'targets' not in st.session_state: st.session_state.targets = {'360750.KS': 0.6, '133690.KS': 0.4}

# 데이터 계산
prices = {t: get_price(t) for t in ETF_UNIVERSE.values()}
current_total = sum(prices.get(t, 0) * q for t, q in st.session_state.portfolio.items())

# 대시보드 (핵심 정보)
st.metric("현재 총 자산", f"{current_total:,.0f} 원")

# 리밸런싱 계산
st.subheader("🎯 이번 달 자산 배분 지시서")
budget = st.number_input("추가 투자 금액 (원)", value=1000000, step=10000)
new_total = current_total + budget

# 계산 로직
st.markdown("---")
orders = []
for name, ticker in ETF_UNIVERSE.items():
    target_weight = st.slider(f"{name} 비중", 0.0, 1.0, st.session_state.targets.get(ticker, 0.0))
    st.session_state.targets[ticker] = target_weight
    
    price = prices.get(ticker, 0)
    if price > 0:
        current_val = price * st.session_state.portfolio.get(ticker, 0)
        target_val = new_total * target_weight
        needed_val = target_val - current_val
        buy_shares = int(needed_val / price)
        
        if buy_shares > 0:
            orders.append(f"✅ **{name}**: {buy_shares}주 매수 (약 {buy_shares * price:,.0f}원)")
        elif buy_shares < 0:
            orders.append(f"⚠️ **{name}**: {abs(buy_shares)}주 매도 (비중 초과)")

# 실행
if st.button("투자 지시서 생성"):
    st.markdown("### 📋 오늘의 매매 지시")
    for order in orders:
        st.write(order)
