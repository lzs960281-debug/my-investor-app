import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from groq import Groq
import concurrent.futures
import time

# [설정] 
st.set_page_config(page_title="ETF 관제탑", layout="centered")

# UI 스타일: 토스증권의 깔끔한 다크 모드 스타일
st.markdown("""
<style>
    .metric-box { background-color: #1a1b23; padding: 25px; border-radius: 20px; text-align: center; }
    .action-box { background-color: #24252f; padding: 20px; border-radius: 15px; border-left: 5px solid #3182f6; }
    .stButton>button { width: 100%; border-radius: 10px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# 1. ETF 리스트 및 설정 (개별주식 삭제)
ETF_UNIVERSE = {
    'TIGER 미국S&P500': '360750.KS',
    'TIGER 미국나스닥100': '133690.KS',
    'KODEX 국고채30년': '439870.KS',
    'TIGER 미국배당다우': '458730.KS',
    'TIGER 미국테크TOP10': '441680.KS',
    'KODEX 골드선물': '132030.KS'
}

if 'portfolio' not in st.session_state: st.session_state.portfolio = {'360750.KS': 100}
if 'targets' not in st.session_state: st.session_state.targets = {'360750.KS': 1.0}

# 2. 강건한 데이터 호출 엔진 (에러 방지)
def fetch_price(ticker):
    try:
        t = yf.Ticker(ticker)
        price = t.history(period="1d")['Close'].iloc[-1]
        return ticker, price if price > 0 else 0
    except: return ticker, 0

# 3. 메인 UI
st.title("📈 ETF 자산 관제탑")
tab1, tab2, tab3 = st.tabs(["🏠 홈", "⚖️ 리밸런싱", "🤖 AI 전략"])

# [홈 탭]
with tab1:
    with st.spinner("데이터 로딩 중..."):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            prices = dict(executor.map(fetch_price, st.session_state.portfolio.keys()))
    
    total_val = sum(prices.get(t, 0) * q for t, q in st.session_state.portfolio.items())
    st.markdown(f"<div class='metric-box'><h3>총 평가금액</h3><h1>{total_val:,.0f} 원</h1></div>", unsafe_allow_html=True)
    
    for t, q in st.session_state.portfolio.items():
        name = next((k for k, v in ETF_UNIVERSE.items() if v == t), t)
        st.write(f"**{name}** | {q}주 | 평가: {prices.get(t,0)*q:,.0f}원")

# [리밸런싱 탭]
with tab2:
    st.subheader("매월 투자금 리밸런싱")
    budget = st.number_input("월 투자 가능 금액", value=1000000, step=10000)
    
    for t, name in ETF_UNIVERSE.items():
        ticker = name
        target_pct = st.slider(f"{t} 목표 비중 (%)", 0, 100, int(st.session_state.targets.get(ticker, 0)*100))
        st.session_state.targets[ticker] = target_pct / 100

    if st.button("자동 주문서 생성"):
        total_after = total_val + budget
        for t, target in st.session_state.targets.items():
            if target > 0:
                current = prices.get(t, 0) * st.session_state.portfolio.get(t, 0)
                ideal = total_after * target
                to_buy = int((ideal - current) / prices.get(t, 1))
                if to_buy > 0:
                    st.success(f"매수 추천: {t} {to_buy}주")

# [AI 탭]
with tab3:
    st.subheader("AI 운용역 전략")
    if st.button("AI 시장 진단 및 비중 수정 제안"):
        client = Groq(api_key=st.secrets.get("GROQ_API_KEY", ""))
        prompt = f"현재 비중: {st.session_state.targets}. ETF 시장 테마와 금리 상황을 고려하여 최적의 타겟 비중을 제안해줘. 답변은 비중 표만 줘."
        res = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}])
        st.write(res.choices[0].message.content)
