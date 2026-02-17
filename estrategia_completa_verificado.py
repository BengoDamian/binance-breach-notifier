import os
from dotenv import load_dotenv
load_dotenv()

import subprocess
import time
import json
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
import telegram
import asyncio
from telegram.error import TimedOut, NetworkError, TelegramError
import logging

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuración de Selenium y Telegram
chrome_path = r"D:\Backupp\Descargas\chrome-win64\chrome.exe"
chromedriver_path = r"D:\Backupp\Documentos\Proyectos Python\aviso de brecha binance\chromedriver.exe"
user_data_dir = r"C:\Users\bengo\AppData\Local\Google\Chrome for Testing\User Data"

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHAT_ID', '')
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
    raise SystemExit('Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID (ver .env.example)')

bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

# Constantes
MERCHANT_COMMISSION = 0.0032  # 0.32%
MAX_PAGES = 10
STRATEGY_INTERVAL = 3600  # 1 hora en segundos
SPREAD_INTERVAL = 600    # 10 minutos en segundos
MIN_PROFIT_PERCENTAGE = 0.2  # 0.2% de ganancia mínima después de comisiones

# Obtener límites de capital del comerciante
MERCHANT_LIMIT_MIN = float(input("Ingrese el capital mínimo que va a manejar como comerciante: "))
MERCHANT_LIMIT_MAX = float(input("Ingrese el capital máximo que va a manejar como comerciante: "))

def setup_driver():
    """
    Configura y retorna una instancia de WebDriver de Chrome.
    
    Returns:
        webdriver.Chrome: Instancia configurada del WebDriver de Chrome.
    
    Raises:
        WebDriverException: Si hay un problema al inicializar el WebDriver.
    """
    try:
        options = Options()
        options.binary_location = chrome_path
        options.add_argument(f"user-data-dir={user_data_dir}")
        options.add_argument("--profile-directory=Default")
        #options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920x1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--remote-debugging-port=9222")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-software-rasterizer")
        
        # Añadir estas nuevas opciones
        options.add_argument("--ignore-gpu-blocklist")
        options.add_argument("--disable-gpu-sandbox")
        options.add_argument("--disable-accelerated-2d-canvas")
        options.add_argument("--disable-accelerated-jpeg-decoding")
        options.add_argument("--disable-accelerated-mjpeg-decode")
        options.add_argument("--disable-accelerated-video-decode")
        options.add_argument("--disable-gpu-compositing")

        service = Service(executable_path=chromedriver_path)
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        logger.error(f"Error al configurar el WebDriver: {e}")
        raise

def get_binance_p2p_price():
    """
    Obtiene el precio de compra y venta de Binance P2P.
    
    Returns:
        tuple: Precio de compra (bid) y venta (ask), o (None, None) si hay un error.
    """
    try:
        response = requests.get('https://criptoya.com/api/binancep2p/USDT/ARS/0.1')
        response.raise_for_status()
        data = response.json()
        return data['bid'], data['ask']
    except requests.RequestException as e:
        logger.error(f"Error al obtener el precio de Binance P2P: {e}")
        return None, None

def get_binance_price():
    """
    Obtiene el precio de compra y venta de Binance (Venta).
    
    Returns:
        tuple: Precio de compra (bid) y venta (ask), o (None, None) si hay un error.
    """
    try:
        response = requests.get('https://criptoya.com/api/binance/USDT/ARS/0.1')
        response.raise_for_status()
        data = response.json()
        return data['bid'], data['ask']
    except requests.RequestException as e:
        logger.error(f"Error al obtener el precio de Binance (Venta): {e}")
        return None, None

def get_okx_price():
    """
    Obtiene el precio de compra y venta de OKX.
    
    Returns:
        tuple: Precio de compra (bid) y venta (ask), o (None, None) si hay un error.
    """
    try:
        response = requests.get('https://criptoya.com/api/okexp2p/USDT/ARS/0.1')
        response.raise_for_status()
        data = response.json()
        return data['bid'], data['ask']
    except requests.RequestException as e:
        logger.error(f"Error al obtener el precio de OKX: {e}")
        return None, None

def get_general_dollar_price():
    """
    Obtiene el precio del dólar general.
    
    Returns:
        tuple: Precio del dólar general (bid), y precios de ccl al30 y gd30, o (None, None, None) si hay un error.
    """
    try:
        response = requests.get('https://criptoya.com/api/dolar')
        response.raise_for_status()
        data = response.json()
        return data['cripto']['usdt']['bid'], data['ccl']['al30']['24hs']['price'], data['ccl']['gd30']['24hs']['price']
    except requests.RequestException as e:
        logger.error(f"Error al obtener el precio del dólar general: {e}")
        return None, None, None

def analyze_trend(price_current, price_previous):
    """
    Analiza la tendencia de los precios.
    
    Args:
        price_current (float): Precio actual.
        price_previous (float): Precio anterior.
    
    Returns:
        str: Tendencia ('subiendo', 'bajando', 'estable' o 'No disponible').
    """
    if price_current is None or price_previous is None:
        return 'No disponible'
    elif price_current > price_previous:
        return 'subiendo'
    elif price_current < price_previous:
        return 'bajando'
    else:
        return 'estable'

def determine_strategy_liquidity(liquidez):
    """
    Determina la estrategia basada en la liquidez.
    
    Args:
        liquidez (dict): Diccionario con información de liquidez.
    
    Returns:
        str: Estrategia recomendada.
    """
    if liquidez['cambio_precios_rapido']:
        return "No colocarse en la primera página"
    else:
        return "Colocarse en la primera página"

def determine_strategy_dollar(precio_dolar):
    """
    Determina la estrategia basada en el precio del dólar.
    
    Args:
        precio_dolar (dict): Diccionario con información del precio del dólar.
    
    Returns:
        str: Estrategia recomendada.
    """
    if precio_dolar['sube']:
        return "Congelar compra y vender como en la 4ta página"
    elif precio_dolar['baja']:
        return "Vender en primeras páginas y posicionarse lejos para comprar"
    else:
        return "Estrategia no definida"

def get_trends_and_strategies():
    """
    Obtiene las tendencias y estrategias actuales.
    
    Returns:
        dict: Diccionario con las tendencias y estrategias, o None si hay un error.
    """
    try:
        logger.info("Obteniendo precios iniciales...")
        previous_binance_p2p_price_bid, _ = get_binance_p2p_price()
        previous_binance_price_bid, _ = get_binance_price()
        previous_okx_price_bid, _ = get_okx_price()
        previous_general_dollar_price, _, _ = get_general_dollar_price()

        logger.info(f"Precios iniciales obtenidos: Binance P2P: {previous_binance_p2p_price_bid}, Binance: {previous_binance_price_bid}, OKX: {previous_okx_price_bid}, Dólar general: {previous_general_dollar_price}")

        logger.info(f"Esperando {SPREAD_INTERVAL} segundos para analizar tendencias...")
        time.sleep(SPREAD_INTERVAL)

        logger.info("Obteniendo precios actuales...")
        current_binance_p2p_price_bid, _ = get_binance_p2p_price()
        current_binance_price_bid, _ = get_binance_price()
        current_okx_price_bid, _ = get_okx_price()
        current_general_dollar_price, _, _ = get_general_dollar_price()

        logger.info(f"Precios actuales obtenidos: Binance P2P: {current_binance_p2p_price_bid}, Binance: {current_binance_price_bid}, OKX: {current_okx_price_bid}, Dólar general: {current_general_dollar_price}")

        binance_p2p_trend = analyze_trend(current_binance_p2p_price_bid, previous_binance_p2p_price_bid)
        binance_trend = analyze_trend(current_binance_price_bid, previous_binance_price_bid)
        okx_trend = analyze_trend(current_okx_price_bid, previous_okx_price_bid)
        general_dollar_trend = analyze_trend(current_general_dollar_price, previous_general_dollar_price)

        liquidez = {
            'cambio_precios_rapido': current_binance_p2p_price_bid != previous_binance_p2p_price_bid
        }
        estrategia_liquidez = determine_strategy_liquidity(liquidez)

        precio_dolar = {
            'sube': current_general_dollar_price > previous_general_dollar_price,
            'baja': current_general_dollar_price < previous_general_dollar_price
        }
        estrategia_dolar = determine_strategy_dollar(precio_dolar)

        logger.info("Análisis de tendencias completado.")

        return {
            'binance_p2p_trend': binance_p2p_trend,
            'binance_trend': binance_trend,
            'okx_trend': okx_trend,
            'general_dollar_trend': general_dollar_trend,
            'estrategia_liquidez': estrategia_liquidez,
            'estrategia_dolar': estrategia_dolar
        }
    except Exception as e:
        logger.exception(f"Error en get_trends_and_strategies: {e}")
        return None

def extract_prices(driver, url, price_type, min_amount, max_amount, max_pages):
    """
    Extrae los precios de las páginas de Binance P2P.
    
    Args:
        driver (webdriver.Chrome): Instancia del WebDriver.
        url (str): URL de la página a extraer.
        price_type (str): Tipo de precio ('compra' o 'venta').
        min_amount (float): Cantidad mínima para filtrar.
        max_amount (float): Cantidad máxima para filtrar.
        max_pages (int): Número máximo de páginas a extraer.
    
    Returns:
        dict: Diccionario con los precios extraídos por página, o None si hay un error.
    """
    prices = {}
    page = 1
    driver.get(url)
    time.sleep(5)  # Espera inicial para que la página cargue

    while page <= max_pages:
        logger.info(f"Extrayendo precios de la página {page} de {price_type}...")
        
        try:
            rows = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#__APP > div:nth-child(2) > main > div:nth-child(2) > div:nth-child(3) > div > div:nth-child(1) > div > div > div > table > tbody > tr"))
            )
            
            logger.info(f"Número de elementos de precio encontrados en la página {page}: {len(rows)}")
            
            if not rows:
                logger.warning(f"No se encontraron filas en la página {page}. Finalizando extracción.")
                break

            for row in rows:
                try:
                    tasa_element = WebDriverWait(row, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "td:nth-child(2) > div > div:nth-child(1)"))
                    )
                    tasa = float(tasa_element.text.replace('$', '').replace(',', ''))
                    
                    limits_element = WebDriverWait(row, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "td:nth-child(3) > div > div:nth-child(2)"))
                    )
                    limits_text = limits_element.text.split('\n')
                    min_tasa = float(limits_text[0].replace('$', '').replace(',', ''))
                    max_tasa = float(limits_text[2].replace('$', '').replace(',', ''))
                    
                    if min_amount <= max_tasa and min_tasa <= max_amount:
                        if page not in prices:
                            prices[page] = []
                        prices[page].append((tasa, min_tasa, max_tasa))
                        logger.info(f"{price_type} - Página: {page} - Tasa: {tasa} - Min: {min_tasa} - Max: {max_tasa}")
                except TimeoutException:
                    logger.error(f"Tiempo de espera agotado al procesar una fila en la página {page}")
                except NoSuchElementException:
                    logger.error(f"No se encontró un elemento esperado en una fila de la página {page}")
                except Exception as e:
                    logger.error(f"Error al procesar una fila en la página {page}: {e}")

            # Intentar cambiar a la siguiente página
            try:
                next_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "#__APP > div.scroll-container.css-10kkqzn > main > div.mb-\[60px\].tablet\:mb-\[96px\].pc\:mb-\[128px\] > div.container.relative.bg-backgroundBasic > div > div.bn-flex.mt-xl.justify-center > div > div.bn-pagination-next > svg"))
                )
                
                if not next_button.is_enabled():
                    logger.info(f"No hay más páginas después de la página {page}")
                    break
                
                next_button.click()
                time.sleep(3)  # Espera adicional para asegurar que la página se cargue completamente
                page += 1
            except ElementClickInterceptedException:
                logger.error(f"No se pudo hacer clic en el botón de siguiente página en la página {page}")
                break
            except Exception as e:
                logger.error(f"Error al cambiar de página: {e}")
                break

        except TimeoutException:
            logger.error(f"Tiempo de espera agotado al cargar elementos en la página {page}")
            break
        except Exception as e:
            logger.error(f"Error al extraer precios de la página {page} de {price_type}: {e}")
            break

    logger.info(f"Precios extraídos para {price_type}: {len(prices)} elementos")
    return prices if prices else None

def calculate_spreads(buy_prices, sell_prices):
    """
    Calcula los spreads entre los precios de compra y venta.
    
    Args:
        buy_prices (dict): Diccionario con los precios de compra.
        sell_prices (dict): Diccionario con los precios de venta.
    
    Returns:
        list: Lista de spreads calculados.
    """
    all_spreads = []
    for buy_page, buy_list in buy_prices.items():
        for buy_tasa, buy_min, buy_max in buy_list:
            for sell_page, sell_list in sell_prices.items():
                for sell_tasa, sell_min, sell_max in sell_list:
                    if max(buy_min, MERCHANT_LIMIT_MIN) <= min(buy_max, MERCHANT_LIMIT_MAX) and \
                       max(sell_min, MERCHANT_LIMIT_MIN) <= min(sell_max, MERCHANT_LIMIT_MAX):
                        buy_tasa_adjusted = buy_tasa + 0.01
                        sell_tasa_adjusted = sell_tasa - 0.01
                        spread = sell_tasa_adjusted - buy_tasa_adjusted
                        ganancia_neta = spread - (buy_tasa_adjusted * MERCHANT_COMMISSION + sell_tasa_adjusted * MERCHANT_COMMISSION)
                        porcentaje_ganancia = (ganancia_neta / buy_tasa_adjusted) * 100
                        all_spreads.append(("Comerciante", buy_tasa_adjusted, sell_tasa_adjusted, ganancia_neta, porcentaje_ganancia, 
                                            max(buy_min, MERCHANT_LIMIT_MIN), min(buy_max, MERCHANT_LIMIT_MAX), 
                                            max(sell_min, MERCHANT_LIMIT_MIN), min(sell_max, MERCHANT_LIMIT_MAX), 
                                            buy_page, sell_page))
    return all_spreads

def determine_strategy(spread):
    """
    Determina la estrategia basada en el spread.
    
    Args:
        spread (tuple): Información del spread.
    
    Returns:
        str: Estrategia recomendada.
    """
    tipo, compra, venta, ganancia, porcentaje, compra_min, compra_max, venta_min, venta_max, compra_page, venta_page = spread
    if compra_page <= 5 and venta_page <= 5:
        return "Alta competencia. Considerar ajustes frecuentes de precio."
    elif porcentaje > 0.2:
        return f"Oportunidad potencial. Colocar órdenes cerca de ${compra:.2f} y ${venta:.2f}."
    elif porcentaje > 0:
        return f"Margen estrecho. Vigilar cambios y actuar si mejora a más de 0.2%."
    else:
        return "Condiciones desfavorables. Esperar mejores oportunidades."

def format_results(all_spreads, estrategia_dolar):
    """
    Formatea los resultados para enviar por Telegram.
    
    Args:
        all_spreads (list): Lista de spreads calculados.
        estrategia_dolar (str): Estrategia general del dólar.
    
    Returns:
        str: Mensaje formateado para Telegram.
    """
    message = "🔍 *Mejores oportunidades de arbitraje*\n\n"
    
    message += f"💼 *Estrategia general:* {estrategia_dolar}\n\n"

    def classify_opportunity(spread):
        compra_page, venta_page = spread[9], spread[10]
        if max(compra_page, venta_page) <= 3:
            return 0, "⚡️⚡️ Oportunidad ultra rápida"
        elif max(compra_page, venta_page) <= 5:
            return 1, "⚡️ Oportunidad rápida"
        elif min(compra_page, venta_page) <= 5 and max(compra_page, venta_page) > 5:
            return 2, "⏱️ Oportunidad media"
        else:
            return 3, "🐢 Oportunidad lenta"

    # Filtrar spreads por el porcentaje mínimo de ganancia y ganancia positiva
    filtered_spreads = [s for s in all_spreads if s[4] >= MIN_PROFIT_PERCENTAGE and s[3] > 0]
    
    if not filtered_spreads:
        return "No se encontraron oportunidades que cumplan con el porcentaje mínimo de ganancia después de comisiones."

    filtered_spreads.sort(key=lambda x: (classify_opportunity(x)[0], -x[4]))

    final_spreads = []
    categories = [0, 1, 2, 3]
    for category in categories:
        category_spreads = [s for s in filtered_spreads if classify_opportunity(s)[0] == category]
        final_spreads.extend(category_spreads[:2])

    for i, spread in enumerate(final_spreads, 1):
        tipo, compra, venta, ganancia, porcentaje, compra_min, compra_max, venta_min, venta_max, compra_page, venta_page = spread
        classification = classify_opportunity(spread)[1]
        strategy = determine_strategy(spread)
        
        message += f"*{i}. 🔄 Operar como: {tipo}*\n"
        message += f"   📉 Compra: `${compra:.2f}` (Pág {compra_page}) ➡️ 📈 Venta: `${venta:.2f}` (Pág {venta_page})\n"
        message += f"   💵 Ganancia neta: `${ganancia:.2f}` (__{porcentaje:.2f}%__) (después de comisiones)\n"
        message += f"   🔢 Límites - Compra: `${compra_min:.2f}-${compra_max:.2f}`\n"
        message += f"              Venta: `${venta_min:.2f}-${venta_max:.2f}`\n"
        message += f"   {classification}\n"
        message += f"   🔧 Estrategia: _{strategy}_\n\n"
        message += "───────────────────────\n\n"

    return message

async def send_telegram_message_with_retry(message, max_retries=3, delay=5):
    """
    Envía un mensaje a Telegram con reintentos en caso de fallo.
    
    Args:
        message (str): Mensaje a enviar.
        max_retries (int): Número máximo de reintentos.
        delay (int): Tiempo de espera entre reintentos en segundos.
    """
    for attempt in range(max_retries):
        try:
            await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message, parse_mode='Markdown')
            return
        except TimedOut:
            logger.warning(f"Intento {attempt + 1} fallido por tiempo de espera. Reintentando en {delay} segundos...")
            await asyncio.sleep(delay)
        except NetworkError:
            logger.warning(f"Intento {attempt + 1} fallido por error de red. Reintentando en {delay} segundos...")
            await asyncio.sleep(delay)
        except TelegramError as e:
            logger.error(f"Error de Telegram en el intento {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                raise
    logger.error("No se pudo enviar el mensaje después de varios intentos.")

async def main_loop():
    """
    Función principal que ejecuta el bucle principal del script.
    """
    driver_buy = setup_driver()
    driver_sell = setup_driver()
    url_buy = 'https://p2p.binance.com/trade/sell/USDT?fiat=ARS&payment=all-payments'
    url_sell = 'https://p2p.binance.com/trade/all-payments/USDT?fiat=ARS'
    
    last_strategy_time = 0
    current_strategy = None

    try:
        while True:
            current_time = time.time()

            if current_strategy is None or current_time - last_strategy_time >= STRATEGY_INTERVAL:
                logger.info("Analizando tendencias y estrategias...")
                trends_and_strategies = get_trends_and_strategies()
                
                if trends_and_strategies is None:
                    logger.warning("Error al obtener tendencias y estrategias. Saltando esta iteración.")
                    continue

                current_strategy = trends_and_strategies['estrategia_dolar']
                last_strategy_time = current_time

            logger.info("Extrayendo tasas de todas las páginas de compra...")
            buy_prices = extract_prices(driver_buy, url_buy, 'compra', min_amount=MERCHANT_LIMIT_MIN, max_amount=MERCHANT_LIMIT_MAX, max_pages=MAX_PAGES)
            if buy_prices is None:
                logger.error("Error: No se pudieron extraer los precios de compra.")
                continue

            logger.info("Extrayendo tasas de todas las páginas de venta...")
            sell_prices = extract_prices(driver_sell, url_sell, 'venta', min_amount=MERCHANT_LIMIT_MIN, max_amount=MERCHANT_LIMIT_MAX, max_pages=MAX_PAGES)
            if sell_prices is None:
                logger.error("Error: No se pudieron extraer los precios de venta.")
                continue

            all_spreads = calculate_spreads(buy_prices, sell_prices)
            message = format_results(all_spreads, current_strategy)

            await send_telegram_message_with_retry(message)
            logger.info("Mensaje enviado por Telegram")

            logger.info(f"Esperando {SPREAD_INTERVAL} segundos antes de la siguiente iteración...")
            await asyncio.sleep(SPREAD_INTERVAL)

    except Exception as e:
        logger.exception(f"Error durante la ejecución: {e}")
        await send_telegram_message_with_retry(f"Error durante la ejecución: {e}")
    finally:
        driver_buy.quit()
        driver_sell.quit()

def main():
    """
    Función principal que inicia el script.
    """
    logger.info("Iniciando el script...")
    logger.info("Iniciando el bucle principal...")
    try:
        asyncio.run(main_loop())
    except Exception as e:
        logger.exception(f"Error en el bucle principal: {e}")
    logger.info("Script finalizado.")

if __name__ == "__main__":
    main()