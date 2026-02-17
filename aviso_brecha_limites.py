import os
from dotenv import load_dotenv
load_dotenv()

import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
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
chrome_options.add_argument("--headless")  # Modo headless activado

# Configurar el servicio de ChromeDriver
service = Service(executable_path=chrome_driver_path)

# Inicializar el navegador
driver = webdriver.Chrome(service=service, options=chrome_options)

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

# Solicitar capital mínimo y máximo al usuario de manera secuencial
def get_capital_limits():
    while True:
        try:
            min_amount = float(input("Ingrese el capital mínimo que va a manejar: "))
            max_amount = float(input("Ingrese el capital máximo que va a manejar: "))
            if min_amount <= max_amount:
                return min_amount, max_amount
            else:
                print("El capital mínimo debe ser menor o igual al capital máximo. Inténtelo nuevamente.")
        except ValueError:
            print("Por favor, ingrese valores numéricos válidos.")

# Definir límites mínimo y máximo
LIMIT_MIN, LIMIT_MAX = get_capital_limits()
ADJUSTMENT = 0.01  # Ajuste de 1 centavo
COMMISSION = 0.0032  # Comisión del 0.32%
MAX_PAGES = 20     # Número máximo de páginas a procesar
MIN_PROFIT_PERCENTAGE = 0.19  # Porcentaje mínimo de ganancia

def extract_prices(url, price_type, min_amount=LIMIT_MIN, max_amount=LIMIT_MAX):
    prices = {}
    page = 1
    driver.get(url)
    time.sleep(5)  # Espera inicial para que la página cargue completamente

    while page <= MAX_PAGES:
        print(f"Extrayendo precios de la página {page} de {price_type}...")
        
        try:
            # Seleccionar los elementos que contienen los precios
            prices_elements = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#__APP > div.scroll-container.css-10kkqzn > main > div.mb-\[60px\].tablet\:mb-\[96px\].pc\:mb-\[128px\] > div.container.relative.bg-backgroundBasic > div > div.bn-web-table-wrapper.bn-web-table-wrapper__line > div > div > div > table > tbody > tr"))
            )
            
            if not prices_elements:
                print(f"No se encontraron elementos de precio en la página {page}")
                break

            for price_element in prices_elements:
                try:
                    # Extraer la tasa de compra/venta
                    tasa_element = price_element.find_element(By.CSS_SELECTOR, "td:nth-child(2) > div > div.headline5.mr-4xs.text-primaryText")
                    tasa_texto = tasa_element.text.replace('$', '').replace(',', '')
                    tasa = float(tasa_texto)
                    
                    # Extraer el mínimo y máximo asociados
                    min_element = price_element.find_element(By.CSS_SELECTOR, "td:nth-child(3) > div > div.bn-flex.flex-wrap.body3 > div.bn-flex")
                    max_element = price_element.find_element(By.CSS_SELECTOR, "td:nth-child(3) > div > div.bn-flex.flex-wrap.body3 > div:nth-child(3)")
                    
                    min_texto = min_element.text.replace('$', '').replace(',', '')
                    max_texto = max_element.text.replace('$', '').replace(',', '')
                    
                    min_tasa = float(min_texto)
                    max_tasa = float(max_texto)
                    
                    # Filtrar por los montos
                    if min_amount <= max_tasa and min_amount <= min_tasa and max_tasa <= max_amount and max_tasa <= max_amount:
                        if page not in prices:
                            prices[page] = []
                        prices[page].append((tasa, min_tasa, max_tasa))
                        print(f"{price_type} - Página: {page} - Tasa: {tasa} - Min: {min_tasa} - Max: {max_tasa}")
                except Exception as e:
                    print(f"Error al procesar el precio o mínimo/máximo '{price_element.text}': {e}")

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
                
                next_button.click()
                time.sleep(5)  # Esperar a que la nueva página cargue
                page += 1
            except TimeoutException:
                print(f"No se pudo encontrar el botón de siguiente página en la página {page}")
                break
            except NoSuchElementException:
                print(f"No se pudo encontrar el botón de siguiente página en la página {page}")
                break
            except Exception as e:
                print(f"Error al cambiar de página: {e}")
                break

        except Exception as e:
            print(f"Error al extraer precios de la página {page} de {price_type}: {e}")
            break
    
    return prices

def calculate_spreads(buy_prices, sell_prices):
    all_spreads = []
    
    for buy_page, buy_data in buy_prices.items():
        for sell_page, sell_data in sell_prices.items():
            for buy_tasa, buy_min, buy_max in buy_data:
                for sell_tasa, sell_min, sell_max in sell_data:
                    # Verificar si los rangos de precios se superponen
                    if not (buy_max < sell_min or sell_max < buy_min):
                        spread = sell_tasa - buy_tasa
                        # Ajustar las tasas por 1 centavo
                        buy_tasa_adjusted = buy_tasa + ADJUSTMENT
                        sell_tasa_adjusted = sell_tasa - ADJUSTMENT
                        # Calcular ganancia neta y porcentaje de ganancia
                        ganancia_neta = (sell_tasa_adjusted - buy_tasa_adjusted) - (buy_tasa_adjusted * COMMISSION + sell_tasa_adjusted * COMMISSION)
                        porcentaje_ganancia = (ganancia_neta / buy_tasa_adjusted) * 100
                        
                        # Almacenar solo las brechas con ganancia mayor o igual al 0.19%
                        if porcentaje_ganancia >= MIN_PROFIT_PERCENTAGE:
                            all_spreads.append((buy_tasa_adjusted, sell_tasa_adjusted, spread, buy_min, buy_max, sell_min, sell_max, ganancia_neta, porcentaje_ganancia, buy_page, sell_page))
                            print(f"Compra - Tasa: {buy_tasa_adjusted} vs Venta - Tasa: {sell_tasa_adjusted} | Brecha: {spread} | Ganancia Neta: {ganancia_neta} | Porcentaje de Ganancia: {porcentaje_ganancia:.2f}%")

    # Ordenar las brechas por porcentaje de ganancia de mayor a menor
    all_spreads.sort(key=lambda x: x[8], reverse=True)
    
    return all_spreads

def format_results(all_spreads):
    """Formatea los resultados para su presentación en Telegram."""
    message = "🔍 *Mejores oportunidades de arbitraje*\n\n"
    
    if all_spreads:
        message += "💰 *Oportunidades con ganancia positiva:*\n"
        for i, spread in enumerate(all_spreads[:5], 1):
            buy, sell, _, buy_min, buy_max, sell_min, sell_max, ganancia, porcentaje, buy_page, sell_page = spread
            message += f"{i}. 📈 Compra: `${buy:.2f}` (Pág {buy_page}) ➡️ Venta: `${sell:.2f}` (Pág {sell_page})\n"
            message += f"   💵 Ganancia: `${ganancia:.2f}` (__{porcentaje:.2f}%__)\n"
            message += f"   🔢 Límites - Compra: `${buy_min:.2f}-${buy_max:.2f}`, Venta: `${sell_min:.2f}-${sell_max:.2f}`\n\n"
    else:
        message += "😔 *No se encontraron oportunidades con ganancia mayor o igual al 0.19%.*\n\n"
    
    return message

# Bucle de monitoreo continuo
async def main_loop():
    while True:
        try:
            # Extraer tasas de compra y venta
            print("Extrayendo tasas de todas las páginas de compra...")
            buy_prices = extract_prices(url_buy, 'compra', min_amount=LIMIT_MIN, max_amount=LIMIT_MAX)

            print("Extrayendo tasas de todas las páginas de venta...")
            sell_prices = extract_prices(url_sell, 'venta', min_amount=LIMIT_MIN, max_amount=LIMIT_MAX)

            # Calcular brechas
            all_spreads = calculate_spreads(buy_prices, sell_prices)

            # Formatear resultados
            message = format_results(all_spreads)

            # Enviar mensaje a Telegram y mostrar en consola
            await send_telegram_message_with_retry(message)
            print(message)

        except Exception as e:
            error_message = f"Error durante la ejecución: {e}"
            print(error_message)
            await send_telegram_message_with_retry(error_message)

        print("\nEsperando 10 minutos antes de la siguiente iteración...\n")
        time.sleep(600)  # Esperar 10 minutos antes de la siguiente iteración

# Punto de entrada del programa
if __name__ == "__main__":
    asyncio.run(main_loop())

# Cerrar el navegador
driver.quit()