import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from groq import Groq

# [앱 설정]
st.set_page_config(page_title="자산 성장 관제탑", layout="centered")

# [핵심 데이터: ETF 유니버스]
ETF_UNIVERSE = {
    'S&P500(TIGER)': '360750.KS', '나스닥100(TIGER)': '133690.KS',
    '국고채30년(KODEX)': '439870.KS', '미국배당다우(TIGER)': '458730.KS',
    '미국테크TOP10(TIGER)': '441680.KS', '골드선물(KODEX)': '132030.KS'
}

# [데이터 엔진]
@st.cache_data(ttl=60)
def get_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="1d")
        return float(data['Close'].iloc[-1]) if not data.empty else 0
    except: return 0

# [초기 세팅]
if 'portfolio' not in st.session_state: st.session_state.portfolio = {'360750.KS': 100, '133690.KS': 50}
if 'targets' not in st.session_state: st.session_state.targets = {'360750.KS': 0.6, '133690.KS': 0.4}

st.title("📈 자산 성장 관제탑")

# 1. 자산 현황 요약 (토스식 카드)
prices = {t: get_price(t) for t in ETF_UNIVERSE.values()}
current_total = sum(prices.get(t, 0) * q for t, q in st.session_state.portfolio.items())

st.metric("현재 자산 평가금액", f"{current_total:,.0f} 원")

# 2. 탭 구성
tab1, tab2, tab3 = st.tabs(["자산 현황", "리밸런싱 가이드", "시장 인사이트"])

with tab1:
    # 도넛 차트
    fig = go.Figure(data=[go.Pie(
        labels=list(ETF_UNIVERSE.keys()), 
        values=[prices.get(v, 0)*st.session_state.portfolio.get(v, 0) for v in ETF_UNIVERSE.values()],
        hole=.8, marker=dict(colors=['#3182f6', '#31c48d', '#f04452', '#ff9f43', '#8b5cf6', '#64748b'])
    )])
    fig.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=200)
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("### 📋 보유 내역")
    for t, q in st.session_state.portfolio.items():
        name = next((k for k, v in ETF_UNIVERSE.items() if v == t), t)
        val = prices.get(t, 0) * q
        st.write(f"**{name}** · {q}주 · ₩{val:,.0f}")

with tab2:
    st.markdown("### ⚖️ 포트폴리오 리밸런싱 가이드")
    st.info("목표 비중을 설정하면, 현재 자산 기준 '적정 수량'을 알려드립니다.")
    
    for name, ticker in ETF_UNIVERSE.items():
        val = st.slider(f"{name} 목표 비중", 0, 100, int(st.session_state.targets.get(ticker, 0)*100))
        st.session_state.targets[ticker] = val / 100
        
    if st.button("가이드 확인하기"):
        st.markdown("---")
        for ticker, target in st.session_state.targets.items():
            price = prices.get(ticker, 0)
            if price > 0:
                current_val = price * st.session_state.portfolio.get(ticker, 0)
                ideal_val = current_total * target
                diff = ideal_val - current_val
                
                # 텍스트 안내 (매수/매도/유지)
                if diff > price * 0.5: # 0.5주 이상 차이 날 때만 표시
                    st.success(f"**{next((k for k,v in ETF_UNIVERSE.items() if v==ticker), ticker)}**: 비중 부족 (약 {int(diff/price)}주 추가 필요)")
                elif diff < -price * 0.5:
                    st.warning(f"**{next((k for k,v in ETF_UNIVERSE.items() if v==ticker), ticker)}**: 비중 초과 (약 {int(abs(diff)/price)}주 조정 권장)")
                else:
                    st.write(f"**{next((k for k,v in ETF_UNIVERSE.items() if v==ticker), ticker)}**: 적정 비중 유지")

with tab3:
    st.markdown("### 🤖 시장 전략 AI")
    if st.button("시장 분석 및 포트폴리오 조언"):
        api_key = st.secrets.get("GROQ_API_KEY")
        client = Groq(api_key=api_key)
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "지금 ETF 시장에서 장기 투자자가 주목해야 할 핵심 테마와 포트폴리오 관리 팁을 알려줘."}]
        )
        st.info(res.choices[0].message.content)
