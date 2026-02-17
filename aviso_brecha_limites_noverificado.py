import os
from dotenv import load_dotenv
load_dotenv()

import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
import time
import telegram
import asyncio
from telegram.error import TimedOut

# Suprimir mensajes de TensorFlow
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# Ruta del chromedriver
DEFAULT_DRIVER = 'chromedriver.exe' if os.name == 'nt' else 'chromedriver'
chrome_driver_path = os.getenv('CHROMEDRIVER_PATH', DEFAULT_DRIVER)
# Configurar opciones de Chrome
chrome_options = Options()
# Desactivar el modo headless para ver el navegador
# chrome_options.add_argument("--headless")

# Configurar el servicio de ChromeDriver
service = Service(executable_path=chrome_driver_path)

# Inicializar los navegadores
driver_buy = webdriver.Chrome(service=service, options=chrome_options)
driver_sell = webdriver.Chrome(service=service, options=chrome_options)

# URL de prueba para precios de compra
url_buy = 'https://p2p.binance.com/trade/sell/USDT?fiat=ARS&payment=all-payments'
# URL de prueba para precios de venta
url_sell = 'https://p2p.binance.com/trade/all-payments/USDT?fiat=ARS'

# Configuración de Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHAT_ID', '')

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
    raise SystemExit('Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID (ver .env.example)')

bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

async def send_telegram_message_with_retry(message, max_retries=3, delay=5):
    """Envía un mensaje a Telegram con reintentos en caso de fallo."""
    for attempt in range(max_retries):
        try:
            await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message, parse_mode='Markdown')
            return
        except TimedOut:
            print(f"Intento {attempt + 1} fallido. Reintentando en {delay} segundos...")
            await asyncio.sleep(delay)
    print("No se pudo enviar el mensaje después de varios intentos.")

# Constantes
USER_MIN_AMOUNT = 100000  # Monto mínimo fijo para operar como usuario
MERCHANT_COMMISSION = 0.004  # Comisión del 0.40% para comerciantes
USER_COMMISSION = 0  # Sin comisión para usuarios

def get_capital_limits():
    """Solicita al usuario los límites de capital mínimo y máximo para operar como comerciante."""
    while True:
        try:
            min_amount = float(input("Ingrese el capital mínimo que va a manejar como comerciante: "))
            max_amount = float(input("Ingrese el capital máximo que va a manejar como comerciante: "))
            if min_amount <= max_amount:
                return min_amount, max_amount
            else:
                print("El capital mínimo debe ser menor o igual al capital máximo. Inténtelo nuevamente.")
        except ValueError:
            print("Por favor, ingrese valores numéricos válidos.")

# Definir límites mínimo y máximo para comerciantes
MERCHANT_LIMIT_MIN, MERCHANT_LIMIT_MAX = get_capital_limits()
ADJUSTMENT = 0.00  # Ajuste de 0 centavos
MAX_PAGES = 10     # Número máximo de páginas a procesar

def extract_prices(driver, url, price_type, min_amount=MERCHANT_LIMIT_MIN, max_amount=MERCHANT_LIMIT_MAX):
    """Extrae los precios de las páginas de Binance P2P."""
    prices = {}
    page = 1
    driver.get(url)
    time.sleep(5)  # Espera inicial para que la página cargue

    while page <= MAX_PAGES:
        print(f"Extrayendo precios de la página {page} de {price_type}...")
        
        try:
            rows = driver.find_elements(By.CSS_SELECTOR, "#__APP > div:nth-child(2) > main > div:nth-child(2) > div:nth-child(3) > div > div:nth-child(1) > div > div > div > table > tbody > tr")
            
            print(f"Número de elementos de precio encontrados en la página {page}: {len(rows)}")
            
            for row in rows:
                try:
                    # Extraer tasa, mínimo y máximo de cada fila
                    tasa_element = row.find_element(By.CSS_SELECTOR, "td:nth-child(2) > div > div:nth-child(1)")
                    tasa_texto = tasa_element.text.replace('$', '').replace(',', '')
                    tasa = float(tasa_texto)
                    
                    min_element = row.find_element(By.CSS_SELECTOR, "td:nth-child(3) > div > div:nth-child(2) > div:nth-child(1)")
                    max_element = row.find_element(By.CSS_SELECTOR, "td:nth-child(3) > div > div:nth-child(2) > div:nth-child(3)")
                    
                    min_texto = min_element.text.replace('$', '').replace(',', '')
                    max_texto = max_element.text.replace('$', '').replace(',', '')
                    
                    min_tasa = float(min_texto)
                    max_tasa = float(max_texto)
                    
                    # Verificar si los valores están dentro de los límites
                    if min_amount <= max_tasa and min_amount <= min_tasa and max_tasa <= max_amount and max_tasa <= max_amount:
                        if page not in prices:
                            prices[page] = []
                        prices[page].append((tasa, min_tasa, max_tasa))
                        print(f"{price_type} - Página: {page} - Tasa: {tasa} - Min: {min_tasa} - Max: {max_tasa}")
                except Exception as e:
                    print(f"Error al procesar el precio o mínimo/máximo en la página {page}: {e}")

            # Intentar cambiar a la siguiente página
            try:
                next_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "#__APP > div.scroll-container.css-10kkqzn > main > div.mb-\[60px\].tablet\:mb-\[96px\].pc\:mb-\[128px\] > div.container.relative.bg-backgroundBasic > div > div.bn-flex.mt-xl.justify-center > div > div.bn-pagination-next > svg"))
                )
                
                # Verificar si el botón está deshabilitado
                parent_div = next_button.find_element(By.XPATH, "..")
                if 'css-4ufx2c' in parent_div.get_attribute('class'):
                    print(f"No hay más páginas después de la página {page}")
                    break
                
                # Hacer clic en el botón
                next_button.click()
                
                # Esperar a que la nueva página cargue
                WebDriverWait(driver, 10).until(
                    EC.staleness_of(rows[0])
                )
                
                time.sleep(3)  # Espera adicional para asegurar que la página se cargue completamente
                page += 1
            except TimeoutException:
                print(f"Tiempo de espera excedido al intentar cambiar a la página {page + 1}")
                break
            except NoSuchElementException:
                print(f"No se pudo encontrar el botón de siguiente página en la página {page}")
                break
            except ElementClickInterceptedException:
                print(f"No se pudo hacer clic en el botón de siguiente página en la página {page}")
                break
            except Exception as e:
                print(f"Error al cambiar de página: {e}")
                break

        except Exception as e:
            print(f"Error al extraer precios de la página {page} de {price_type}: {e}")
            break
    
    return prices

def calculate_spreads(buy_prices, sell_prices):
    """Calcula los spreads entre los precios de compra y venta, considerando operaciones como usuario y como comerciante."""
    all_spreads = []

    def add_spread(tipo, compra, venta, compra_min, compra_max, venta_min, venta_max, compra_page, venta_page):
        spread = venta - compra
        if tipo == "Comerciante":
            ganancia_neta = spread - (compra * MERCHANT_COMMISSION + venta * MERCHANT_COMMISSION)
            porcentaje_ganancia = (ganancia_neta / compra) * 100
        else:  # Usuario
            ganancia_neta = spread  # Sin comisión para usuarios
            porcentaje_ganancia = (ganancia_neta / compra) * 100
        
        all_spreads.append((tipo, compra, venta, spread, compra_min, compra_max, venta_min, venta_max, ganancia_neta, porcentaje_ganancia, compra_page, venta_page))

    # Calcular spreads para operaciones como comerciante
    for buy_page, buy_list in buy_prices.items():
        for buy_tasa, buy_min, buy_max in buy_list:
            for sell_page, sell_list in sell_prices.items():
                for sell_tasa, sell_min, sell_max in sell_list:
                    if not (buy_max < MERCHANT_LIMIT_MIN or sell_max < MERCHANT_LIMIT_MIN or buy_min > MERCHANT_LIMIT_MAX or sell_min > MERCHANT_LIMIT_MAX):
                        add_spread("Comerciante", buy_tasa, sell_tasa, buy_min, buy_max, sell_min, sell_max, buy_page, sell_page)

    # Calcular spreads para operaciones como usuario (invirtiendo compra y venta)
    for sell_page, sell_list in sell_prices.items():
        for sell_tasa, sell_min, sell_max in sell_list:
            for buy_page, buy_list in buy_prices.items():
                for buy_tasa, buy_min, buy_max in buy_list:
                    if sell_max >= USER_MIN_AMOUNT and buy_max >= USER_MIN_AMOUNT:
                        add_spread("Usuario", sell_tasa, buy_tasa, sell_min, sell_max, buy_min, buy_max, sell_page, buy_page)

    print(f"Número de oportunidades encontradas: {len(all_spreads)}")

    # Función para clasificar las oportunidades
    def classify_opportunity(spread):
        compra_page, venta_page = spread[10], spread[11]
        if max(compra_page, venta_page) <= 3:
            return 0  # Prioridad máxima: ambas páginas muy cercanas (ultra rápido)
        elif max(compra_page, venta_page) <= 5:
            return 1  # Segunda prioridad: ambas páginas cercanas (rápido)
        elif min(compra_page, venta_page) <= 5 and max(compra_page, venta_page) > 5:
            return 2  # Tercera prioridad: una página cercana y otra lejana (medio)
        else:
            return 3  # Cuarta prioridad: ambas páginas lejanas (lento)

    # Ordenar las oportunidades por clasificación y luego por porcentaje de ganancia
    all_spreads.sort(key=lambda x: (classify_opportunity(x), -x[9]))

    # Seleccionar las mejores oportunidades de cada categoría
    final_spreads = []
    categories = [0, 1, 2, 3]
    for category in categories:
        category_spreads = [s for s in all_spreads if classify_opportunity(s) == category]
        final_spreads.extend(category_spreads[:2])  # Tomar las 2 mejores de cada categoría

    return final_spreads

def format_results(all_spreads):
    """Formatea los resultados para su presentación en Telegram."""
    message = "🔍 *Mejores oportunidades de arbitraje*\n\n"
    
    if all_spreads:
        for i, spread in enumerate(all_spreads, 1):
            tipo, compra, venta, _, compra_min, compra_max, venta_min, venta_max, ganancia, porcentaje, compra_page, venta_page = spread
            message += f"{i}. 🔄 Operar como: *{tipo}*\n"
            message += f"   📉 Compra: `${compra:.2f}` (Pág {compra_page}) ➡️ 📈 Venta: `${venta:.2f}` (Pág {venta_page})\n"
            message += f"   💵 Ganancia: `${ganancia:.2f}` (__{porcentaje:.2f}%__)\n"
            message += f"   🔢 Límites - Compra: `${compra_min:.2f}-${compra_max:.2f}`, Venta: `${venta_min:.2f}-${venta_max:.2f}`\n"
            if max(compra_page, venta_page) <= 3:
                message += f"   ⚡⚡ Oportunidad ultra rápida\n\n"
            elif max(compra_page, venta_page) <= 5:
                message += f"   ⚡ Oportunidad rápida\n\n"
            elif min(compra_page, venta_page) <= 5 and max(compra_page, venta_page) > 5:
                message += f"   ⏱️ Oportunidad media\n\n"
            else:
                message += f"   🐢 Oportunidad lenta\n\n"
    else:
        message += "😔 *No se encontraron oportunidades de arbitraje.*\n\n"
    
    return message

def open_browser_and_wait(url, driver):
    driver.get(url)
    time.sleep(10)  # Espera 10 segundos para cargar la página
    input("Presiona Enter después de aplicar los filtros manualmente...")

async def main_loop():
    while True:
        try:
            print("Extrayendo tasas de todas las páginas de compra...")
            buy_prices = extract_prices(driver_buy, url_buy, 'compra', min_amount=MERCHANT_LIMIT_MIN, max_amount=MERCHANT_LIMIT_MAX)

            print("Extrayendo tasas de todas las páginas de venta...")
            sell_prices = extract_prices(driver_sell, url_sell, 'venta', min_amount=MERCHANT_LIMIT_MIN, max_amount=MERCHANT_LIMIT_MAX)

            all_spreads = calculate_spreads(buy_prices, sell_prices)
            message = format_results(all_spreads)

            await send_telegram_message_with_retry(message)
            print(message)

            print("\nEsperando 5 minutos antes de la siguiente iteración...\n")
            time.sleep(300)  # Esperar 5 minutos

        except Exception as e:
            print(f"Error durante la ejecución: {e}")
            await send_telegram_message_with_retry(f"Error durante la ejecución: {e}")
            break

if __name__ == "__main__":
    print("Abriendo navegador para precios de compra...")
    open_browser_and_wait(url_buy, driver_buy)

    print("Abriendo navegador para precios de venta...")
    open_browser_and_wait(url_sell, driver_sell)

    asyncio.run(main_loop())

    driver_buy.quit()
    driver_sell.quit()