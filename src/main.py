import asyncio
import json
import os
from .arxiv_fetcher import ArxivFetcher
from .paper_summarizer import PaperSummarizer
from .email_notifier import EmailNotifier
from typing import List, Dict, Any, Optional, Union
from loguru import logger
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# 定数
CHECK_INTERVAL = 3600  # 1時間ごとにチェック

# ロガーの設定
logger.add("logs/main.log", rotation="500 MB")

class PaperService:
    def __init__(self):
        self.fetcher = ArxivFetcher()
        self.summarizer = PaperSummarizer()
        self.notifier = EmailNotifier()
        self.scheduler = AsyncIOScheduler()
        
        # スケジューラーの設定（毎日午前1時に実行）
        self.scheduler.add_job(
            self.check_and_notify,
            'cron',
            hour=1,
            minute=0,
            id='daily_paper_check'
        )

    def start_scheduler(self):
        """スケジューラーを開始"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")

    def stop_scheduler(self):
        """スケジューラーを停止"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")

    async def check_and_notify(self):
        """新規論文をチェックしてメール通知"""
        try:
            papers_dict = await self.check_new_papers()
            if papers_dict and len(papers_dict) > 0:
                # 辞書からリストに変換
                all_papers = []
                for keyword, papers_list in papers_dict.items():
                    all_papers.extend(papers_list)
                
                if all_papers:
                    await self.notifier.send_notification(all_papers)
        except Exception as e:
            logger.error(f"Error in scheduled check: {str(e)}")

    def save_email_config(self, config: Dict[str, Any]):
        """メール設定を保存"""
        self.notifier.save_config(config)

    def get_categories(self) -> Dict[str, Any]:
        """利用可能なカテゴリー一覧を取得"""
        return self.fetcher.get_categories()

    async def _generate_summary_for_papers(self, 
                                     papers: List[Dict[str, Any]], 
                                     use_japanese_summary: bool = True) -> List[Dict[str, Any]]:
        """
        論文リストに対して日本語要約を生成する共通処理
        
        Args:
            papers (List[Dict[str, Any]]): 要約する論文のリスト
            use_japanese_summary (bool): 日本語要約を生成するかどうか
            
        Returns:
            List[Dict[str, Any]]: 要約を追加した論文リスト
        """
        if not papers:
            return []
            
        results = []
        for paper in papers:
            paper_result = paper.copy()
            
            # 日本語要約が必要な場合のみ要約処理を行う
            if use_japanese_summary:
                try:
                    logger.info(f"論文「{paper['title']}」の日本語要約・タイトルを生成します")
                    
                    # キャッシュがあるかチェックし、あれば使用
                    if hasattr(self.summarizer, 'cache') and self.summarizer.cache:
                        cache_key = paper.get("entry_id", None)
                        if cache_key:
                            cached_result = self.summarizer.cache.get(cache_key)
                            if cached_result:
                                paper_result["title_ja"] = cached_result.get("title_ja", paper["title"])
                                paper_result["summary_ja"] = cached_result.get("summary_ja", "")
                                logger.info(f"キャッシュから日本語タイトル・要約を取得しました")
                                results.append(paper_result)
                                continue
                    
                    # 日本語要約処理を実行
                    summary = await self.summarizer.summarize(paper)
                    title_ja = summary.get("title_ja", paper["title"])
                    summary_ja = summary.get("summary_ja", "要約の生成に失敗しました。")
                    
                    paper_result.update({
                        "title_ja": title_ja,
                        "summary_ja": summary_ja
                    })
                    
                    logger.info(f"日本語タイトル・要約の生成完了")
                    
                except Exception as e:
                    logger.error(f"要約生成エラー: {str(e)}")
                    paper_result.update({
                        "title_ja": paper["title"],  # エラー時は英語タイトルをそのまま使用
                        "summary_ja": "要約の生成に失敗しました。"
                    })
            else:
                # 日本語要約が不要な場合は要約処理をスキップ
                logger.info(f"論文「{paper['title']}」の日本語要約・タイトルはスキップします")
                
            results.append(paper_result)
            
        return results

    async def search_and_summarize(self, 
                           query: str, 
                           max_results: int = 50,
                           categories: Optional[List[str]] = None,
                           use_japanese_summary: bool = True,
                           since_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """論文を検索し、要約を生成"""
        try:
            # 論文検索を実行
            papers = await self.fetcher.search_papers(query, max_results, categories, since_date)
            
            # 検索結果が空の場合は空のリストを返す（エラーではない）
            if not papers:
                logger.info(f"検索クエリ '{query}' に一致する論文は見つかりませんでした")
                return []

            # 共通の要約処理を利用
            return await self._generate_summary_for_papers(papers, use_japanese_summary)

        except Exception as e:
            logger.error(f"検索・要約処理エラー: {str(e)}")
            raise

    def add_watch_keyword(self, keyword: str, categories: Optional[List[str]] = None):
        """監視キーワードを追加"""
        self.fetcher.add_watch_keyword(keyword, categories)

    def remove_watch_keyword(self, keyword: str):
        """監視キーワードを削除"""
        self.fetcher.remove_watch_keyword(keyword)

    def get_watched_keywords(self) -> Dict[str, List[str]]:
        """監視中のキーワード一覧を取得"""
        return self.fetcher.get_watched_keywords()

    def group_papers_by_date_and_keyword(self, papers: List[Dict[str, Any]], keywords: List[str]) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """論文を日付とキーワードでグループ化"""
        grouped = {}
        # キーワード未指定時や論文が0件の場合のチェック
        if not papers:
            return grouped
            
        # 既に表示に含まれた論文のIDを管理
        displayed_paper_ids = set()
            
        for paper in papers:
            # 日付の取得とフォーマット（タイムゾーン情報を保持）
            published_date = datetime.fromisoformat(paper['published'])
            date = published_date.astimezone(timezone.utc).strftime('%Y-%m-%d')
            
            # 論文のキーワードを取得（新しい実装では既にmatched_keywordが設定されている）
            keyword = paper.get('matched_keyword', 'その他の論文')
            
            # 日付グループの追加
            if date not in grouped:
                grouped[date] = {}
            if keyword not in grouped[date]:
                grouped[date][keyword] = []
            
            # 論文IDを確認して重複を防止
            paper_id = paper.get('entry_id', '')
            if paper_id not in displayed_paper_ids:
                grouped[date][keyword].append(paper)
                displayed_paper_ids.add(paper_id)
        
        # 日付でソート（新しい順）
        return dict(sorted(grouped.items(), reverse=True))

    async def check_new_papers(self, use_japanese_summary: bool = True) -> Dict[str, List[Dict[str, Any]]]:
        """キーワードごとの新しい論文をチェックして要約する"""
        try:
            # 監視キーワードとカテゴリを読み込み
            watched_keywords = self._load_watched_keywords()
            
            # 前回のチェック日時を読み込み
            last_check_date = self._load_last_check_date()
            logger.info(f"前回のチェック日時: {last_check_date}")
            
            # 現在の日時を記録（終了時に保存）
            current_time = datetime.now(timezone.utc)
            
            results = {}
            # watched_keywordsの構造は {"keywords": [...], "categories": [...]} の形式
            if "keywords" in watched_keywords and watched_keywords["keywords"]:
                keywords_list = watched_keywords["keywords"]
                categories_list = watched_keywords.get("categories", [])
                
                for keyword in keywords_list:
                    # キーワードに対する新しい論文を検索
                    papers = await self.fetcher.search_papers(
                        keyword, 
                        max_results=50,  # デフォルトの最大結果数
                        categories=categories_list if categories_list else None,
                        since_date=last_check_date
                    )
                    
                    if papers:
                        logger.info(f"キーワード '{keyword}' に一致する新しい論文が {len(papers)} 件見つかりました")
                        
                        # 共通要約処理で論文を処理
                        summarized_papers = await self._generate_summary_for_papers(papers, use_japanese_summary)
                        
                        results[keyword] = summarized_papers
                    else:
                        logger.info(f"キーワード '{keyword}' に一致する新しい論文は見つかりませんでした")
            else:
                logger.info("監視キーワードが設定されていません")
            
            # 最終チェック日時を更新
            self._save_last_check_date(current_time)
            
            return results

        except Exception as e:
            logger.error(f"新しい論文のチェックエラー: {str(e)}")
            raise

    def _load_watched_keywords(self) -> Dict[str, Union[List[str], List[Dict[str, Any]]]]:
        """監視キーワードを読み込む"""
        return self.fetcher.get_watched_keywords()
        
    def _load_last_check_date(self) -> datetime:
        """最終チェック日時を読み込む"""
        return self.fetcher.load_last_check()
        
    def _save_last_check_date(self, date: datetime):
        """最終チェック日時を保存する"""
        self.fetcher.update_last_check_with_date(date)

async def main():
    """メインの非同期処理"""
    service = PaperService()
    service.start_scheduler()
    try:
        while True:
            papers = await service.check_new_papers()
            # 結果が辞書の場合
            if papers and isinstance(papers, dict) and len(papers) > 0:
                # 全論文の総数を計算
                total_papers = sum(len(paper_list) for paper_list in papers.values())
                logger.info(f"{total_papers}件の新着論文が見つかりました")
            
            # 1時間待機
            await asyncio.sleep(CHECK_INTERVAL)
            
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
    finally:
        service.stop_scheduler()

if __name__ == "__main__":
    asyncio.run(main())