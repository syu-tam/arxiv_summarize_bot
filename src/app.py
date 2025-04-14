from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from .main import PaperService
from fastapi import Request
import json
import os
from fastapi import Query
from typing import Optional, List, Dict, Any
from pathlib import Path
from loguru import logger
from datetime import datetime, timedelta, timezone

app = FastAPI(title="arXiv Paper Summarizer")

# 静的ファイルとテンプレートの設定
static_dir = Path(__file__).parent.parent / "static"
templates_dir = Path(__file__).parent.parent / "templates"
static_dir.mkdir(exist_ok=True)
templates_dir.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)

# サービスの初期化
paper_service = PaperService()

@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の処理"""
    paper_service.start_scheduler()

@app.on_event("shutdown")
async def shutdown_event():
    """アプリケーション終了時の処理"""
    paper_service.stop_scheduler()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/categories")
async def get_categories():
    categories = paper_service.get_categories()
    return {"status": "success", "categories": categories}

@app.get("/api/search")
async def search_papers(
    query: str,
    max_results: int = Query(default=5, ge=1, le=100)
):
    """論文検索API"""
    try:
        papers = await paper_service.search_and_summarize(query, max_results)
        return {
            "status": "success",
            "message": "新着論文はありませんでした" if not papers else f"{len(papers)}件の論文が見つかりました",
            "papers": papers
        }
    except Exception as e:
        logger.error(f"検索エラー: {str(e)}")
        return {
            "status": "error",
            "message": "検索に失敗しました",
            "papers": []
        }

@app.post("/api/watch")
async def add_watch_keyword(keyword: str, categories: Optional[List[str]] = Query(None)):
    """キーワードを監視リストに追加"""
    paper_service.add_watch_keyword(keyword, categories)
    return {"status": "success", "message": f"キーワード '{keyword}' を監視リストに追加しました"}

@app.delete("/api/watch/{keyword}")
async def remove_watch_keyword(keyword: str):
    """キーワードを監視リストから削除"""
    paper_service.remove_watch_keyword(keyword)
    return {"status": "success", "message": f"キーワード '{keyword}' を監視リストから削除しました"}

@app.get("/api/watch")
async def get_watched_keywords():
    """監視中のキーワード一覧を取得"""
    return {"status": "success", "watched_keywords": paper_service.get_watched_keywords()}

@app.get("/api/new-papers")
async def check_new_papers():
    """新規論文をチェック"""
    try:
        papers = await paper_service.check_new_papers()
        if isinstance(papers, dict):
            papers = papers.get("papers", [])
        return {
            "status": "success",
            "papers": papers
        }
    except Exception as e:
        logger.error(f"新規論文チェックエラー: {str(e)}")
        return {"status": "error", "message": "新着論文の確認に失敗しました"}

@app.post("/api/email-config")
async def save_email_config(config: Dict[str, Any]):
    """メール設定を保存"""
    try:
        paper_service.save_email_config(config)
        return {"status": "success", "message": "メール設定を保存しました"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/processing/pause")
async def pause_processing():
    """処理を一時停止"""
    try:
        paper_service.pause_processing()
        return {"status": "success", "message": "処理を一時停止しました"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/processing/resume")
async def resume_processing():
    """処理を再開"""
    try:
        paper_service.resume_processing()
        return {"status": "success", "message": "処理を再開しました"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/processing/status")
async def get_processing_status():
    """現在の処理状態を取得"""
    try:
        is_active = paper_service.is_processing()
        return {
            "status": "success",
            "is_processing": is_active,
            "message": "処理実行中" if is_active else "処理停止中"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/test_recent")
async def test_recent_papers(
    query: str = "machine learning",
    max_results: int = Query(default=10, ge=1, le=100)
):
    """テスト用：最近5日間の論文を検索"""
    try:
        # 5日前の日時を計算
        since_date = datetime.now(timezone.utc) - timedelta(days=5)
        papers = await paper_service.test_recent_papers(query, max_results, since_date)
        return {
            "status": "success",
            "message": "新着論文はありませんでした" if not papers else f"{len(papers)}件の論文が見つかりました",
            "papers": papers,
            "search_since": since_date.isoformat()
        }
    except Exception as e:
        logger.error(f"テスト検索エラー: {str(e)}")
        return {
            "status": "error",
            "message": "論文の検索に失敗しました",
            "papers": []
        }