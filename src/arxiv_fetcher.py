import json
from datetime import datetime
from typing import List, Dict, Any
from loguru import logger
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path
import arxiv

logger.add("logs/arxiv_fetcher.log", rotation="500 MB")

ARXIV_CATEGORIES = {
    'cs': {
        'name': 'Computer Science',
        'subcategories': {
            'cs.AI': 'Artificial Intelligence',
            'cs.CL': 'Computation and Language',
            'cs.CV': 'Computer Vision',
            'cs.LG': 'Machine Learning',
            'cs.RO': 'Robotics'
        }
    },
    'stat': {
        'name': 'Statistics',
        'subcategories': {
            'stat.ML': 'Machine Learning',
        }
    }
}

class ArxivFetcher:
    def __init__(self):
        self.client = arxiv.Client()
        self.watch_file = Path("data/watched_keywords.json")
        self.last_check_file = Path("data/last_check.json")
        
        # データディレクトリの作成
        self.watch_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 監視キーワードの読み込み
        self.watched_keywords = self._load_watched_keywords()
        self.last_check = self._load_last_check()

    def _load_watched_keywords(self) -> Dict[str, List[str]]:
        """監視キーワードを読み込む"""
        if self.watch_file.exists():
            with open(self.watch_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"keywords": [], "categories": []}

    def _load_last_check(self) -> datetime:
        """最終チェック日時を読み込む"""
        if self.last_check_file.exists():
            with open(self.last_check_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return datetime.fromisoformat(data["last_check"])
        return datetime.now(timezone.utc)

    def _save_watched_keywords(self):
        """監視キーワードを保存"""
        with open(self.watch_file, 'w', encoding='utf-8') as f:
            json.dump(self.watched_keywords, f, ensure_ascii=False, indent=2)

    def _save_last_check(self):
        """最終チェック日時を保存"""
        with open(self.last_check_file, 'w', encoding='utf-8') as f:
            json.dump(self.last_check, f, ensure_ascii=False, indent=2)

    def add_watch_keyword(self, keyword: str, categories: List[str] = None):
        """監視キーワードを追加"""
        if keyword not in self.watched_keywords["keywords"]:
            self.watched_keywords["keywords"].append(keyword)
        if categories:
            for cat in categories:
                if cat not in self.watched_keywords["categories"]:
                    self.watched_keywords["categories"].append(cat)
        self._save_watched_keywords()

    def remove_watch_keyword(self, keyword: str):
        """監視キーワードを削除"""
        if keyword in self.watched_keywords["keywords"]:
            self.watched_keywords["keywords"].remove(keyword)
            self._save_watched_keywords()

    def get_watched_keywords(self) -> Dict[str, List[str]]:
        """監視中のキーワード一覧を取得"""
        return self.watched_keywords

    async def check_new_papers(self) -> List[Dict[str, Any]]:
        """監視中のキーワードに関連する新規論文をチェック"""
        try:
            last_check = self.load_last_check()
            logger.info(f"Checking papers since: {last_check}")
            
            watched_keywords = self.get_watched_keywords()
            if not watched_keywords["keywords"]:
                return []

            queries = []
            for keyword in watched_keywords["keywords"]:
                queries.append(f"({keyword})")
            
            if watched_keywords["categories"]:
                category_filter = ' OR '.join(f'cat:{cat}' for cat in watched_keywords["categories"])
                search_query = f"({' OR '.join(queries)}) AND ({category_filter})"
            else:
                search_query = ' OR '.join(queries)
            
            logger.info(f"Searching with query: {search_query}")

            search = arxiv.Search(
                query=search_query,
                max_results=100,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )

            papers = []
            # ジェネレータを一度にリストに変換
            results = list(self.client.results(search))
            for result in results:
                if result.published < last_check:
                    continue

                paper = {
                    "title": result.title,
                    "authors": [author.name for author in result.authors],
                    "summary": result.summary,
                    "published": result.published.isoformat(),
                    "pdf_url": result.pdf_url,
                    "entry_id": result.entry_id,
                    "primary_category": result.primary_category,
                    "categories": result.categories
                }
                papers.append(paper)
            
            if papers:
                self.update_last_check()
                logger.info(f"Found {len(papers)} new papers matching the watched keywords")
            else:
                logger.info("No new papers found")
            
            return papers

        except Exception as e:
            logger.error(f"Error checking new papers: {str(e)}")
            raise

    def get_categories(self) -> Dict[str, Any]:
        """利用可能なカテゴリー一覧を返す"""
        return ARXIV_CATEGORIES

    async def search_papers(self, 
                     query: str, 
                     max_results: int = 10,
                     categories: List[str] = None,
                     since_date: datetime = None) -> List[Dict[str, Any]]:
        """arXivから論文を検索"""
        try:
            if categories:
                category_filter = ' OR '.join(f'cat:{cat}' for cat in categories)
                if query:
                    search_query = f"({query}) AND ({category_filter})"
                else:
                    search_query = category_filter
            else:
                search_query = query

            logger.info(f"Executing search with query: {search_query}")

            search = arxiv.Search(
                query=search_query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )

            papers = []
            results = list(self.client.results(search))
            for result in results:
                if len(papers) >= max_results:
                    break
                
                if since_date and result.published < since_date:
                    continue

                paper = {
                    "title": result.title,
                    "authors": [author.name for author in result.authors],
                    "summary": result.summary,
                    "published": result.published.isoformat(),
                    "pdf_url": result.pdf_url,
                    "entry_id": result.entry_id,
                    "primary_category": result.primary_category,
                    "categories": result.categories
                }
                papers.append(paper)
            
            logger.info(f"Found {len(papers)} papers for query: {search_query}")
            return papers

        except Exception as e:
            logger.error(f"Error during paper search: {str(e)}")
            raise

    def load_last_check(self) -> datetime:
        """最終チェック日時を取得"""
        return self._load_last_check()

    def update_last_check(self):
        """最終チェック日時を現在時刻で更新"""
        self.last_check = datetime.now(timezone.utc)
        with open(self.last_check_file, 'w', encoding='utf-8') as f:
            json.dump({"last_check": self.last_check.isoformat()}, f, ensure_ascii=False, indent=2)
        logger.info(f"Updated last check time to: {self.last_check}")