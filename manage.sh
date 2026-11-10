#!/bin/bash
# ═══════════════════════════════════════════════════════════
# 🛠️ اسکریپت مدیریت ربات زرکوین
# ═══════════════════════════════════════════════════════════
# نحوه اجرا: bash manage.sh
# ═══════════════════════════════════════════════════════════

BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$BOT_DIR/.env"

# رنگ‌ها
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

print_ok()   { echo -e "${GREEN}✅ $1${NC}"; }
print_info() { echo -e "${CYAN}ℹ️  $1${NC}"; }
print_warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_err()  { echo -e "${RED}❌ $1${NC}"; }

# ─────── خواندن فایل .env ───────
read_env() {
    if [ ! -f "$ENV_FILE" ]; then
        print_err "فایل .env پیدا نشد! ابتدا install.sh را اجرا کنید."
        exit 1
    fi
    source "$ENV_FILE"
}

# ─────── منو ───────
show_menu() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════╗"
    echo "║    🛠️ مدیریت ربات زرکوین               ║"
    echo "╚══════════════════════════════════════════╝"
    echo -e "${NC}"
    echo "  ۱) 📊 وضعیت ربات"
    echo "  ۲) 🔄 ری‌استارت ربات"
    echo "  ۳) ▶️  شروع ربات"
    echo "  ۴) ⏹️ توقف ربات"
    echo "  ۵) 📋 لاگ زنده ربات (Ctrl+C برای خروج)"
    echo "  6) 🗄️  اطلاعات دیتابیس + لینک Adminer"
    echo "  ۷) 📝 ویرایش فایل تنظیمات (.env)"
    echo "  ۸) 📦 آپدیت ربات (git pull + restart)"
    echo "  ۹) 🧹 پاک‌سازی لاگ‌ها"
    echo "  ۱۰) 📊 اطلاعات سیستم"
    echo "  ۰) خروج"
    echo ""
    read -p "انتخاب: " choice
}

# ─────── توابع ───────

cmd_status() {
    echo -e "\n${CYAN}═══ وضعیت ربات ═══${NC}"
    if systemctl is-active --quiet zarbot; then
        print_ok "ربات در حال اجراست ✅"
    else
        print_err "ربات متوقف است ❌"
    fi
    systemctl status zarbot --no-pager -l 2>/dev/null | head -15
    echo ""
    echo -e "${CYAN}═══ وضعیت Adminer ═══${NC}"
    if systemctl is-active --quiet zarbot-adminer 2>/dev/null; then
        print_ok "Adminer در حال اجراست ✅"
    else
        print_warn "Adminer متوقف است"
    fi
}

cmd_restart() {
    print_info "ری‌استارت ربات..."
    systemctl restart zarbot
    sleep 2
    if systemctl is-active --quiet zarbot; then
        print_ok "ربات با موفقیت ری‌استارت شد!"
    else
        print_err "ربات شروع نشد! لاگ را ببینید:"
        journalctl -u zarbot -n 20 --no-pager
    fi
}

cmd_start() {
    print_info "شروع ربات..."
    systemctl start zarbot
    sleep 2
    if systemctl is-active --quiet zarbot; then
        print_ok "ربات شروع شد!"
    else
        print_err "ربات شروع نشد!"
    fi
}

cmd_stop() {
    print_info "توقف ربات..."
    systemctl stop zarbot
    print_ok "ربات متوقف شد."
}

cmd_logs() {
    print_info "لاگ زنده (Ctrl+C برای خروج)..."
    journalctl -u zarbot -f
}

cmd_db_info() {
    read_env
    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

    # پیدا کردن پورت Adminer از سرویس
    ADMINER_PORT=$(grep -oP '0\.0\.0\.0:\K[0-9]+' /etc/systemd/system/zarbot-adminer.service 2>/dev/null || echo "8080")

    echo -e "\n${CYAN}═══ 🗄️ اطلاعات دیتابیس ═══${NC}"
    echo ""
    echo -e "${GREEN}🔗 لینک مدیریت دیتابیس (Adminer):${NC}"
    echo -e "   ${YELLOW}http://$SERVER_IP:$ADMINER_PORT${NC}"
    echo ""
    echo "   اطلاعات ورود به Adminer:"
    echo "     ┌─────────────────────────────┐"
    echo "     │ سیستم:     MySQL           │"
    echo "     │ سرور:      $DB_HOST"
    echo "     │ کاربر:     $DB_USER"
    echo "     │ رمز:       $DB_PASSWORD"
    echo "     │ دیتابیس:   $DB_NAME"
    echo "     └─────────────────────────────┘"
    echo ""
    echo -e "${CYAN}═══ 📋 جداول دیتابیس ═══${NC}"
    echo "   • users        — کاربران (موجودی، بانک، XP، لول)"
    echo "   • assets       — ملک‌ها و کارگرها"
    echo "   • user_missions — ماموریت‌های روزانه"
    echo ""
    echo -e "${CYAN}═══ 💡 دستورات مفید MySQL ═══${NC}"
    echo "   ورود به MySQL:"
    echo "     mysql -u $DB_USER -p$DB_PASSWORD $DB_NAME"
    echo ""
    echo "   مشاهده تمام کاربران:"
    echo "     SELECT user_id, first_name, balance, bank_balance FROM users;"
    echo ""
    echo "   تغییر موجودی یک کاربر:"
    echo "     UPDATE users SET balance = 1000000 WHERE user_id = 123456789;"
    echo ""
    echo "   حذف یک کاربر:"
    echo "     DELETE FROM users WHERE user_id = 123456789;"
}

cmd_edit_env() {
    read_env
    print_info "ویرایش فایل .env..."
    ${EDITOR:-nano} "$ENV_FILE"
    print_warn "فراموش نکن بعد از تغییر، ربات را ری‌استارت کن:"
    echo "  systemctl restart zarbot"
}

cmd_update() {
    print_info "آپدیت ربات..."
    cd "$BOT_DIR"
    if [ -d .git ]; then
        git pull
        print_info "به‌روزرسانی وابستگی‌ها..."
        "$BOT_DIR/venv/bin/pip" install -r requirements.txt -q
        cmd_restart
    else
        print_warn "این پوشه git نیست. فایل‌ها را دستی جایگزین کنید."
        print_info "سپس اجرا کن: bash manage.sh → انتخاب ۲ (ری‌استارت)"
    fi
}

cmd_clean_logs() {
    print_info "پاک‌سازی لاگ‌های قدیمی..."
    journalctl --vacuum-time=3d 2>/dev/null
    print_ok "لاگ‌های قدیمی پاک شدند."
}

cmd_sysinfo() {
    echo -e "\n${CYAN}═══ اطلاعات سیستم ═══${NC}"
    echo "   hostname:    $(hostname)"
    echo "   OS:          $(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2 | tr -d '"')"
    echo "   Kernel:      $(uname -r)"
    echo "   RAM:         $(free -h | awk '/Mem:/{print $2 " کل / " $7 " آزاد"}')"
    echo "   Disk:        $(df -h / | awk 'NR==2{print $2 " کل / " $4 " آزاد"}')"
    echo "   Uptime:      $(uptime -p)"
    echo "   IP:          $(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
    echo ""
    echo -e "${CYAN}═══ وضعیت سرویس‌ها ═══${NC}"
    echo "   zarbot:          $(systemctl is-active zarbot 2>/dev/null)"
    echo "   zarbot-adminer:  $(systemctl is-active zarbot-adminer 2>/dev/null)"
    echo "   mysql:           $(systemctl is-active mysql 2>/dev/null || systemctl is-active mariadb 2>/dev/null || echo 'نامشخص')"
}

# ─────── حلقه اصلی ───────
while true; do
    show_menu
    case $choice in
        1) cmd_status ;;
        2) cmd_restart ;;
        3) cmd_start ;;
        4) cmd_stop ;;
        5) cmd_logs ;;
        6) cmd_db_info ;;
        7) cmd_edit_env ;;
        8) cmd_update ;;
        9) cmd_clean_logs ;;
        10) cmd_sysinfo ;;
        0|q|Q) echo "خداحافظ! 👋"; exit 0 ;;
        *) print_err "انتخاب نامعتبر!" ;;
    esac
    echo ""
    read -p "برای ادامه Enter را بزنید..."
done
