import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, time
import requests
from bs4 import BeautifulSoup
from groq import Groq
import re
import json
from supabase import create_client
import hashlib

st.set_page_config(page_title="육과장 AI 풀오토 v10", layout="wide", initial_sidebar_state="collapsed")

# Supabase 연결
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 비밀번호 해시
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# 1. DB 함수 - 유저 + 포트폴리오 저장
def load_users():
    try:
        res = supabase.table('users').select("*").execute()
        users = {}
        for user in res.data:
            users[user['email']] = {
                'password': user['password'],
                'data': user['data'] if user['data'] else {}
            }
        return users
    except:
        return {}

def save_user(email, password, data):
    supabase.table('users').upsert({
        'email': email,
        'password': hash_password(password),
        'data': data
    }).execute()

def get_user_data(email):
    try:
        res = supabase.table('users').select("data").eq('email', email).execute()
        if res.data:
            return res.data[0]['data'] if res.data[0]['data'] else {}
        return {}
    except:
        return {}

def update_user_data(email, data):
    supabase.table('users').update({'data': data}).eq('email', email).execute()

# 2. 글로벌 CSS
st.markdown("""
<style>
 .main.block-container {padding-top: 1rem; padding-bottom: 0rem;}
 .stMetric {background-color: #0E1117; padding: 15px; border-radius: 10px; border: 1px solid #262730;}
 .stAlert {border-radius: 10px;}
    h1 {text-align: center; color: #FAFAFA;}
    h3 {color: #FAFAFA; border-bottom: 2px solid #FF4B4B; padding-bottom: 5px;}
</style>
""", unsafe_allow_html=True)

# 3. 로그인 상태 체크
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = None

# 4. 로그인 안됐으면 로그인 화면
if not st.session_state.logged_in:
    st.markdown("<h1>🤖 육과장 AI 풀오토 v10</h1>", unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["로그인", "회원가입"])

    with tab1:
        st.subheader("로그인")
        login_email = st.text_input("이메일", key="login_email")
        login_pw = st.text_input("비밀번호", type="password", key="login_pw")
        if st.button("로그인", type="primary", use_container_width=True):
            users = load_users()
            if login_email in users and users[login_email]['password'] == hash_password(login_pw):
                st.session_state.logged_in = True
                st.session_state.user_email = login_email
                # 유저 데이터 불러오기
                user_data = get_user_data(login_email)
                st.session_state.portfolio = user_data.get('portfolio', {})
                st.session_state.rules = user_data.get('rules', {
                    'core_min': 0.6, 'irp_risky_max': 0.7, 'cov_max': 0.15, 'single_stock_max': 0.2
                })
                st.session_state.groq_key = user_data.get('groq_key', "")
                st.session_state.account_type = user_data.get('account_type', "ISA")
                st.rerun()
            else:
                st.error("이메일 또는 비밀번호가 틀렸습니다")

    with tab2:
        st.subheader("회원가입")
        signup_email = st.text_input("이메일", key="signup_email")
        signup_pw = st.text_input("비밀번호", type="password", key="signup_pw")
        signup_pw2 = st.text_input("비밀번호 확인", type="password", key="signup_pw2")
        if st.button("회원가입", type="primary", use_container_width=True):
            if signup_pw!= signup_pw2:
                col1, col2, col3 = st.columns([3,1,1])
            elif signup_email in load_users():
                st.error("이미 가입된 이메일입니다")
            else:
                save_user(signup_email, signup_pw, {
                    'portfolio': {},
                    'rules': {'core_min': 0.6, 'irp_risky_max': 0.7, 'cov_max': 0.15, 'single_stock_max': 0.2},
                    'groq_key': "",
                    'account_type': "ISA"
                })
                st.success("회원가입 완료! 로그인해주세요")
    st.stop()

# 5. 로그인 됐으면 메인 앱
st.markdown("<h1>🤖 육과장 AI 풀오토 v10</h1>", unsafe_allow_html=True)
st.caption(f"<p style='text-align: right; color: #AAA;'>👤 {st.session_state.user_email} | <a href='#' onclick='window.location.reload()'>로그아웃</a></p>", unsafe_allow_html=True)

if st.button("로그아웃"):
    st.session_state.logged_in = False
    st.session_state.user_email = None
    st.rerun()

# 6. 장중 30초 새로고침
now = datetime.now().time()
is_market_open = time(9, 0) <= now <= time(15, 30)
if is_market_open:
    st_autorefresh(interval=30000, limit=None, key="auto_refresh")
    st.caption(f"<p style='text-align: center; color: #00FF00;'>🔴 LIVE {datetime.now().strftime('%H:%M:%S')} | 무한피드백 작동중</p>", unsafe_allow_html=True)
else:
    st.caption(f"<p style='text-align: center; color: #FFA500;'>🌙 장마감 | AI 야간 최적화중</p>", unsafe_allow_html=True)

# 7. 상태 초기화
if 'portfolio' not in st.session_state: st.session_state.portfolio = {}
if 'ai_logs' not in st.session_state: st.session_state.ai_logs = []
if 'rules' not in st.session_state: st.session_state.rules = {
    'core_min': 0.6, 'irp_risky_max': 0.7, 'cov_max': 0.15, 'single_stock_max': 0.2
}
if 'groq_key' not in st.session_state: st.session_state.groq_key = ""
if 'account_type' not in st.session_state: st.session_state.account_type = "ISA"
if 'krx_list' not in st.session_state: st.session_state.krx_list = None

# 8. 한국거래소 전종목 리스트 캐싱
@st.cache_data(ttl=86400)
def get_krx_list():
    try:
        url = "http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
        df = pd.read_html(url, header=0)[0]
        df = df[['회사명', '종목코드']]
        df['종목코드'] = df['종목코드'].astype(str).str.zfill(6) + '.KS'
        etf_url = "http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13&marketType=etfMarket"
        etf_df = pd.read_html(etf_url, header=0)[0]
        etf_df = etf_df[['회사명', '종목코드']]
        etf_df['종목코드'] = etf_df['종목코드'].astype(str).str.zfill(6) + '.KS'
        full_df = pd.concat([df, etf_df]).drop_duplicates()
        return full_df.set_index('회사명')['종목코드'].to_dict()
    except:
        return {
            'KODEX 200': '069500.KS', 'TIGER 미국S&P500': '360750.KS', '삼성전자': '005930.KS',
            'TIGER 미국나스닥100': '133690.KS', 'KODEX 국고채30년': '439870.KS'
        }

if st.session_state.krx_list is None:
    with st.spinner("한국거래소 전종목 로딩중..."):
        st.session_state.krx_list = get_krx_list()

# 9. 상단 설정
with st.popover("⚙ 설정", use_container_width=True):
    new_groq_key = st.text_input("Groq API", type="password", value=st.session_state.groq_key)
    new_account_type = st.selectbox("계좌", ["IRP", "ISA", "연금저축", "일반계좌"],
                                    index=["IRP", "ISA", "연금저축", "일반계좌"].index(st.session_state.account_type))
    if st.button("설정 저장"):
        st.session_state.groq_key = new_groq_key
        st.session_state.account_type = new_account_type
        # DB에 저장
        update_user_data(st.session_state.user_email, {
            'portfolio': st.session_state.portfolio,
            'rules': st.session_state.rules,
            'groq_key': new_groq_key,
            'account_type': new_account_type
        })
        st.success("저장완료")
        st.rerun()

# 10. 종목 추가
st.subheader("💰 보유종목 관리")
col1, col2, col3 = st.columns([3, 1, 1])
search_name = col1.selectbox("종목 검색", options=list(st.session_state.krx_list.keys()), index=None, placeholder="삼성전자, TIGER 등 검색")
add_shares = col2.number_input("수량", min_value=0, step=1)
if col3.button("추가/수정", use_container_width=True, type="primary"):
    if search_name:
        ticker = st.session_state.krx_list[search_name]
        if add_shares > 0:
            st.session_state.portfolio[ticker] = add_shares
        elif ticker in st.session_state.portfolio:
            del st.session_state.portfolio[ticker]
        # DB에 저장
        update_user_data(st.session_state.user_email, {
            'portfolio': st.session_state.portfolio,
            'rules': st.session_state.rules,
            'groq_key': st.session_state.groq_key,
            'account_type': st.session_state.account_type
        })
        st.rerun()

# 11. 무한피드백 엔진
@st.cache_data(ttl=180)
def infinite_feedback_v2(groq_key, current_rules, portfolio_tickers):
    logs = []
    new_rules = current_rules.copy()
    try:
        sources = []
        soup = BeautifulSoup(requests.get("https://finance.naver.com/news/mainnews.naver", timeout=2).text, 'lxml')
        sources.append(" ".join([a.text for a in soup.select('.articleSubject a')[:20]]))
        dart = BeautifulSoup(requests.get("https://dart.fss.or.kr/dsac001/main.do", timeout=2).text, 'lxml')
        sources.append(" ".join([a.text for a in dart.select('.list_txt a')[:10]]))
        full_text = " ".join(sources)
        risks = {
            '커버드콜': len(re.findall(r'커버드콜.*위험|분배금.*삭감', full_text)),
            '금리': len(re.findall(r'금리.*인상|긴축|매파', full_text)),
            '침체': len(re.findall(r'침체|리세션|하드랜딩', full_text)),
            '개별종목': len(re.findall(r'횡령|감사의견.*거절|상장폐지', full_text))
        }
        if risks['커버드콜'] >= 2:
            new_rules['cov_max'] = 0.0
            logs.append(f"[{datetime.now().strftime('%H:%M')}] 🔴 긴급: 커버드콜 위험 {risks['커버드콜']}건. 비중 0% 강제청산")
        if risks['금리'] >= 3:
            new_rules['core_min'] = 0.4
            new_rules['single_stock_max'] = 0.1
            logs.append(f"[{datetime.now().strftime('%H:%M')}] 🔴 긴급: 금리인상 공포. 코어 40%완화, 개별주 10% 제한")
        if risks['침체'] >= 2:
            new_rules['irp_risky_max'] = 0.5
            logs.append(f"[{datetime.now().strftime('%H:%M')}] 🔴 긴급: 침체경고. IRP 위험자산 50% 제한")
        if groq_key and portfolio_tickers:
            client = Groq(api_key=groq_key)
            ticker_names = [k for k in portfolio_tickers]
            prompt = f"다음 종목 중 오늘 당장 매도해야할 위험종목 있나? 뉴스: {full_text[:1000]}\n종목: {ticker_names}\n답: 종목코드 or 없음"
            res = client.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50
            )
            danger = res.choices[0].message.content.strip()
            if danger!= "없음" and danger in portfolio_tickers:
                logs.append(f"[{datetime.now().strftime('%H:%M')}] 🔴 AI긴급: {danger} 즉시매도 권고. 뉴스에서 위험 감지")
    except Exception as e:
        logs.append(f"[{datetime.now().strftime('%H:%M')}] 피드백엔진 오류: {e}")
    return new_rules, logs

if is_market_open and st.session_state.groq_key:
    new_rules, new_logs = infinite_feedback_v2(st.session_state.groq_key, st.session_state.rules, st.session_state.portfolio)
    if new_rules!= st.session_state.rules:
        st.session_state.rules = new_rules
        # 룰 바뀌면 DB 저장
        update_user_data(st.session_state.user_email, {
            'portfolio': st.session_state.portfolio,
            'rules': st.session_state.rules,
            'groq_key': st.session_state.groq_key,
            'account_type': st.session_state.account_type
        })
    st.session_state.ai_logs.extend(new_logs)
    st.session_state.ai_logs = st.session_state.ai_logs[-50:]

# 12. 실시간 포트폴리오 계산
@st.cache_data(ttl=30)
def calc_portfolio(portfolio_dict, rules, acc_type):
    if not portfolio_dict: return {}, 0, [], [], {}
    holdings, total = {}, 0
    for ticker, shares in portfolio_dict.items():
        if shares == 0: continue
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="2d")
            price = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2]
            value = shares * price
            holdings[ticker] = {
                'name': ticker, 'shares': shares, 'price': price, 'value': value,
                'change_pct': (price/prev-1)*100, 'div': t.dividends.last('365D').sum()
            }
            total += value
        except:
            holdings[ticker] = {'name': ticker, 'shares': shares, 'price': 0, 'value': 0, 'change_pct': 0, 'div': 0}
    issues, orders = [], []
    if total == 0: return holdings, 0, ["종목 추가하세요"], [], {}
    core_tickers = ['360750.KS', '133690.KS', '069500.KS']
    core_value = sum(holdings.get(t, {}).get('value', 0) for t in core_tickers)
    if core_value / total < rules['core_min']:
        need = total * rules['core_min'] - core_value
        shares = int(need / holdings.get('360750.KS', {}).get('price', 1))
        issues.append(f"코어 {core_value/total*100:.0f}% < {rules['core_min']*100:.0f}%. S&P500 {shares}주 매수")
        orders.append({'action': '매수', 'ticker': '360750.KS', 'shares': shares, 'name': 'TIGER 미국S&P500'})
    safe_tickers = ['439870.KS', '153130.KS']
    safe_value = sum(holdings.get(t, {}).get('value', 0) for t in safe_tickers)
    risky_ratio = (total - safe_value) / total
    if acc_type == "IRP" and risky_ratio > rules['irp_risky_max']:
        need_bond = (total - safe_value) / rules['irp_risky_max'] * (1-rules['irp_risky_max']) - safe_value
        shares = int(need_bond / holdings.get('439870.KS', {}).get('price', 1))
        issues.append(f"IRP 위험 {risky_ratio*100:.1f}% > {rules['irp_risky_max']*100:.0f}%. 국고채 {shares}주 매수")
        orders.append({'action': '매수', 'ticker': '439870.KS', 'shares': shares, 'name': 'KODEX 국고채30년'})
    cov_value = holdings.get('441640.KS', {}).get('value', 0)
    if cov_value / total > rules['cov_max']:
        excess = cov_value - total * rules['cov_max']
        shares = int(excess / holdings.get('441640.KS', {}).get('price', 1))
        issues.append(f"커버드콜 {cov_value/total*100:.0f}% > {rules['cov_max']*100:.0f}%. {shares}주 매도")
        orders.append({'action': '매도', 'ticker': '441640.KS', 'shares': shares, 'name': 'TIGER 커버드콜'})
    for t, h in holdings.items():
        if h['value'] / total > rules['single_stock_max'] and t not in core_tickers + safe_tickers:
            excess = h['value'] - total * rules['single_stock_max']
            shares = int(excess / h['price'])
            issues.append(f"{t} 비중과다. {shares}주 매도")
            orders.append({'action': '매도', 'ticker': t, 'shares': shares, 'name': t})
    if not issues: issues = ["✅ 문제점 0개. 포트폴리오 최적상태"]
    return holdings, total, issues, orders, rules

holdings, total, issues, orders, current_rules = calc_portfolio(
    st.session_state.portfolio, st.session_state.rules, st.session_state.account_type
)

# 13. 대시보드 UI
if total > 0:
    prev_total = sum(st.session_state.portfolio[t] * yf.Ticker(t).history(period="2d")['Close'].iloc[-2]
                     for t in st.session_state.portfolio if st.session_state.portfolio[t] > 0)
    today_change = total - prev_total
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 총자산", f"{total:,.0f}원", f"{today_change:+,.0f}원")
    col2.metric("📈 오늘수익률", f"{today_change/prev_total*100:+.2f}%" if prev_total > 0 else "0%")
    vix = yf.Ticker('^VIX').history(period='1d')['Close'].iloc[-1]
    col3.metric("😱 VIX", f"{vix:.1f}", "위험" if vix > 30 else "안정")
    monthly_div = sum(h['div'] * h['shares'] / 12 for h in holdings.values())
    col4.metric("💵 월배당", f"{monthly_div:,.0f}원")
    st.markdown("### 🚨 AI 실시간 진단")
    for issue in issues:
        if "✅" in issue: st.success(issue)
        else: st.error(issue)
    if orders:
        st.markdown("### ⚖ 자동 리밸런싱 주문서")
        df = pd.DataFrame([{
            '종목': o['name'], '구분': o['action'], '수량': f"{o['shares']}주",
            '금액': f"{o['shares'] * holdings[o['ticker']]['price']:,.0f}원"
        } for o in orders])
        st.dataframe(df, hide_index=True, use_container_width=True)
    st.markdown("### 📡 AI 무한피드백 로그")
    with st.container(height=200):
        for log in reversed(st.session_state.ai_logs[-15:]):
            if "🔴" in log: st.error(log)
            elif "📡" in log: st.info(log)
            else: st.caption(log)
    st.markdown("### 📋 보유종목 상세")
    df_hold = pd.DataFrame([{
        '종목': h['name'], '수량': h['shares'], '현재가': f"{h['price']:,.0f}",
        '평가금액': f"{h['value']:,.0f}", '수익률': f"{h['change_pct']:+.2f}%"
    } for h in holdings.values()])
    st.dataframe(df_hold, hide_index=True, use_container_width=True)
else:
    st.info("👆 위에서 종목을 검색해서 추가하세요. AI가 자동으로 분석 시작합니다")

# 14. 현재 룰 표시
with st.expander("⚙ AI가 실시간으로 수정중인 룰"):
    st.json({k: f"{v*100:.0f}%" for k, v in st.session_state.rules.items()})

st.caption("v10 풀오토: 종목무제한 + 무한피드백 + 승인없이 자동실행. 개인자산증가 전용")
