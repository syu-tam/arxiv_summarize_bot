from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from .main import PaperService
from fastapi import Request
import json
import os
from fastapi import Query
from typing import Optional, List, Dict, Any
from pathlib import Path
from loguru import logger
from datetime import datetime, timezone, timedelta

# 共通のレスポンス形式を定義
def create_response(status_code: int, status: str, message: str, data: Any = None):
    """
    統一されたレスポンス形式を生成する

    Args:
        status_code: HTTPステータスコード
        status: 成功/失敗の状態 ("success" または "error")
        message: レスポンスメッセージ
        data: レスポンスデータ (オプション)

    Returns:
        JSONResponse: 統一形式のレスポンス
    """
    response = {
        "status": status,
        "message": message
    }
    
    if data is not None:
        # FastAPIのQueryオブジェクトを処理するための特別な処理
        processed_data = {}
        for key, value in data.items():
            # リスト型のQueyパラメータを変換
            if hasattr(value, '__iter__') and not isinstance(value, (str, dict, list)):
                try:
                    processed_data[key] = list(value)
                except:
                    processed_data[key] = str(value)
            # 単一のQueryパラメータを変換
            elif hasattr(value, '__str__') and not isinstance(value, (str, int, float, bool, dict, list)):
                processed_data[key] = str(value)
            # 標準的なJSON化可能なデータ型はそのまま
            else:
                processed_data[key] = value
        response.update(processed_data)
    
    return JSONResponse(
        status_code=status_code,
        content=response
    )

app = FastAPI(title="arXiv Paper Summarizer", 
              description="arXivの論文を検索・監視・要約するAPI",
              version="1.0.0")

# 静的ファイルとテンプレートの設定
static_dir = Path(__file__).parent.parent / "static"
templates_dir = Path(__file__).parent.parent / "templates"
static_dir.mkdir(exist_ok=True)
templates_dir.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)

# サービスの依存性注入
def get_paper_service():
    return PaperService()

# サービスのグローバルインスタンス（スケジューラ用）
paper_service = PaperService()

@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の処理"""
    paper_service.start_scheduler()
    logger.info("アプリケーションを開始しました")

@app.on_event("shutdown")
async def shutdown_event():
    """アプリケーション終了時の処理"""
    paper_service.stop_scheduler()
    logger.info("アプリケーションを終了しました")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/categories")
async def get_categories(service: PaperService = Depends(get_paper_service)):
    categories = service.get_categories()
    return create_response(
        status_code=status.HTTP_200_OK,
        status="success",
        message=f"{len(categories)}種類のカテゴリが利用可能です",
        data={"categories": categories}
    )

@app.get("/api/search")
async def search_papers(
    query: str,
    max_results: int = Query(default=20, ge=1, le=100),
    use_japanese_summary: bool = Query(default=True),
    from_date: Optional[str] = None,  # 'YYYY-MM-DD'形式で日付絞り込みを追加
    categories: Optional[List[str]] = Query(None),  # カテゴリフィルタを追加
    service: PaperService = Depends(get_paper_service)
):
    """論文検索API - 検索クエリ、日付、カテゴリによるフィルタリングに対応"""
    try:
        # 日付絞り込みがある場合はdatetimeに変換
        since_date = None
        if from_date:
            try:
                since_date = datetime.fromisoformat(from_date)
                # タイムゾーン情報がない場合はUTCとして扱う
                if since_date.tzinfo is None:
                    since_date = since_date.replace(tzinfo=timezone.utc)
            except ValueError:
                return create_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    status="error",
                    message="日付の形式が正しくありません。YYYY-MM-DD形式で指定してください。",
                    data={"papers": []}
                )
        
        # categoriesをリスト化（JSON化できるようにするため）
        categories_list = list(categories) if categories else None
                
        # 論文検索実行
        papers = await service.search_and_summarize(
            query, 
            max_results, 
            categories=categories_list,
            use_japanese_summary=use_japanese_summary, 
            since_date=since_date
        )
        
        # レスポンスデータの作成
        response_underlying_data = {
            "papers": papers, 
            "query": query, 
            "max_results": max_results
        }
        
        # 日付フィルタが指定された場合は応答データに追加
        if from_date:
            response_underlying_data["search_from_date"] = from_date
        
        # カテゴリフィルタが指定された場合は応答データに追加 - JSON化できる形式に変換
        if categories_list:
            response_underlying_data["categories"] = categories_list
            
        return create_response(
            status_code=status.HTTP_200_OK,
            status="success",
            message="新着論文はありませんでした" if not papers else f"{len(papers)}件の論文が見つかりました",
            data=response_underlying_data
        )
    except Exception as e:
        logger.error(f"検索エラー: {str(e)}")
        return create_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            status="error",
            message=f"検索に失敗しました: {str(e)}",
            data={"papers": []}
        )

@app.post("/api/watch")
async def add_watch_keyword(
    keyword: str, 
    categories: Optional[List[str]] = Query(None),
    service: PaperService = Depends(get_paper_service)
):
    """キーワードを監視リストに追加"""
    try:
        service.add_watch_keyword(keyword, categories)
        return create_response(
            status_code=status.HTTP_201_CREATED,
            status="success",
            message=f"キーワード '{keyword}' を監視リストに追加しました",
            data={"keyword": keyword, "categories": categories or []}
        )
    except Exception as e:
        logger.error(f"監視キーワード追加エラー: {str(e)}")
        return create_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            status="error",
            message=f"キーワードの追加に失敗しました: {str(e)}"
        )

@app.delete("/api/watch/{keyword}")
async def remove_watch_keyword(
    keyword: str,
    service: PaperService = Depends(get_paper_service)
):
    """キーワードを監視リストから削除"""
    try:
        service.remove_watch_keyword(keyword)
        return create_response(
            status_code=status.HTTP_200_OK,
            status="success",
            message=f"キーワード '{keyword}' を監視リストから削除しました"
        )
    except Exception as e:
        logger.error(f"監視キーワード削除エラー: {str(e)}")
        return create_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            status="error",
            message=f"キーワードの削除に失敗しました: {str(e)}"
        )

@app.get("/api/watch")
async def get_watched_keywords(service: PaperService = Depends(get_paper_service)):
    """監視中のキーワード一覧を取得"""
    try:
        watched_keywords = service.get_watched_keywords()
        return create_response(
            status_code=status.HTTP_200_OK,
            status="success",
            message=f"{len(watched_keywords.get('keywords', []))}件の監視中キーワードがあります",
            data={"watched_keywords": watched_keywords}
        )
    except Exception as e:
        logger.error(f"監視キーワード取得エラー: {str(e)}")
        return create_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            status="error",
            message=f"監視キーワードの取得に失敗しました: {str(e)}"
        )

@app.get("/api/new-papers")
async def check_new_papers(
    use_japanese_summary: bool = Query(default=True),
    service: PaperService = Depends(get_paper_service)
):
    """新規論文をチェック"""
    try:
        papers_by_keyword = await service.check_new_papers(use_japanese_summary=use_japanese_summary)
        
        # 論文が見つかった場合の処理
        if papers_by_keyword:
            # 監視中のキーワードを取得
            watched_keywords = service.get_watched_keywords()
            
            # 辞書からすべての論文を単一のリストに変換
            all_papers = []
            for keyword, paper_list in papers_by_keyword.items():
                # 各論文にマッチしたキーワードを追加
                for paper in paper_list:
                    paper['matched_keyword'] = keyword
                all_papers.extend(paper_list)
            
            # watched_keywordsが辞書型かつkeyswordsキーを持っていることを確認
            if isinstance(watched_keywords, dict) and "keywords" in watched_keywords:
                # 論文を日付とキーワードでグループ化
                grouped_papers = service.group_papers_by_date_and_keyword(
                    all_papers, watched_keywords["keywords"]
                )
            else:
                logger.error(f"監視キーワードの形式が不正です: {watched_keywords}")
                # デフォルトとして空のキーワードリストを使用
                grouped_papers = service.group_papers_by_date_and_keyword(
                    all_papers, []
                )
                
            return create_response(
                status_code=status.HTTP_200_OK,
                status="success",
                message=f"{len(all_papers)}件の新着論文が見つかりました",
                data={
                    "grouped_papers": grouped_papers,
                    "papers": papers_by_keyword,  # 後方互換性のために元の形式も残す
                    "total_papers": len(all_papers)
                }
            )
        
        # 論文が見つからなかった場合
        return create_response(
            status_code=status.HTTP_200_OK,
            status="success",
            message="新着論文はありませんでした",
            data={
                "grouped_papers": {},
                "papers": {},
                "total_papers": 0
            }
        )
    except Exception as e:
        logger.error(f"新規論文チェックエラー: {str(e)}")
        return create_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            status="error",
            message=f"新着論文の確認に失敗しました: {str(e)}"
        )

@app.post("/api/email-config")
async def save_email_config(config: Dict[str, Any], service: PaperService = Depends(get_paper_service)):
    """メール設定を保存"""
    try:
        service.save_email_config(config)
        return create_response(
            status_code=status.HTTP_200_OK,
            status="success",
            message="メール設定を保存しました"
        )
    except Exception as e:
        logger.error(f"メール設定保存エラー: {str(e)}")
        return create_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            status="error",
            message=f"メール設定の保存に失敗しました: {str(e)}"
        )

@app.get("/api/search_by_date")
async def search_papers_by_date(
    query: str,
    from_date: str,  # 'YYYY-MM-DD'形式
    max_results: int = Query(default=50, ge=1, le=100),
    use_japanese_summary: bool = Query(default=True),  # パラメータ名をuse_japanese_summaryに変更
    categories: Optional[List[str]] = Query(None),
    service: PaperService = Depends(get_paper_service)
):
    """特定の日付以降の論文を検索するAPI - 後方互換性のために残すが、search_papersでfrom_dateを使用することを推奨"""
    try:
        # 明示的にJSONシリアライズ可能な形式に変換
        max_results_value = int(max_results)
        use_japanese_summary_value = bool(use_japanese_summary)  # 変数名も一致させる
        categories_list = list(categories) if categories else None
        
        # 日本語要約の設定状態をログに記録
        logger.info(f"日本語要約設定: {use_japanese_summary_value}")
        
        # メインの検索APIにリダイレクト
        return await search_papers(
            query=query,
            max_results=max_results_value,
            use_japanese_summary=use_japanese_summary_value,  # 正しい変数名を使用
            from_date=from_date,
            categories=categories_list,
            service=service
        )
    except Exception as e:
        logger.error(f"日付検索リダイレクトエラー: {str(e)}")
        return create_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            status="error",
            message=f"日付検索に失敗しました: {str(e)}",
            data={"papers": []}
        )