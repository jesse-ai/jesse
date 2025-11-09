#!/usr/bin/env python3
"""
Jesse Research API ile Backtest
CSV verisini kullanarak doğrudan backtest yapar (veritabanı import gerektirmez)
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime

# Add strategies path to Python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STRATEGIES_DIR = os.path.join(CURRENT_DIR, 'strategies')
if STRATEGIES_DIR not in sys.path:
    sys.path.insert(0, STRATEGIES_DIR)

# Set Jesse config for strategies location
os.environ['JESSE_STRATEGIES_PATH'] = STRATEGIES_DIR

# Jesse imports
from jesse import research
from jesse.config import config, reset_config
from jesse.routes import router
from jesse.store import store

# Import strategy class directly
from FractalGeneticOptimization import FractalGeneticStrategy


def load_candles_from_csv(csv_file: str, start_date: str, end_date: str):
    """CSV'den Jesse formatında candle yükle"""
    print(f"📂 CSV yükleniyor: {csv_file}")
    df = pd.read_csv(csv_file)

    # Tarih filtresi
    start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
    end_ts = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000)

    df = df[(df['timestamp'] >= start_ts) & (df['timestamp'] <= end_ts)]

    print(f"✅ {len(df)} candle yüklendi")
    print(f"📅 {datetime.fromtimestamp(df['timestamp'].iloc[0]/1000)} - {datetime.fromtimestamp(df['timestamp'].iloc[-1]/1000)}")

    # Jesse formatına çevir: [timestamp, open, close, high, low, volume]
    candles = np.column_stack([
        df['timestamp'].values,
        df['open'].values,
        df['close'].values,
        df['high'].values,
        df['low'].values,
        df['volume'].values,
    ])

    return candles


def run_backtest(
    csv_file: str,
    start_date: str,
    end_date: str,
    exchange: str = 'Binance',
    symbol: str = 'BTC-USDT',
    timeframe: str = '15m',
    strategy: str = 'FractalGeneticOptimization',
    starting_balance: int = 10000,
):
    """Jesse Research API ile backtest çalıştır"""

    print("=" * 80)
    print("🚀 JESSE FRACTAL GENETIC STRATEGY BACKTEST")
    print("=" * 80)

    print(f"\n⚙️  Konfigürasyon:")
    print(f"   Exchange: {exchange}")
    print(f"   Pair: {symbol}")
    print(f"   Timeframe: {timeframe}")
    print(f"   Strategy: {strategy}")
    print(f"   Başlangıç Sermayesi: ${starting_balance:,}")
    print(f"   Tarih: {start_date} → {end_date}")

    # Candles yükle
    print(f"\n" + "=" * 80)
    candles = load_candles_from_csv(csv_file, start_date, end_date)

    if len(candles) < 1000:
        print(f"⚠️  Yetersiz veri! En az 1000 candle gerekli, {len(candles)} var.")
        return None

    # ÖNEMLİ: Jesse research.backtest() sadece 1m candle kabul ediyor
    # Ancak bizim 15m verimiz var. Çözüm: Her 15m candle'ı 15 adet 1m candle olarak genişletelim
    print(f"\n🔄 15m candles'ları 1m formatına genişletiliyor...")
    print(f"   (Her 15m candle → 15 adet 1m candle, aynı OHLC değerleriyle)")

    expanded_candles = []
    for candle in candles:
        timestamp = candle[0]
        open_price = candle[1]
        close_price = candle[2]
        high_price = candle[3]
        low_price = candle[4]
        volume = candle[5] / 15  # Volume'u 15'e böl

        # Her 15m candle için 15 adet 1m candle oluştur
        for i in range(15):
            minute_timestamp = timestamp + (i * 60 * 1000)  # Her dakika 60000 ms
            expanded_candles.append([
                minute_timestamp,
                open_price,
                close_price,
                high_price,
                low_price,
                volume
            ])

    expanded_candles = np.array(expanded_candles)
    print(f"   ✅ {len(candles)} candle → {len(expanded_candles)} candle (1m)")

    # Route yapılandırması - 15m timeframe kullan
    # Jesse strateji adını string olarak bekliyor (klasör adı)
    routes_config = [
        {'exchange': exchange, 'strategy': strategy, 'symbol': symbol, 'timeframe': timeframe}
    ]

    # Data routes (multi-timeframe için) - boş bırak, strateji get_timeframe_candles ile çekecek
    data_routes = []

    print(f"\n🔧 Jesse Research API hazırlanıyor...")
    print(f"   Ana route: {exchange} {symbol} {timeframe}")
    print(f"   1m candles: {len(expanded_candles):,}")

    # Jesse candles format (1m candles gerekli!)
    jesse_candles = {
        f"{exchange}-{symbol}": {
            'exchange': exchange,
            'symbol': symbol,
            'candles': expanded_candles  # 1m candles kullan
        }
    }

    # Backtest parametreleri
    backtest_config = {
        'starting_balance': starting_balance,
        'fee': 0.001,  # %0.1
        'type': 'futures',  # 'spot' veya 'futures'
        'futures_leverage': 1,
        'futures_leverage_mode': 'cross',
        'exchange': exchange,
        'warm_up_candles': 500,  # İndikatörler için
    }

    print(f"\n" + "=" * 80)
    print(f"⏳ Backtest başlatılıyor...")
    print(f"   Bu işlem birkaç dakika sürebilir...")
    print(f"=" * 80 + "\n")

    try:
        # Jesse research.backtest() çağrısı
        result = research.backtest(
            config=backtest_config,
            routes=routes_config,
            data_routes=data_routes,
            candles=jesse_candles,
            generate_csv=True,
            generate_json=True,
            generate_tradingview=False,
        )

        # Sonuçları göster
        print_results(result, start_date, end_date)

        # CSV ve JSON kaydet
        save_results(result, strategy)

        return result

    except Exception as e:
        print(f"\n❌ Backtest hatası:")
        print(f"   {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def print_results(result, start_date, end_date):
    """Sonuçları ekrana yazdır"""
    print("\n" + "=" * 80)
    print("📊 BACKTEST SONUÇLARI")
    print("=" * 80)

    if not result or 'metrics' not in result:
        print("⚠️  Sonuç alınamadı")
        return

    m = result['metrics']

    print(f"\n💰 PERFORMANS")
    print(f"   Başlangıç Sermayesi:  ${m.get('starting_balance', 0):>12,.2f}")
    print(f"   Bitiş Sermayesi:      ${m.get('finishing_balance', 0):>12,.2f}")
    print(f"   Net Kar:              ${m.get('net_profit', 0):>12,.2f}")
    print(f"   Net Kar %:            {m.get('net_profit_percentage', 0):>12.2f}%")

    print(f"\n📈 İŞLEM İSTATİSTİKLERİ")
    print(f"   Toplam İşlem:         {m.get('total', 0):>12}")
    print(f"   Kazanan İşlem:        {m.get('total_winning_trades', 0):>12}")
    print(f"   Kaybeden İşlem:       {m.get('total_losing_trades', 0):>12}")
    print(f"   Kazanma Oranı:        {m.get('win_rate', 0):>12.2f}%")

    print(f"\n💵 KAR/ZARAR ANALİZİ")
    print(f"   Brüt Kar:             ${m.get('gross_profit', 0):>12,.2f}")
    print(f"   Brüt Zarar:           ${m.get('gross_loss', 0):>12,.2f}")
    print(f"   Ort. Kazanan İşlem:   ${m.get('average_win', 0):>12,.2f}")
    print(f"   Ort. Kaybeden İşlem:  ${m.get('average_loss', 0):>12,.2f}")
    print(f"   En Büyük Kazanç:      ${m.get('largest_winning_trade', 0):>12,.2f}")
    print(f"   En Büyük Kayıp:       ${m.get('largest_losing_trade', 0):>12,.2f}")

    print(f"\n📉 RİSK METRİKLERİ")
    print(f"   Max Drawdown:         ${m.get('max_drawdown', 0):>12,.2f}")
    print(f"   Max Drawdown %:       {m.get('max_drawdown_percentage', 0):>12.2f}%")
    print(f"   Ardışık Kazanç:       {m.get('max_consecutive_winning_trades', 0):>12}")
    print(f"   Ardışık Kayıp:        {m.get('max_consecutive_losing_trades', 0):>12}")

    print(f"\n📊 ORANLAR")
    print(f"   Sharpe Ratio:         {m.get('sharpe_ratio', 0):>12.2f}")
    print(f"   Sortino Ratio:        {m.get('sortino_ratio', 0):>12.2f}")
    print(f"   Calmar Ratio:         {m.get('calmar_ratio', 0):>12.2f}")
    print(f"   Profit Factor:        {m.get('profit_factor', 0):>12.2f}")
    print(f"   Serenity Index:       {m.get('serenity_index', 0):>12.2f}")

    print(f"\n⏱️  SÜRE")
    print(f"   Backtest Dönemi:      {start_date} → {end_date}")
    print(f"   Toplam Gün:           {m.get('total_days', 0):>12}")


def save_results(result, strategy_name):
    """Sonuçları dosyaya kaydet"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # JSON
    json_file = f"backtest_{strategy_name}_{timestamp}.json"
    import json
    with open(json_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n💾 JSON kaydedildi: {json_file}")

    # CSV (trades)
    if 'trades' in result and result['trades']:
        csv_file = f"backtest_{strategy_name}_{timestamp}_trades.csv"
        trades_df = pd.DataFrame(result['trades'])
        trades_df.to_csv(csv_file, index=False)
        print(f"💾 Trades CSV kaydedildi: {csv_file}")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("Jesse Fractal Genetic Strategy - Backtest")
    print("=" * 80)

    # Parametreler
    CSV_FILE = "btc_15m_jesse_format.csv"

    # Test periyodu (2 yıl - hızlı test için)
    START_DATE = "2023-01-01"
    END_DATE = "2025-01-01"

    # Daha uzun test için:
    # START_DATE = "2020-01-01"
    # END_DATE = "2025-01-01"

    print(f"\n💡 Not: Tarih aralığını değiştirmek için scripti düzenleyin")
    print(f"   Mevcut: {START_DATE} - {END_DATE}\n")

    result = run_backtest(
        csv_file=CSV_FILE,
        start_date=START_DATE,
        end_date=END_DATE,
        starting_balance=10000
    )

    if result:
        print("\n" + "=" * 80)
        print("✅ BACKTEST TAMAMLANDI!")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("❌ BACKTEST BAŞARISIZ!")
        print("=" * 80)
        sys.exit(1)
