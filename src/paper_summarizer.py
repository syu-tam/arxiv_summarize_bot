from typing import Dict, Any
import os
from openai import AsyncOpenAI
from dotenv import load_dotenv
from diskcache import Cache
from .utils import setup_logger

# 共通ロギング設定を使用
logger = setup_logger("paper_summarizer")

class PaperSummarizer:
    def __init__(self):
        load_dotenv()
        self.test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        # 重複した設定を削除
        if not self.test_mode:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEYが設定されていません")
            self.client = AsyncOpenAI(api_key=api_key)
        self.cache = Cache("cache")

    async def summarize(self, paper: Dict[str, Any]) -> Dict[str, str]:
        """
        論文の日本語要約を生成

        Args:
            paper (Dict[str, Any]): 論文データ（title, summaryが必要）

        Returns:
            Dict[str, str]: 要約結果 
                {
                    "title": 論文タイトル,
                    "title_ja": 論文タイトル(日本語),
                    "summary_ja": 日本語要約
                }
        """
        cache_key = paper["entry_id"] if "entry_id" in paper else None
        
        if cache_key:
            cached_result = self.cache.get(cache_key)
            if cached_result is not None:
                logger.info(f"Cache hit for paper: {paper['title']}")
                return cached_result

        if self.test_mode:
            return {
                "title": paper["title"],
                "title_ja": f"[テスト] {paper['title']}",
                "summary_ja": "[テストモード] この要約はテストモードで生成されました。"
            }

        try:
            system_prompt = "あなたは学術論文の専門家です。英語の学術論文のタイトルと要約を日本語に翻訳してください。簡潔かつ正確に翻訳してください。"
            user_prompt = f"""タイトル：{paper['title']}
アブストラクト：{paper['summary']}

以下の形式で必ず回答してください：
タイトル：[論文タイトルの日本語訳]
要約：[アブストラクトの日本語要約]"""

            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1000,  # トークン数を増やして十分な要約を得られるようにする
                top_p=0.9
            )
            
            content = response.choices[0].message.content
            logger.info(f"Raw AI response: {content}")
            
            # タイトルと要約を抽出
            title_ja = ""
            summary_ja = ""
            
            # 応答が期待通りのフォーマットかチェック
            lines = content.split("\n")
            for line in lines:
                if line.startswith("タイトル：") or line.startswith("タイトル:"):
                    title_ja = line.split("：", 1)[1].strip() if "：" in line else line.split(":", 1)[1].strip()
                elif line.startswith("要約：") or line.startswith("要約:"):
                    summary_ja = line.split("：", 1)[1].strip() if "：" in line else line.split(":", 1)[1].strip()
            
            # 抽出に失敗した場合のフォールバック
            if not title_ja:
                title_ja = paper["title"]  # 英語タイトルをそのまま使用
                logger.warning(f"Failed to extract Japanese title for: {paper['title']}")
            
            if not summary_ja:
                logger.error(f"Failed to extract summary for paper: {paper['title']}")
                summary_ja = "要約の抽出に失敗しました。"
            
            result = {
                "title": paper["title"],
                "title_ja": title_ja,
                "summary_ja": summary_ja
            }

            # デバッグ情報を追加
            logger.info(f"Generated result for paper: {paper['title']}")
            logger.info(f"title_ja: {title_ja}")
            logger.info(f"summary_ja length: {len(summary_ja)}")

            if cache_key:
                self.cache.set(cache_key, result)
                logger.info(f"Cached summary for paper: {paper['title']}")

            return result

        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            # エラー時にもデフォルト値を返す
            return {
                "title": paper["title"],
                "title_ja": paper["title"],  # エラー時は英語タイトルをそのまま使用
                "summary_ja": f"要約の生成中にエラーが発生しました: {str(e)}"
            }
