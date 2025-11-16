#!/usr/bin/env python3
"""
Batch CSV Data Loader with Progress Bar
Пакетная загрузка CSV данных с прогресс-баром и детальной статистикой.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse'))

from jesse.research.external_data.csv_ticks_to_db import CSVDataLoader, BASE_URL, AUTHORIZATION
import time
from tqdm import tqdm
import json
from datetime import datetime

class BatchCSVLoader:
    """Пакетный загрузчик CSV данных с прогресс-баром"""
    
    def __init__(self):
        self.loader = CSVDataLoader(BASE_URL, AUTHORIZATION)
        self.stats = {
            'total_symbols': 0,
            'successful': 0,
            'failed': 0,
            'total_candles': 0,
            'start_time': None,
            'end_time': None,
            'errors': []
        }
    
    def load_with_progress(self, 
                          timeframe: str = "1m",
                          max_symbols: int = None,
                          start_date: str = None,
                          finish_date: str = None,
                          batch_size: int = 10,
                          delay: float = 0.1):
        """
        Загрузить данные с прогресс-баром
        
        Args:
            timeframe: Таймфрейм
            max_symbols: Максимальное количество символов
            start_date: Начальная дата
            finish_date: Конечная дата
            batch_size: Размер батча для обработки
            delay: Задержка между запросами
        """
        
        print("🚀 Пакетная загрузка CSV данных в Jesse...")
        print(f"📊 Таймфрейм: {timeframe}")
        if start_date:
            print(f"📅 Начальная дата: {start_date}")
        if finish_date:
            print(f"📅 Конечная дата: {finish_date}")
        print("-" * 60)
        
        # Получение списка символов
        print("📋 Получаем список символов...")
        symbols = self.loader.get_available_symbols()
        
        if not symbols:
            print("❌ Символы не найдены!")
            return
        
        # Ограничение количества
        if max_symbols and max_symbols < len(symbols):
            symbols = symbols[:max_symbols]
            print(f"🔄 Ограничиваем до {max_symbols} символов")
        
        self.stats['total_symbols'] = len(symbols)
        self.stats['start_time'] = time.time()
        
        print(f"✅ Найдено {len(symbols)} символов для загрузки")
        print(f"📦 Размер батча: {batch_size}")
        print()
        
        # Создание прогресс-бара
        with tqdm(total=len(symbols), desc="Загрузка данных", unit="символ") as pbar:
            for i in range(0, len(symbols), batch_size):
                batch = symbols[i:i + batch_size]
                
                # Обработка батча
                self._process_batch(batch, timeframe, start_date, finish_date, delay)
                
                # Обновление прогресс-бара
                pbar.update(len(batch))
                
                # Обновление описания
                pbar.set_postfix({
                    'Успешно': self.stats['successful'],
                    'Ошибок': self.stats['failed'],
                    'Свечей': f"{self.stats['total_candles']:,}"
                })
        
        # Завершение
        self.stats['end_time'] = time.time()
        self._print_final_stats()
    
    def _process_batch(self, batch, timeframe, start_date, finish_date, delay):
        """Обработать батч символов"""
        for symbol in batch:
            try:
                # Импорт символа
                success = self.loader.import_symbol(
                    symbol=symbol,
                    timeframe=timeframe,
                    exchange="custom",
                    start_date=start_date,
                    finish_date=finish_date
                )
                
                if success:
                    self.stats['successful'] += 1
                    
                    # Получение количества свечей
                    candles_data = self.loader.get_candles(symbol, timeframe, limit=1)
                    if candles_data:
                        candle_count = candles_data.get('count', 0)
                        self.stats['total_candles'] += candle_count
                else:
                    self.stats['failed'] += 1
                    self.stats['errors'].append(f"Ошибка импорта {symbol}")
                
                # Задержка между запросами
                if delay > 0:
                    time.sleep(delay)
                    
            except Exception as e:
                self.stats['failed'] += 1
                self.stats['errors'].append(f"Исключение для {symbol}: {str(e)}")
    
    def _print_final_stats(self):
        """Вывести итоговую статистику"""
        duration = self.stats['end_time'] - self.stats['start_time']
        
        print("\n" + "=" * 60)
        print("📊 ИТОГОВАЯ СТАТИСТИКА ЗАГРУЗКИ")
        print("=" * 60)
        print(f"📈 Всего символов: {self.stats['total_symbols']}")
        print(f"✅ Успешно загружено: {self.stats['successful']}")
        print(f"❌ Ошибок: {self.stats['failed']}")
        print(f"📊 Всего свечей: {self.stats['total_candles']:,}")
        print(f"⏱️  Время выполнения: {duration:.2f} секунд")
        
        if self.stats['successful'] > 0:
            print(f"⚡ Скорость: {self.stats['successful']/duration:.2f} символов/сек")
            print(f"📈 Среднее свечей на символ: {self.stats['total_candles']/self.stats['successful']:,.0f}")
        
        # Вывод ошибок если есть
        if self.stats['errors']:
            print(f"\n❌ Ошибки ({len(self.stats['errors'])}):")
            for error in self.stats['errors'][:10]:  # Показываем первые 10
                print(f"  • {error}")
            if len(self.stats['errors']) > 10:
                print(f"  ... и еще {len(self.stats['errors']) - 10} ошибок")
        
        # Сохранение статистики
        self._save_stats()
        
        print(f"\n🎉 Загрузка завершена!")
        print(f"💾 Статистика сохранена в batch_loader_stats.json")
    
    def _save_stats(self):
        """Сохранить статистику в файл"""
        stats_data = {
            'timestamp': datetime.now().isoformat(),
            'stats': self.stats,
            'summary': {
                'success_rate': self.stats['successful'] / self.stats['total_symbols'] * 100,
                'avg_candles_per_symbol': self.stats['total_candles'] / max(self.stats['successful'], 1),
                'duration_seconds': self.stats['end_time'] - self.stats['start_time']
            }
        }
        
        with open('batch_loader_stats.json', 'w', encoding='utf-8') as f:
            json.dump(stats_data, f, indent=2, ensure_ascii=False)


def main():
    """Основная функция"""
    print("🔧 Пакетный загрузчик CSV данных")
    print("=" * 40)
    
    # Создание загрузчика
    loader = BatchCSVLoader()
    
    # Настройки загрузки
    settings = {
        'timeframe': '1m',
        'max_symbols': 50,  # Ограничиваем для тестирования
        'start_date': None,  # Загружаем все данные
        'finish_date': None,
        'batch_size': 5,     # Небольшие батчи
        'delay': 0.2         # Задержка между запросами
    }
    
    print("⚙️  Настройки:")
    for key, value in settings.items():
        print(f"  {key}: {value}")
    print()
    
    # Подтверждение
    response = input("Продолжить загрузку? (y/N): ").strip().lower()
    if response not in ['y', 'yes', 'да']:
        print("❌ Загрузка отменена")
        return
    
    # Запуск загрузки
    try:
        loader.load_with_progress(**settings)
    except KeyboardInterrupt:
        print("\n⏹️  Загрузка прервана пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")


if __name__ == "__main__":
    main()
