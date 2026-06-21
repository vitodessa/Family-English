#!/usr/bin/env bash
# Разовая настройка Family English на Hetzner-сервере (рядом с ERP).
# Запускается ОДИН раз на сервере. Дальше всё деплоит GitHub Actions сам.
#
# Перед запуском: поддомен (по умолчанию family-english.duckdns.org) уже должен
# указывать на этот сервер (DNS / DuckDNS).
#
# Использование:  sudo bash bootstrap.sh [поддомен]
set -e

DOMAIN="${1:-family-english.duckdns.org}"
APP_DIR=/opt/family-english
REPO=https://github.com/vitodessa/Family-English.git

echo "==> 1/5 Код в $APP_DIR"
mkdir -p "$APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull origin main
else
  git clone "$REPO" "$APP_DIR"
fi
cd "$APP_DIR"

echo "==> 2/5 Файл .env (секреты)"
if [ ! -f .env ]; then
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  cat > .env <<EOF
SECRET_KEY=$SECRET
ADMIN_NAME=admin
ADMIN_PASSWORD=ПОМЕНЯЙ_ЭТОТ_ПАРОЛЬ
INITIAL_CARDS=20
DATABASE_URL=sqlite:////app/data/family.db
EOF
  echo "    .env создан. ВАЖНО: открой и поменяй ADMIN_PASSWORD."
else
  echo "    .env уже есть — не трогаю."
fi

echo "==> 3/5 Запуск контейнера"
docker compose up -d --build

echo "==> 4/5 SSL-сертификат для $DOMAIN (нужен один раз; DNS должен уже указывать сюда)"
certbot certonly --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@$DOMAIN" || \
  echo "    !! certbot не отработал — проверь, что $DOMAIN указывает на сервер, и запусти certbot вручную."

echo "==> 5/5 Nginx"
cp nginx/family-english.conf /etc/nginx/sites-available/family-english
ln -sf /etc/nginx/sites-available/family-english /etc/nginx/sites-enabled/family-english
nginx -t && systemctl reload nginx

echo ""
echo "Готово. Открой: https://$DOMAIN"
echo "Если меняешь поддомен — поправь его в nginx/family-english.conf и перезапусти этот скрипт."
