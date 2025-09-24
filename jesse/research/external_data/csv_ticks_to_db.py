"""
CSV Ticks to Database Loader
Загружает все доступные CSV данные в базу данных Jesse для бэктестинга и оптимизации.
"""

AUTHORIZATION = "ef260e9aa3c673af240d17a2660480361a8e081d1ffeca2a5ed0e3219fc18567"
BASE_URL = "http://localhost:9000"

import requests
import time
import json
from datetime import datetime
from typing import List, Dict, Optional

class CSVDataLoader:
    """Класс для загрузки CSV данных в базу Jesse"""
    
    def __init__(self, base_url: str, authorization: str):
        self.base_url = base_url
        self.headers = {"Authorization": authorization}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def get_available_symbols(self) -> List[str]:
        """Получить список доступных символов"""
        try:
            response = self.session.get(f"{self.base_url}/csv/symbols")
            response.raise_for_status()
            data = response.json()
            return data.get('symbols', [])
        except Exception as e:
            print(f"Ошибка получения символов: {e}")
            return []
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Получить информацию о символе"""
        try:
            response = self.session.get(f"{self.base_url}/csv/symbols/{symbol}/info")
            response.raise_for_status()
            data = response.json()
            return data.get('info')
        except Exception as e:
            print(f"Ошибка получения информации о {symbol}: {e}")
            return None
    
    def get_available_timeframes(self, symbol: str) -> List[str]:
        """Получить доступные таймфреймы для символа"""
        try:
            response = self.session.get(f"{self.base_url}/csv/symbols/{symbol}/timeframes")
            response.raise_for_status()
            data = response.json()
            return data.get('timeframes', [])
        except Exception as e:
            print(f"Ошибка получения таймфреймов для {symbol}: {e}")
            return []
    
    def preview_data(self, symbol: str, limit: int = 10) -> Optional[Dict]:
        """Предварительный просмотр данных"""
        try:
            response = self.session.get(f"{self.base_url}/csv/preview/{symbol}?limit={limit}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Ошибка предварительного просмотра {symbol}: {e}")
            return None
    
    def import_symbol(self, symbol: str, timeframe: str = "1m", 
                     exchange: str = "custom", 
                     start_date: Optional[str] = None,
                     finish_date: Optional[str] = None) -> bool:
        """Импортировать символ в базу данных"""
        try:
            payload = {
                "symbol": symbol,
                "timeframe": timeframe,
                "exchange": exchange
            }
            
            if start_date:
                payload["start_date"] = start_date
            if finish_date:
                payload["finish_date"] = finish_date
            
            response = self.session.post(
                f"{self.base_url}/csv/import",
                json=payload
            )
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ {symbol}: {data.get('message', 'Импортирован успешно')}")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка импорта {symbol}: {e}")
            return False
    
    def get_candles(self, symbol: str, timeframe: str = "1m",
                   start_date: Optional[str] = None,
                   finish_date: Optional[str] = None,
                   limit: int = 100) -> Optional[Dict]:
        """Получить свечи для символа"""
        try:
            params = {
                "symbol": symbol,
                "timeframe": timeframe,
                "limit": limit
            }
            
            if start_date:
                params["start_date"] = start_date
            if finish_date:
                params["finish_date"] = finish_date
            
            response = self.session.get(f"{self.base_url}/csv/candles", params=params)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"Ошибка получения свечей для {symbol}: {e}")
            return None
    
    def clear_cache(self) -> bool:
        """Очистить кэш"""
        try:
            response = self.session.post(f"{self.base_url}/csv/clear-cache")
            response.raise_for_status()
            print("✅ Кэш очищен")
            return True
        except Exception as e:
            print(f"❌ Ошибка очистки кэша: {e}")
            return False


def load_all_data(timeframe: str = "1m", 
                 max_symbols: Optional[int] = None,
                 start_date: Optional[str] = None,
                 finish_date: Optional[str] = None,
                 preview_only: bool = False):
    """
    Загрузить все доступные данные
    
    Args:
        timeframe: Таймфрейм для загрузки (по умолчанию "1m")
        max_symbols: Максимальное количество символов для загрузки
        start_date: Начальная дата (формат: "2023-01-01")
        finish_date: Конечная дата (формат: "2023-12-31")
        preview_only: Только предварительный просмотр без импорта
    """
    
    print("🚀 Начинаем загрузку CSV данных в Jesse...")
    print(f"Таймфрейм: {timeframe}")
    if start_date:
        print(f"Начальная дата: {start_date}")
    if finish_date:
        print(f"Конечная дата: {finish_date}")
    print("-" * 50)
    
    # Инициализация загрузчика
    loader = CSVDataLoader(BASE_URL, AUTHORIZATION)
    
    # Получение списка символов
    print("📋 Получаем список доступных символов...")
    symbols = loader.get_available_symbols()
    
    if not symbols:
        print("❌ Символы не найдены!")
        return
    
    print(f"✅ Найдено {len(symbols)} символов")
    
    # Ограничение количества символов если указано
    if max_symbols and max_symbols < len(symbols):
        symbols = symbols[:max_symbols]
        print(f"🔄 Ограничиваем до {max_symbols} символов")
    
    # Статистика
    successful_imports = 0
    failed_imports = 0
    total_candles = 0
    
    start_time = time.time()
    
    for i, symbol in enumerate(symbols, 1):
        print(f"\n[{i}/{len(symbols)}] Обрабатываем {symbol}...")
        
        # Получение информации о символе
        info = loader.get_symbol_info(symbol)
        if info:
            print(f"  📊 Период: {info['start_date']} - {info['end_date']}")
            print(f"  📁 Размер файла: {info['file_size']:,} байт")
        
        # Предварительный просмотр
        if preview_only:
            preview = loader.preview_data(symbol, limit=5)
            if preview:
                print(f"  👀 Предварительный просмотр:")
                for row in preview.get('preview', [])[:3]:
                    print(f"    {row}")
            continue
        
        # Импорт данных
        success = loader.import_symbol(
            symbol=symbol,
            timeframe=timeframe,
            exchange="custom",
            start_date=start_date,
            finish_date=finish_date
        )
        
        if success:
            successful_imports += 1
            
            # Получение информации о загруженных свечах
            candles_data = loader.get_candles(symbol, timeframe, limit=1)
            if candles_data:
                candle_count = candles_data.get('count', 0)
                total_candles += candle_count
                print(f"  📈 Загружено {candle_count:,} свечей")
        else:
            failed_imports += 1
        
        # Небольшая пауза между запросами
        time.sleep(0.1)
    
    # Итоговая статистика
    end_time = time.time()
    duration = end_time - start_time
    
    print("\n" + "=" * 50)
    print("📊 ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 50)
    print(f"✅ Успешно импортировано: {successful_imports}")
    print(f"❌ Ошибок импорта: {failed_imports}")
    print(f"📈 Всего свечей: {total_candles:,}")
    print(f"⏱️  Время выполнения: {duration:.2f} секунд")
    print(f"⚡ Скорость: {successful_imports/duration:.2f} символов/сек")
    
    if not preview_only:
        print(f"\n🎉 Данные готовы для бэктестинга!")
        print(f"Используйте exchange: 'custom' в конфигурации бэктеста")


def load_specific_symbols(symbols: List[str], timeframe: str = "1m"):
    """Загрузить конкретные символы"""
    print(f"🎯 Загружаем конкретные символы: {symbols}")
    
    loader = CSVDataLoader(BASE_URL, AUTHORIZATION)
    
    for symbol in symbols:
        print(f"\n📊 Загружаем {symbol}...")
        
        # Проверяем доступность символа
        available_symbols = loader.get_available_symbols()
        if symbol not in available_symbols:
            print(f"❌ Символ {symbol} не найден в доступных")
            continue
        
        # Импортируем
        success = loader.import_symbol(symbol, timeframe, "custom")
        if success:
            print(f"✅ {symbol} загружен успешно")
        else:
            print(f"❌ Ошибка загрузки {symbol}")


#%%
# Основные функции для использования

def quick_preview():
    """Быстрый предварительный просмотр данных"""
    print("🔍 Быстрый предварительный просмотр...")
    load_all_data(preview_only=True, max_symbols=5)

def load_sample_data():
    """Загрузить образец данных (первые 10 символов)"""
    print("📦 Загружаем образец данных...")
    load_all_data(max_symbols=10)

def load_all_data_full():
    """Загрузить все доступные данные"""
    print("🌍 Загружаем все доступные данные...")
    load_all_data()

def load_custom_date_range():
    """Загрузить данные за определенный период"""
    print("📅 Загружаем данные за определенный период...")
    load_all_data(
        start_date="2023-01-01",
        finish_date="2023-12-31"
    )

#%%
# Примеры использования:

if __name__ == "__main__":
    # Выберите один из вариантов:
    
    # 1. Быстрый предварительный просмотр
    # quick_preview()
    
    # 2. Загрузить образец данных
    # load_sample_data()
    
    # 3. Загрузить все данные
    # load_all_data_full()
    
    # 4. Загрузить конкретные символы
    # load_specific_symbols(["ACH", "BTC", "ETH"])
    
    # 5. Загрузить данные за период
    # load_custom_date_range()
    
    # По умолчанию - быстрый предварительный просмотр
    quick_preview()
