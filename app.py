from flask import Flask, jsonify
import threading
import time
import os
from bot import TradingBot

app = Flask(__name__)

# Instância global do bot
trading_bot = None
bot_thread = None
bot_status = {
    'running': False,
    'last_update': None,
    'current_position': None,
    'error': None
}

def run_bot():
    """Executa o bot em uma thread separada"""
    global trading_bot, bot_status
    
    try:
        trading_bot = TradingBot()
        bot_status['running'] = True
        bot_status['error'] = None
        
        # Loop principal do bot
        while bot_status['running']:
            try:
                trading_bot.run_strategy()
                bot_status['last_update'] = time.strftime('%Y-%m-%d %H:%M:%S')
                bot_status['current_position'] = trading_bot.current_position
                bot_status['error'] = None
                
                # Aguardar 5 minutos
                time.sleep(300)
                
            except Exception as e:
                bot_status['error'] = str(e)
                print(f"Erro na execução do bot: {e}")
                time.sleep(30)  # Aguarda 30 segundos em caso de erro
                
    except Exception as e:
        bot_status['running'] = False
        bot_status['error'] = str(e)
        print(f"Erro fatal no bot: {e}")

@app.route('/')
def home():
    """Página inicial com status do bot"""
    return jsonify({
        'message': 'Trading Bot is running',
        'status': bot_status,
        'version': '1.0.0'
    })

@app.route('/status')
def status():
    """Endpoint para verificar o status do bot"""
    return jsonify(bot_status)

@app.route('/health')
def health():
    """Health check para o Render"""
    return jsonify({
        'status': 'healthy',
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/start')
def start_bot():
    """Inicia o bot manualmente"""
    global bot_thread, bot_status
    
    if not bot_status['running']:
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        return jsonify({'message': 'Bot started successfully'})
    else:
        return jsonify({'message': 'Bot is already running'})

@app.route('/stop')
def stop_bot():
    """Para o bot manualmente"""
    global bot_status
    
    bot_status['running'] = False
    return jsonify({'message': 'Bot stop signal sent'})

@app.route('/position')
def get_position():
    """Retorna informações da posição atual"""
    if trading_bot:
        try:
            position_info = trading_bot.get_position_info()
            return jsonify({
                'current_position': trading_bot.current_position,
                'entry_price': trading_bot.entry_price,
                'position_size': trading_bot.position_size,
                'exchange_position': position_info
            })
        except Exception as e:
            return jsonify({'error': str(e)})
    else:
        return jsonify({'error': 'Bot not initialized'})

if __name__ == '__main__':
    # Iniciar o bot automaticamente
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Iniciar o servidor Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
