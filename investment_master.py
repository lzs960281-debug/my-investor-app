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
import hashlib
from supabase import create_client

# ==========================================
# 앱 기본 설정
# ==========================================
st.set_page_config(page_title="육과장 AI 풀오토 v11 Pro", layout="wide", initial_sidebar_state="collapsed")

# 크롤링 차단 방지용 브라우저 헤더
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Supabase 연결
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"].strip()
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 비밀번호 해시
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ==========================================
# 1. DB 함수
# ==========================================
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

# ==========================================
# 2. 기본 데이터 및 글로벌 스타일
# ==========================================
YUK_TEMPLATES = {
    "육과장 코어4종": {
        '360750.KS': 10, # TIGER 미국S&P500
        '133690.KS': 10, # TIGER 미국나스닥100
        '458730.KS': 10, # TIGER 미국배당다우존스
        '439870.KS': 10  # KODEX 국고채30년액티브
    },
    "반도체 올인": {
        '091230.KS': 10, # TIGER 반도체
        '005930.KS': 10  # 삼성전자
    }
}

st.markdown("""
<style>
.main.block-container {padding-top: 1rem; padding-bottom: 0rem;}
.stMetric {background-color: #0E1117; padding: 15px; border-radius: 10px; border: 1px solid #262730;}
.stAlert {border-radius: 10px;}
h1 {text-align: center; color: #FAFAFA;}
h3 {color: #FAFAFA; border-bottom: 2px solid #FF4B4B; padding-bottom: 5px; margin-top: 2rem;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 로그인 및 세션 관리
# ==========================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_email' not in st.session_state: st.session_state.user_email = None

if not st.session_state.logged_in:
    st.markdown("<h1>🤖 육과장 AI 풀오토 v11 Pro</h1>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["로그인", "회원가입"])

    with tab1:
        st.subheader("로그인")
        login_email = st.text_input("이메일", key="login_email")
        login_pw = st.text_input("비밀번호", type="password", key="login_pw")
        if st.button("로그인", type="primary", use_container_width=True):
            users = load_users()
            input_hash = hash_password(login_pw)
            if login_email in users and users[login_email]['password'] == input_hash:
                st.session_state.logged_in = True
                st.session_state.user_email = login_email
                user_data = users[login_email]['data']
                st.session_state.portfolio = user_data.get('portfolio', {})
                st.session_state.rules = user_data.get('rules', {'core_min': 0.6, 'irp_risky_max': 0.7, 'cov_max': 0.15, 'single_stock_max': 0.2})
                st.session_state.groq_key = user_data.get('groq_key', "")
                st.session_state.account_type = user_data.get('account_type', "ISA")
                st.rerun()
            else:
                st.error("이메일 또는 비밀번호가 일치하지 않습니다.")

    with tab2:
        st.subheader("회원가입")
        signup_email = st.text_input("이메일", key="signup_email")
        signup_pw = st.text_input("비밀번호", type="password", key="signup_pw")
        signup_pw2 = st.text_input("비밀번호 확인", type="password", key="signup_pw2")
        if st.button("회원가입", type="primary", use_container_width=True):
            if signup_pw != signup_pw2:
                st.error("비밀번호가 일치하지 않습니다.")
            elif not signup_email or not signup_pw:
                st.error("정보를 모두 입력하세요.")
            elif signup_email in load_users():
                st.error("이미 가입된 이메일입니다.")
            else:
                success = save_user(signup_email, signup_pw, {
                    'portfolio': {},
                    'rules': {'core_min': 0.6, 'irp_risky_max': 0.7, 'cov_max': 0.15, 'single_stock_max': 0.2},
                    'groq_key': "",
                    'account_type': "ISA"
                })
                if success:
                    st.success("회원가입 완료! 로그인해주세요.")
                    st.balloons()
    st.stop()

# 세션 기본값 초기화
if 'ai_logs' not in st.session_state: st.session_state.ai_logs = []
if 'krx_list' not in st.session_state: st.session_state.krx_list = None
if 'ai_recommendations' not in st.session_state: st.session_state.ai_recommendations = []

# 메인 UI 헤더
st.markdown("<h1>🤖 육과장 AI 풀오토 v11 Pro</h1>", unsafe_allow_html=True)
col_user, col_logout = st.columns([5, 1])
col_user.caption(f"👤 {st.session_state.user_email}")
if col_logout.button("로그아웃", use_container_width=True):
    st.session_state.logged_in = False
    st.rerun()

# 장중 새로고침
now = datetime.now().time()
is_market_open = time(9, 0) <= now <= time(15, 30)
if is_market_open:
    st_autorefresh(interval=30000, limit=None, key="auto_refresh")
    st.caption(f"<p style='text-align: center; color: #00FF00;'>🔴 LIVE {datetime.now().strftime('%H:%M:%S')} | 무한피드백 작동중</p>", unsafe_allow_html=True)
else:
    st.caption("<p style='text-align: center; color: #FFA500;'>🌙 장마감 | 야간 캐시 최적화 모드</p>", unsafe_allow_html=True)

# ==========================================
# 4. 핵심 데이터 Fetching 함수 (캐싱 최적화)
# ==========================================
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
            'S&P500 ETF(SPY)': 'SPY', '나스닥100 ETF(QQQ)': 'QQQ', '미국배당다우(SCHD)': 'SCHD'
        }
        krx_dict.update(us_stocks)
        return krx_dict
    except:
        return {'삼성전자': '005930.KS', 'TIGER 미국S&P500': '360750.KS', '애플': 'AAPL', '엔비디아': 'NVDA'}

if st.session_state.krx_list is None:
    with st.spinner("종목 마스터 데이터를 로딩중입니다..."):
        st.session_state.krx_list = get_krx_list()

@st.cache_data(ttl=600)
def get_vix():
    try:
        return yf.Ticker('^VIX').history(period='1d')['Close'].iloc[-1]
    except:
        return 0.0

@st.cache_data(ttl=3600)
def draw_stock_chart(ticker, name):
    try:
        hist = yf.Ticker(ticker).history(period="3mo")
        if hist.empty: return None
        fig = go.Figure(data=[go.Candlestick(
            x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name=name
        )])
        fig.update_layout(
            title=f"📈 {name} ({ticker}) 최근 3개월 추이",
            yaxis_title="주가",
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            margin=dict(l=20, r=20, t=40, b=20)
        )
        return fig
    except:
        return None

# ==========================================
# 5. 설정 및 종목 관리
# ==========================================
with st.popover("⚙ 설정 및 계좌관리", use_container_width=True):
    new_groq_key = st.text_input("Groq API Key", type="password", value=st.session_state.groq_key)
    new_account_type = st.selectbox("계좌 종류", ["IRP", "ISA", "연금저축", "일반계좌"], 
                                    index=["IRP", "ISA", "연금저축", "일반계좌"].index(st.session_state.account_type))
    if st.button("설정 저장"):
        st.session_state.groq_key = new_groq_key
        st.session_state.account_type = new_account_type
        update_user_data(st.session_state.user_email, {
            'portfolio': st.session_state.portfolio, 'rules': st.session_state.rules,
            'groq_key': new_groq_key, 'account_type': new_account_type
        })
        st.success("설정이 저장되었습니다.")
        st.rerun()

st.subheader("🚀 원클릭 포트폴리오 템플릿")
col_t1, col_t2 = st.columns(2)
for idx, (name, stocks) in enumerate(YUK_TEMPLATES.items()):
    if [col_t1, col_t2][idx].button(f"[{name}] 덮어쓰기", use_container_width=True):
        st.session_state.portfolio = stocks.copy() # 완전히 새로 세팅
        update_user_data(st.session_state.user_email, {
            'portfolio': st.session_state.portfolio, 'rules': st.session_state.rules,
            'groq_key': st.session_state.groq_key, 'account_type': st.session_state.account_type
        })
        st.success(f"'{name}' 템플릿으로 포트폴리오가 리셋되었습니다!")
        st.rerun()

st.subheader("💰 내 종목 관리 (수동)")
col1, col2, col3 = st.columns([3, 1, 1])
search_name = col1.selectbox("종목 검색", options=list(st.session_state.krx_list.keys()), index=None, placeholder="삼성전자, AAPL 등 검색")
manual_ticker = col1.text_input("또는 티커 직접입력", placeholder="예: NVDA, 005930.KS")
add_shares = col2.number_input("보유 수량 설정 (0 입력시 삭제)", min_value=0, step=1)

if col3.button("적용하기", use_container_width=True, type="primary"):
    ticker = manual_ticker.strip().upper() if manual_ticker else (st.session_state.krx_list.get(search_name) if search_name else None)
    if ticker:
        if add_shares > 0:
            st.session_state.portfolio[ticker] = add_shares
        elif ticker in st.session_state.portfolio:
            del st.session_state.portfolio[ticker]
            
        update_user_data(st.session_state.user_email, {
            'portfolio': st.session_state.portfolio, 'rules': st.session_state.rules,
            'groq_key': st.session_state.groq_key, 'account_type': st.session_state.account_type
        })
        st.rerun()
    else:
        st.error("종목을 선택하거나 티커를 정확히 입력하세요.")

# ==========================================
# 6. AI 추천 및 무한피드백 엔진
# ==========================================
@st.cache_data(ttl=600)
def ai_recommendation_engine(groq_key, portfolio_tickers):
    if not groq_key: return []
    try:
        client = Groq(api_key=groq_key)
        urls = ["https://finance.naver.com/news/mainnews.naver", "https://www.hankyung.com/economy"]
        sources = []
        for url in urls:
            try:
                soup = BeautifulSoup(requests.get(url, headers=HEADERS, timeout=3).text, 'lxml')
                sources.append(" ".join([a.text for a in soup.select('a')[:30]]))
            except: continue
        
        full_text = " ".join(sources)[:3000]
        prompt = f"""너는 육과장처럼 개인투자자 자산증식 전문 AI야.
뉴스: {full_text}
현재 보유: {list(portfolio_tickers.keys())}
위 뉴스 기반으로 지금 당장 사야할 종목 3개만 추천해.
형식: 티커|종목명|추천이유
예: AAPL|애플|AI수요폭증 기대감"""

        res = client.chat.completions.create(
            model="llama-3.1-70b-versatile", messages=[{"role": "user", "content": prompt}], max_tokens=300
        )
        
        recs = []
        for line in res.choices[0].message.content.strip().split('\n'):
            line = line.strip('*-`[]. ') # 마크다운 등 불순물 제거
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 3:
                    recs.append({'ticker': parts[0].strip(), 'name': parts[1].strip(), 'reason': parts[2].strip()})
        return recs
    except Exception as e:
        return [{'ticker': 'ERROR', 'name': '추천 실패', 'reason': f"API 에러: {str(e)}"}]

@st.cache_data(ttl=180)
def infinite_feedback_v2(groq_key, current_rules, portfolio_tickers):
    logs = []
    new_rules = current_rules.copy()
    try:
        soup = BeautifulSoup(requests.get("https://finance.naver.com/news/mainnews.naver", headers=HEADERS, timeout=3).text, 'lxml')
        full_text = " ".join([a.text for a in soup.select('.articleSubject a')[:20]])
        
        risks = {
            '커버드콜': len(re.findall(r'커버드콜.*위험|분배금.*삭감', full_text)),
            '금리': len(re.findall(r'금리.*인상|긴축|매파', full_text)),
            '침체': len(re.findall(r'침체|리세션|하드랜딩|폭락', full_text))
        }
        if risks['커버드콜'] >= 1:
            new_rules['cov_max'] = 0.0
            logs.append(f"[{datetime.now().strftime('%H:%M')}] 🔴 긴급: 커버드콜 배당 삭감 위험. 비중 0% 강제 축소")
        if risks['금리'] >= 2:
            new_rules['core_min'] = 0.4
            logs.append(f"[{datetime.now().strftime('%H:%M')}] 🔴 긴급: 금리인상 시그널. 코어 비중 40%로 하향 조정")
        if risks['침체'] >= 2:
            new_rules['irp_risky_max'] = 0.5
            logs.append(f"[{datetime.now().strftime('%H:%M')}] 🔴 긴급: 경기침체 경고. IRP 위험자산 50%로 제한")
    except Exception as e:
        pass # 크롤링 실패시 조용히 패스
    return new_rules, logs

if st.session_state.groq_key:
    st.session_state.ai_recommendations = ai_recommendation_engine(st.session_state.groq_key, st.session_state.portfolio)
    if is_market_open:
        new_rules, new_logs = infinite_feedback_v2(st.session_state.groq_key, st.session_state.rules, st.session_state.portfolio)
        if new_rules != st.session_state.rules:
            st.session_state.rules = new_rules
            update_user_data(st.session_state.user_email, {
                'portfolio': st.session_state.portfolio, 'rules': st.session_state.rules,
                'groq_key': st.session_state.groq_key, 'account_type': st.session_state.account_type
            })
        if new_logs:
            st.session_state.ai_logs.extend(new_logs)
            st.session_state.ai_logs = st.session_state.ai_logs[-30:] # 최근 30개 유지

# AI 추천 표시 영역
if st.session_state.ai_recommendations:
    st.markdown("### 🎯 AI 실시간 종목 추천 (뉴스 기반)")
    for rec in st.session_state.ai_recommendations:
        if rec['ticker'] == 'ERROR':
            st.error(rec['reason'])
            break
        col_r1, col_r2, col_r3 = st.columns([2, 4, 1])
        col_r1.markdown(f"**{rec['name']}** `{rec['ticker']}`")
        col_r2.caption(rec['reason'])
        if col_r3.button("1주 담기", key=f"add_{rec['ticker']}"):
            st.session_state.portfolio[rec['ticker']] = st.session_state.portfolio.get(rec['ticker'], 0) + 1
            update_user_data(st.session_state.user_email, {
                'portfolio': st.session_state.portfolio, 'rules': st.session_state.rules,
                'groq_key': st.session_state.groq_key, 'account_type': st.session_state.account_type
            })
            st.rerun()

# ==========================================
# 7. 포트폴리오 계산 엔진
# ==========================================
@st.cache_data(ttl=30)
def calc_portfolio(portfolio_dict, rules, acc_type):
    if not portfolio_dict: return {}, 0, [], [], {}
    
    holdings, total = {}, 0
    # dict 변경에러 방지용 복사
    safe_portfolio = dict(portfolio_dict)
    
    for ticker, shares in safe_portfolio.items():
        if shares <= 0: continue
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d") # 안정성을 위해 5일치 확보 후 최근 2일 사용
            if hist.empty: raise Exception("No data")
            
            price = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2] if len(hist) > 1 else price
            value = shares * price
            div = t.dividends.last('365D').sum() if hasattr(t, 'dividends') and not t.dividends.empty else 0
            
            holdings[ticker] = {
                'name': ticker, 'shares': shares, 'price': price, 'value': value,
                'change_pct': (price/prev - 1) * 100 if prev > 0 else 0,
                'div': div
            }
            total += value
        except:
            # 야후 파이낸스 에러 시 0으로 방어
            holdings[ticker] = {'name': ticker, 'shares': shares, 'price': 0, 'value': 0, 'change_pct': 0, 'div': 0}

    issues, orders = [], []
    if total == 0: return holdings, 0, ["종목 현재가를 불러올 수 없거나 수량이 0입니다."], [], {}

    # 코어 비중 검사
    core_tickers = ['360750.KS', '133690.KS', '069500.KS', 'SPY', 'QQQ']
    core_value = sum(holdings.get(t, {}).get('value', 0) for t in core_tickers if t in holdings)
    
    if core_value / total < rules['core_min']:
        need = total * rules['core_min'] - core_value
        ref_price = holdings.get('360750.KS', {}).get('price', 15000)
        ref_price = 15000 if ref_price == 0 else ref_price # 0으로 나누기 방지
        
        shares_to_buy = int(need / ref_price)
        if shares_to_buy > 0:
            issues.append(f"⚠️ 코어 비중 부족 ({core_value/total*100:.0f}% < 권장 {rules['core_min']*100:.0f}%)")
            orders.append({'action': '매수', 'ticker': '360750.KS', 'shares': shares_to_buy, 'name': 'TIGER 미국S&P500'})

    if not issues: issues = ["✅ 문제점 0개. 현재 포트폴리오 비율이 완벽합니다."]
    
    return holdings, total, issues, orders, rules

holdings, total, issues, orders, current_rules = calc_portfolio(
    st.session_state.portfolio, st.session_state.rules, st.session_state.account_type
)

# ==========================================
# 8. 최종 대시보드 렌더링
# ==========================================
if total > 0:
    st.markdown("---")
    # 전일 대비 자산 변화 계산
    try:
        prev_total = sum(h['shares'] * (h['price'] / (1 + h['change_pct']/100)) for h in holdings.values())
        today_change = total - prev_total
        today_roi = (today_change / prev_total) * 100 if prev_total > 0 else 0
    except:
        today_change, today_roi = 0, 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 총 자산 평가금액", f"{total:,.0f}원", f"전일비 {today_change:+,.0f}원")
    col2.metric("📈 일일 수익률(전일비)", f"{today_roi:+.2f}%")
    
    vix = get_vix()
    col3.metric("😱 공포지수 (VIX)", f"{vix:.1f}", "위험" if vix > 30 else "안정", delta_color="inverse")
    
    monthly_div = sum(h['div'] * h['shares'] / 12 for h in holdings.values())
    col4.metric("💵 예상 월 평균 배당금", f"{monthly_div:,.0f}원")

    # 진단 및 주문서
    st.markdown("### 🚨 AI 실시간 포트폴리오 진단")
    for issue in issues:
        if "✅" in issue: st.success(issue)
        else: st.warning(issue)

    if orders:
        st.markdown("### ⚖ 자동 리밸런싱 주문서 (원클릭 복사)")
        
        # 표 출력
        df_orders = pd.DataFrame([{
            '종목명': o['name'], '주문 구분': o['action'], '수량': f"{o['shares']}주",
            '예상 필요금액': f"{o['shares'] * holdings[o['ticker']]['price']:,.0f}원"
        } for o in orders])
        st.dataframe(df_orders, hide_index=True, use_container_width=True)
        
        # 복사 가능한 텍스트 블록 생성
        order_text = "[육과장 AI 리밸런싱 지시서]\n"
        for o in orders:
            price = holdings[o['ticker']]['price']
            order_text += f"▪ {o['name']} ({o['ticker']}): {o['action']} {o['shares']}주 (예상금액: {o['shares'] * price:,.0f}원)\n"
            
        st.caption("👇 아래 박스 우측 상단의 **'복사' 아이콘**을 눌러 증권사 앱에서 바로 활용하세요.")
        st.code(order_text, language="text")

    # 무한피드백 로그
    if st.session_state.ai_logs:
        st.markdown("### 📡 AI 무한피드백 로그")
        with st.container(height=150):
            for log in reversed(st.session_state.ai_logs):
                if "🔴" in log: st.error(log)
                else: st.caption(log)

    # 상세 보유 현황
    st.markdown("### 📋 내 보유종목 상세 현황")
    df_hold = pd.DataFrame([{
        '종목명': h['name'], '보유수량': f"{h['shares']}주", '현재가': f"{h['price']:,.0f}원",
        '평가금액': f"{h['value']:,.0f}원", '일일 변동률': f"{h['change_pct']:+.2f}%"
    } for h in holdings.values()])
    st.dataframe(df_hold, hide_index=True, use_container_width=True)

    # 개별 종목 차트 분석 (Plotly 캔들차트)
    st.markdown("### 📊 개별 종목 차트 분석")
    chart_options = {f"{h['name']} ({h['shares']}주)": ticker for ticker, h in holdings.items()}
    selected_stock_label = st.selectbox("차트를 확인할 종목을 선택하세요", options=list(chart_options.keys()))
    
    if selected_stock_label:
        target_ticker = chart_options[selected_stock_label]
        target_name = selected_stock_label.split(" (")[0] 
        
        with st.spinner("최근 3개월 차트 데이터를 그리는 중입니다..."):
            chart_fig = draw_stock_chart(target_ticker, target_name)
            if chart_fig:
                st.plotly_chart(chart_fig, use_container_width=True)
            else:
                st.error("야후 파이낸스에서 해당 종목의 차트 데이터를 제공하지 않습니다.")

else:
    st.info("👆 위에서 **[육과장 템플릿]**을 클릭하거나 종목을 직접 검색해서 포트폴리오를 구성해보세요.")

# ==========================================
# 9. 초보자 안내
# ==========================================
st.markdown("---")
with st.expander("❓ 왜 S&P500 같은 코어 비중을 지켜야 하나요?"):
    st.write("""
    **육과장 피드백:** 코어(Core) 자산은 S&P500, 나스닥과 같은 검증된 우량 지수입니다.
    개별 종목에 100% 몰빵하면 단기 수익은 클 수 있지만 시장 하락기에 멘탈이 무너집니다. 
    반면 코어를 전체 자산의 60% 이상 깔아두면, 2008년 금융위기급 폭락이 와도 결국 시장 평균 수익률을 추종하며 회복합니다.
    초보자일수록 **'잃지 않는 투자(코어 먼저 채우기)'**가 가장 빠른 자산 증식의 길입니다.
    """)

with st.expander("⚙ 현재 AI가 무한피드백으로 감시 중인 룰"):
    st.json({k: f"{v*100:.0f}%" for k, v in st.session_state.rules.items()})

st.caption("v11 Pro: 육과장 템플릿 + 뉴스기반 AI추천 + Plotly 차트 + 원클릭 복사 + 무한피드백")
