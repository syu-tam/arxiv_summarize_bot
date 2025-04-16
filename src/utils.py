from loguru import logger
from pathlib import Path
import json
from typing import Dict, Any, Optional, TypeVar, Generic, Type, Callable, Awaitable
import os
import functools
import asyncio
from datetime import datetime
from diskcache import Cache

def setup_logger(name):
    """
    ロガーの設定を行う共通関数
    
    Args:
        name (str): ログファイル名のプレフィックス
    
    Returns:
        logger: 設定済みのloggerインスタンス
    """
    # ログディレクトリの確保
    Path("logs").mkdir(exist_ok=True)
    
    # ロガーの設定
    log_file = f"logs/{name}.log"
    logger.add(log_file, rotation="500 MB", enqueue=True)
    
    return logger

T = TypeVar('T')

class ConfigManager:
    """設定ファイルの読み込み・保存を行う共通クラス"""
    
    @staticmethod
    def load_json(file_path: str) -> Dict[str, Any]:
        """JSONファイルを読み込む
        
        Args:
            file_path (str): JSONファイルのパス
            
        Returns:
            Dict[str, Any]: JSONの内容、ファイルが存在しない場合は空辞書
        """
        path = Path(file_path)
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    @staticmethod
    def save_json(file_path: str, data: Dict[str, Any]) -> None:
        """JSONファイルに保存する
        
        Args:
            file_path (str): 保存先のパス
            data (Dict[str, Any]): 保存するデータ
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
    @staticmethod
    def ensure_dir(directory: str) -> None:
        """ディレクトリの存在を確認し、必要に応じて作成する
        
        Args:
            directory (str): 作成するディレクトリのパス
        """
        Path(directory).mkdir(parents=True, exist_ok=True)

def async_error_handler(log_prefix: str):
    """
    非同期関数のエラーハンドリングを行うデコレータ
    
    Args:
        log_prefix (str): ログメッセージのプレフィックス
    
    Returns:
        Callable: デコレータ関数
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                module_logger = setup_logger("error_handler")
                module_logger.error(f"{log_prefix}: {str(e)}", exc_info=True)
                raise
        return wrapper
    return decorator

class CacheManager:
    """キャッシュ操作のための共通クラス"""
    
    _cache_instance = None
    
    @classmethod
    def get_cache(cls) -> Cache:
        """キャッシュインスタンスを取得（シングルトン）"""
        if cls._cache_instance is None:
            # キャッシュディレクトリの確保
            Path("cache").mkdir(exist_ok=True)
            cls._cache_instance = Cache("cache")
        return cls._cache_instance
    
    @classmethod
    def get_or_set(cls, key: str, value_func: Callable[[], Any], expire: int = None) -> Any:
        """
        キャッシュからデータを取得、なければ関数を実行して結果をキャッシュ
        
        Args:
            key (str): キャッシュのキー
            value_func (Callable): キャッシュがない場合に実行する関数
            expire (int, optional): 有効期限（秒）
            
        Returns:
            Any: キャッシュデータまたは関数の実行結果
        """
        cache = cls.get_cache()
        value = cache.get(key)
        if value is None:
            value = value_func()
            cache.set(key, value, expire=expire)
        return value
    
    @classmethod
    async def get_or_set_async(cls, key: str, value_func: Callable[[], Awaitable[Any]], expire: int = None) -> Any:
        """
        非同期関数用のキャッシュ取得・設定
        
        Args:
            key (str): キャッシュのキー
            value_func (Callable): キャッシュがない場合に実行する非同期関数
            expire (int, optional): 有効期限（秒）
            
        Returns:
            Any: キャッシュデータまたは関数の実行結果
        """
        cache = cls.get_cache()
        value = cache.get(key)
        if value is None:
            value = await value_func()
            cache.set(key, value, expire=expire)
        return value