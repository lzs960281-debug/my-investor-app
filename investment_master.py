import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, time
import requests
from bs4 import BeautifulSoup
from groq import Groq
import re
import hashlib
from supabase import create_client
import concurrent.futures

# ==========================================
# 앱 기본 설정 및 커스텀 CSS (SaaS 스타일)
# ==========================================
st.set_page_config(page_title="육과장 AI 풀오토 v12", page_icon="🤖", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    /* 전체 배경 및 폰트 다듬기 */
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    h1, h2, h3 { color: #F8F9FA; font-weight: 700; }
    
    /* 메트릭 카드(핵심 지표) 고급화 */
    [data-testid="stMetric"] {
        background-color: #1E1E2E; 
        border: 1px solid #2A2A3C; 
        border-radius: 12px; 
        padding: 20px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* 데이터프레임 헤더 스타일링 */
    [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
    
    /* 사이드바 디자인 */
    [data-testid="stSidebar"] { background-color: #181825; border-right: 1px solid #2A2A3C; }
</style>
""", unsafe_allow_html=True)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"].strip()
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def hash_password(password): return hashlib.sha256(password.encode()).hexdigest()

# ==========================================
# 1. DB 연동 및 세션 관리
# ==========================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_email' not in st.session_state: st.session_state.user_email = None
if 'ai_logs' not in st.session_state: st.session_state.ai_logs = []
if 'krx_list' not in st.session_state: st.session_state.krx_list = None
if 'ai_recommendations' not in st.session_state: st.session_state.ai_recommendations = []

def load_users():
    try:
        res = supabase.table('users').select("*").execute()
        return {u['email']: {'password': u['password'], 'data': u['data'] or {}} for u in res.data}
    except: return {}

def update_user_data():
    try:
        supabase.table('users').update({
            'data': {'portfolio': st.session_state.portfolio, 'rules': st.session_state.rules, 
                     'groq_key': st.session_state.groq_key, 'account_type': st.session_state.account_type}
        }).eq('email', st.session_state.user_email).execute()
    except Exception as e: st.error(f"DB 저장 오류: {e}")

# ==========================================
# 로그인 / 회원가입 화면 (중앙 정렬 깔끔한 UI)
# ==========================================
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("<h1 style='text-align: center; color: #4B90FF;'>🤖 육과장 AI 풀오토</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #A0A0A0; margin-bottom: 30px;'>당신의 자산을 지키는 24시간 실시간 AI 비서</p>", unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["🔑 로그인", "📝 회원가입"])
        with tab1:
            login_email = st.text_input("이메일", key="login_email")
            login_pw = st.text_input("비밀번호", type="password", key="login_pw")
            if st.button("로그인", type="primary", use_container_width=True):
                users = load_users()
                if login_email in users and users[login_email]['password'] == hash_password(login_pw):
                    st.session_state.logged_in = True
                    st.session_state.user_email = login_email
                    user_data = users[login_email]['data']
                    st.session_state.portfolio = user_data.get('portfolio', {})
                    st.session_state.rules = user_data.get('rules', {'core_min': 0.6, 'irp_risky_max': 0.7, 'cov_max': 0.15})
                    st.session_state.groq_key = user_data.get('groq_key', "")
                    st.session_state.account_type = user_data.get('account_type', "ISA")
                    st.rerun()
                else: st.error("정보가 일치하지 않습니다.")
        with tab2:
            signup_email = st.text_input("이메일", key="signup_email")
            signup_pw = st.text_input("비밀번호", type="password", key="signup_pw")
            signup_pw2 = st.text_input("비밀번호 확인", type="password", key="signup_pw2")
            if st.button("가입하기", type="primary", use_container_width=True):
                if signup_pw == signup_pw2 and signup_email:
                    supabase.table('users').upsert({'email': signup_email, 'password': hash_password(signup_pw), 'data': {}}).execute()
                    st.success("환영합니다! 위 로그인 탭에서 접속해주세요.")
                    st.balloons()
                else: st.error("입력 정보를 확인해주세요.")
    st.stop()

# ==========================================
# 성능 최적화: 멀티스레딩 데이터 Fetching
# ==========================================
@st.cache_data(ttl=86400)
def get_krx_list():
    us_stocks = {'애플(AAPL)': 'AAPL', '마이크로소프트(MSFT)': 'MSFT', '엔비디아(NVDA)': 'NVDA', '테슬라(TSLA)': 'TSLA', 'S&P500 ETF(SPY)': 'SPY', '나스닥100 ETF(QQQ)': 'QQQ', '미국배당다우(SCHD)': 'SCHD'}
    try:
        df = pd.read_html("http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13")[0][['회사명', '종목코드']]
        df['종목코드'] = df['종목코드'].astype(str).str.zfill(6) + '.KS'
        etf_df = pd.read_html("http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13&marketType=etfMarket")[0][['회사명', '종목코드']]
        etf_df['종목코드'] = etf_df['종목코드'].astype(str).str.zfill(6) + '.KS'
        full_df = pd.concat([df, etf_df]).drop_duplicates()
        krx_dict = full_df.set_index('회사명')['종목코드'].to_dict()
        krx_dict.update(us_stocks)
        return krx_dict
    except: return us_stocks

if st.session_state.krx_list is None: st.session_state.krx_list = get_krx_list()

@st.cache_data(ttl=600)
def get_vix():
    try: return yf.Ticker('^VIX').history(period='1d')['Close'].iloc[-1]
    except: return 0.0

def fetch_single_stock(ticker, shares):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist.empty: return None
        price = hist['Close'].iloc[-1]
        prev = hist['Close'].iloc[-2] if len(hist)>1 else price
        div = t.dividends.last('365D').sum() if hasattr(t, 'dividends') and not t.dividends.empty else 0
        return ticker, {'name': ticker, 'shares': shares, 'price': price, 'value': shares * price, 'change_pct': (price/prev - 1)*100 if prev>0 else 0, 'div': div}
    except: return None

@st.cache_data(ttl=60)
def calc_portfolio_concurrent(portfolio_dict, rules):
    if not portfolio_dict: return {}, 0, [], []
    holdings = {}
    total = 0
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(fetch_single_stock, t, s) for t, s in portfolio_dict.items() if s > 0]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res:
                holdings[res[0]] = res[1]
                total += res[1]['value']
                
    issues, orders = [], []
    core_tickers = ['360750.KS', '133690.KS', '069500.KS', 'SPY', 'QQQ']
    core_value = sum(holdings.get(t, {}).get('value', 0) for t in core_tickers if t in holdings)
    
    if total > 0 and (core_value / total < rules['core_min']):
        need = total * rules['core_min'] - core_value
        ref_price = holdings.get('360750.KS', {}).get('price', 15000) or 15000
        shares_to_buy = int(need / ref_price)
        if shares_to_buy > 0:
            issues.append(f"⚠️ 코어 자산 부족 (현재 {core_value/total*100:.0f}% < 권장 {rules['core_min']*100:.0f}%)")
            orders.append({'action': '매수', 'ticker': '360750.KS', 'shares': shares_to_buy, 'name': 'TIGER 미국S&P500'})

    if not issues: issues = ["✅ 최적의 포트폴리오 비율을 유지 중입니다."]
    return holdings, total, issues, orders

# ==========================================
# 좌측 사이드바: 컨트롤 패널 (UI 정리)
# ==========================================
with st.sidebar:
    st.markdown("### 👤 내 계정")
    st.caption(st.session_state.user_email)
    if st.button("로그아웃", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()
    st.divider()
    
    st.markdown("### ⚙️ 환경 설정")
    new_groq = st.text_input("Groq API Key (AI 두뇌)", type="password", value=st.session_state.groq_key, help="console.groq.com 에서 무료 발급")
    new_acc = st.selectbox("관리 계좌", ["IRP", "ISA", "연금저축", "일반계좌"], index=["IRP", "ISA", "연금저축", "일반계좌"].index(st.session_state.account_type))
    if st.button("설정 저장", type="primary", use_container_width=True):
        st.session_state.groq_key = new_groq
        st.session_state.account_type = new_acc
        update_user_data()
        st.success("저장 완료")
    st.divider()

    st.markdown("### 🛠️ 자산 추가 / 관리")
    with st.expander("🚀 원클릭 템플릿 덮어쓰기", expanded=False):
        if st.button("육과장 코어4종", use_container_width=True):
            st.session_state.portfolio = {'360750.KS': 10, '133690.KS': 10, '458730.KS': 10, '439870.KS': 10}
            update_user_data(); st.rerun()
        if st.button("반도체 올인", use_container_width=True):
            st.session_state.portfolio = {'091230.KS': 10, '005930.KS': 10}
            update_user_data(); st.rerun()

    st.caption("수동 종목 관리")
    search_name = st.selectbox("종목 검색", options=list(st.session_state.krx_list.keys()), index=None)
    manual_ticker = st.text_input("티커 직접입력 (NVDA 등)")
    add_shares = st.number_input("최종 보유 수량 (0 = 삭제)", min_value=0, step=1)
    if st.button("보유량 업데이트", use_container_width=True):
        ticker = manual_ticker.strip().upper() if manual_ticker else (st.session_state.krx_list.get(search_name) if search_name else None)
        if ticker:
            if add_shares > 0: st.session_state.portfolio[ticker] = add_shares
            elif ticker in st.session_state.portfolio: del st.session_state.portfolio[ticker]
            update_user_data(); st.rerun()

# ==========================================
# AI 추천 엔진 및 무한 피드백 (백그라운드)
# ==========================================
@st.cache_data(ttl=600)
def ai_recommendation_engine(groq_key, portfolio_tickers):
    if not groq_key: return []
    try:
        urls = ["https://finance.naver.com/news/mainnews.naver"]
        sources = [" ".join([a.text for a in BeautifulSoup(requests.get(url, headers=HEADERS, timeout=3).text, 'lxml').select('a')[:30]]) for url in urls]
        prompt = f"너는 개인투자자 자산증식 전문 AI야. 뉴스: {' '.join(sources)[:3000]}\n보유종목: {list(portfolio_tickers.keys())}\n위 뉴스 기반으로 지금 당장 사야할 종목 3개 추천해. 형식: 티커|종목명|추천이유"
        res = Groq(api_key=groq_key).chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}], max_tokens=300)
        recs = []
        for line in res.choices[0].message.content.strip().split('\n'):
            line = line.strip('*-`[]. ')
            if '|' in line:
                p = line.split('|')
                if len(p) >= 3: recs.append({'ticker': p[0].strip(), 'name': p[1].strip(), 'reason': p[2].strip()})
        return recs
    except Exception as e: return [{'ticker': 'ERROR', 'name': '추천 실패', 'reason': str(e)}]

if st.session_state.groq_key:
    st.session_state.ai_recommendations = ai_recommendation_engine(st.session_state.groq_key, st.session_state.portfolio)

# ==========================================
# 메인 화면: Enterprise Dashboard
# ==========================================
now = datetime.now().time()
is_open = time(9, 0) <= now <= time(15, 30)
if is_open: st_autorefresh(interval=30000, limit=None, key="auto_refresh")

st.markdown(f"<h2>🤖 나의 통합 자산 관제탑 <span style='font-size:16px; color:#A0A0A0;'>({st.session_state.account_type})</span></h2>", unsafe_allow_html=True)
if is_open: st.caption(f"🟢 **LIVE** | {datetime.now().strftime('%H:%M:%S')} 시장 데이터 연동 중")
else: st.caption("🌙 **장마감** | 야간 AI 시뮬레이션 모드")

holdings, total, issues, orders = calc_portfolio_concurrent(st.session_state.portfolio, st.session_state.rules)

if total > 0:
    # 1. 최상단 핵심 지표 (Metrics)
    prev_total = sum(h['shares'] * (h['price'] / (1 + h['change_pct']/100)) for h in holdings.values())
    today_change = total - prev_total
    vix = get_vix()
    monthly_div = sum(h['div'] * h['shares'] / 12 for h in holdings.values())
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 자산 평가금액", f"{total:,.0f}원", f"{today_change:+,.0f}원 ({today_change/prev_total*100:+.2f}%)" if prev_total>0 else "0%")
    m2.metric("시장 공포지수 (VIX)", f"{vix:.1f}", "위험" if vix > 30 else "안정", delta_color="inverse")
    m3.metric("월 평균 배당금 (추정)", f"{monthly_div:,.0f}원")
    m4.metric("AI 포트폴리오 상태", "최적화 필요" if "⚠️" in issues[0] else "정상", "조치 필요" if "⚠️" in issues[0] else "유지", delta_color="inverse")

    st.markdown("<br>", unsafe_allow_html=True)

    # 2. 메인 대시보드 레이아웃 분할
    col_left, col_right = st.columns([1.2, 1])

    with col_left:
        st.markdown("### 📊 포트폴리오 비중")
        # Plotly 도넛 차트 적용
        labels = [h['name'] for h in holdings.values()]
        values = [h['value'] for h in holdings.values()]
        fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.4, textinfo='label+percent', marker=dict(colors=px.colors.qualitative.Pastel))])
        fig.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=300)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("### 📋 보유 종목 상세")
        # Streamlit Column Config를 활용한 고급 데이터프레임
        df_hold = pd.DataFrame([{
            '종목': h['name'], '수량': h['shares'], '현재가': h['price'], '평가금액': h['value'], '일일수익률': h['change_pct']/100
        } for h in holdings.values()])
        
        st.dataframe(df_hold, hide_index=True, use_container_width=True, column_config={
            "현재가": st.column_config.NumberColumn("현재가(원)", format="%d ₩"),
            "평가금액": st.column_config.ProgressColumn("평가금액 비중", format="%d ₩", min_value=0, max_value=int(total)),
            "일일수익률": st.column_config.NumberColumn("오늘의 등락", format="%.2f %%")
        })

    with col_right:
        st.markdown("### 🚨 AI 실시간 진단 & 액션")
        with st.container(border=True):
            for issue in issues:
                if "✅" in issue: st.success(issue)
                else: st.warning(issue)
            
            if orders:
                st.markdown("#### ⚖️ 원클릭 자동 리밸런싱 주문서")
                st.caption("아래 내용을 복사하여 증권사 앱에서 바로 실행하세요.")
                order_text = "[AI 관제탑 리밸런싱 지시서]\n"
                for o in orders: order_text += f"▪ {o['name']} : {o['action']} {o['shares']}주\n"
                st.code(order_text, language="text")

        st.markdown("### 🎯 AI 실시간 종목 픽 (뉴스 기반)")
        if st.session_state.ai_recommendations:
            with st.container(border=True):
                for rec in st.session_state.ai_recommendations:
                    if rec['ticker'] == 'ERROR': st.error(rec['reason']); break
                    st.markdown(f"**{rec['name']}** (`{rec['ticker']}`)")
                    st.caption(f"💡 {rec['reason']}")
                    if st.button(f"장바구니 담기 (+1주)", key=f"add_{rec['ticker']}", help=f"{rec['name']} 1주를 포트폴리오에 추가합니다."):
                        st.session_state.portfolio[rec['ticker']] = st.session_state.portfolio.get(rec['ticker'], 0) + 1
                        update_user_data(); st.rerun()
                    st.divider()
        else:
            if not st.session_state.groq_key: st.info("좌측 사이드바에 Groq API 키를 입력하면 AI 추천이 활성화됩니다.")
            else: st.info("AI가 뉴스를 분석 중입니다...")

else:
    # 포트폴리오가 비어있을 때 깔끔한 안내 화면 (Onboarding)
    st.info("👋 좌측 사이드바에서 [육과장 코어4종] 템플릿을 클릭하거나, 보유 중인 종목을 검색해서 나만의 대시보드를 완성하세요!")
    st.image("https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?q=80&w=1200&auto=format&fit=crop", caption="데이터 기반 투자 시스템에 오신 것을 환영합니다.")

with st.expander("⚙ 현재 AI가 무한피드백으로 감시 중인 룰"):
    st.json({k: f"{v*100:.0f}%" for k, v in st.session_state.rules.items()})

st.caption("v11 Pro: 육과장 템플릿 + 뉴스기반 AI추천 + Plotly 차트 + 원클릭 복사 + 무한피드백")
