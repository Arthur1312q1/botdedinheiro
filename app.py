#!/usr/bin/env python3
"""
App.py - Servidor web + Bot de trading para Render.com
Combina servidor HTTP (para satisfazer Render) com bot de trading
"""

from main import BitgetTradingBot
import logging
import sys
import os
import threading
from flask import Flask, jsonify
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Criar app Flask
app = Flask(__name__)

# Variáveis globais para status do bot
bot_instance = None
bot_status = {
    'running': False,
    'last_update': None,
    'current_price': 0,
    'current_position': None,
    'error_count': 0
}

@app.route('/')
def home():
    """Página inicial com status do bot"""
    return jsonify({
        'status': 'Bot de Trading Bitget',
        'running': bot_status['running'],
        'last_update': bot_status['last_update'],
        'current_price': bot_status['current_price'],
        'current_position': bot_status['current_position'],
        'error_count': bot_status['error_count'],
        'timestamp': datetime.now().isoformat()
    })

@app.route('/status')
def status():
    """Endpoint de status detalhado"""
    return jsonify(bot_status)

@app.route('/health')
def health():
    """Health check para Render.com"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

def update_bot_status(running=None, price=None, position=None, error=False):
    """Atualiza o status global do bot"""
    global bot_status
    if running is not None:
        bot_status['running'] = running
    if price is not None:
        bot_status['current_price'] = price
    if position is not None:
        bot_status['current_position'] = position
    if error:
        bot_status['error_count'] += 1
    bot_status['last_update'] = datetime.now().isoformat()

def run_bot():
    """Executa o bot em thread separada"""
    global bot_instance
    try:
        logger.info("🚀 Iniciando Bot de Trading Bitget...")
        
        # Verificar variáveis de ambiente
        required_vars = ['BITGET_API_KEY', 'BITGET_SECRET', 'BITGET_PASSPHRASE']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            logger.error(f"❌ Variáveis de ambiente não encontradas: {missing_vars}")
            update_bot_status(running=False, error=True)
            return
        
        logger.info("✅ Variáveis de ambiente configuradas")
        
        # Modificar a classe BitgetTradingBot para atualizar status
        class MonitoredBot(BitgetTradingBot):
            def run_strategy(self):
                try:
                    result = super().run_strategy()
                    # Atualizar status após cada execução
                    df = self.get_candles()
                    if df is not None and not df.empty:
                        current_price = df['close'].iloc[-1]
                        current_position = self.get_current_position()
                        position_info = None
                        if current_position:
                            position_info = {
                                'side': current_position.get('side'),
                                'size': current_position.get('size'),
                                'entry_price': current_position.get('entryPrice')
                            }
                        update_bot_status(running=True, price=current_price, position=position_info)
                    return result
                except Exception as e:
                    logger.error(f"Erro na estratégia: {e}")
                    update_bot_status(error=True)
                    raise
        
        # Inicializar e executar bot
        bot_instance = MonitoredBot()
        update_bot_status(running=True)
        bot_instance.run()
        
    except Exception as e:
        logger.error(f"💥 Erro fatal no bot: {e}")
        update_bot_status(running=False, error=True)

def main():
    """Função principal - inicia servidor web e bot"""
    # Iniciar bot em thread separada
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Iniciar servidor Flask
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🌐 Iniciando servidor web na porta {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == "__main__":
    main()
