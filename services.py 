import os, datetime as dt, math
import httpx
import feedparser
from openai import OpenAI

OPENAI = os.getenv("OPENAI_API_KEY")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
ECOS_KEY = os.getenv("ECOS_KEY")
FRED_KEY = os.getenv("FRED_KEY")

# ---------------- RSS 뉴스 수집 (무료) ----------------
async def fetch_rss_news(kind: str) -> list[dict]:
    """
    RSS 피드에서 최신 뉴스를 수집합니다.
    Fallback: 네트워크 실패 시 stub 데이터 반환
    """
    news_sources = []
    
    try:
        # 1. 연합뉴스 RSS
        yna_feed = feedparser.parse("https://www.yna.co.kr/rss/all.xml")
        for entry in yna_feed.entries[:5]:
            news_sources.append({
                "title": entry.get("title", "제목 없음"),
                "url": entry.get("link", ""),
                "source": "연합뉴스",
                "date": entry.get("published", "")
            })
    except Exception as e:
        print(f"연합뉴스 RSS 오류: {e}")
    
    try:
        # 2. 한국경제 RSS
        hankyung_feed = feedparser.parse("https://www.hankyung.com/feed/")
        for entry in hankyung_feed.entries[:5]:
            news_sources.append({
                "title": entry.get("title", "제목 없음"),
                "url": entry.get("link", ""),
                "source": "한국경제",
                "date": entry.get("published", "")
            })
    except Exception as e:
        print(f"한국경제 RSS 오류: {e}")
    
    try:
        # 3. Google News RSS (경제 키워드)
        if kind == "daily":
            query = "KOSPI OR KOSDAQ OR 한국경제 OR 증시"
        elif kind == "weekly":
            query = "수출 OR 무역 OR 산업동향"
        else:
            query = "경제전망 OR 금리 OR 인플레이션"
        
        google_url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
        google_feed = feedparser.parse(google_url)
        for entry in google_feed.entries[:5]:
            news_sources.append({
                "title": entry.get("title", "제목 없음"),
                "url": entry.get("link", ""),
                "source": "Google News",
                "date": entry.get("published", "")
            })
    except Exception as e:
        print(f"Google News RSS 오류: {e}")
    
    # Fallback: stub 데이터
    if not news_sources:
        print("모든 RSS 피드 실패 - stub 데이터 사용")
        return [
            {"title": "[스텁] 한국 CPI 3.2% 기록, 예상치 상회", "url": "https://example.com/kcpi", "source": "stub", "date": dt.datetime.now().isoformat()},
            {"title": "[스텁] 코스피 외국인 순매도 지속", "url": "https://example.com/kospi", "source": "stub", "date": dt.datetime.now().isoformat()},
            {"title": "[스텁] 미 연준 금리 동결 결정", "url": "https://example.com/fed", "source": "stub", "date": dt.datetime.now().isoformat()},
            {"title": "[스텁] 서울 아파트 매매가 6주 연속 상승", "url": "https://example.com/apt", "source": "stub", "date": dt.datetime.now().isoformat()},
        ]
    
    return news_sources[:10]  # 최대 10개 반환

# ---------------- FRED helpers ----------------
async def fred_latest(series_id: str):
    if not FRED_KEY: return None
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={FRED_KEY}&file_type=json&sort_order=desc&limit=1"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url)
            r.raise_for_status()
            j = r.json()
        obs = j.get("observations", [])
        if not obs: return None
        o = obs[0]
        return {"date": o.get("date"), "value": o.get("value")}
    except Exception as e:
        print(f"FRED API 오류 ({series_id}): {e}")
        return None

async def enrich_with_fred(data: dict) -> dict:
    dgs10 = await fred_latest("DGS10")
    if dgs10 and dgs10["value"] not in (None, "."):
        data.setdefault("daily_snapshot", {}).setdefault("rates", {})["UST10Y"] = float(dgs10["value"])
    krw = await fred_latest("DEXKOUS")
    if krw and krw["value"] not in (None, "."):
        data.setdefault("daily_snapshot", {}).setdefault("fx", {})["USDKRW"] = float(krw["value"])
    cpi = await fred_latest("CPIAUCSL")
    if cpi and cpi["value"] not in (None, "."):
        data.setdefault("macro", []).append({"name":"US CPI (index)", "latest": float(cpi["value"]), "note": cpi["date"]})
    unrate = await fred_latest("UNRATE")
    if unrate and unrate["value"] not in (None, "."):
        data.setdefault("macro", []).append({"name":"US Unemployment Rate", "latest": float(unrate["value"]), "note": unrate["date"]})
    ffr = await fred_latest("FEDFUNDS")
    if ffr and ffr["value"] not in (None, "."):
        data.setdefault("macro", []).append({"name":"Fed Funds Rate", "latest": float(ffr["value"]), "note": ffr["date"]})
    korcpi = await fred_latest("KORCPIALLMINMEI")
    if korcpi and korcpi["value"] not in (None, "."):
        data.setdefault("macro", []).append({"name":"Korea CPI (OECD/FRED)", "latest": float(korcpi["value"]), "note": korcpi["date"]})
    return data

# ---------------- ECOS(옵션) ----------------
async def ecos_korea_cpi_latest():
    if not ECOS_KEY: return None
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{ECOS_KEY}/json/kr/1/2/901Y014/M/2020/2030/"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url)
            r.raise_for_status()
            j = r.json()
        row = j["StatisticSearch"]["row"][-1]
        return {"value": float(row["DATA_VALUE"]), "date": row["TIME"]}
    except Exception as e:
        print(f"ECOS API 오류: {e}")
        return None

async def enrich_with_ecos(data: dict) -> dict:
    kcpi = await ecos_korea_cpi_latest()
    if kcpi:
        data.setdefault("macro", []).append({"name":"Korea CPI (ECOS)", "latest": kcpi["value"], "note": kcpi["date"]})
    return data

# ---------------- 입력 데이터 구성 ----------------
async def build_inputs(kind: str) -> dict:
    today = dt.datetime.now().date().isoformat()
    
    # RSS 뉴스 수집
    headlines = await fetch_rss_news(kind)
    
    data = {
        "date": today,
        "daily_snapshot": {
            "indices": {"KOSPI": 2640.0, "KOSDAQ": 850.0, "S&P500": 5350.0, "Nasdaq": 17000.0, "Dow": 39000.0},
            "fx": {"USDKRW": 1390.0},
            "rates": {"UST10Y": 4.4, "KR3Y": 3.5},
            "commodities": {"WTI": 78.5, "Brent": 82.0, "Gold": 2350.0}
        },
        "macro": [
            {"name": "Korea CPI (stub)", "latest": 3.2, "prev": 3.0, "consensus": 3.1, "yoy": 3.2},
            {"name": "US CPI (stub)", "latest": 3.4, "consensus": 3.4, "core": 3.8}
        ],
        "headlines": headlines,
        "user_profile": {"risk_pref": "중립", "interests": ["반도체", "부동산"]}
    }
    
    # 실데이터 보강
    data = await enrich_with_fred(data)
    data = await enrich_with_ecos(data)
    
    return data

# ---------------- LLM 호출 ----------------
async def call_llm(system_prompt: str, user_prompt: str) -> str:
    if not OPENAI:
        return (
            "**요약**: (스텁) 물가 둔화 기대와 정책 불확실성 혼재.\n\n"
            "**핵심 데이터**\n\n"
            "|지표|수치|전월/전년|컨센서스|코멘트|\n"
            "|---|---:|---:|---:|---|\n"
            "|Korea CPI|3.2%|+0.2%p|3.1%|식료·에너지 영향|\n"
            "|US CPI|3.4%|-|3.4%|근원 높은 편|\n\n"
            "**해석**: (스텁) 긴축 장기화 리스크.\n\n"
            "**시장 반응**: (스텁) 나스닥 약세, 원/달러 강세.\n\n"
            "**리스크 Top3**: (1) 인플레 재가속 (2) 달러 강세 (3) 지정학.\n\n"
            "**맞춤 코멘트**: 반도체 단기 변동성 주의, 주택은 금리 피크아웃 확인후 접근."
        )
    
    try:
        client = OpenAI(api_key=OPENAI)
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"OpenAI API 오류: {e}")
        return f"**오류**: OpenAI API 호출 실패 - {str(e)}\n\n(제공된 데이터를 기반으로 분석을 진행할 수 없습니다)"

# ---------------- 해석 프롬프트 ----------------
def build_analysis_prompt(data: dict) -> tuple[str, str]:
    system = (
        "You are a Korean macro & markets analyst for one user (Junki). "
        "Style: concise, neutral, actionable. Explain terms briefly. "
        "Ground claims in provided data and links."
    )
    
    # 뉴스 헤드라인 포맷팅
    news_section = "\n\n### 📰 오늘의 주요 뉴스 (RSS 기반)\n\n"
    for idx, headline in enumerate(data.get("headlines", []), 1):
        news_section += f"[{idx}] **{headline.get('title')}**\n"
        news_section += f"   - 출처: {headline.get('source')}\n"
        news_section += f"   - 링크: {headline.get('url')}\n"
        news_section += f"   - 날짜: {headline.get('date', 'N/A')}\n\n"
    
    user = f"""
아래 JSON과 RSS 뉴스 링크로 리포트를 작성:

## 제공된 데이터
{data}

{news_section}

[TASK]
1) 3~5문단 요약 (RSS 뉴스 헤드라인을 참고하여 현재 시장 상황 설명).
2) 핵심 데이터 표 (지표/수치/전기·전년비/컨센서스/코멘트).
3) 거시 해석 (인플레/성장/고용/정책 각 2~3문장, RSS 뉴스와 연결).
4) 시장 반응 & 관전 포인트 (RSS 뉴스에서 언급된 이슈 중심).
5) 리스크 Top 3 (구체적 시나리오).
6) 사용자 맞춤 코멘트 (관심 섹터: 반도체, 부동산. 과한 확신 금지).
7) 참고 링크: 위 RSS 뉴스를 [1], [2], [3]... 형태로 본문에 인용.
8) 마지막에 "### 📰 뉴스 출처" 섹션을 추가하여 모든 링크 나열.

한국어 마크다운으로 출력하되, 전문적이면서도 이해하기 쉽게 작성.
"""
    return system, user
