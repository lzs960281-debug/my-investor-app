import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, time
import requests
from bs4 import BeautifulSoup
from groq import Groq
import re
from streamlit_autorefresh import st_autorefresh

# 1. UI 설정
st.set_page_config(page_title="육과장 AI 풀오토", layout="wide")
st.title("🤖 육과장 AI - 풀오토 자산관리")

# 장중 30초 새로고침
now = datetime.now().time()
if time(9, 0) <= now <= time(15, 30):
    st_autorefresh(interval=30000, limit=None, key="auto_refresh")
    st.caption(f"🔴 LIVE {datetime.now().strftime('%H:%M:%S')} | 무한피드백 작동중")

# 2. 상태 초기화 (Secrets에서 API 키 로드)
if 'portfolio' not in st.session_state: st.session_state.portfolio = {}
if 'ai_logs' not in st.session_state: st.session_state.ai_logs = []
if 'rules' not in st.session_state: st.session_state.rules = {
    'core_min': 0.6, 'irp_risky_max': 0.7, 'cov_max': 0.15
}
groq_key = st.secrets.get("GROQ_API_KEY", "")

# 3. 사이드바 UI
st.sidebar.header("🔑 보유종목 관리")
name_map = {
    '365990.KS': 'S&P500', '133690.KS': '나스닥100', '441640.KS': '월배당커버드콜',
    '458730.KS': '미국배당다우', '463350.KS': '반도체', '462010.KS': '2차전지',
    '439870.KS': '국고채30년', '153130.KS': '단기채권'
}
ticker = st.sidebar.selectbox("종목 선택", list(name_map.keys()), format_func=lambda x: name_map[x])
shares = st.sidebar.number_input("수량 입력", min_value=0, step=1)
if st.sidebar.button("추가/수정"):
    st.session_state.portfolio[ticker] = shares
    st.rerun()

# 4. 분석 엔진 (포트폴리오 최적화 & 리밸런싱)
def calculate_portfolio(portfolio, rules):
    if not portfolio: return {}, 0, [], []
    
    holdings, total = {}, 0
    for t, s in portfolio.items():
        price = yf.Ticker(t).history(period="1d")['Close'].iloc[-1]
        holdings[t] = {'name': name_map[t], 'value': s * price, 'price': price}
        total += s * price
        
    issues, orders = [], []
    
    # 룰 기반 분석
    core_val = holdings.get('365990.KS', {}).get('value', 0) + holdings.get('133690.KS', {}).get('value', 0)
    if core_val / total < rules['core_min']:
        issues.append(f"코어비중 낮음. S&P500 매수 필요.")
        orders.append({'action': '매수', 'ticker': '365990.KS', 'shares': int((total * rules['core_min'] - core_val) / holdings['365990.KS']['price'])})

    # 포트폴리오 적합성 검진
    if '133690.KS' in portfolio and '365990.KS' in portfolio:
        issues.append("💡 [건강검진] 나스닥과 S&P500 동시 보유로 기술주 비중이 높습니다.")
        
    return holdings, total, issues, orders

holdings, total, issues, orders = calculate_portfolio(st.session_state.portfolio, st.session_state.rules)

# 5. 결과 출력
st.subheader("📊 실시간 진단 결과")
if total > 0:
    st.metric("총 평가금액", f"{total:,.0f}원")
    st.subheader("🚨 AI 진단 및 주문서")
    for issue in issues: st.warning(issue)
    if orders:
        st.dataframe(pd.DataFrame(orders))
    else:
        st.success("✅ 현재 포트폴리오 최적 상태")
else:
    st.info("종목을 추가하세요.")