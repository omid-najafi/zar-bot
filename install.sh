#!/bin/bash
# ═══════════════════════════════════════════════════════════
# 🤖 اسکریپت نصب ربات زرکوین روی سرور (VPS)
# ═══════════════════════════════════════════════════════════
# این اسکریپت:
#   ۱. پکیج‌های سیستمی (Python, MySQL, PHP) را نصب می‌کند
#   ۲. دیتابیس MySQL را راه‌اندازی می‌کند
#   ۳. Adminer (مدیریت دیتابیس تحت وب) را نصب می‌کند
#   ۴. ربات را به‌صورت سرویس خودکار پیکربندی می‌کند
#   ۵. لینک مدیریت دیتابیس را نمایش می‌دهد
#
# نحوه اجرا:
#   sudo bash install.sh
# ═══════════════════════════════════════════════════════════

set -e

# رنگ‌ها
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_ok()   { echo -e "${GREEN}✅ $1${NC}"; }
print_info() { echo -e "${CYAN}ℹ️  $1${NC}"; }
print_warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_err()  { echo -e "${RED}❌ $1${NC}"; }
print_step() { echo -e "\n${CYAN}═══ $1 ═══${NC}"; }

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════╗"
echo "║    🤖 نصب ربات زرکوین روی سرور         ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# ─────── بررسی root ───────
if [ "$EUID" -ne 0 ]; then
    print_err "این اسکریپت باید با دسترسی root اجرا شود"
    echo "   اجرا کن: sudo bash install.sh"
    exit 1
fi

# ─────── بررسی سیستم‌عامل ───────
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    if [[ "$OS" != "ubuntu" && "$OS" != "debian" ]]; then
        print_warn "سیستم‌عامل تست‌شده: Ubuntu/Debian. سیستم‌عامل شما: $OS"
        print_warn "ممکن است نیاز به تغییرات دستی داشته باشد."
        read -p "ادامه می‌دهید؟ (y/n): " CONTINUE
        [[ "$CONTINUE" != "y" ]] && exit 0
    fi
else
    print_err "سیستم‌عامل پشتیبانی نمی‌شود (فقط Ubuntu/Debian)"
    exit 1
fi

# ─────── مسیر ربات ───────
BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
print_info "مسیر ربات: $BOT_DIR"

# بررسی فایل bot.py
if [ ! -f "$BOT_DIR/bot.py" ]; then
    print_err "فایل bot.py در مسیر فعلی پیدا نشد!"
    print_err "این اسکریپت را از پوشه ربات اجرا کنید."
    exit 1
fi

# ═══════════ مرحله ۱: دریافت اطلاعات از کاربر ═══════════
print_step "مرحله ۱: دریافت اطلاعات"

read -p "🤖 توکن ربات را وارد کنید: " BOT_TOKEN
if [ -z "$BOT_TOKEN" ]; then
    print_err "توکن نمی‌تواند خالی باشد!"
    exit 1
fi

read -p "👤 آیدی عددی ادمین (OWNER_ID): " OWNER_ID
if [ -z "$OWNER_ID" ]; then
    print_err "آیدی ادمین نمی‌تواند خالی باشد!"
    exit 1
fi

read -p "💰 موجودی شروع کاربران (پیش‌فرض: 0): " START_BALANCE
START_BALANCE=${START_BALANCE:-0}

echo ""
print_info "انتخاب نوع دیتابیس:"
echo "  1) نصب MySQL روی همین سرور (پیشنهادی)"
echo "  2) استفاده از دیتابیس خارجی (قبلاً نصب شده)"
read -p "انتخاب (1/2): " DB_CHOICE
DB_CHOICE=${DB_CHOICE:-1}

if [ "$DB_CHOICE" == "2" ]; then
    # ─────── دیتابیس خارجی ───────
    print_step "تنظیمات دیتابیس خارجی"
    read -p "🖥️  آدرس سرور دیتابیس (host): " DB_HOST
    read -p "🔌 پورت دیتابیس (پیش‌فرض: 3306): " DB_PORT
    DB_PORT=${DB_PORT:-3306}
    read -p "👤 کاربر دیتابیس: " DB_USER
    read -s -p "🔑 رمز دیتابیس: " DB_PASSWORD
    echo ""
    read -p "📊 نام دیتابیس: " DB_NAME
    INSTALL_MYSQL=false
else
    # ─────── نصب MySQL محلی ───────
    DB_HOST="localhost"
    DB_PORT="3306"
    DB_NAME="zarbot"
    DB_USER="zarbot"
    # تولید رمز تصادفی قوی
    DB_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)
    INSTALL_MYSQL=true
fi

# پورت Adminer
read -p "🌐 پورت Adminer مدیریت دیتابیس (پیش‌فرض: 8080): " ADMINER_PORT
ADMINER_PORT=${ADMINER_PORT:-8080}

# ═══════════ مرحله ۲: نصب پکیج‌های سیستمی ═══════════
print_step "مرحله ۲: نصب پکیج‌های سیستمی"

export DEBIAN_FRONTEND=noninteractive

print_info "به‌روزرسانی apt..."
apt-get update -y -qq

print_info "نصب Python، PHP و ابزارها..."
apt-get install -y -qq python3 python3-pip python3-venv curl ufw openssl > /dev/null 2>&1

if [ "$INSTALL_MYSQL" == "true" ]; then
    print_info "نصب MySQL Server..."
    apt-get install -y -qq mysql-server > /dev/null 2>&1
    print_ok "MySQL نصب شد"
fi

print_info "نصب PHP برای Adminer..."
apt-get install -y -qq php-cli php-mysql php-xml > /dev/null 2>&1
print_ok "PHP نصب شد"

print_ok "پکیج‌های سیستمی نصب شدند"

# ═══════════ مرحله ۳: راه‌اندازی MySQL ═══════════
if [ "$INSTALL_MYSQL" == "true" ]; then
    print_step "مرحله ۳: راه‌اندازی MySQL"

    print_info "شروع سرویس MySQL..."
    systemctl enable mysql > /dev/null 2>&1 || true
    systemctl start mysql > /dev/null 2>&1 || true
    sleep 2

    print_info "ایجاد دیتابیس و کاربر..."
    mysql <<MYSQL_SCRIPT 2>/dev/null
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
ALTER USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';
FLUSH PRIVILEGES;
MYSQL_SCRIPT

    print_ok "دیتابیس '$DB_NAME' و کاربر '$DB_USER' ساخته شدند"
fi

# ═══════════ مرحله ۴: نصب Adminer ═══════════
print_step "مرحله ۴: نصب Adminer (مدیریت دیتابیس تحت وب)"

ADMINER_DIR="/var/www/zarbot-adminer"
mkdir -p "$ADMINER_DIR"

print_info "دانلود Adminer..."
ADMINER_VERSION="4.8.1"
curl -sL "https://github.com/vrana/adminer/releases/download/v${ADMINER_VERSION}/adminer-${ADMINER_VERSION}.php" -o "$ADMINER_DIR/index.php"

if [ ! -s "$ADMINER_DIR/index.php" ]; then
    print_warn "دانلود از GitHub ناموفق بود، تلاش از mirror..."
    curl -sL "https://www.adminer.org/static/download/${ADMINER_VERSION}/adminer-${ADMINER_VERSION}.php" -o "$ADMINER_DIR/index.php"
fi

if [ -s "$ADMINER_DIR/index.php" ]; then
    print_ok "Adminer نصب شد"
else
    print_err "نصب Adminer ناموفق بود!"
    print_warn "می‌توانید بعداً به‌صورت دستی نصب کنید."
fi

# ═══════════ مرحله ۵: ایجاد فایل .env ═══════════
print_step "مرحله ۵: ایجاد فایل تنظیمات (.env)"

cat > "$BOT_DIR/.env" <<EOF
# ═══════════ تنظیمات ربات زرکوین ═══════════
# این فایل توسط اسکریپت install.sh ساخته شده

# ─── تنظیمات ربات ───
BOT_TOKEN=$BOT_TOKEN
OWNER_ID=$OWNER_ID
START_BALANCE=$START_BALANCE

# ─── تنظیمات دیتابیس MySQL ───
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_NAME=$DB_NAME
EOF

chmod 600 "$BOT_DIR/.env"
print_ok "فایل .env ساخته شد: $BOT_DIR/.env"

# ═══════════ مرحله ۶: نصب وابستگی‌های Python ═══════════
print_step "مرحله ۶: نصب وابستگی‌های Python"

print_info "ایجاد محیط مجازی (virtualenv)..."
python3 -m venv "$BOT_DIR/venv"

print_info "نصب پکیج‌های Python..."
"$BOT_DIR/venv/bin/pip" install --upgrade pip -q
"$BOT_DIR/venv/bin/pip" install -r "$BOT_DIR/requirements.txt" -q
print_ok "وابستگی‌های Python نصب شدند"

# ═══════════ مرحله ۷: سرویس systemd برای ربات ═══════════
print_step "مرحله ۷: ایجاد سرویس خودکار ربات"

cat > /etc/systemd/system/zarbot.service <<EOF
[Unit]
Description=Zar Bot Telegram Bot
After=network.target mysql.service
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$BOT_DIR
EnvironmentFile=$BOT_DIR/.env
ExecStart=$BOT_DIR/venv/bin/python bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable zarbot > /dev/null 2>&1
print_ok "سرویس zarbot ساخته شد"

# ═══════════ مرحله ۸: سرویس systemd برای Adminer ═══════════
if [ -s "$ADMINER_DIR/index.php" ]; then
    print_step "مرحله ۸: ایجاد سرویس Adminer"

    cat > /etc/systemd/system/zarbot-adminer.service <<EOF
[Unit]
Description=Zar Bot Adminer Database Manager
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/php -S 0.0.0.0:$ADMINER_PORT -t $ADMINER_DIR
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable zarbot-adminer > /dev/null 2>&1
    print_ok "سرویس zarbot-adminer ساخته شد"
fi

# ═══════════ مرحله ۹: تنظیم فایروال ═══════════
print_step "مرحله ۹: تنظیم فایروال"

ufw allow OpenSSH > /dev/null 2>&1 || true
ufw allow $ADMINER_PORT/tcp > /dev/null 2>&1 || true
echo "y" | ufw enable > /dev/null 2>&1 || true
print_ok "فایروال تنظیم شد (پورت $ADMINER_PORT باز شد)"

# ═══════════ مرحله ۱۰: شروع سرویس‌ها ═══════════
print_step "مرحله ۱۰: شروع سرویس‌ها"

systemctl restart zarbot-adminer 2>/dev/null || true
sleep 1
systemctl restart zarbot

sleep 3
if systemctl is-active --quiet zarbot; then
    print_ok "ربات با موفقیت شروع شد!"
else
    print_err "ربات شروع نشد! لاگ را بررسی کنید:"
    print_warn "journalctl -u zarbot -n 30"
fi

# ═══════════ نمایش خلاصه نهایی ═══════════
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          ✅ نصب کامل شد!                                ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}═══ 🤖 ربات ═══${NC}"
echo "   وضعیت:       systemctl status zarbot"
echo "   لاگ زنده:    journalctl -u zarbot -f"
echo "   ری‌استارت:   systemctl restart zarbot"
echo "   توقف:        systemctl stop zarbot"
echo ""
echo -e "${CYAN}═══ 📊 مدیریت دیتابیس (Adminer) ═══${NC}"
echo -e "   ${YELLOW}🔗 لینک: http://$SERVER_IP:$ADMINER_PORT${NC}"
echo ""
echo "   اطلاعات ورود به Adminer:"
echo "     سیستم:     MySQL"
echo "     سرور:      $DB_HOST"
echo "     کاربر:     $DB_USER"
echo "     رمز:       $DB_PASSWORD"
echo "     دیتابیس:   $DB_NAME"
echo ""
echo -e "${CYAN}═══ 📁 فایل‌ها ═══${NC}"
echo "   مسیر ربات:    $BOT_DIR"
echo "   فایل تنظیمات: $BOT_DIR/.env"
echo "   محیط Python:  $BOT_DIR/venv"
echo ""
echo -e "${CYAN}══️ 🔒 امنیت ═══${NC}"
echo "   ⚠️  برای امنیت بیشتر:"
echo "   ۱. پورت Adminer را فقط برای IP خودتان باز کنید:"
echo "      ufw delete allow $ADMINER_PORT && ufw allow from YOUR_IP to any port $ADMINER_PORT"
echo "   ۲. فایل .env حاوی رمز دیتابیس است — آن را با کسی به اشتراک نگذارید"
echo ""
echo -e "${CYAN}═══ 📋 مدیریت ربات ═══${NC}"
echo "   برای مدیریت آسان، از اسکریپت manage.sh استفاده کنید:"
echo "      bash $BOT_DIR/manage.sh"
echo ""
echo -e "${GREEN}موفق باشید! 🎉${NC}"
