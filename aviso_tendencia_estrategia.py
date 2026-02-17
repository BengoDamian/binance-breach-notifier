import os
from dotenv import load_dotenv
load_dotenv()

import requests
import time

def get_binance_p2p_price():
    try:
        response = requests.get('https://criptoya.com/api/binancep2p/USDT/ARS/0.1')
        response.raise_for_status()
        data = response.json()
        return data['bid'], data['ask']
    except requests.RequestException as e:
        print(f"Error al obtener el precio de Binance P2P: {e}")
        return None, None

def get_binance_price():
    try:
        response = requests.get('https://criptoya.com/api/binance/USDT/ARS/0.1')
        response.raise_for_status()
        data = response.json()
        return data['bid'], data['ask']
    except requests.RequestException as e:
        print(f"Error al obtener el precio de Binance (Venta): {e}")
        return None, None

def get_okx_price():
    try:
        response = requests.get('https://criptoya.com/api/okexp2p/USDT/ARS/0.1')
        response.raise_for_status()
        data = response.json()
        return data['bid'], data['ask']
    except requests.RequestException as e:
        print(f"Error al obtener el precio de OKX: {e}")
        return None, None

def get_general_dollar_price():
    try:
        response = requests.get('https://criptoya.com/api/dolar')
        response.raise_for_status()
        data = response.json()
        return data['cripto']['usdt']['bid'], data['ccl']['al30']['24hs']['price'], data['ccl']['gd30']['24hs']['price']
    except requests.RequestException as e:
        print(f"Error al obtener el precio del dólar general: {e}")
        return None, None, None

def analyze_trend(price_current, price_previous):
    if price_current is None or price_previous is None:
        return 'No disponible'
    elif price_current > price_previous:
        return 'subiendo'
    elif price_current < price_previous:
        return 'bajando'
    else:
        return 'estable'

def determine_strategy_liquidity(liquidez):
    if liquidez['cambio_precios_rapido']:
        return "No colocarse en la primera página"
    else:
        return "Colocarse en la primera página"

def determine_strategy_dollar(precio_dolar):
    if precio_dolar['sube']:
        return "Congelar compra y vender como en la 4ta página"
    elif precio_dolar['baja']:
        return "Vender en primeras páginas y posicionarse lejos para comprar"
    else:
        return "Estrategia no definida"

def main():
    # Tomar el primer precio
    previous_binance_p2p_price_bid, previous_binance_p2p_price_ask = get_binance_p2p_price()
    previous_binance_price_bid, previous_binance_price_ask = get_binance_price()
    previous_okx_price_bid, previous_okx_price_ask = get_okx_price()
    previous_general_dollar_price, previous_ccl_al30, previous_ccl_gd30 = get_general_dollar_price()

    if None in [previous_binance_p2p_price_bid, previous_binance_price_bid, previous_okx_price_bid, previous_general_dollar_price]:
        print("No se pudo obtener alguno de los precios iniciales. Verifica las URLs y el acceso a las APIs.")
        return

    print(f"Precio inicial en Binance P2P (Bid): {previous_binance_p2p_price_bid} ARS")
    print(f"Precio inicial en Binance (Venta) (Bid): {previous_binance_price_bid} ARS")
    print(f"Precio inicial en OKX (Bid): {previous_okx_price_bid} ARS")
    print(f"Precio inicial del dólar general (Bid): {previous_general_dollar_price} ARS")

    # Esperar 10 minutos
    print("Esperando 10 minutos...")
    time.sleep(600)  # Esperar 10 minutos

    # Tomar el precio nuevamente después de 10 minutos
    current_binance_p2p_price_bid, current_binance_p2p_price_ask = get_binance_p2p_price()
    current_binance_price_bid, current_binance_price_ask = get_binance_price()
    current_okx_price_bid, current_okx_price_ask = get_okx_price()
    current_general_dollar_price, current_ccl_al30, current_ccl_gd30 = get_general_dollar_price()

    binance_p2p_trend = analyze_trend(current_binance_p2p_price_bid, previous_binance_p2p_price_bid)
    binance_trend = analyze_trend(current_binance_price_bid, previous_binance_price_bid)
    okx_trend = analyze_trend(current_okx_price_bid, previous_okx_price_bid)
    general_dollar_trend = analyze_trend(current_general_dollar_price, previous_general_dollar_price)

    # Determinar la estrategia basada en la liquidez
    liquidez = {
        'cambio_precios_rapido': current_binance_p2p_price_bid != previous_binance_p2p_price_bid  # Si los precios cambian rápido
    }
    estrategia_liquidez = determine_strategy_liquidity(liquidez)

    # Determinar la estrategia basada en el precio del dólar
    precio_dolar = {
        'sube': current_general_dollar_price > previous_general_dollar_price,
        'baja': current_general_dollar_price < previous_general_dollar_price
    }
    estrategia_dolar = determine_strategy_dollar(precio_dolar)

    # Mostrar resultados
    print(f"Tendencia en Binance P2P (Bid): {binance_p2p_trend}")
    print(f"Tendencia en Binance (Venta) (Bid): {binance_trend}")
    print(f"Tendencia en OKX (Bid): {okx_trend}")
    print(f"Tendencia del dólar general (Bid): {general_dollar_trend}")

    print(f"Estrategia basada en liquidez: {estrategia_liquidez}")
    print(f"Estrategia basada en el precio del dólar: {estrategia_dolar}")

if __name__ == "__main__":
    main()
