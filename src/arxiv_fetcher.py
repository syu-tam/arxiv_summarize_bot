import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union, Sequence
from pathlib import Path
import arxiv
from .utils import setup_logger, ConfigManager, async_error_handler, CacheManager

# 共通ロギング設定を使用
logger = setup_logger("arxiv_fetcher")

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
    """
    arXivから論文を検索・取得するためのクラス。
    指定したキーワードやカテゴリに基づいて論文を検索し、
    定期的なチェックによる新規論文の発見機能も提供します。
    """
    
    def __init__(self):
        """
        ArxivFetcherクラスの初期化。
        設定ファイルの読み込みと必要なディレクトリの作成を行います。
        """
        self.client = arxiv.Client()
        self.watch_file = Path("data/watched_keywords.json")
        self.last_check_file = Path("data/last_check.json")
        
        # データディレクトリの作成
        ConfigManager.ensure_dir("data")
        
        # 監視キーワードの読み込み
        self.watched_keywords = self._load_watched_keywords()
        self.last_check = self._load_last_check()
        
        # キャッシュの有効期間（秒）
        self.cache_expire = 3600  # 1時間

    def _load_watched_keywords(self) -> Dict[str, List[str]]:
        """
        監視キーワードを読み込む
        
        Returns:
            Dict[str, List[str]]: キーワードとカテゴリのリスト
        """
        data = ConfigManager.load_json(str(self.watch_file))
        return data if data else {"keywords": [], "categories": []}

    def _load_last_check(self) -> datetime:
        """
        最終チェック日時を読み込む
        
        Returns:
            datetime: 最終チェック日時、ない場合は現在時刻
        """
        data = ConfigManager.load_json(str(self.last_check_file))
        if data and "last_check" in data:
            return datetime.fromisoformat(data["last_check"])
        return datetime.now(timezone.utc)

    def _save_watched_keywords(self):
        """監視キーワードを保存"""
        ConfigManager.save_json(str(self.watch_file), self.watched_keywords)

    def _save_last_check(self, date: datetime = None):
        """
        最終チェック日時を保存
        
        Args:
            date (datetime, optional): 保存する日時。指定がない場合は現在時刻
        """
        if date is None:
            date = datetime.now(timezone.utc)
        self.last_check = date
        ConfigManager.save_json(str(self.last_check_file), {"last_check": self.last_check.isoformat()})
        logger.info(f"最終チェック時刻を更新しました: {self.last_check.isoformat()}")

    def add_watch_keyword(self, keyword: str, categories: List[str] = None) -> bool:
        """
        監視キーワードを追加
        
        Args:
            keyword (str): 追加するキーワード
            categories (List[str], optional): 追加するカテゴリのリスト
            
        Returns:
            bool: 追加に成功したかどうか
        """
        try:
            if not keyword:
                logger.warning("空のキーワードは追加できません")
                return False
                
            if keyword not in self.watched_keywords["keywords"]:
                self.watched_keywords["keywords"].append(keyword)
            
            if categories:
                for cat in categories:
                    if cat and cat not in self.watched_keywords["categories"]:
                        self.watched_keywords["categories"].append(cat)
            
            self._save_watched_keywords()
            logger.info(f"キーワード '{keyword}' を監視リストに追加しました")
            return True
        except Exception as e:
            logger.error(f"キーワード追加エラー: {str(e)}")
            return False

    def remove_watch_keyword(self, keyword: str) -> bool:
        """
        監視キーワードを削除
        
        Args:
            keyword (str): 削除するキーワード
            
        Returns:
            bool: 削除に成功したかどうか
        """
        try:
            if keyword in self.watched_keywords["keywords"]:
                self.watched_keywords["keywords"].remove(keyword)
                self._save_watched_keywords()
                logger.info(f"キーワード '{keyword}' を監視リストから削除しました")
                return True
            else:
                logger.warning(f"キーワード '{keyword}' は監視リストに存在しません")
                return False
        except Exception as e:
            logger.error(f"キーワード削除エラー: {str(e)}")
            return False

    def get_watched_keywords(self) -> Dict[str, List[str]]:
        """
        監視中のキーワード一覧を取得
        
        Returns:
            Dict[str, List[str]]: キーワードとカテゴリのリスト
        """
        return self.watched_keywords

    def _extract_arxiv_id(self, entry_id: str) -> str:
        """
        entry_idからarXiv IDを抽出する
        
        Args:
            entry_id (str): 論文のentry_id
            
        Returns:
            str: arXiv ID
        """
        # 典型的なentry_idは http://arxiv.org/abs/2401.12345v1 のような形式
        if entry_id.startswith('http'):
            arxiv_id = entry_id.split('/')[-1]
        else:
            arxiv_id = entry_id
        return arxiv_id

    def _generate_arxiv_url(self, entry_id: str) -> str:
        """
        arXivのURLを生成する
        
        Args:
            entry_id (str): 論文のentry_id
            
        Returns:
            str: arXivのURL
        """
        arxiv_id = self._extract_arxiv_id(entry_id)
        return f"https://arxiv.org/abs/{arxiv_id}"

    def _prepare_search_query(self, keyword: str, categories: List[str] = None) -> str:
        """
        検索クエリを準備する
        
        Args:
            keyword (str): 検索キーワード
            categories (List[str], optional): 検索対象カテゴリのリスト
            
        Returns:
            str: 検索クエリ文字列
        """
        # スペースを含むキーワードはダブルクォートで囲んでフレーズ検索を強制
        keyword_for_search = f'"{keyword}"' if ' ' in keyword else keyword
        
        # カテゴリーフィルターを適用
        if categories and len(categories) > 0:
            category_filter = ' OR '.join(f'cat:{cat}' for cat in categories)
            return f"({keyword_for_search}) AND ({category_filter})"
        else:
            return keyword_for_search

    def _convert_paper_to_dict(self, result: arxiv.Result, matched_keyword: str = None) -> Dict[str, Any]:
        """
        論文オブジェクトを辞書に変換する
        
        Args:
            result (arxiv.Result): 論文オブジェクト
            matched_keyword (str, optional): マッチしたキーワード
            
        Returns:
            Dict[str, Any]: 論文情報の辞書
        """
        # 日付をUTCタイムゾーンで保持
        published_date = result.published.astimezone(timezone.utc)
        
        paper = {
            "title": result.title,
            "authors": [author.name for author in result.authors],
            "summary": result.summary,
            "published": published_date.isoformat(),
            "pdf_url": result.pdf_url,
            "url": self._generate_arxiv_url(result.entry_id),
            "entry_id": result.entry_id,
            "primary_category": result.primary_category,
            "categories": result.categories
        }
        
        # マッチしたキーワードが指定されていれば追加
        if matched_keyword:
            paper["matched_keyword"] = matched_keyword
            
        return paper

    @async_error_handler("論文検索")
    async def search_papers(self, 
                    query: str, 
                    max_results: int = 10,
                    categories: Optional[Any] = None,
                    since_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        arXivから論文を検索
        
        Args:
            query (str): 検索クエリ
            max_results (int, optional): 取得する最大結果数。デフォルト10
            categories (Any, optional): 検索対象カテゴリのリスト
            since_date (datetime, optional): この日時以降の論文のみ検索
            
        Returns:
            List[Dict[str, Any]]: 論文情報のリスト
        """
        # FastAPIのQueryオブジェクトやその他の型からリストに変換
        categories_list = None
        if categories is not None:
            try:
                # イテラブルかどうか確認し、リストに変換
                categories_list = list(categories) if hasattr(categories, '__iter__') and not isinstance(categories, str) else [categories]
            except TypeError:
                # イテラブルでない場合は単一の値として扱う
                categories_list = [str(categories)]
            
            # 空の値を除外
            categories_list = [cat for cat in categories_list if cat]
            
            # リストが空の場合はNoneに設定
            if not categories_list:
                categories_list = None
        
        # キャッシュキーの生成 - JSON化できない問題を回避するため文字列表現を使用
        cache_key_categories = str(categories_list) if categories_list else "None"
        cache_key = f"search_{query}_{max_results}_{cache_key_categories}_{since_date.isoformat() if since_date else 'None'}"
        
        # キャッシュがあればそれを返す
        return await CacheManager.get_or_set_async(
            cache_key,
            lambda: self._search_papers_impl(query, max_results, categories_list, since_date),
            expire=self.cache_expire
        )
    
    async def _search_papers_impl(self, 
                    query: str, 
                    max_results: int = 10,
                    categories: Optional[List[str]] = None,
                    since_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """検索の実装部分"""
        # スペースを含むクエリはダブルクォートで囲んでフレーズ検索を強制
        if query and ' ' in query and not (query.startswith('"') and query.endswith('"')):
            query = f'"{query}"'
            logger.info(f"フレーズ検索として処理: {query}")

        # categoriesパラメータの処理を強化
        search_query = query
        if categories:
            # 不正な値やオブジェクト表現を排除し、有効なカテゴリIDのみを抽出
            valid_categories = []
            for cat in categories:
                # 文字列化し、標準的なカテゴリIDパターンに一致するもののみを使用
                cat_str = str(cat).strip()
                # cs.AI, stat.ML などの一般的なカテゴリID形式をチェック
                if '.' in cat_str and len(cat_str) < 20 and not ' ' in cat_str:
                    valid_categories.append(cat_str)
            
            # 有効なカテゴリが存在する場合のみフィルタを適用
            if valid_categories:
                category_filter = ' OR '.join(f'cat:{cat}' for cat in valid_categories)
                search_query = f"({query}) AND ({category_filter})"
                logger.info(f"カテゴリフィルター '{category_filter}' を適用します")
            else:
                logger.warning(f"無効なカテゴリが指定されました: {categories}")

        # 日付による絞り込みのログ出力
        if since_date:
            # タイムゾーンを確実に設定
            if since_date.tzinfo is None:
                since_date = since_date.replace(tzinfo=timezone.utc)
            logger.info(f"検索の対象期間: {since_date.isoformat()}以降 (日付で絞り込み)")
            # 日付をより読みやすい形式でもログに出力
            readable_date = since_date.strftime("%Y年%m月%d日 %H:%M:%S")
            logger.info(f"日本時間表示: {readable_date} 以降の論文のみ表示します")

        logger.info(f"検索クエリ: {search_query}")

        # max_resultsの上限を設定
        actual_max_results = min(max_results, 100)
        logger.info(f"最大 {actual_max_results} 件の論文を取得します")

        # arXivの検索オブジェクトを作成 - 日付でのソートを指定
        search = arxiv.Search(
            query=search_query,
            max_results=actual_max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending
        )

        # 検索を実行して結果を取得
        try:
            results = list(self.client.results(search))
            logger.info(f"arXiv APIから {len(results)} 件の論文を取得しました")
        except Exception as e:
            logger.error(f"arXiv APIの検索中にエラーが発生しました: {str(e)}")
            return []
        
        # 結果を処理
        papers = []
        filtered_count = 0
        
        # 日付のフィルタリング
        for result in results:
            published_date = result.published.astimezone(timezone.utc)
            
            # 日付によるフィルタリング - 指定日以降の論文のみ
            if since_date:
                # ここでは「指定日より前」の論文をスキップ
                if published_date < since_date:
                    filtered_count += 1
                    # 詳細なデバッグログ
                    if filtered_count <= 5:  # 最初の5件だけログ出力
                        logger.debug(f"日付フィルター: 除外された論文 '{result.title}', 公開日: {published_date.isoformat()}")
                    continue
            
            # 条件を満たす論文を結果に追加
            paper = self._convert_paper_to_dict(result)
            papers.append(paper)
        
        if filtered_count > 0:
            logger.info(f"日付フィルターにより {filtered_count} 件の論文が除外されました")
        
        logger.info(f"検索クエリ '{search_query}' に一致する論文が {len(papers)} 件見つかりました")
        
        # 結果が0件の場合、詳細情報をログに出力
        if len(papers) == 0:
            logger.warning(f"検索結果が0件です。クエリ: '{search_query}', 日付指定: {since_date.isoformat() if since_date else '指定なし'}")
            # APIからは論文が取得できたが、フィルターで除外された場合
            if len(results) > 0:
                logger.warning(f"API検索自体では {len(results)} 件ありましたが、フィルターで全て除外されました")
                # 念のため、最初の数件の論文の日付を出力
                for i, result in enumerate(results[:3]):
                    published_date = result.published.astimezone(timezone.utc)
                    logger.warning(f"  除外された論文 #{i+1}: '{result.title}', 公開日: {published_date.isoformat()}")
        
        return papers

    @async_error_handler("新規論文チェック")
    async def check_new_papers(self) -> List[Dict[str, Any]]:
        """
        監視中のキーワードに関連する新規論文をチェック
        
        Returns:
            List[Dict[str, Any]]: 新規論文情報のリスト
        """
        last_check = self._load_last_check()
        watched_keywords = self.get_watched_keywords()
        
        if not watched_keywords["keywords"]:
            logger.info("監視キーワードが設定されていません")
            return []
        
        all_papers = []
        newest_paper_date = None
        
        for keyword in watched_keywords["keywords"]:
            # キーワードごとに検索
            search_query = self._prepare_search_query(keyword, watched_keywords.get("categories"))
            
            search = arxiv.Search(
                query=search_query,
                max_results=50,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending
            )
            
            results = list(self.client.results(search))
            
            # 各論文をフィルタリング
            for result in results:
                # 日付をUTCタイムゾーンで保持
                paper_date = result.published.astimezone(timezone.utc)
                
                # last_checkより後の論文のみを処理
                if paper_date > last_check:
                    # 最新の論文日時を更新
                    if newest_paper_date is None or paper_date > newest_paper_date:
                        newest_paper_date = paper_date
                        
                    # 重複チェック
                    if not any(p["entry_id"] == result.entry_id for p in all_papers):
                        paper = self._convert_paper_to_dict(result, keyword)
                        logger.info(f"新しい論文が見つかりました: {result.title}, 公開日: {paper_date.isoformat()}, キーワード: {keyword}")
                        all_papers.append(paper)
        
        # 最終チェック日時を更新
        if newest_paper_date:
            self._save_last_check(newest_paper_date)
        elif all_papers:
            self._save_last_check()
        
        logger.info(f"監視キーワードに一致する新しい論文が {len(all_papers)} 件見つかりました")
        return all_papers

    def get_categories(self) -> Dict[str, Any]:
        """
        利用可能なカテゴリー一覧を返す
        
        Returns:
            Dict[str, Any]: カテゴリー情報
        """
        return ARXIV_CATEGORIES

    def load_last_check(self) -> datetime:
        """
        最終チェック日時を取得
        
        Returns:
            datetime: 最終チェック日時
        """
        return self._load_last_check()

    def update_last_check(self):
        """最終チェック日時を現在時刻で更新"""
        self._save_last_check()

    def update_last_check_with_date(self, date: Union[datetime, str]):
        """
        指定された日時で最終チェック日時を更新
        
        Args:
            date (Union[datetime, str]): 更新する日時。文字列の場合はISOフォーマットが必要
        """
        if isinstance(date, str):
            date = datetime.fromisoformat(date)
        self._save_last_check(date)