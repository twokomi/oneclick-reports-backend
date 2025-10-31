from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import os, datetime as dt
from pathlib import Path
from storage import save_report, list_reports
from services import build_inputs, build_analysis_prompt, call_llm
from notion_client import Client as NotionClient
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from dotenv import load_dotenv

load_dotenv()

def format_data_report(data: dict, kind: str) -> str:
    """
    데이터모드: 수집된 데이터를 보기 좋은 마크다운으로 포맷팅
    """
    lines = [
        f"# {kind.upper()} 데이터 리포트",
        f"**날짜**: {data.get('date')}",
        "",
        "---",
        ""
    ]
    
    # 1. 시장 스냅샷
    snapshot = data.get("daily_snapshot", {})
    if snapshot:
        lines.extend([
            "## 📊 시장 스냅샷",
            ""
        ])
        
        # 주요 지수
        indices = snapshot.get("indices", {})
        if indices:
            lines.extend([
                "### 주요 지수",
                "",
                "| 지수 | 현재가 |",
                "|------|-------:|"
            ])
            for name, value in indices.items():
                lines.append(f"| {name} | {value:,.2f} |")
            lines.append("")
        
        # 환율
        fx = snapshot.get("fx", {})
        if fx:
            lines.extend([
                "### 환율",
                "",
                "| 통화쌍 | 환율 |",
                "|--------|-----:|"
            ])
            for name, value in fx.items():
                lines.append(f"| {name} | {value:,.2f} |")
            lines.append("")
        
        # 금리
        rates = snapshot.get("rates", {})
        if rates:
            lines.extend([
                "### 금리",
                "",
                "| 상품 | 금리(%) |",
                "|------|--------:|"
            ])
            for name, value in rates.items():
                lines.append(f"| {name} | {value:.2f}% |")
            lines.append("")
        
        # 원자재
        commodities = snapshot.get("commodities", {})
        if commodities:
            lines.extend([
                "### 원자재",
                "",
                "| 상품 | 가격 |",
                "|------|-----:|"
            ])
            for name, value in commodities.items():
                lines.append(f"| {name} | ${value:.2f} |")
            lines.append("")
    
    # 2. 거시 경제 지표
    macro = data.get("macro", [])
    if macro:
        lines.extend([
            "---",
            "",
            "## 📈 거시 경제 지표",
            "",
            "| 지표명 | 최신값 | 비고 |",
            "|--------|-------:|------|"
        ])
        for item in macro:
            name = item.get("name", "N/A")
            latest = item.get("latest", "N/A")
            note = item.get("note", "")
            
            if isinstance(latest, (int, float)):
                latest_str = f"{latest:.2f}"
            else:
                latest_str = str(latest)
            
            lines.append(f"| {name} | {latest_str} | {note} |")
        lines.append("")
    
    # 3. 뉴스 헤드라인
    headlines = data.get("headlines", [])
    if headlines:
        lines.extend([
            "---",
            "",
            "## 📰 최신 뉴스 헤드라인 (RSS)",
            ""
        ])
        for idx, news in enumerate(headlines, 1):
            title = news.get("title", "제목 없음")
            url = news.get("url", "")
            source = news.get("source", "N/A")
            date = news.get("date", "")
            
            lines.append(f"### [{idx}] {title}")
            lines.append(f"- **출처**: {source}")
            if url:
                lines.append(f"- **링크**: [{url}]({url})")
            if date:
                lines.append(f"- **날짜**: {date}")
            lines.append("")
    
    # 4. 사용자 프로필
    profile = data.get("user_profile", {})
    if profile:
        lines.extend([
            "---",
            "",
            "## 👤 사용자 프로필",
            "",
            f"- **리스크 선호**: {profile.get('risk_pref', 'N/A')}",
            f"- **관심 섹터**: {', '.join(profile.get('interests', []))}",
            ""
        ])
    
    # 5. 데이터 소스 정보
    lines.extend([
        "---",
        "",
        "## ℹ️ 데이터 소스",
        "",
        "- **시장 데이터**: 실시간 스냅샷 (일부 stub 포함)",
        "- **경제 지표**: FRED API (실제 데이터)",
        "- **뉴스**: RSS 피드 (연합뉴스, 한국경제, Google News)",
        "",
        "---",
        "",
        "*본 리포트는 데이터 수집 모드로 생성되었습니다. 해석이 필요하면 '해석모드'를 선택하세요.*"
    ])
    
    return "\n".join(lines)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EXPORT_DIR = Path(__file__).parent / "exports"
EXPORT_DIR.mkdir(exist_ok=True)

class ReportReq(BaseModel):
    kind: str  # daily | weekly | monthly
    mode: str | None = "analysis"  # data | analysis

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/reports")
def get_reports(kind: str | None = None, mode: str | None = None):
    return {"items": list_reports(kind, mode)}

@app.post("/report")
async def create_report(req: ReportReq):
    kind = req.kind.lower()
    mode = (req.mode or "analysis").lower()
    if kind not in ("daily", "weekly", "monthly"):
        return {"error": "kind must be daily|weekly|monthly"}
    if mode not in ("data", "analysis"):
        return {"error": "mode must be data|analysis"}

    data = await build_inputs(kind)

    if mode == "data":
        # 데이터만 수집 → 마크다운으로 정리(LLM 호출 없음)
        title = f"{kind.capitalize()} Report (DATA) — {data['date']}"
        md = format_data_report(data, kind)
    else:
        system, user = build_analysis_prompt(data)
        md = await call_llm(system, user)
        title = f"{kind.capitalize()} Report — {data['date']}"

    created_at = dt.datetime.now().isoformat()
    sources = [h.get("url", "") for h in data.get("headlines", []) if h.get("url")]
    rid = save_report(kind, mode, data["date"], title, md, sources, created_at)

    return {"id": rid, "title": title, "date": data["date"], "mode": mode, "markdown": md, "sources": sources}

@app.get("/report/{rid}")
def get_report_by_id(rid: int):
    items = list_reports()
    for it in items:
        if it["id"] == rid:
            return it
    raise HTTPException(status_code=404, detail="report not found")

@app.get("/report/{rid}/export")
def export_report(rid: int, fmt: str = "md"):
    items = list_reports()
    target = next((x for x in items if x["id"]==rid), None)
    if not target:
        raise HTTPException(status_code=404, detail="report not found")
    title = target["title"]; md = target["markdown"]
    if fmt == "md":
        fp = EXPORT_DIR / f"report_{rid}.md"
        fp.write_text(md, encoding="utf-8")
        return FileResponse(str(fp), filename=fp.name, media_type="text/markdown")
    elif fmt == "pdf":
        fp = EXPORT_DIR / f"report_{rid}.pdf"
        c = canvas.Canvas(str(fp), pagesize=A4)
        width, height = A4; x, y = 40, height - 40
        c.setFont("Helvetica", 11)
        for line in (f"# {title}", "", *md.splitlines()):
            if y < 40:
                c.showPage(); c.setFont("Helvetica", 11); y = height - 40
            c.drawString(x, y, line[:110]); y -= 16
        c.save()
        return FileResponse(str(fp), filename=fp.name, media_type="application/pdf")
    else:
        raise HTTPException(status_code=400, detail="fmt must be md|pdf")

@app.post("/report/{rid}/notion")
def export_to_notion(rid: int):
    token = os.getenv("NOTION_TOKEN"); page_id = os.getenv("NOTION_PAGE_ID")
    if not token or not page_id:
        raise HTTPException(status_code=400, detail="NOTION_TOKEN/NOTION_PAGE_ID required")
    items = list_reports()
    target = next((x for x in items if x["id"]==rid), None)
    if not target:
        raise HTTPException(status_code=404, detail="report not found")
    client = NotionClient(auth=token)
    title = target["title"]; md = target["markdown"]
    client.blocks.children.append(
        block_id=page_id,
        children=[
            {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":title}}]}},
            {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":md[:1950]}}]}},
        ]
    )
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
