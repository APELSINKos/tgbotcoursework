# Развёртывание на сервере

Бот работает на Linux-сервере (Ubuntu 24.04) как служба systemd: запускается при загрузке системы и перезапускается после сбоя. Входящие соединения боту не нужны — он сам опрашивает Telegram, поэтому на сервере открыт только SSH.

## Что где лежит

| Путь | Назначение |
|---|---|
| `/opt/tgbot/app` | код из этого репозитория, файл базы `bot.db` |
| `/opt/tgbot/app/.env` | токен бота, права `600` |
| `/opt/tgbot/venv` | виртуальное окружение Python |
| `/etc/systemd/system/tgbot.service` | служба, копия [deploy/tgbot.service](../deploy/tgbot.service) |

Служба работает от отдельного пользователя `tgbot` без права входа в систему и без `sudo`.

## Установка

```bash
sudo apt update && sudo apt install -y python3-venv git
sudo useradd --system --create-home --home-dir /opt/tgbot --shell /usr/sbin/nologin tgbot
sudo -u tgbot git clone https://github.com/APELSINKos/tgbotcoursework.git /opt/tgbot/app
sudo -u tgbot python3 -m venv /opt/tgbot/venv
sudo -u tgbot /opt/tgbot/venv/bin/pip install -r /opt/tgbot/app/requirements.txt
sudo install -o tgbot -g tgbot -m 600 /dev/null /opt/tgbot/app/.env   # затем вписать BOT_TOKEN=...
sudo cp /opt/tgbot/app/deploy/tgbot.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now tgbot
```

## Управление

```bash
systemctl status tgbot          # состояние
journalctl -u tgbot -f          # журнал в реальном времени
sudo systemctl restart tgbot    # перезапуск
```

Обновление до свежей версии из репозитория:

```bash
sudo -u tgbot git -C /opt/tgbot/app pull
sudo systemctl restart tgbot
```

С одним токеном должен работать только один экземпляр бота: перед запуском на сервере локальную копию нужно остановить.

## Защита сервера

- вход по SSH только по ключу, пароли и вход под `root` отключены;
- межсетевой экран `ufw`: входящие соединения закрыты, кроме SSH;
- `fail2ban` блокирует адреса, подбирающие доступ по SSH;
- обновления безопасности ставятся автоматически (`unattended-upgrades`);
- служба изолирована средствами systemd: файловая система доступна только для чтения, запись разрешена лишь в каталог бота.
