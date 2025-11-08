# Kullanım Kılavuzu - Fraktal Genetik Optimizasyon Stratejisi

## 🚀 Hızlı Başlangıç

### Adım 1: Stratejiyi Kopyalama

Strateji zaten Jesse proje klasörünüzde `strategies/FractalGeneticOptimization/` altında bulunmaktadır.

### Adım 2: Config Dosyasını Düzenleme

`config.py` dosyanızı düzenleyin:

```python
from jesse.strategies import FractalGeneticStrategy

# Trading routes
routes = [
    {
        'exchange': 'Binance Futures',
        'symbol': 'BTC-USDT',
        'timeframe': '5m',
        'strategy': 'FractalGeneticStrategy'
    },
]

# Extra candles (çoklu zaman dilimi için gerekli)
extra_candles = [
    ('Binance Futures', 'BTC-USDT', '1D'),
    ('Binance Futures', 'BTC-USDT', '4h'),
    ('Binance Futures', 'BTC-USDT', '1h'),
    ('Binance Futures', 'BTC-USDT', '30m'),
    ('Binance Futures', 'BTC-USDT', '15m'),
]
```

### Adım 3: İlk Backtest

```bash
# Basit backtest
jesse backtest 2023-01-01 2023-12-31

# Chart ile backtest
jesse backtest 2023-01-01 2023-12-31 --chart

# Debug modu
jesse backtest 2023-01-01 2023-12-31 --debug
```

## 📊 Backtest Senaryoları

### Senaryo 1: Temel Backtest (Default Parametreler)

```bash
jesse backtest 2023-01-01 2023-12-31 --chart
```

Bu komut default hyperparameter değerleriyle çalışır. İlk test için idealdir.

### Senaryo 2: Farklı Zaman Periyotları

```bash
# Kısa dönem (1 ay)
jesse backtest 2023-11-01 2023-12-01

# Orta dönem (6 ay)
jesse backtest 2023-06-01 2023-12-01

# Uzun dönem (2 yıl)
jesse backtest 2022-01-01 2023-12-31
```

### Senaryo 3: Farklı Kripto Paralar

`config.py` içinde symbol değiştirin:

```python
routes = [
    {
        'exchange': 'Binance Futures',
        'symbol': 'ETH-USDT',  # BTC yerine ETH
        'timeframe': '5m',
        'strategy': 'FractalGeneticStrategy'
    },
]
```

## 🧬 Genetik Algoritma Optimizasyonu

### Temel Optimizasyon

```bash
jesse optimize 2023-01-01 2023-06-30 \
  --cpu 8 \
  --iterations 50 \
  --population-size 30
```

### İleri Seviye Optimizasyon

```bash
jesse optimize 2023-01-01 2023-06-30 \
  --cpu $(nproc) \                    # Tüm CPU çekirdekleri
  --iterations 100 \                  # Daha fazla iterasyon
  --population-size 50 \              # Daha büyük populasyon
  --solution-len 30 \                 # Daha fazla parametre optimize et
  --charset decimal                   # Ondalık sayı charset'i
```

### Özel Fitness Function

```bash
# Sharpe ratio optimize et
jesse optimize 2023-01-01 2023-06-30 \
  --optimal-total sharpe-ratio

# Calmar ratio optimize et
jesse optimize 2023-01-01 2023-06-30 \
  --optimal-total calmar-ratio
```

### Walk-Forward Analysis

```bash
# Training period: 6 ay
# Testing period: 2 ay
jesse optimize 2023-01-01 2023-06-30 \
  --iterations 50 \
  --cpu 8

# Sonuçları test et
jesse backtest 2023-07-01 2023-09-01 --dna "YOUR_DNA_STRING"
```

## 🔧 Parametre Ayarlama

### Manuel Parametre Testi

DNA string kullanarak belirli parametreleri test edebilirsiniz:

```bash
jesse backtest 2023-01-01 2023-12-31 \
  --dna "5.2,4.8,4.1,3.6,3.1,2.9,2.6,2.3,2.1,1.6,1.3,1.1,0.9,14,2.2,12,26,9,2.6,20,2.1,1.6,14,3,1.7,14,1.2,2.1,2.2,3.1,0.02,0.52,0.48,1,0.23"
```

### Parametrelerin Anlamı

DNA string'deki sıra (ilk 35 parametre):

```
1-13:  Zaman dilimi ağırlıkları (3M, 1M, 1W, 1D, 12h, 8h, 4h, 2h, 1h, 30m, 15m, 10m, 5m)
14:    RSI period
15:    RSI weight
16-18: MACD fast, slow, signal
19:    MACD weight
20:    BB period
21:    BB std
22:    BB weight
23:    Stoch K
24:    Stoch D
25:    Stoch weight
26:    ATR period
27:    ATR weight
28:    HA weight
29:    Stop-loss ATR multiplier
30:    Take-profit ATR multiplier
31:    Risk per trade
32:    Min score long
33:    Min score short
34:    Require trend alignment (0 veya 1)
35:    Min trend strength
```

## 📈 Performans Analizi

### Metrikleri Anlamak

Backtest sonunda şu metrikler gösterilir:

```
Total Closed Trades: 150
Total Net Profit: $5,420.50
Starting => Finishing Balance: $10,000 => $15,420.50
Total Open Trades: 0
Open PL: $0
Total Paid Fees: $543.20
Max Drawdown: -12.4%
Annual Return: 54.2%
Sharpe Ratio: 1.82
Calmar Ratio: 4.37
Win Rate: 58%
Profit Factor: 1.85
```

**Önemli Metrikler**:

- **Sharpe Ratio > 1.5**: Mükemmel
- **Sharpe Ratio > 1.0**: İyi
- **Sharpe Ratio < 1.0**: Zayıf

- **Calmar Ratio > 3.0**: Mükemmel
- **Calmar Ratio > 1.5**: İyi

- **Profit Factor > 2.0**: Mükemmel
- **Profit Factor > 1.5**: İyi
- **Profit Factor < 1.2**: Zayıf

- **Win Rate %**: Önemli ama tek başına yeterli değil

### Chart Analizi

```bash
jesse backtest 2023-01-01 2023-12-31 --chart
```

Chart açıldığında:
- Yeşil oklar: Long entry
- Kırmızı oklar: Short entry
- Mavi/kırmızı çizgiler: Stop-loss ve take-profit seviyeleri
- Watch list: Fractal Score, Indicator Score, Combined Score

## 🎯 Optimizasyon Stratejileri

### Strateji 1: Aşamalı Optimizasyon

```bash
# Aşama 1: Risk parametrelerini optimize et (kısa süre)
jesse optimize 2023-01-01 2023-02-01 \
  --iterations 30 \
  --cpu 4

# Aşama 2: En iyi DNA'yı al, daha uzun dönemde test et
jesse backtest 2023-01-01 2023-06-01 --dna "BEST_DNA_FROM_STEP_1"

# Aşama 3: İndikatör parametrelerini fine-tune et
jesse optimize 2023-01-01 2023-06-01 \
  --iterations 50 \
  --cpu 8
```

### Strateji 2: Multi-Symbol Optimizasyon

Her sembol için ayrı optimize edin:

```bash
# BTC için
jesse optimize 2023-01-01 2023-06-30 --cpu 8

# ETH için
# (config.py'de symbol'u değiştirin)
jesse optimize 2023-01-01 2023-06-30 --cpu 8

# SOL için
jesse optimize 2023-01-01 2023-06-30 --cpu 8
```

### Strateji 3: Farklı Market Koşulları

```bash
# Bull market (Yükselen piyasa)
jesse optimize 2023-01-01 2023-04-30

# Bear market (Düşen piyasa)
jesse optimize 2022-05-01 2022-12-31

# Sideways market (Yatay piyasa)
jesse optimize 2023-08-01 2023-10-31
```

## 🔍 Debugging ve Sorun Giderme

### Debug Modu

```bash
jesse backtest 2023-01-01 2023-02-01 --debug
```

Debug modunda:
- Her işlem detaylı loglanır
- Fractal skorlar gösterilir
- Indicator değerleri çıktılanır

### Log Analizi

Logları incelemek için:

```bash
# Son 100 satır
tail -n 100 storage/logs/backtest.log

# Canlı takip
tail -f storage/logs/backtest.log

# Sadece hataları göster
grep ERROR storage/logs/backtest.log
```

### Yaygın Hatalar ve Çözümleri

#### Hata 1: "Insufficient data"

**Neden**: Yeterli historical veri yok.

**Çözüm**:
```bash
jesse import-candles "Binance Futures" BTC-USDT 2020-01-01
```

#### Hata 2: "Timeframe not found"

**Neden**: `extra_candles` içinde timeframe tanımlı değil.

**Çözüm**: `config.py` içinde timeframe'i ekleyin:
```python
extra_candles = [
    ('Binance Futures', 'BTC-USDT', '1D'),
    ('Binance Futures', 'BTC-USDT', '4h'),  # Ekleyin
]
```

#### Hata 3: "No trades"

**Neden**: Parametreler çok katı, sinyal üretilemiyor.

**Çözüm**:
- `min_score_long` ve `min_score_short` değerlerini düşürün
- `require_trend_alignment` = False yapın
- Daha kısa timeframe deneyin

## 📊 Sonuç Raporları

### JSON Export

```bash
jesse backtest 2023-01-01 2023-12-31 --json > results.json
```

### CSV Export

```bash
# Trades listesi
jesse backtest 2023-01-01 2023-12-31 --csv > trades.csv
```

### Özel Rapor

Python script ile özel analiz:

```python
import json

with open('results.json', 'r') as f:
    results = json.load(f)

print(f"Sharpe: {results['sharpe_ratio']}")
print(f"Max DD: {results['max_drawdown']}%")
print(f"Win Rate: {results['win_rate']}%")
```

## 🚦 Live Trading'e Geçiş

### Adım 1: Paper Trading

```bash
# Paper trading modunda test
jesse run --paper

# Bir süre çalıştırın (en az 1 hafta)
# Performansı izleyin
```

### Adım 2: Küçük Pozisyonlarla Başlama

`config.py`:
```python
# Risk'i düşürün
'risk_per_trade': 0.01  # %1
```

### Adım 3: Canlı İzleme

```bash
# Telegram notification aktif edin
jesse run --telegram
```

## ⚙️ İleri Seviye Konfigürasyon

### Multi-Route Trading

```python
routes = [
    {
        'exchange': 'Binance Futures',
        'symbol': 'BTC-USDT',
        'timeframe': '5m',
        'strategy': 'FractalGeneticStrategy'
    },
    {
        'exchange': 'Binance Futures',
        'symbol': 'ETH-USDT',
        'timeframe': '5m',
        'strategy': 'FractalGeneticStrategy'
    },
]

extra_candles = [
    # BTC için
    ('Binance Futures', 'BTC-USDT', '1D'),
    ('Binance Futures', 'BTC-USDT', '4h'),
    ('Binance Futures', 'BTC-USDT', '1h'),

    # ETH için
    ('Binance Futures', 'ETH-USDT', '1D'),
    ('Binance Futures', 'ETH-USDT', '4h'),
    ('Binance Futures', 'ETH-USDT', '1h'),
]
```

### Custom Hyperparameters

Strateji dosyasını fork edip custom parametreler ekleyebilirsiniz.

## 📚 Ek Kaynaklar

- [Jesse Discord Community](https://discord.gg/jesse)
- [Jesse GitHub](https://github.com/jesse-ai/jesse)
- [Video Tutorial](https://www.youtube.com/c/JesseTrade)

## 💡 İpuçları

1. **Sabırlı Olun**: Optimizasyon saatler sürebilir
2. **Overfitting'den Kaçının**: Out-of-sample test yapın
3. **Commission Ekleyin**: Gerçekçi sonuçlar için
4. **Slippage Ayarlayın**: Özellikle düşük likidite pairler için
5. **Risk Yönetimi**: Max %2 risk per trade
6. **Diversification**: Tek coin'e bağlı kalmayın

---

**Destek için**: GitHub Issues veya Jesse Discord

