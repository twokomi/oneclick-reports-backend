import os, datetime as dt, math
from datetime import timedelta
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
    ⚠️ STUB 제거: 실패시 빈 배열 반환
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
    
    # ⚠️ STUB 제거: 실패시 빈 배열 반환
    if not news_sources:
        print("⚠️ 모든 RSS 피드 실패 - 빈 배열 반환")
        return []
    
    return news_sources[:10]  # 최대 10개 반환

# ---------------- FRED helpers ----------------
async def fred_latest(series_id: str):
    """FRED API에서 최신 값 조회"""
    if not FRED_KEY: 
        print(f"⚠️ FRED_KEY 없음 - {series_id} 조회 불가")
        return None
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

async def fred_historical(series_id: str, days: int = 30):
    """
    FRED API에서 히스토리컬 데이터 조회
    - days: 최근 며칠간의 데이터 (기본 30일)
    - 반환: [{"date": "YYYY-MM-DD", "value": float}, ...]
    """
    if not FRED_KEY:
        print(f"⚠️ FRED_KEY 없음 - {series_id} 히스토리컬 조회 불가")
        return []
    
    end_date = dt.datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}"
        f"&api_key={FRED_KEY}"
        f"&file_type=json"
        f"&observation_start={start_date.isoformat()}"
        f"&observation_end={end_date.isoformat()}"
        f"&sort_order=asc"
    )
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url)
            r.raise_for_status()
            j = r.json()
        
        observations = j.get("observations", [])
        result = []
        for obs in observations:
            value = obs.get("value")
            date = obs.get("date")
            # "." 값 필터링 (FRED에서 데이터 없음을 의미)
            if value and value != "." and date:
                try:
                    result.append({"date": date, "value": float(value)})
                except ValueError:
                    continue
        
        return result
    except Exception as e:
        print(f"FRED 히스토리컬 API 오류 ({series_id}): {e}")
        return []

async def enrich_with_fred(data: dict) -> dict:
    """실제 FRED 데이터로 보강 (스텁 없음)"""
    
    # 미국 10년물 국채 금리
    dgs10 = await fred_latest("DGS10")
    if dgs10 and dgs10["value"] not in (None, "."):
        data.setdefault("daily_snapshot", {}).setdefault("rates", {})["UST10Y"] = float(dgs10["value"])
    
    # 원/달러 환율
    krw = await fred_latest("DEXKOUS")
    if krw and krw["value"] not in (None, "."):
        data.setdefault("daily_snapshot", {}).setdefault("fx", {})["USDKRW"] = float(krw["value"])
    
    # 미국 CPI
    cpi = await fred_latest("CPIAUCSL")
    if cpi and cpi["value"] not in (None, "."):
        data.setdefault("macro", []).append({
            "name": "US CPI (index)", 
            "latest": float(cpi["value"]), 
            "note": cpi["date"]
        })
    
    # 미국 실업률
    unrate = await fred_latest("UNRATE")
    if unrate and unrate["value"] not in (None, "."):
        data.setdefault("macro", []).append({
            "name": "US Unemployment Rate", 
            "latest": float(unrate["value"]), 
            "note": unrate["date"]
        })
    
    # 미국 연준 기준금리
    ffr = await fred_latest("FEDFUNDS")
    if ffr and ffr["value"] not in (None, "."):
        data.setdefault("macro", []).append({
            "name": "Fed Funds Rate", 
            "latest": float(ffr["value"]), 
            "note": ffr["date"]
        })
    
    # 한국 CPI (OECD/FRED)
    korcpi = await fred_latest("KORCPIALLMINMEI")
    if korcpi and korcpi["value"] not in (None, "."):
        data.setdefault("macro", []).append({
            "name": "Korea CPI (OECD/FRED)", 
            "latest": float(korcpi["value"]), 
            "note": korcpi["date"]
        })
    
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
        data.setdefault("macro", []).append({
            "name": "Korea CPI (ECOS)", 
            "latest": kcpi["value"], 
            "note": kcpi["date"]
        })
    return data

# ---------------- 입력 데이터 구성 ----------------
async def build_inputs(kind: str) -> dict:
    """
    ⚠️ STUB 제거: 실제 데이터만 수집
    - 시장 스냅샷: FRED 실데이터만 포함 (stub indices 제거)
    - 뉴스: RSS 실패시 빈 배열
    - 매크로: FRED/ECOS 실데이터만
    """
    today = dt.datetime.now().date().isoformat()
    
    # RSS 뉴스 수집 (stub 없음)
    headlines = await fetch_rss_news(kind)
    
    # ⚠️ STUB 제거: 기본 구조만 생성 (실데이터로만 채움)
    data = {
        "date": today,
        "daily_snapshot": {},  # FRED에서만 채움
        "macro": [],           # FRED/ECOS에서만 채움
        "headlines": headlines,
        "user_profile": {
            "risk_pref": "중립", 
            "interests": ["반도체", "부동산"]
        }
    }
    
    # 실데이터 보강
    data = await enrich_with_fred(data)
    data = await enrich_with_ecos(data)
    
    return data

# ---------------- LLM 호출 ----------------
async def call_llm(system_prompt: str, user_prompt: str) -> str:
    if not OPENAI:
        return (
            "**⚠️ OpenAI API 키가 설정되지 않았습니다.**\n\n"
            "환경변수 `OPENAI_API_KEY`를 설정해주세요.\n\n"
            "분석 리포트를 생성하려면 OpenAI API가 필요합니다."
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
    headlines = data.get("headlines", [])
    if headlines:
        for idx, headline in enumerate(headlines, 1):
            news_section += f"[{idx}] **{headline.get('title')}**\n"
            news_section += f"   - 출처: {headline.get('source')}\n"
            news_section += f"   - 링크: {headline.get('url')}\n"
            news_section += f"   - 날짜: {headline.get('date', 'N/A')}\n\n"
    else:
        news_section += "⚠️ RSS 뉴스 수집 실패 (네트워크 오류)\n\n"
    
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
