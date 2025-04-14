from typing import Dict, Any
import os
from openai import AsyncOpenAI  # AsyncOpenAIに変更
from dotenv import load_dotenv
from diskcache import Cache
from loguru import logger

logger.add("logs/paper_summarizer.log", rotation="500 MB")

class PaperSummarizer:
    def __init__(self):
        load_dotenv()
        self.test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        if not self.test_mode:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEYが設定されていません")
            self.client = AsyncOpenAI(api_key=api_key)  # AsyncOpenAIに変更
        self.cache = Cache("cache")

    async def summarize(self, paper: Dict[str, Any]) -> Dict[str, str]:
        """
        論文の要約を生成

        Args:
            paper (Dict[str, Any]): 論文データ（title, summaryが必要）

        Returns:
            Dict[str, str]: 要約結果 
                {
                    "title": 論文タイトル,
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
                "summary_ja": "[テストモード] この要約はテストモードで生成されました。"
            }

        try:
            system_prompt = "英語の学術論文を簡潔に日本語で要約してください。"
            user_prompt = f"""タイトル：{paper['title']}
アブストラクト：{paper['summary']}"""

            response = await self.client.chat.completions.create(  # createに変更
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=500,
                top_p=0.9
            )

            result = {
                "title": paper["title"],
                "summary_ja": response.choices[0].message.content
            }

            if cache_key:
                self.cache.set(cache_key, result)
                logger.info(f"Cached summary for paper: {paper['title']}")

            return result

        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            raise
