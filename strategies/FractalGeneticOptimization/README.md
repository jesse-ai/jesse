# Fraktal Genetik Optimizasyon Stratejisi

## 📊 Genel Bakış

Bu strateji, piyasanın fraktal doğasını temel alan çok zaman dilimli (multi-timeframe) bir al-sat stratejisidir. Jesse trading framework'ü üzerine inşa edilmiştir ve Genetik Algoritma (GA) ile optimize edilebilir.

### 🎯 Temel Özellikler

- **Fraktal Mum Analizi**: Her zaman diliminde mevcut mum ile bir önceki mum arasındaki 4'lü ilişkiyi analiz eder
- **Çoklu Zaman Dilimi**: 13 farklı zaman diliminden veri analiz eder (3ay - 5m arası)
- **Klasik İndikatörler**: RSI, MACD, Bollinger Bands, Stochastic, ATR, Heiken Ashi
- **Genetik Algoritma**: 40+ parametre ile optimize edilebilir
- **Dinamik Risk Yönetimi**: ATR tabanlı stop-loss ve take-profit

## 🧬 Strateji Mimarisi

### 1. Fraktal Mum İlişkileri (4 Durum)

Stratejinin kalbi, her zaman dilimindeki mumların birbirleriyle olan ilişkisidir:

| Durum | Açıklama | Piyasa Yorumu |
|-------|----------|---------------|
| **HHHL** | High > Prev_High VE Low > Prev_Low | Yükselen Güç (Bullish) |
| **HLLH** | High < Prev_High VE Low < Prev_Low | Düşen Güç (Bearish) |
| **INSIDE** | High < Prev_High VE Low > Prev_Low | Kararsızlık/Daralma |
| **OUTSIDE** | High > Prev_High VE Low < Prev_Low | Volatilite/Genişleme |

### 2. Çok Zamanlı Analiz

Strateji aşağıdaki tüm zaman dilimlerini analiz eder:

```
Büyük Resim:   3M → 1M → 1W → 1D
Orta Vadeli:   12h → 8h → 4h → 2h → 1h
Kısa Vadeli:   30m → 15m → 10m → 5m (işlem zaman dilimi)
```

Her zaman dilimi için:
- Fraktal durum hesaplanır
- Ağırlık katsayısı uygulanır (büyük zaman dilimleri daha ağırdır)
- Toplam skor hesaplanır

### 3. Teknik İndikatörler

Her indikatör kendi ağırlığına sahiptir ve toplam skora katkıda bulunur:

#### RSI (Relative Strength Index)
- Aşırı alım/satım bölgelerini tespit eder
- Parametre: Period (7-21, default: 14)
- Ağırlık: 0-5 (default: 2.0)

#### MACD (Moving Average Convergence Divergence)
- Trend yönünü ve momentumu gösterir
- Parametreler: Fast (8-16), Slow (20-32), Signal (7-12)
- Ağırlık: 0-5 (default: 2.5)

#### Bollinger Bands
- Volatilite ve fiyat pozisyonunu ölçer
- Parametreler: Period (15-25), Std Dev (1.5-3.0)
- Ağırlık: 0-5 (default: 1.5)

#### Stochastic Oscillator
- Fiyatın menzildeki pozisyonunu gösterir
- Parametreler: %K (10-21), %D (2-5)
- Ağırlık: 0-5 (default: 1.5)

#### ATR (Average True Range)
- Volatilite ölçümü ve risk yönetimi için kullanılır
- Parametre: Period (10-21, default: 14)
- Stop-Loss ve Take-Profit hesaplamalarında kullanılır

#### Heiken Ashi
- Trend filtreleme ve gürültü azaltma
- Mum rengi ve gövde boyutu analiz edilir
- Ağırlık: 0-5 (default: 2.0)

## 🧪 Genetik Algoritma Optimizasyonu

Strateji 40+ hyperparameter ile optimize edilebilir:

### Parametre Kategorileri

1. **Zaman Dilimi Ağırlıkları** (13 parametre)
   - Her zaman dilimi için özel ağırlık
   - Büyük zaman dilimlerine daha fazla önem verilir

2. **İndikatör Parametreleri** (12 parametre)
   - Her indikatör için özel ayarlar
   - Period, multiplier gibi değerler

3. **İndikatör Ağırlıkları** (6 parametre)
   - Her indikatörün sinyal üretmedeki etkisi

4. **Risk Yönetimi** (3 parametre)
   - Stop-loss ATR multiplier: 1.0-4.0
   - Take-profit ATR multiplier: 1.5-6.0
   - Risk per trade: 0.01-0.05 (1%-5%)

5. **Sinyal Eşikleri** (2 parametre)
   - Minimum long score: 0.3-0.8
   - Minimum short score: 0.3-0.8

### Fitness Function

Genetik algoritma şu metrikleri optimize eder:
- **Sharpe Ratio**: Risk-adjusted return
- **Calmar Ratio**: Return/Max Drawdown
- **Profit Factor**: Gross Profit/Gross Loss

## 📁 Dosya Yapısı

```
FractalGeneticOptimization/
├── __init__.py                    # Strateji export
├── FractalGeneticStrategy.py      # Ana strateji sınıfı
├── fractal_analyzer.py            # Fraktal analiz modülü
├── indicator_manager.py           # İndikatör yönetimi
└── README.md                      # Bu dosya
```

## 🚀 Kullanım

### 1. Backtest

```bash
jesse backtest '2022-01-01' '2023-01-01' --chart
```

### 2. Genetik Algoritma Optimizasyonu

```bash
jesse optimize '2022-01-01' '2023-01-01' \
  --cpu 8 \
  --iterations 100 \
  --population-size 50 \
  --solution-len 20
```

### 3. Live Trading

```bash
jesse run
```

## ⚙️ Konfigürasyon

`config.py` dosyanızda routes tanımlaması:

```python
from jesse.strategies import FractalGeneticStrategy

routes = [
    {
        'exchange': 'Binance Futures',
        'symbol': 'BTC-USDT',
        'timeframe': '5m',
        'strategy': 'FractalGeneticStrategy'
    },
]
```

### Çoklu Zaman Dilimi Ayarları

Strateji otomatik olarak aşağıdaki zaman dilimlerini kullanır. `config.py` içinde `extra_candles` tanımlamanız gerekir:

```python
extra_candles = [
    # Exchange, symbol, timeframe
    ('Binance Futures', 'BTC-USDT', '1D'),
    ('Binance Futures', 'BTC-USDT', '4h'),
    ('Binance Futures', 'BTC-USDT', '1h'),
    ('Binance Futures', 'BTC-USDT', '15m'),
    # İsteğe bağlı diğer zaman dilimleri:
    # ('Binance Futures', 'BTC-USDT', '1W'),
    # ('Binance Futures', 'BTC-USDT', '12h'),
    # ('Binance Futures', 'BTC-USDT', '30m'),
]
```

## 📊 Skor Hesaplama Mantığı

### 1. Fraktal Skor

```
Fraktal Skor = Σ(Durum_Skoru × Zaman_Dilimi_Ağırlığı) / Σ(Ağırlıklar)

Durum Skorları:
- HHHL (Bullish): +1.0
- HLLH (Bearish): -1.0
- INSIDE/OUTSIDE: 0.0
```

### 2. İndikatör Skoru

Her indikatör kendi skorunu üretir (-1 ile +1 arası):

```
İndikatör Skoru = Σ(İndikatör_Skoru × İndikatör_Ağırlığı) / Σ(Ağırlıklar)
```

### 3. Final Skor

```
Final Skor = (Fraktal Skor + İndikatör Skoru) / 2

Long Sinyali: Final Skor > Minimum_Long_Score
Short Sinyali: Final Skor < -Minimum_Short_Score
```

## 🎯 Sinyal Üretimi

### Long Sinyali Koşulları

1. Combined Score > `min_score_long` (default: 0.5)
2. Eğer `require_trend_alignment` = True ise:
   - Fractal Score > `min_trend_strength`
   - VE Indicator Score > `min_trend_strength`

### Short Sinyali Koşulları

1. Combined Score < -`min_score_short` (default: -0.5)
2. Eğer `require_trend_alignment` = True ise:
   - Fractal Score < -`min_trend_strength`
   - VE Indicator Score < -`min_trend_strength`

## 💰 Risk Yönetimi

### Pozisyon Boyutlandırma

```python
Risk Amount = Balance × Risk_Per_Trade
Position Size = Risk Amount / Stop_Loss_Distance
```

### Stop-Loss

```python
Stop Loss = Entry Price ± (ATR × Stop_Loss_ATR_Multiplier)
```

### Take-Profit

```python
Take Profit = Entry Price ± (ATR × Take_Profit_ATR_Multiplier)
```

## 🔍 Debugging ve İzleme

Strateji önemli metrikleri `self.vars` içinde saklar:

- `fractal_score`: Fraktal analiz skoru
- `indicator_score`: İndikatör skoru
- `combined_score`: Birleşik skor
- `indicators`: Tüm indikatör değerleri
- `atr`: Mevcut ATR değeri
- `entry_price`, `stop_loss_price`, `take_profit_price`

Watch list üzerinden canlı olarak görülebilir.

## 📈 Optimizasyon İpuçları

1. **Küçük Başlayın**: İlk optimizasyonu kısa bir dönemde yapın (1-2 ay)
2. **Population Size**: 30-100 arası optimum
3. **Iterations**: En az 50, tercihen 100+
4. **CPU Kullanımı**: Tüm çekirdeklerinizi kullanın
5. **Walk-Forward Analysis**: Stratejinin geleceğe dönük performansını test edin
6. **Overfitting'den Kaçının**: Validation period kullanın

## ⚠️ Önemli Notlar

1. **Veri Gereksinimleri**: Strateji en az 50 mum gerektirir (büyük zaman dilimleri için daha fazla)
2. **Hesaplama Yoğunluğu**: 13 zaman dilimi + 6 indikatör = yoğun hesaplama
3. **Backtest Süresi**: Büyük veri setlerinde yavaş olabilir
4. **Commission ve Slippage**: Gerçekçi ayarlar kullanın
5. **Timeframe Uygunluğu**: Tüm exchange'ler tüm timeframe'leri desteklemez

## 🔬 İleri Seviye Özellikler

### Gelecek Geliştirmeler

- [ ] Trailing stop-loss implementasyonu
- [ ] Volume analizi ekleme
- [ ] Machine Learning model entegrasyonu
- [ ] Multi-asset correlation analizi
- [ ] Sentiment analysis entegrasyonu
- [ ] Custom fitness function (Multi-objective optimization)

## 📚 Kaynaklar

- [Jesse Documentation](https://docs.jesse.trade/)
- [Genetic Algorithm Optimization](https://docs.jesse.trade/docs/optimize/)
- [Multi-Timeframe Analysis](https://docs.jesse.trade/docs/strategies/api.html#get-candles)

## 📄 Lisans

Bu strateji eğitim amaçlıdır. Gerçek paralarla işlem yapmadan önce kapsamlı backtest ve paper trading yapınız.

## 🤝 Katkıda Bulunma

Stratejiye katkıda bulunmak isterseniz:
1. Fork yapın
2. Feature branch oluşturun
3. Değişikliklerinizi commit edin
4. Pull request açın

---

**Yazan**: Claude AI Assistant
**Framework**: Jesse Trading Framework
**Versiyon**: 1.0.0
**Tarih**: 2025-11-08
