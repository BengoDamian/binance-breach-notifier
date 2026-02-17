# Binance Breach Notifier (Python)

Scripts para monitorear condiciones/umbrales y enviar alertas por Telegram.

## ⚠️ Seguridad
Este repo está sanitizado: **no contiene tokens**.
- Definí variables de entorno (ver `.env.example`)
- Si un token estuvo expuesto alguna vez, **rotalo** en Telegram.

## Requisitos
- Python 3.10+
- Chrome + ChromeDriver compatible (ponelo en PATH o definí `CHROMEDRIVER_PATH`)
- Dependencias: ver `requirements.txt`

## Setup rápido
```bash
pip install -r requirements.txt
cp .env.example .env
# completá .env
python aviso_brecha_limites.py
```

## Variables
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `CHROMEDRIVER_PATH` (opcional)
