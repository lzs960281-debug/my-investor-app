import streamlit as st
import yfinance as yf
import pandas as pd
from groq import Groq

# 1. 페이지 설정
st.set_page_config(page_title="육과장 AI 풀오토", layout="wide")
st.title("🤖 육과장 AI - 풀오토 자산관리")

# 2. 상태 초기화
if 'portfolio' not in st.session_state: st.session_state.portfolio = {}
if 'rules' not in st.session_state: st.session_state.rules = {'core_min': 0.6, 'cov_max': 0.15}

# 3. 사이드바 UI
st.sidebar.header("🔑 종목 관리")
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

# 4. 분석 로직
def calculate_portfolio(portfolio, rules):
    if not portfolio: return {}, 0, [], []
    holdings, total = {}, 0
    for t, s in portfolio.items():
        if s > 0:
            price = yf.Ticker(t).history(period="1d")['Close'].iloc[-1]
            holdings[t] = {'name': name_map[t], 'value': s * price, 'price': price}
            total += s * price
            
    issues, orders = [], []
    # 코어 비중 체크
    core_val = holdings.get('365990.KS', {}).get('value', 0) + holdings.get('133690.KS', {}).get('value', 0)
    if total > 0 and (core_val / total < rules['core_min']):
        issues.append("⚠️ 코어비중 부족. S&P500 추가 매수 권장.")
        orders.append({'종목': 'S&P500', '주문': '매수'})
    
    return holdings, total, issues, orders

# 5. 화면 출력
holdings, total, issues, orders = calculate_portfolio(st.session_state.portfolio, st.session_state.rules)

if total > 0:
    st.metric("총 평가금액", f"{total:,.0f}원")
    st.subheader("🚨 AI 진단 결과")
    for issue in issues: st.warning(issue)
    if not issues: st.success("✅ 포트폴리오 최적 상태")
    
    if orders:
        st.subheader("⚖️ 리밸런싱 주문서")
        st.table(pd.DataFrame(orders))
else:
    st.info("사이드바에서 종목을 추가하세요.")
