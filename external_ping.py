"""
Script de Ping Externo - Para manter o serviço ativo 24/7
Execute este script em um servidor externo (ex: seu computador, VPS, ou outro serviço)

Este script enviará um ping a cada 10 segundos para manter o serviço ativo.
"""

import requests
import time
from datetime import datetime

# CONFIGURAÇÃO
APP_URL = "https://seu-app.onrender.com"  # Substitua pela URL do seu app no Render
PING_INTERVAL = 10  # Segundos entre cada ping

def send_ping():
    """Envia um ping para o endpoint /ping"""
    try:
        response = requests.get(f"{APP_URL}/ping", timeout=5)
        status = "✓" if response.status_code == 200 else "✗"
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {status} Ping enviado - Status: {response.status_code}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✗ Erro ao enviar ping: {e}")
        return False

def main():
    """Loop principal de ping"""
    print(f"🚀 Iniciando ping externo para {APP_URL}")
    print(f"📡 Intervalo: {PING_INTERVAL} segundos")
    print("-" * 60)
    
    while True:
        send_ping()
        time.sleep(PING_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Script interrompido pelo usuário")
    except Exception as e:
        print(f"\n\n❌ Erro crítico: {e}")
