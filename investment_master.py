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

st.set_page_config(page_title="육과장 AI 풀오토 v11", layout="wide", initial_sidebar_state="collapsed")

# Supabase 연결
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# ========== 디버그 - 화면에 뜨는 값 보내주면 바로 해결해줌 ==========
st.title("Supabase 키 디버깅")
newline_check = '\n' in SUPABASE_KEY or '\r' in SUPABASE_KEY
space_check = ' ' in SUPABASE_KEY or SUPABASE_KEY.startswith(' ') or SUPABASE_KEY.endswith(' ')
slash_check = SUPABASE_URL.endswith('/')

st.write(f"URL: {SUPABASE_URL}")
st.write(f"KEY 길이: {len(SUPABASE_KEY)}")
st.write(f"KEY 앞 30자: {SUPABASE_KEY[:30]}")
st.write(f"KEY 뒤 30자: {SUPABASE_KEY[-30:]}")
st.write(f"URL 끝에 / 있음?: {slash_check}")
st.write(f"KEY에 줄바꿈 있음?: {newline_check}")
st.write(f"KEY에 공백 있음?: {space_check}")
st.stop()
# ========== 디버그 끝 - 값 확인 후 이 블록 11줄 삭제하고 푸시 ==========

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 비밀번호 해시
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# 1. DB 함수
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
    except Exception as e:
        st.error(f"DB 연결 오류: {e}")
        return {}

def save_user(email, password, data):
    try:
        supabase.table('users').upsert({
            'email': email,
            'password': hash_password(password),
            'data': data
        }).execute()
        return True
    except Exception as e:
        st.error(f"회원가입 DB 오류: {e}")
        return False

def update_user_data(email, data):
    try:
        supabase.table('users').update({'data': data}).eq('email', email).execute()
    except Exception as e:
        st.error(f"데이터 저장 오류: {e}")

# 2. 육과장 템플릿 종목
YUK_TEMPLATES = {
    "육과장 코어4종": {
        '360750.KS': 10, # TIGER 미국S&P500
        '133690.KS': 10, # TIGER 미국나스닥100
        '458730.KS': 10, # TIGER 미국배당다우존스
        '439870.KS': 10 # KODEX 국고채30년액티브
    },
    "반도체 올인": {
        '091230.KS': 10, # TIGER 반도체
        '005930.KS': 10 # 삼성전자
    }
}

# 3. 글로벌 CSS
st.markdown("""
<style>
.main.block-container {padding-top: 1rem; padding-bottom: 0rem;}
.stMetric {background-color: #0E1117; padding: 15px; border-radius: 10px; border: 1px solid #262730;}
.stAlert {border-radius: 10px;}
    h1 {text-align: center; color: #FAFAFA;}
    h3 {color: #FAFAFA; border-bottom: 2px solid #FF4B4B; padding-bottom: 5px;}
</style>
""", unsafe_allow_html=True)

# 4. 로그인 상태 체크
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = None

# 5. 로그인 화면
if not st.session_state.logged_in:
    st.markdown("<h1>🤖 육과장 AI 풀오토 v11</h1>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["로그인", "회원가입"])

    with tab1:
        st.subheader("로그인")
        login_email = st.text_input("이메일", key="login_email")
        login_pw = st.text_input("비밀번호", type="password", key="login_pw")
        if st.button("로그인", type="primary", use_container_width=True):
            users = load_users()
            input_hash = hash_password(login_pw)
            if login_email in users:
                if users[login_email]['password'] == input_hash:
                    st.session_state.logged_in = True
                    st.session_state.user_email = login_email
                    user_data = users[login_email]['data']
                    st.session_state.portfolio = user_data.get('portfolio', {})
                    st.session_state.rules = user_data.get('rules', {
                        'core_min': 0.6, 'irp_risky_max': 0.7, 'cov_max': 0.15, 'single_stock_max': 0.2
                    })
                    st.session_state.groq_key = user_data.get('groq_key', "")
                    st.session_state.account_type = user_data.get('account_type', "ISA")
                    st.rerun()
                else:
                    st.error(f"비밀번호 불일치")
            else:
                st.error("존재하지 않는 이메일입니다")

    with tab2:
        st.subheader("회원가입")
        signup_email = st.text_input("이메일", key="signup_email")
        signup_pw = st.text_input("비밀번호", type="password", key="signup_pw")
        signup_pw2 = st.text_input("비밀번호 확인", type="password", key="signup_pw2")
        if st.button("회원가입", type="primary", use_container_width=True):
            if signup_pw!= signup_pw2:
                st.error("비밀번호가 일치하지 않습니다")
            elif not signup_email or not signup_pw:
                st.error("이메일과 비밀번호를 입력하세요")
            elif signup_email in load_users():
                st.error("이미 가입된 이메일입니다")
            else:
                success = save_user(signup_email, signup_pw, {
                    'portfolio': {},
                    'rules': {'core_min': 0.6, 'irp_risky_max': 0.7, 'cov_max': 0.15, 'single_stock_max': 0.2},
                    'groq_key': "",
                    'account_type': "ISA"
                })
                if success:
                    st.success("회원가입 완료! 로그인해주세요")
                    st.balloons()
    st.stop()

# 6. 메인 앱
st.markdown("<h1>🤖 육과장 AI 풀오토 v11</h1>", unsafe_allow_html=True)
col_user, col_logout = st.columns([5,1])
col_user.caption(f"👤 {st.session_state.user_email}")
if col_logout.button("로그아웃", use_container_width=True):
    st.session_state.logged_in = False
    st.session_state.user_email = None
    st.rerun()

# 7. 장중 새로고침
now = datetime.now().time()
is_market_open = time(9, 0) <= now <= time(15, 30)
if is_market_open:
    st_autorefresh(interval=30000, limit=None, key="auto_refresh")
    st.caption(f"<p style='text-align: center; color: #00FF00;'>🔴 LIVE {datetime.now().strftime('%H:%M:%S')} | 무한피드백 작동중</p>", unsafe_allow_html=True)
else:
    st.caption(f"<p style='text-align: center; color: #FFA500;'>🌙 장마감 | AI 야간 최적화중</p>", unsafe_allow_html=True)

# 8. 상태 초기화
if 'portfolio' not in st.session_state: st.session_state.portfolio = {}
if 'ai_logs' not in st.session_state: st.session_state.ai_logs = []
if 'rules' not in st.session_state: st.session_state.rules = {'core_min': 0.6, 'irp_risky_max': 0.7, 'cov_max': 0.15, 'single_stock_max': 0.2}
if 'groq_key' not in st.session_state: st.session_state.groq_key = ""
if 'account_type' not in st.session_state: st.session_state.account_type = "ISA"
if 'krx_list' not in st.session_state: st.session_state.krx_list = None
if 'ai_recommendations' not in st.session_state: st.session_state.ai_recommendations = []

# 9. KRX + 미국 종목 리스트
@st.cache_data(ttl=86400)
def get_krx_list():
    try:
        url = "http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
        df = pd.read_html(url, header=0)[0][['회사명', '종목코드']]
        df['종목코드'] = df['종목코드'].astype(str).str.zfill(6) + '.KS'
        etf_url = "http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13&marketType=etfMarket"
        etf_df = pd.read_html(etf_url, header=0)[0][['회사명', '종목코드']]
        etf_df['종목코드'] = etf_df['종목코드'].astype(str).str.zfill(6) + '.KS'
        full_df = pd.concat([df, etf_df]).drop_duplicates()
        krx_dict = full_df.set_index('회사명')['종목코드'].to_dict()
        us_stocks = {
            '애플': 'AAPL', '마이크로소프트': 'MSFT', '엔비디아': 'NVDA', '테슬라': 'TSLA',
            'S&P500 ETF': 'SPY', '나스닥100 ETF': 'QQQ', '미국배당다우': 'SCHD'
        }
        krx_dict.update(us_stocks)
        return krx_dict
    except:
        return {'KODEX 200': '069500.KS', 'TIGER 미국S&P500': '360750.KS', '애플': 'AAPL'}

if st.session_state.krx_list is None:
    with st.spinner("전종목 로딩중..."):
        st.session_state.krx_list = get_krx_list()

# 10. 설정
with st.popover("⚙ 설정", use_container_width=True):
    new_groq_key = st.text_input("Groq API Key", type="password", value=st.session_state.groq_key, help="https://console.groq.com/keys 무료")
    new_account_type = st.selectbox("계좌", ["IRP", "ISA", "연금저축", "일반계좌"],
                                    index=["IRP", "ISA", "연금저축", "일반계좌"].index(st.session_state.account_type))
    if st.button("설정 저장"):
        st.session_state.groq_key = new_groq_key
        st.session_state.account_type = new_account_type
        update_user_data(st.session_state.user_email, {
            'portfolio': st.session_state.portfolio,
            'rules': st.session_state.rules,
            'groq_key': new_groq_key,
            'account_type': new_account_type
        })
        st.success("저장완료")
        st.rerun()

# 11. 육과장 템플릿 버튼
st.subheader("🚀 원클릭 템플릿")
col_t1, col_t2 = st.columns(2)
for idx, (name, stocks) in enumerate(YUK_TEMPLATES.items()):
    if [col_t1, col_t2][idx].button(f"{name} 추가", use_container_width=True):
        for ticker, shares in stocks.items():
            st.session_state.portfolio[ticker] = st.session_state.portfolio.get(ticker, 0) + shares
        update_user_data(st.session_state.user_email, {
            'portfolio': st.session_state.portfolio,
            'rules': st.session_state.rules,
            'groq_key': st.session_state.groq_key,
            'account_type': st.session_state.account_type
        })
        st.success(f"{name} 포트폴리오에 추가됨!")
        st.rerun()

# 12. 종목 추가 - 제한없음
st.subheader("💰 보유종목 관리")
col1, col2, col3 = st.columns([3, 1, 1])
search_name = col1.selectbox("종목 검색", options=list(st.session_state.krx_list.keys()), index=None, placeholder="삼성전자, AAPL, TIGER 등 검색")
manual_ticker = col1.text_input("또는 티커 직접입력", placeholder="예: NVDA, 005930.KS")
add_shares = col2.number_input("수량", min_value=0, step=1)
if col3.button("추가/수정", use_container_width=True, type="primary"):
    ticker = manual_ticker if manual_ticker else (st.session_state.krx_list.get(search_name) if search_name else None)
    if ticker:
        if add_shares > 0:
            st.session_state.portfolio[ticker] = add_shares
        elif ticker in st.session_state.portfolio:
            del st.session_state.portfolio[ticker]
        update_user_data(st.session_state.user_email, {
            'portfolio': st.session_state.portfolio,
            'rules': st.session_state.rules,
            'groq_key': st.session_state.groq_key,
            'account_type': st.session_state.account_type
        })
        st.rerun()
    else:
        st.error("종목을 선택하거나 티커를 입력하세요")

# 13. AI 추천 엔진 - 뉴스+테마 분석
@st.cache_data(ttl=600)
def ai_recommendation_engine(groq_key, portfolio_tickers):
    if not groq_key: return []
    try:
        client = Groq(api_key=groq_key)
        sources = []
        urls = [
            "https://finance.naver.com/news/mainnews.naver",
            "https://www.hankyung.com/economy",
            "https://www.mk.co.kr/news/economy/"
        ]
        for url in urls:
            soup = BeautifulSoup(requests.get(url, timeout=3).text, 'lxml')
            sources.append(" ".join([a.text for a in soup.select('a')[:30]]))
        full_text = " ".join(sources)[:3000]

        prompt = f"""너는 육과장처럼 개인투자자 자산증식 전문 AI야.
뉴스: {full_text}
현재 보유: {list(portfolio_tickers.keys())}
위 뉴스 기반으로 지금 사야할 종목 3개만 추천해. 이유도 초보자용으로 쉽게.
형식: 티커|종목명|이유
예: AAPL|애플|AI반도체 수요폭증으로 실적 기대"""

        res = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300
        )
        recs = []
        for line in res.choices[0].message.content.strip().split('\n'):
            if '|' in line:
                parts = line.split('|')
                if len(parts) == 3:
                    recs.append({'ticker': parts[0].strip(), 'name': parts[1].strip(), 'reason': parts[2].strip()})
        return recs
    except Exception as e:
        return [{'ticker': 'ERROR', 'name': '오류', 'reason': str(e)}]

if st.session_state.groq_key:
    st.session_state.ai_recommendations = ai_recommendation_engine(st.session_state.groq_key, st.session_state.portfolio)

# 14. AI 추천 표시
if st.session_state.ai_recommendations:
    st.subheader("🎯 AI 실시간 추천")
    for rec in st.session_state.ai_recommendations:
        if rec['ticker'] == 'ERROR':
            st.error(f"추천 엔진 오류: {rec['reason']}")
        else:
            col_r1, col_r2, col_r3 = st.columns([2,3,1])
            col_r1.markdown(f"**{rec['name']}** `{rec['ticker']}`")
            col_r2.caption(rec['reason'])
            if col_r3.button("담기", key=f"add_{rec['ticker']}"):
                st.session_state.portfolio[rec['ticker']] = st.session_state.portfolio.get(rec['ticker'], 0) + 1
                update_user_data(st.session_state.user_email, {
                    'portfolio': st.session_state.portfolio,
                    'rules': st.session_state.rules,
                    'groq_key': st.session_state.groq_key,
                    'account_type': st.session_state.account_type
                })
                st.rerun()

# 15. 무한피드백 엔진
@st.cache_data(ttl=180)
def infinite_feedback_v2(groq_key, current_rules, portfolio_tickers):
    logs = []
    new_rules = current_rules.copy()
    try:
        soup = BeautifulSoup(requests.get("https://finance.naver.com/news/mainnews.naver", timeout=2).text, 'lxml')
        full_text = " ".join([a.text for a in soup.select('.articleSubject a')[:20]])
        risks = {
            '커버드콜': len(re.findall(r'커버드콜.*위험|분배금.*삭감', full_text)),
            '금리': len(re.findall(r'금리.*인상|긴축|매파', full_text)),
            '침체': len(re.findall(r'침체|리세션|하드랜딩', full_text))
        }
        if risks['커버드콜'] >= 2:
            new_rules['cov_max'] = 0.0
            logs.append(f"[{datetime.now().strftime('%H:%M')}] 🔴 긴급: 커버드콜 위험. 비중 0% 강제")
        if risks['금리'] >= 3:
            new_rules['core_min'] = 0.4
            logs.append(f"[{datetime.now().strftime('%H:%M')}] 🔴 긴급: 금리인상. 코어 40%로 완화")
        if risks['침체'] >= 2:
            new_rules['irp_risky_max'] = 0.5
            logs.append(f"[{datetime.now().strftime('%H:%M')}] 🔴 긴급: 침체경고. IRP 위험자산 50% 제한")
    except Exception as e:
        logs.append(f"[{datetime.now().strftime('%H:%M')}] 피드백 오류: {e}")
    return new_rules, logs

if is_market_open and st.session_state.groq_key:
    new_rules, new_logs = infinite_feedback_v2(st.session_state.groq_key, st.session_state.rules, st.session_state.portfolio)
    if new_rules!= st.session_state.rules:
        st.session_state.rules = new_rules
        update_user_data(st.session_state.user_email, {
            'portfolio': st.session_state.portfolio,
            'rules': st.session_state.rules,
            'groq_key': st.session_state.groq_key,
            'account_type': st.session_state.account_type
        })
    st.session_state.ai_logs.extend(new_logs)
    st.session_state.ai_logs = st.session_state.ai_logs[-50:]

# 16. 포트폴리오 계산
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
            prev = hist['Close'].iloc[-2] if len(hist) > 1 else price
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

    core_tickers = ['360750.KS', '133690.KS', '069500.KS', 'SPY', 'QQQ']
    core_value = sum(holdings.get(t, {}).get('value', 0) for t in core_tickers if t in holdings)
    if core_value / total < rules['core_min']:
        need = total * rules['core_min'] - core_value
        shares = int(need / holdings.get('360750.KS', {}).get('price', 10000))
        issues.append(f"코어 {core_value/total*100:.0f}% < {rules['core_min']*100:.0f}%. S&P500 {shares}주 매수")
        orders.append({'action': '매수', 'ticker': '360750.KS', 'shares': shares, 'name': 'TIGER 미국S&P500'})

    if not issues: issues = ["✅ 문제점 0개. 포트폴리오 최적상태"]
    return holdings, total, issues, orders, rules

holdings, total, issues, orders, current_rules = calc_portfolio(
    st.session_state.portfolio, st.session_state.rules, st.session_state.account_type
)

# 17. 대시보드
if total > 0:
    try:
        prev_total = sum(st.session_state.portfolio[t] * yf.Ticker(t).history(period="2d")['Close'].iloc[-2]
                         for t in st.session_state.portfolio if st.session_state.portfolio[t] > 0)
        today_change = total - prev_total
    except:
        today_change = 0
        prev_total = total

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 총자산", f"{total:,.0f}원", f"{today_change:+,.0f}원")
    col2.metric("📈 오늘수익률", f"{today_change/prev_total*100:+.2f}%" if prev_total > 0 else "0%")
    try:
        vix = yf.Ticker('^VIX').history(period='1d')['Close'].iloc[-1]
    except:
        vix = 0
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
            else: st.caption(log)

    st.markdown("### 📋 보유종목 상세")
    df_hold = pd.DataFrame([{
        '종목': h['name'], '수량': h['shares'], '현재가': f"{h['price']:,.0f}",
        '평가금액': f"{h['value']:,.0f}", '수익률': f"{h['change_pct']:+.2f}%"
    } for h in holdings.values()])
    st.dataframe(df_hold, hide_index=True, use_container_width=True)
else:
    st.info("👆 위에서 육과장 템플릿 클릭하거나 종목을 검색해서 추가하세요")

# 18. 초보자 설명
with st.expander("❓ 왜 코어 비중 60%여야 하나요?"):
    st.write("""
    **육과장 공식 답변:** 코어는 S&P500, 나스닥 같은 우량 지수예요.
    개별주 100% 몰빵하면 한방에 훅 가지만, 코어 60% 이상이면 시장 평균 수익은 먹고 들어가요.
    2008년 금융위기에도 S&P500은 5년만에 회복했어요. 개별주는 상장폐지되면 0원이죠.
    그래서 초보는 코어부터 채우는 게 자산증식 1순위입니다.
    """)

with st.expander("⚙ AI가 실시간으로 수정중인 룰"):
    st.json({k: f"{v*100:.0f}%" for k, v in st.session_state.rules.items()})

st.caption("v11 풀오토: 육과장 템플릿 + AI추천 + 신상ETF 감지 + 무한피드백")
