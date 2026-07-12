import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from groq import Groq
import requests
from bs4 import BeautifulSoup
import concurrent.futures

# [전체 구조] ETF 중심 자산 관리 엔진
st.set_page_config(page_title="육과장 Pro 자산운용", layout="centered")

# CSS: 토스 스타일 카드 UI
st.markdown("""
<style>
    .metric-card { background: #1a1b23; padding: 20px; border-radius: 20px; text-align: center; margin-bottom: 20px; }
    .buy-btn { background: #3182f6; color: white; padding: 15px; border-radius: 12px; text-align: center; font-weight: bold; }
    .stock-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

# 초기화
if 'portfolio' not in st.session_state: st.session_state.portfolio = {'360750.KS': 100, '133690.KS': 50, '439870.KS': 50} # 예시 ETF 3개
if 'monthly_budget' not in st.session_state: st.session_state.monthly_budget = 1000000
if 'targets' not in st.session_state: st.session_state.targets = {'360750.KS': 0.5, '133690.KS': 0.3, '439870.KS': 0.2}

# [핵심 로직] 멀티스레드 ETF 데이터 확보
def get_etf_data(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1d")
        return ticker, hist['Close'].iloc[-1]
    except: return ticker, 0

# 메인 UI
st.title("💰 AI 자산 관제탑")

# 1. 자산 현황
with st.spinner("시장 데이터 동기화 중..."):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        prices = dict(executor.map(lambda t: get_etf_data(t), st.session_state.portfolio.keys()))
    
    total_val = sum(prices[t] * st.session_state.portfolio[t] for t in st.session_state.portfolio)
    
    st.markdown(f"<div class='metric-card'><div style='color:#8b95a1'>총 평가금액</div><div style='font-size:32px; font-weight:800;'>{total_val:,.0f}원</div></div>", unsafe_allow_html=True)

# 2. 리밸런싱 / 월 투자금 엔진
st.subheader("📊 리밸런싱 및 월 투자")
budget = st.number_input("이번 달 투자 가능 금액 (원)", value=st.session_state.monthly_budget, step=10000)
st.session_state.monthly_budget = budget

st.markdown("---")
st.markdown("#### 🎯 타겟 비중 및 구매 제안")
orders = []
for t, target in st.session_state.targets.items():
    current_val = prices.get(t, 0) * st.session_state.portfolio.get(t, 0)
    ideal_val = (total_val + budget) * target
    diff = ideal_val - current_val
    
    shares_to_buy = int(diff / prices.get(t, 1)) if diff > 0 else 0
    
    col1, col2 = st.columns([2, 1])
    col1.write(f"**{t}** (타겟 {target*100}%)")
    col2.write(f"→ **{shares_to_buy}주 매수 추천**")
    
    if shares_to_buy > 0: orders.append({'ticker': t, 'shares': shares_to_buy})

if st.button("🚀 위 비율대로 자동 주문서 생성"):
    st.code("\n".join([f"매수: {o['ticker']} {o['shares']}주" for o in orders]))

# 3. AI 시장 전략 리포트
st.markdown("---")
st.subheader("🤖 AI 운용역 전략 리포트")
if st.button("시장 분석 및 비중 조정 제안"):
    with st.spinner("ETF 시장 테마 학습 중..."):
        # LLM에게 현재 포트폴리오와 시장 뉴스를 제공하고 타겟 비중 수정을 제안받음
        client = Groq(api_key=st.secrets.get("GROQ_API_KEY", ""))
        prompt = f"""당신은 ETF 전문 자산운용사 AI입니다. 
        현재 포트폴리오 비중: {st.session_state.targets}
        최근 시장 환경을 분석하여, 위험을 줄이고 수익을 극대화하기 위한 '비중 수정 제안'을 하세요.
        답변은 반드시 다음 형식으로 하세요:
        1. 시장 상황 분석 (핵심 테마 3줄)
        2. 수정 제안 비중 (예: 360750.KS: 0.6, 133690.KS: 0.2, 439870.KS: 0.2)
        3. 제안 이유"""
        
        resp = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}])
        st.write(resp.choices[0].message.content)

# [주의] 이 코드는 로직의 뼈대입니다. 실제 운영을 위해선 Groq API 키 설정과 Supabase 연동이 필수입니다.
