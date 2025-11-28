"""
Gerador de Sinais Automáticos - Simula sinais do TradingView
Execute este script em um servidor externo para gerar sinais automaticamente

ATENÇÃO: Este é um script de TESTE. Para produção, use sinais reais do TradingView.
"""

import requests
import time
import random
from datetime import datetime

# CONFIGURAÇÃO
APP_URL = "https://seu-app.onrender.com"  # Substitua pela URL do seu app no Render
SIGNAL_INTERVAL = 10  # Segundos entre cada sinal
ENABLE_AUTO_TRADING = True  # True para enviar sinais automaticamente

# Simulação de preços ETH/USDT
INITIAL_PRICE = 3500.0
current_price = INITIAL_PRICE
position_open = False

def generate_realistic_price():
    """Gera um preço realista com volatilidade"""
    global current_price
    
    # Variação entre -2% e +2%
    variation = random.uniform(-0.02, 0.02)
    current_price = current_price * (1 + variation)
    
    # Mantém entre limites razoáveis
    current_price = max(2000, min(5000, current_price))
    
    return round(current_price, 2)

def send_signal(action, price):
    """Envia um sinal de compra ou venda"""
    
    payload = {
        "data": {
            "action": action,
            "contracts": "1",
            "position_size": "1"
        },
        "price": str(price),
        "signal_param": "{}",
        "signal_type": "759155c9-0c69-4169-9f19-0d09394bbaf1",
        "symbol": "ETHUSDT",
        "time": datetime.now().isoformat()
    }
    
    try:
        response = requests.post(
            f"{APP_URL}/webhook",
            json=payload,
            timeout=5
        )
        
        status = "✓" if response.status_code == 200 else "✗"
        emoji = "🟢" if action.lower() == "buy" else "🔴"
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {status} {emoji} {action.upper()} @ ${price:.2f} - Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if 'profit_loss' in result:
                profit = result['profit_loss']
                profit_emoji = "💰" if profit > 0 else "📉"
                print(f"    └─ {profit_emoji} P&L: ${profit:.2f} ({result.get('profit_percentage', 0):.2f}%)")
        
        return response.status_code == 200
        
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ Erro ao enviar sinal: {e}")
        return False

def trading_strategy():
    """Estratégia de trading simples (para teste)"""
    global position_open
    
    price = generate_realistic_price()
    
    # Estratégia simples: abre posição em 30% das vezes, fecha em 70%
    if not position_open:
        if random.random() < 0.3:  # 30% de chance de abrir posição
            send_signal("buy", price)
            position_open = True
    else:
        if random.random() < 0.7:  # 70% de chance de fechar posição
            send_signal("sell", price)
            position_open = False

def main():
    """Loop principal de geração de sinais"""
    print("🤖 Gerador de Sinais Automáticos Iniciado")
    print(f"🎯 URL: {APP_URL}")
    print(f"⏱️  Intervalo: {SIGNAL_INTERVAL} segundos")
    print(f"💰 Preço Inicial ETH: ${INITIAL_PRICE:.2f}")
    print("-" * 60)
    print()
    
    if not ENABLE_AUTO_TRADING:
        print("⚠️  Trading automático DESABILITADO. Apenas enviando pings...")
        print()
    
    while True:
        try:
            if ENABLE_AUTO_TRADING:
                trading_strategy()
            else:
                # Apenas envia ping se trading estiver desabilitado
                requests.get(f"{APP_URL}/ping", timeout=5)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 📡 Ping enviado")
            
            time.sleep(SIGNAL_INTERVAL)
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Script interrompido pelo usuário")
            break
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Erro: {e}")
            time.sleep(SIGNAL_INTERVAL)

if __name__ == "__main__":
    print()
    print("=" * 60)
    print("  GERADOR DE SINAIS AUTOMÁTICOS - PAPER TRADING ETH/USDT")
    print("=" * 60)
    print()
    
    # Menu de opções
    print("Escolha o modo de operação:")
    print("1. Apenas Ping (mantém serviço ativo)")
    print("2. Trading Automático (envia sinais de compra/venda)")
    print()
    
    choice = input("Digite sua escolha (1 ou 2): ").strip()
    
    if choice == "1":
        ENABLE_AUTO_TRADING = False
        print("\n✓ Modo: APENAS PING")
    else:
        ENABLE_AUTO_TRADING = True
        print("\n✓ Modo: TRADING AUTOMÁTICO")
    
    print()
    
    try:
        main()
    except Exception as e:
        print(f"\n\n❌ Erro crítico: {e}")
