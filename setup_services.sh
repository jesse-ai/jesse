#!/bin/bash
#
# Jesse Trading Bot için Redis ve PostgreSQL Kurulum ve Başlatma Scripti
# Kullanım: sudo bash setup_services.sh
#

set -e  # Hata durumunda dur

echo "=========================================="
echo "Jesse için Servis Kurulumu Başlıyor..."
echo "=========================================="
echo ""

# Sistem güncellemesi (opsiyonel - hızlı olması için yorum satırı)
# echo "1️⃣  Sistem güncellemesi yapılıyor..."
# apt update

# Redis kurulumu
echo "2️⃣  Redis kurulumu kontrol ediliyor..."
if ! command -v redis-server &> /dev/null; then
    echo "   Redis bulunamadı, kuruluyor..."
    apt install -y redis-server
    echo "   ✅ Redis kuruldu"
else
    echo "   ✅ Redis zaten kurulu"
fi

# PostgreSQL kurulumu
echo "3️⃣  PostgreSQL kurulumu kontrol ediliyor..."
if ! command -v psql &> /dev/null; then
    echo "   PostgreSQL bulunamadı, kuruluyor..."
    apt install -y postgresql postgresql-contrib
    echo "   ✅ PostgreSQL kuruldu"
else
    echo "   ✅ PostgreSQL zaten kurulu"
fi

echo ""
echo "=========================================="
echo "Servisler Başlatılıyor..."
echo "=========================================="
echo ""

# Redis başlatma
echo "4️⃣  Redis başlatılıyor..."
systemctl start redis-server || systemctl start redis || redis-server --daemonize yes
systemctl enable redis-server 2>/dev/null || systemctl enable redis 2>/dev/null || true
echo "   ✅ Redis başlatıldı"

# PostgreSQL başlatma
echo "5️⃣  PostgreSQL başlatılıyor..."
systemctl start postgresql
systemctl enable postgresql
echo "   ✅ PostgreSQL başlatıldı"

echo ""
echo "=========================================="
echo "PostgreSQL Veritabanı Yapılandırması"
echo "=========================================="
echo ""

# PostgreSQL kullanıcısı ve veritabanı oluşturma
echo "6️⃣  Jesse için PostgreSQL kullanıcısı ve veritabanı oluşturuluyor..."

# postgres kullanıcısı olarak komutları çalıştır
sudo -u postgres psql -c "SELECT 1 FROM pg_roles WHERE rolname='jesse_user'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE USER jesse_user WITH PASSWORD 'password';"

sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw jesse_db || \
    sudo -u postgres psql -c "CREATE DATABASE jesse_db OWNER jesse_user;"

sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE jesse_db TO jesse_user;"

echo "   ✅ PostgreSQL yapılandırıldı"
echo "      - Kullanıcı: jesse_user"
echo "      - Şifre: password"
echo "      - Veritabanı: jesse_db"

echo ""
echo "=========================================="
echo "Servis Durumları Kontrol Ediliyor..."
echo "=========================================="
echo ""

# Redis durumu
echo "7️⃣  Redis durumu:"
if systemctl is-active --quiet redis-server || systemctl is-active --quiet redis; then
    echo "   ✅ Redis çalışıyor"
    redis-cli ping && echo "   ✅ Redis bağlantısı başarılı (PONG)"
else
    echo "   ❌ Redis çalışmıyor!"
    exit 1
fi

echo ""

# PostgreSQL durumu
echo "8️⃣  PostgreSQL durumu:"
if systemctl is-active --quiet postgresql; then
    echo "   ✅ PostgreSQL çalışıyor"
    sudo -u postgres psql -c "SELECT version();" | head -3
else
    echo "   ❌ PostgreSQL çalışmıyor!"
    exit 1
fi

echo ""

# Bağlantı testleri
echo "9️⃣  Bağlantı testleri:"

# Redis bağlantı testi
echo "   Redis (127.0.0.1:6379):"
nc -zv 127.0.0.1 6379 2>&1 | grep -q succeeded && echo "      ✅ Bağlantı başarılı" || echo "      ❌ Bağlantı başarısız"

# PostgreSQL bağlantı testi
echo "   PostgreSQL (127.0.0.1:5432):"
nc -zv 127.0.0.1 5432 2>&1 | grep -q succeeded && echo "      ✅ Bağlantı başarılı" || echo "      ❌ Bağlantı başarısız"

echo ""
echo "=========================================="
echo "✅ TÜM SERVİSLER HAZIR!"
echo "=========================================="
echo ""
echo "Şimdi backtest'i çalıştırabilirsiniz:"
echo "  cd /home/voidstring/Desktop/trader/jesse"
echo "  python backtest_with_jesse.py"
echo ""
echo "Servisleri durdurmak için:"
echo "  sudo systemctl stop redis-server postgresql"
echo ""
