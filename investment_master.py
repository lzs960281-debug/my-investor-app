import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, time
import requests
from bs4 import BeautifulSoup
from groq import Groq
import hashlib
from supabase import create_client
import concurrent.futures

# ==========================================
# 1. 앱 기본 설정 & 토스 스타일 CSS
# ==========================================
st.set_page_config(page_title="육과장 AI 풀오토 v13", page_icon="📈", layout="centered") # 폰에서 보기 편한 가운데 정렬

st.markdown("""
<style>
    /* 둥글고 부드러운 토스 스타일 UI */
    .block-container { max-width: 800px; padding-top: 2rem; }
    h1, h2, h3 { font-weight: 800; letter-spacing: -1px; }
    
    /* 자산 카드 스타일 */
    .asset-card {
        background-color: #1a1b23; border-radius: 20px; padding: 30px; margin-bottom: 20px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.2); text-align: center;
    }
    .asset-title { color: #8b95a1; font-size: 16px; font-weight: 600; margin-bottom: 10px; }
    .asset-price { color: #ffffff; font-size: 42px; font-weight: 800; margin-bottom: 10px; }
    .asset-change { color: #f04452; font-size: 18px; font-weight: 600; } /* 토스는 상승이 빨간색 */
    .asset-change.minus { color: #3182f6; } /* 하락은 파란색 */

    /* 주식 리스트 카드 */
    .stock-card {
        background-color: #24252f; border-radius: 15px; padding: 20px; margin-bottom: 15px;
        display: flex; justify-content: space-between; align-items: center;
    }
    .stock-name { font-size: 18px; font-weight: 700; color: #fff; }
    .stock-shares { font-size: 14px; color: #8b95a1; }
    .stock-value { font-size: 18px; font-weight: 700; color: #fff; text-align: right; }
    
    /* 경고/치료 카드 */
    .alert-card {
        background-color: #3e1b1e; border: 1px solid #f04452; border-radius: 15px; padding: 20px; margin-bottom: 20px;
    }
    
    /* st.tabs 폰트 키우기 */
    button[data-baseweb="tab"] { font-size: 18px !important; font-weight: 700 !important; }
</style>
""", unsafe_allow_html=True)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"].strip()
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def hash_password(password): return hashlib.sha256(password.encode()).hexdigest()

# ==========================================
# 2. 세션 및 로그인
# ==========================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'portfolio' not in st.session_state: st.session_state.portfolio = {}
if 'ai_analysis' not in st.session_state: st.session_state.ai_analysis = None
if 'krx_list' not in st.session_state: st.session_state.krx_list = {'삼성전자': '005930.KS', '애플': 'AAPL', '엔비디아': 'NVDA', 'S&P500 ETF': '360750.KS', '나스닥100 ETF': '133690.KS'}

def update_db():
    supabase.table('users').update({'data': {'portfolio': st.session_state.portfolio, 'groq_key': st.session_state.groq_key}}).eq('email', st.session_state.user_email).execute()

if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align:center;'>🚀 내 손안의 AI 비서</h1>", unsafe_allow_html=True)
    login_email = st.text_input("이메일")
    login_pw = st.text_input("비밀번호", type="password")
    if st.button("시작하기", use_container_width=True, type="primary"):
        res = supabase.table('users').select("*").eq('email', login_email).execute()
        if res.data and res.data[0]['password'] == hash_password(login_pw):
            st.session_state.logged_in = True
            st.session_state.user_email = login_email
            st.session_state.portfolio = res.data[0]['data'].get('portfolio', {})
            st.session_state.groq_key = res.data[0]['data'].get('groq_key', "")
            st.rerun()
        else: st.error("정보가 틀렸거나 없는 계정입니다.")
    st.stop()

# ==========================================
# 3. 초고속 데이터 로딩 (멀티스레딩)
# ==========================================
def fetch_stock(ticker, shares):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist.empty: return None
        price = hist['Close'].iloc[-1]
        prev = hist['Close'].iloc[-2] if len(hist)>1 else price
        return ticker, {'name': ticker, 'shares': shares, 'price': price, 'value': shares * price, 'change_pct': (price/prev - 1)*100}
    except: return None

@st.cache_data(ttl=60)
def get_my_assets(portfolio):
    holdings, total, prev_total = {}, 0, 0
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(fetch_stock, t, s) for t, s in portfolio.items() if s > 0]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res:
                holdings[res[0]] = res[1]
                total += res[1]['value']
                prev_total += res[1]['shares'] * (res[1]['price'] / (1 + res[1]['change_pct']/100))
    return holdings, total, prev_total

holdings, total_asset, prev_asset = get_my_assets(st.session_state.portfolio)
today_diff = total_asset - prev_asset
diff_pct = (today_diff / prev_asset * 100) if prev_asset > 0 else 0
color_class = "minus" if today_diff < 0 else ""
sign = "+" if today_diff > 0 else ""

# ==========================================
# 4. 토스 스타일 메인 화면 (3개의 탭)
# ==========================================
tab1, tab2, tab3 = st.tabs(["🏠 내 자산", "🔍 주식 모으기", "🤖 AI 전문가"])

# ----------------- 탭 1: 내 자산 -----------------
with tab1:
    # 핵심 자산 카드
    st.markdown(f"""
        <div class="asset-card">
            <div class="asset-title">총 자산 평가금액</div>
            <div class="asset-price">{total_asset:,.0f}원</div>
            <div class="asset-change {color_class}">오늘 {sign}{today_diff:,.0f}원 ({sign}{diff_pct:.1f}%)</div>
        </div>
    """, unsafe_allow_html=True)

    # 포트폴리오 치료 (리밸런싱 직관화)
    core_value = sum(holdings.get(t, {}).get('value', 0) for t in ['360750.KS', '133690.KS', '069500.KS', 'SPY', 'QQQ'])
    if total_asset > 0 and (core_value / total_asset < 0.6):
        need = total_asset * 0.6 - core_value
        st.markdown(f"""
            <div class="alert-card">
                <h3 style="color:#f04452; margin:0 0 10px 0;">🚨 포트폴리오가 위험해요!</h3>
                <p style="color:#fff; margin:0;">시장 하락을 막아줄 안전자산(S&P500 등) 비중이 60% 미만입니다. 지금 당장 방어력을 높이세요.</p>
            </div>
        """, unsafe_allow_html=True)
        st.info(f"💡 **AI 처방전:** TIGER 미국S&P500 (360750.KS) 종목을 **{int(need/15000)}주** 더 매수하세요.")

    # 내 주식 리스트
    st.markdown("### 📋 내 주식")
    if not holdings:
        st.caption("아직 보유한 주식이 없어요. '주식 모으기' 탭에서 추가해보세요!")
    else:
        for ticker, data in holdings.items():
            stock_color = "minus" if data['change_pct'] < 0 else ""
            stock_sign = "+" if data['change_pct'] > 0 else ""
            st.markdown(f"""
                <div class="stock-card">
                    <div>
                        <div class="stock-name">{ticker}</div>
                        <div class="stock-shares">{data['shares']}주 보유</div>
                    </div>
                    <div>
                        <div class="stock-value">{data['value']:,.0f}원</div>
                        <div class="stock-shares" style="text-align:right;"><span class="asset-change {stock_color}">{stock_sign}{data['change_pct']:.2f}%</span></div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

# ----------------- 탭 2: 주식 모으기 -----------------
with tab2:
    st.markdown("### 🔍 종목 검색 및 담기")
    st.caption("실제 보유 중인 종목을 검색해서 수량을 맞춰주세요.")
    
    col1, col2 = st.columns([3, 1])
    search_query = col1.text_input("종목명 또는 티커 (예: 삼성전자, AAPL)", placeholder="어떤 주식을 찾으시나요?")
    
    if search_query:
        # 간단한 검색 로직 (전체 목록 확장이 필요하면 krx_list 업데이트 필요)
        matched = {k: v for k, v in st.session_state.krx_list.items() if search_query.lower() in k.lower() or search_query.lower() in v.lower()}
        if matched:
            for name, ticker in matched.items():
                with st.container(border=True):
                    sc1, sc2 = st.columns([3, 1])
                    sc1.markdown(f"**{name}**\n`{ticker}`")
                    if sc2.button("담기", key=f"add_{ticker}"):
                        st.session_state.portfolio[ticker] = st.session_state.portfolio.get(ticker, 0) + 1
                        update_db(); st.rerun()
        else:
            with st.container(border=True):
                st.markdown(f"**{search_query.upper()}** (직접 입력)")
                if st.button("이 티커로 담기", key="add_manual"):
                    st.session_state.portfolio[search_query.upper()] = st.session_state.portfolio.get(search_query.upper(), 0) + 1
                    update_db(); st.rerun()
                    
    st.divider()
    st.markdown("### 🗑️ 보유 수량 수정")
    for t in list(st.session_state.portfolio.keys()):
        c1, c2 = st.columns([3, 2])
        c1.markdown(f"**{t}**")
        new_val = c2.number_input("수량", value=st.session_state.portfolio[t], min_value=0, step=1, key=f"edit_{t}", label_visibility="collapsed")
        if new_val != st.session_state.portfolio[t]:
            if new_val == 0: del st.session_state.portfolio[t]
            else: st.session_state.portfolio[t] = new_val
            update_db(); st.rerun()

# ----------------- 탭 3: AI 전문가 리포트 -----------------
with tab3:
    st.markdown("### 📰 실시간 시장 요약 & 추천")
    
    if not st.session_state.groq_key:
        st.warning("설정에서 Groq API 키를 입력해야 AI가 뉴스를 읽을 수 있습니다.")
        st.session_state.groq_key = st.text_input("API Key 입력", type="password")
        if st.button("저장"): update_db(); st.rerun()
        st.stop()
        
    if st.button("🔄 최신 시장 분석하기 (약 10초 소요)", use_container_width=True):
        with st.spinner("AI가 네이버 금융 뉴스를 정독하고 있습니다..."):
            try:
                # 1. 뉴스 스크래핑
                soup = BeautifulSoup(requests.get("https://finance.naver.com/news/mainnews.naver", headers=HEADERS, timeout=3).text, 'lxml')
                news_text = " ".join([a.text for a in soup.select('a')[:30]])[:2500]
                
                # 2. AI 분석 프롬프트 (투명성 강화)
                prompt = f"""너는 최고 수준의 펀드매니저야. 아래 오늘자 한국 경제 뉴스를 읽고, 
                1. '현재 시장 상황 요약'을 3줄로 작성해.
                2. 이 상황에서 당장 사야할 주식 3개를 추천해줘.
                
                형식:
                [시장 요약]
                (요약 내용)
                
                [추천 종목]
                티커|종목명|추천이유
                뉴스: {news_text}"""
                
                res = Groq(api_key=st.session_state.groq_key).chat.completions.create(
                    model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}], max_tokens=600
                )
                st.session_state.ai_analysis = res.choices[0].message.content
            except Exception as e:
                st.error("뉴스 분석 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
                
    # AI 분석 결과 출력
    if st.session_state.ai_analysis:
        analysis_text = st.session_state.ai_analysis
        
        # 텍스트 파싱하여 예쁘게 보여주기
        if "[시장 요약]" in analysis_text and "[추천 종목]" in analysis_text:
            summary = analysis_text.split("[추천 종목]")[0].replace("[시장 요약]", "").strip()
            recs = analysis_text.split("[추천 종목]")[1].strip().split('\n')
            
            st.markdown("#### 🧠 AI의 시장 브리핑")
            st.info(summary)
            
            st.markdown("#### 🎯 상황 맞춤 추천 종목")
            for line in recs:
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 3:
                        with st.container(border=True):
                            st.markdown(f"**{parts[1].strip()}** (`{parts[0].strip()}`)")
                            st.caption(f"💡 {parts[2].strip()}")
        else:
            # AI가 정해진 형식을 안 지켰을 경우 원본 출력
            st.write(analysis_text)
