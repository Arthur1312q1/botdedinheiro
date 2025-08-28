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
from flask import Flask, jsonify, render_template_string
from datetime import datetime
import time

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

# Variáveis globais para controle do bot
bot_instance = None
bot_thread = None
bot_status = {
    'running': False,
    'last_update': None,
    'current_price': 0,
    'current_position': None,
    'error_count': 0,
    'started_at': None,
    'manual_stop': False
}

# Template HTML para interface web
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bot de Trading Bitget</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { 
            background: white; 
            padding: 30px; 
            border-radius: 15px; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            margin-bottom: 30px;
            text-align: center;
        }
        .header h1 { color: #4a5568; margin-bottom: 10px; font-size: 2.5em; }
        .header p { color: #718096; font-size: 1.1em; }
        .status-grid { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); 
            gap: 20px; 
            margin-bottom: 30px;
        }
        .status-card { 
            background: white; 
            padding: 25px; 
            border-radius: 15px; 
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
        }
        .status-card h3 { 
            color: #4a5568; 
            margin-bottom: 15px; 
            font-size: 1.3em;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 10px;
        }
        .status-item { 
            display: flex; 
            justify-content: space-between; 
            margin-bottom: 12px; 
            padding: 8px 0;
        }
        .status-item strong { color: #2d3748; }
        .status-running { color: #38a169; font-weight: bold; }
        .status-stopped { color: #e53e3e; font-weight: bold; }
        .price { color: #3182ce; font-weight: bold; font-size: 1.1em; }
        .position-long { color: #38a169; font-weight: bold; }
        .position-short { color: #e53e3e; font-weight: bold; }
        .position-none { color: #718096; }
        .controls { 
            background: white; 
            padding: 30px; 
            border-radius: 15px; 
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
            text-align: center;
            margin-bottom: 30px;
        }
        .btn { 
            padding: 15px 30px; 
            border: none; 
            border-radius: 8px; 
            font-size: 1.1em; 
            font-weight: bold; 
            cursor: pointer; 
            margin: 0 10px;
            transition: all 0.3s ease;
            min-width: 150px;
        }
        .btn-start { 
            background: linear-gradient(135deg, #38a169, #48bb78); 
            color: white; 
        }
        .btn-start:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(56, 161, 105, 0.4); }
        .btn-stop { 
            background: linear-gradient(135deg, #e53e3e, #fc8181); 
            color: white; 
        }
        .btn-stop:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(229, 62, 62, 0.4); }
        .btn-refresh { 
            background: linear-gradient(135deg, #3182ce, #63b3ed); 
            color: white; 
        }
        .btn-refresh:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(49, 130, 206, 0.4); }
        .btn:disabled { 
            opacity: 0.6; 
            cursor: not-allowed; 
            transform: none !important;
            box-shadow: none !important;
        }
        .logs { 
            background: #1a202c; 
            color: #e2e8f0; 
            padding: 20px; 
            border-radius: 10px; 
            font-family: 'Courier New', monospace; 
            font-size: 0.9em;
            max-height: 400px;
            overflow-y: auto;
        }
        .auto-refresh { 
            color: #718096; 
            font-size: 0.9em; 
            margin-top: 15px;
        }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.7; } 100% { opacity: 1; } }
        .pulse { animation: pulse 2s infinite; }
        .footer {
            text-align: center;
            color: white;
            padding: 20px;
            font-size: 0.9em;
            opacity: 0.8;
        }
    </style>
    <script>
        function refreshStatus() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('status-data').innerHTML = JSON.stringify(data, null, 2);
                    updateStatusCards(data);
                })
                .catch(error => console.error('Erro:', error));
        }
        
        function updateStatusCards(data) {
            document.getElementById('running-status').className = data.running ? 'status-running' : 'status-stopped';
            document.getElementById('running-status').textContent = data.running ? 'RODANDO' : 'PARADO';
            
            document.getElementById('current-price').textContent = data.current_price ? `${data.current_price.toFixed(2)}` : 'N/A';
            
            const posElement = document.getElementById('current-position');
            if (data.current_position && data.current_position.side) {
                posElement.className = data.current_position.side === 'long' ? 'position-long' : 'position-short';
                posElement.textContent = `${data.current_position.side.toUpperCase()} (${data.current_position.size})`;
            } else {
                posElement.className = 'position-none';
                posElement.textContent = 'NENHUMA';
            }
            
            document.getElementById('last-update').textContent = data.last_update || 'Nunca';
            document.getElementById('error-count').textContent = data.error_count || 0;
            
            // Atualizar botões
            const startBtn = document.getElementById('start-btn');
            const stopBtn = document.getElementById('stop-btn');
            
            if (data.running) {
                startBtn.disabled = true;
                stopBtn.disabled = false;
            } else {
                startBtn.disabled = false;
                stopBtn.disabled = true;
            }
        }
        
        function startBot() {
            fetch('/start', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    refreshStatus();
                })
                .catch(error => {
                    console.error('Erro:', error);
                    alert('Erro ao iniciar bot');
                });
        }
        
        function stopBot() {
            fetch('/stop', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    refreshStatus();
                })
                .catch(error => {
                    console.error('Erro:', error);
                    alert('Erro ao parar bot');
                });
        }
        
        // Auto refresh a cada 30 segundos
        setInterval(refreshStatus, 30000);
        
        // Carregar status inicial
        window.onload = refreshStatus;
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Bot de Trading Bitget</h1>
            <p>ETH/USDT Futures • Supertrend + EMA • Alavancagem 10x</p>
        </div>
        
        <div class="status-grid">
            <div class="status-card">
                <h3>📊 Status Geral</h3>
                <div class="status-item">
                    <span>Status:</span>
                    <span id="running-status" class="status-stopped">PARADO</span>
                </div>
                <div class="status-item">
                    <span>Preço ETH/USDT:</span>
                    <span id="current-price" class="price">$0.00</span>
                </div>
                <div class="status-item">
                    <span>Última Atualização:</span>
                    <span id="last-update">Nunca</span>
                </div>
            </div>
            
            <div class="status-card">
                <h3>💼 Posição Atual</h3>
                <div class="status-item">
                    <span>Posição:</span>
                    <span id="current-position" class="position-none">NENHUMA</span>
                </div>
                <div class="status-item">
                    <span>Erros:</span>
                    <span id="error-count">0</span>
                </div>
                <div class="status-item">
                    <span>Alavancagem:</span>
                    <span>10x</span>
                </div>
            </div>
        </div>
        
        <div class="controls">
            <h3 style="margin-bottom: 20px; color: #4a5568;">🎮 Controles do Bot</h3>
            <button id="start-btn" class="btn btn-start" onclick="startBot()">▶️ INICIAR BOT</button>
            <button id="stop-btn" class="btn btn-stop" onclick="stopBot()">⏹️ PARAR BOT</button>
            <button class="btn btn-refresh" onclick="refreshStatus()">🔄 ATUALIZAR</button>
            <div class="auto-refresh">
                <p>• A página atualiza automaticamente a cada 30 segundos</p>
                <p>• O bot analisa o mercado a cada 5 minutos</p>
            </div>
        </div>
        
        <div class="status-card">
            <h3>📋 Status Detalhado (JSON)</h3>
            <div class="logs">
                <pre id="status-data">Carregando...</pre>
            </div>
        </div>
        
        <div class="footer">
            <p>⚠️ <strong>AVISO:</strong> Trading com alavancagem envolve alto risco. Use apenas capital que pode perder.</p>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    """Interface web principal"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/status')
def status():
    """Endpoint de status em JSON"""
    return jsonify(bot_status)

@app.route('/start', methods=['POST'])
def start_bot():
    """Inicia o bot"""
    global bot_thread, bot_status
    
    if bot_status['running']:
        return jsonify({'success': False, 'message': 'Bot já está rodando!'})
    
    try:
        bot_status['manual_stop'] = False
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        
        logger.info("🚀 Bot iniciado via interface web")
        return jsonify({'success': True, 'message': 'Bot iniciado com sucesso!'})
    except Exception as e:
        logger.error(f"Erro ao iniciar bot: {e}")
        return jsonify({'success': False, 'message': f'Erro ao iniciar: {e}'})

@app.route('/stop', methods=['POST'])
def stop_bot():
    """Para o bot"""
    global bot_status
    
    if not bot_status['running']:
        return jsonify({'success': False, 'message': 'Bot já está parado!'})
    
    try:
        bot_status['manual_stop'] = True
        bot_status['running'] = False
        
        logger.info("🛑 Bot parado via interface web")
        return jsonify({'success': True, 'message': 'Bot parado com sucesso!'})
    except Exception as e:
        logger.error(f"Erro ao parar bot: {e}")
        return jsonify({'success': False, 'message': f'Erro ao parar: {e}'})

@app.route('/health')
def health():
    """Health check para Render.com"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

def update_bot_status(running=None, price=None, position=None, error=False):
    """Atualiza o status global do bot"""
    global bot_status
    if running is not None:
        bot_status['running'] = running
        if running and not bot_status['started_at']:
            bot_status['started_at'] = datetime.now().isoformat()
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
            
            def run(self):
                """Loop principal modificado para permitir parada manual"""
                logger.info("Bot iniciado!")
                logger.info(f"Par: {self.symbol}")
                logger.info(f"Timeframe: {self.timeframe}")
                logger.info(f"Alavancagem: {self.leverage}x")
                logger.info(f"Stop Loss: {self.stop_loss_pct*100}%")
                
                update_bot_status(running=True)
                
                while not bot_status['manual_stop']:
                    try:
                        logger.info("=" * 50)
                        logger.info(f"Executando análise - {datetime.now()}")
                        self.run_strategy()
                        logger.info("Aguardando 5 minutos para próxima análise...")
                        
                        # Sleep em chunks para permitir parada mais rápida
                        for _ in range(60):  # 60 chunks de 5 segundos = 5 minutos
                            if bot_status['manual_stop']:
                                break
                            time.sleep(5)
                        
                    except KeyboardInterrupt:
                        logger.info("Bot interrompido pelo usuário")
                        break
                    except Exception as e:
                        logger.error(f"Erro no loop principal: {e}")
                        update_bot_status(error=True)
                        logger.info("Aguardando 1 minuto antes de tentar novamente...")
                        time.sleep(60)
                
                update_bot_status(running=False)
                logger.info("🛑 Bot parado")
        
        # Inicializar e executar bot
        bot_instance = MonitoredBot()
        bot_instance.run()
        
    except Exception as e:
        logger.error(f"💥 Erro fatal no bot: {e}")
        update_bot_status(running=False, error=True)

def main():
    """Função principal - inicia apenas o servidor web"""
    # Iniciar servidor Flask
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🌐 Iniciando servidor web na porta {port}")
    logger.info(f"🎮 Interface disponível em: http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == "__main__":
    main()
