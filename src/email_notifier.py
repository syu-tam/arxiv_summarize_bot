from typing import List, Dict, Any
from datetime import datetime
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib
from pydantic import BaseModel, EmailStr
from pathlib import Path
import json
from .utils import setup_logger, ConfigManager

# 共通ロギング設定を使用
logger = setup_logger("email_notifier")

class EmailConfig(BaseModel):
    smtp_server: str
    smtp_port: int
    username: str
    password: str
    from_email: EmailStr
    to_emails: List[EmailStr]

class EmailNotifier:
    def __init__(self):
        self.config_file = "data/email_config.json"
        self.config = self._load_config()

    def _load_config(self) -> EmailConfig:
        """メール設定を読み込む"""
        config_data = ConfigManager.load_json(self.config_file)
        return EmailConfig(**config_data) if config_data else None

    def save_config(self, config: Dict[str, Any]):
        """メール設定を保存"""
        ConfigManager.save_json(self.config_file, config)
        self.config = EmailConfig(**config)

    async def send_notification(self, papers: List[Dict[str, Any]]):
        """新着論文の通知メールを送信"""
        if not self.config or not papers:
            return

        try:
            # 日付でグループ化
            papers_by_date = {}
            for paper in papers:
                date = datetime.fromisoformat(paper['published']).date()
                if date not in papers_by_date:
                    papers_by_date[date] = []
                papers_by_date[date].append(paper)

            # メール本文を作成
            html_content = """
            <html>
            <head>
                <style>
                    .paper { margin-bottom: 20px; padding: 10px; border: 1px solid #ddd; }
                    .title { font-size: 18px; color: #2c3e50; margin-bottom: 10px; }
                    .meta { color: #666; font-size: 14px; margin-bottom: 10px; }
                    .summary { background-color: #f8f9fa; padding: 10px; border-radius: 4px; }
                </style>
            </head>
            <body>
                <h1>新着論文のお知らせ</h1>
            """

            for date, date_papers in sorted(papers_by_date.items(), reverse=True):
                html_content += f"<h2>{date.strftime('%Y年%m月%d日')}</h2>"
                for paper in date_papers:
                    html_content += f"""
                    <div class="paper">
                        <div class="title">{paper['title']}</div>
                        {f'<div class="title-ja">{paper["title_ja"]}</div>' if 'title_ja' in paper and paper['title_ja'] != paper['title'] else ''}
                        <div class="meta">
                            著者: {', '.join(paper['authors'])}<br>
                            カテゴリー: {paper['primary_category']}
                        </div>
                        <div class="summary">
                            <h3>要約:</h3>
                            <p>{paper.get('summary_ja', '要約なし')}</p>
                        </div>
                        <p><a href="{paper['pdf_url']}" target="_blank">PDF を開く</a></p>
                    </div>
                    """

            html_content += """
                </body>
            </html>
            """

            message = MIMEMultipart()
            message["Subject"] = f"新着論文のお知らせ ({len(papers)}件)"
            message["From"] = self.config.from_email
            message["To"] = ", ".join(self.config.to_emails)

            message.attach(MIMEText(html_content, "html"))

            # メール送信
            async with aiosmtplib.SMTP(
                hostname=self.config.smtp_server,
                port=self.config.smtp_port,
                use_tls=True
            ) as smtp:
                await smtp.login(self.config.username, self.config.password)
                await smtp.send_message(message)

            logger.info(f"Sent notification email for {len(papers)} papers")

        except Exception as e:
            logger.error(f"Error sending notification email: {str(e)}")
            raise