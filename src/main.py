import asyncio
import json
import os
from .arxiv_fetcher import ArxivFetcher
from .paper_summarizer import PaperSummarizer
from .email_notifier import EmailNotifier
from typing import List, Dict, Any, Optional
from loguru import logger
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# 定数
CHECK_INTERVAL = 3600  # 1時間ごとにチェック

# コンポーネントの初期化
arxiv_fetcher = ArxivFetcher()
paper_summarizer = PaperSummarizer()
email_notifier = EmailNotifier()

# ロガーの設定
logger.add("logs/main.log", rotation="500 MB")

class PaperService:
    def __init__(self):
        self.fetcher = ArxivFetcher()
        self.summarizer = PaperSummarizer()
        self.notifier = EmailNotifier()
        self.scheduler = AsyncIOScheduler()
        self._should_continue = True
        
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
            if not self._should_continue:
                logger.info("処理が一時停止されています")
                return

            papers = await self.check_new_papers()
            if papers and len(papers) > 0:
                await self.notifier.send_notification(papers)
        except Exception as e:
            logger.error(f"Error in scheduled check: {str(e)}")

    def pause_processing(self):
        """処理を一時停止"""
        self._should_continue = False
        logger.info("処理を一時停止しました")

    def resume_processing(self):
        """処理を再開"""
        self._should_continue = True
        logger.info("処理を再開しました")

    def is_processing(self) -> bool:
        """処理状態を確認"""
        return self._should_continue

    def save_email_config(self, config: Dict[str, Any]):
        """メール設定を保存"""
        self.notifier.save_config(config)

    def get_categories(self) -> Dict[str, Any]:
        """利用可能なカテゴリー一覧を取得"""
        return self.fetcher.get_categories()

    async def search_and_summarize(self, 
                           query: str, 
                           max_results: int = 5,
                           categories: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """論文を検索し、要約を生成"""
        try:
            if not self._should_continue:
                logger.info("処理が一時停止されています")
                return []

            # 論文検索を実行（ジェネレータを一度にリストに変換）
            papers = await self.fetcher.search_papers(query, max_results, categories)
            
            # 検索結果が空の場合は空のリストを返す（エラーではない）
            if not papers:
                logger.info(f"検索クエリ '{query}' に一致する論文は見つかりませんでした")
                return []

            # 要約生成
            results = []
            for paper in papers:
                try:
                    summary = await self.summarizer.summarize(paper)
                    paper.update({"summary_ja": summary["summary_ja"]})
                    results.append(paper)
                except Exception as e:
                    logger.error(f"要約生成エラー: {str(e)}")
                    paper.update({"summary_ja": "要約の生成に失敗しました。"})
                    results.append(paper)

            return results

        except Exception as e:
            logger.error(f"検索・要約処理エラー: {str(e)}")
            raise

    async def test_recent_papers(self, 
                           query: str, 
                           max_results: int = 10,
                           since_date: datetime = None) -> List[Dict[str, Any]]:
        """テスト用：特定の日付以降の論文を検索して要約"""
        try:
            if not self._should_continue:
                logger.info("処理が一時停止されています")
                return []

            # 論文検索を実行
            papers = await self.fetcher.search_papers(query, max_results, categories=None, since_date=since_date)
            if not papers:
                logger.info(f"検索クエリ '{query}' に一致する論文は見つかりませんでした")
                return []

            # 要約生成
            results = []
            for paper in papers:
                try:
                    summary = await self.summarizer.summarize(paper)
                    paper.update({"summary_ja": summary["summary_ja"]})
                    results.append(paper)
                except Exception as e:
                    logger.error(f"要約生成エラー: {str(e)}")
                    paper.update({"summary_ja": "要約の生成に失敗しました。"})
                    results.append(paper)

            return results

        except Exception as e:
            logger.error(f"テスト検索・要約処理エラー: {str(e)}")
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
        for paper in papers:
            # 日付の取得とフォーマット
            date = datetime.fromisoformat(paper['published']).strftime('%Y-%m-%d')
            
            # 論文が含むキーワードを特定
            paper_keywords = []
            title_and_summary = (paper['title'] + ' ' + paper['summary']).lower()
            for keyword in keywords:
                if keyword.lower() in title_and_summary:
                    paper_keywords.append(keyword)
            
            # 各キーワードについて日付グループに追加
            for keyword in paper_keywords:
                if date not in grouped:
                    grouped[date] = {}
                if keyword not in grouped[date]:
                    grouped[date][keyword] = []
                grouped[date][keyword].append(paper)
        
        # 日付でソート
        return dict(sorted(grouped.items(), reverse=True))

    async def check_new_papers(self) -> List[Dict[str, Any]]:
        """新規論文をチェックして要約を生成"""
        try:
            new_papers = await self.fetcher.check_new_papers()
            if not new_papers:
                return []

            # 新規論文の要約を生成
            results = []
            for paper in new_papers:
                try:
                    summary = await self.summarizer.summarize(paper)
                    paper.update({"summary_ja": summary["summary_ja"]})
                    results.append(paper)
                except Exception as e:
                    logger.error(f"要約生成エラー: {str(e)}")
                    paper.update({"summary_ja": "要約の生成に失敗しました。"})
                    results.append(paper)

            return results

        except Exception as e:
            logger.error(f"新規論文チェックエラー: {str(e)}")
            raise

async def main():
    """メインの非同期処理"""
    service = PaperService()
    service.start_scheduler()
    try:
        while True:
            # ユーザー入力を非同期的に処理
            response = await asyncio.get_event_loop().run_in_executor(
                None, input, "反復処理を続行しますか? (y/n): "
            )
            if response.lower() != 'y':
                logger.info("プログラムを終了します。")
                break
            
            papers = await service.check_new_papers()
            if papers and len(papers) > 0:
                logger.info(f"{len(papers)}件の新着論文が見つかりました")
            
            # 1時間待機
            await asyncio.sleep(3600)
            
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
    finally:
        service.stop_scheduler()

if __name__ == "__main__":
    asyncio.run(main())