from flask import Flask, jsonify, render_template_string
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
    'error': None,
    'pnl': 0.0,
    'entry_price': None,
    'current_price': None
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
                bot_status['entry_price'] = trading_bot.entry_price
                bot_status['error'] = None
                
                # Calcular PnL se houver posição
                if trading_bot.current_position and trading_bot.entry_price:
                    try:
                        ticker = trading_bot.exchange.fetch_ticker(trading_bot.symbol)
                        current_price = float(ticker['last'])
                        bot_status['current_price'] = current_price
                        
                        pnl_pct = ((current_price - trading_bot.entry_price) / trading_bot.entry_price) * 100
                        if trading_bot.current_position == 'short':
                            pnl_pct *= -1
                        bot_status['pnl'] = pnl_pct
                    except:
                        bot_status['pnl'] = 0.0
                
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

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Bot Control Panel</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72, #2a5298);
            color: white;
            min-height: 100vh;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            text-align: center;
            margin-bottom: 40px;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .card {
            background: rgba(255,255,255,0.1);
            border-radius: 15px;
            padding: 25px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        
        .card h3 {
            margin-bottom: 15px;
            color: #64ffda;
        }
        
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }
        
        .status-running {
            background-color: #4caf50;
            animation: pulse 2s infinite;
        }
        
        .status-stopped {
            background-color: #f44336;
        }
        
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        
        .control-buttons {
            display: flex;
            gap: 15px;
            justify-content: center;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }
        
        .btn {
            padding: 15px 30px;
            border: none;
            border-radius: 25px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
            text-align: center;
            min-width: 120px;
        }
        
        .btn-start {
            background: linear-gradient(45deg, #4caf50, #45a049);
            color: white;
        }
        
        .btn-start:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(76, 175, 80, 0.4);
        }
        
        .btn-stop {
            background: linear-gradient(45deg, #f44336, #d32f2f);
            color: white;
        }
        
        .btn-stop:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(244, 67, 54, 0.4);
        }
        
        .btn-refresh {
            background: linear-gradient(45deg, #2196f3, #1976d2);
            color: white;
        }
        
        .btn-refresh:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(33, 150, 243, 0.4);
        }
        
        .position-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        
        .info-item {
            text-align: center;
            padding: 15px;
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
        }
        
        .info-label {
            font-size: 0.9em;
            opacity: 0.8;
            margin-bottom: 5px;
        }
        
        .info-value {
            font-size: 1.2em;
            font-weight: bold;
        }
        
        .pnl-positive {
            color: #4caf50;
        }
        
        .pnl-negative {
            color: #f44336;
        }
        
        .error-message {
            background: rgba(244, 67, 54, 0.2);
            border: 1px solid #f44336;
            border-radius: 10px;
            padding: 15px;
            margin-top: 20px;
            word-break: break-word;
        }
        
        .logs {
            background: rgba(0,0,0,0.3);
            border-radius: 10px;
            padding: 20px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            max-height: 400px;
            overflow-y: auto;
            border: 1px solid rgba(255,255,255,0.1);
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .header h1 {
                font-size: 2em;
            }
            
            .control-buttons {
                flex-direction: column;
                align-items: center;
            }
            
            .btn {
                width: 100%;
                max-width: 300px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Trading Bot Control Panel</h1>
            <p>ETH/USDT Perpetual Futures - Bitget</p>
        </div>
        
        <div class="control-buttons">
            <button class="btn btn-start" onclick="startBot()">Iniciar Bot</button>
            <button class="btn btn-stop" onclick="stopBot()">Parar Bot</button>
            <button class="btn btn-refresh" onclick="refreshStatus()">Atualizar</button>
        </div>
        
        <div class="status-grid">
            <div class="card">
                <h3>Status do Sistema</h3>
                <div id="bot-status">
                    <span class="status-indicator" id="status-indicator"></span>
                    <span id="status-text">Carregando...</span>
                </div>
                <div style="margin-top: 15px;">
                    <div class="info-label">Última Atualização:</div>
                    <div class="info-value" id="last-update">-</div>
                </div>
            </div>
            
            <div class="card">
                <h3>Posição Atual</h3>
                <div class="position-info">
                    <div class="info-item">
                        <div class="info-label">Posição</div>
                        <div class="info-value" id="current-position">-</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Preço de Entrada</div>
                        <div class="info-value" id="entry-price">-</div>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h3>Performance</h3>
                <div class="position-info">
                    <div class="info-item">
                        <div class="info-label">Preço Atual</div>
                        <div class="info-value" id="current-price">-</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">P&L (%)</div>
                        <div class="info-value" id="pnl">-</div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h3>Logs do Sistema</h3>
            <div class="logs" id="system-logs">
                Sistema iniciado. Aguardando comandos...
            </div>
        </div>
        
        <div id="error-container"></div>
    </div>
    
    <script>
        let logMessages = [];
        
        function addLog(message) {
            const timestamp = new Date().toLocaleTimeString();
            logMessages.push(`[${timestamp}] ${message}`);
            if (logMessages.length > 50) {
                logMessages.shift();
            }
            document.getElementById('system-logs').innerHTML = logMessages.join('\\n');
            document.getElementById('system-logs').scrollTop = document.getElementById('system-logs').scrollHeight;
        }
        
        async function startBot() {
            try {
                addLog('Enviando comando para iniciar o bot...');
                const response = await fetch('/start');
                const data = await response.json();
                addLog(`Resposta: ${data.message}`);
                setTimeout(refreshStatus, 2000);
            } catch (error) {
                addLog(`Erro ao iniciar bot: ${error.message}`);
            }
        }
        
        async function stopBot() {
            try {
                addLog('Enviando comando para parar o bot...');
                const response = await fetch('/stop');
                const data = await response.json();
                addLog(`Resposta: ${data.message}`);
                setTimeout(refreshStatus, 2000);
            } catch (error) {
                addLog(`Erro ao parar bot: ${error.message}`);
            }
        }
        
        async function refreshStatus() {
            try {
                const response = await fetch('/status');
                const status = await response.json();
                
                // Atualizar indicador de status
                const indicator = document.getElementById('status-indicator');
                const statusText = document.getElementById('status-text');
                
                if (status.running) {
                    indicator.className = 'status-indicator status-running';
                    statusText.textContent = 'Bot Rodando';
                } else {
                    indicator.className = 'status-indicator status-stopped';
                    statusText.textContent = 'Bot Parado';
                }
                
                // Atualizar informações
                document.getElementById('last-update').textContent = status.last_update || '-';
                document.getElementById('current-position').textContent = status.current_position || 'Nenhuma';
                document.getElementById('entry-price').textContent = status.entry_price ? `$${status.entry_price.toFixed(4)}` : '-';
                document.getElementById('current-price').textContent = status.current_price ? `$${status.current_price.toFixed(4)}` : '-';
                
                // Atualizar P&L
                const pnlElement = document.getElementById('pnl');
                if (status.pnl !== undefined && status.pnl !== 0) {
                    pnlElement.textContent = `${status.pnl > 0 ? '+' : ''}${status.pnl.toFixed(2)}%`;
                    pnlElement.className = status.pnl > 0 ? 'info-value pnl-positive' : 'info-value pnl-negative';
                } else {
                    pnlElement.textContent = '-';
                    pnlElement.className = 'info-value';
                }
                
                // Mostrar erros
                const errorContainer = document.getElementById('error-container');
                if (status.error) {
                    errorContainer.innerHTML = `<div class="error-message"><strong>Erro:</strong> ${status.error}</div>`;
                } else {
                    errorContainer.innerHTML = '';
                }
                
                addLog('Status atualizado');
                
            } catch (error) {
                addLog(`Erro ao atualizar status: ${error.message}`);
            }
        }
        
        // Atualizar status automaticamente a cada 30 segundos
        setInterval(refreshStatus, 30000);
        
        // Carregar status inicial
        refreshStatus();
        
        addLog('Interface carregada. Sistema pronto.');
    </script>
</body>
</html>
'''

@app.route('/')
def home():
    """Página inicial com interface completa"""
    return render_template_string(HTML_TEMPLATE)

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
        return jsonify({'message': 'Bot iniciado com sucesso'})
    else:
        return jsonify({'message': 'Bot já está rodando'})

@app.route('/stop')
def stop_bot():
    """Para o bot manualmente"""
    global bot_status
    
    if bot_status['running']:
        bot_status['running'] = False
        return jsonify({'message': 'Comando de parada enviado'})
    else:
        return jsonify({'message': 'Bot já está parado'})

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

@app.route('/force-close')
def force_close():
    """Força o fechamento da posição atual"""
    if trading_bot and trading_bot.current_position:
        try:
            success = trading_bot.close_position()
            if success:
                return jsonify({'message': 'Posição fechada com sucesso'})
            else:
                return jsonify({'error': 'Falha ao fechar posição'})
        except Exception as e:
            return jsonify({'error': str(e)})
    else:
        return jsonify({'error': 'Nenhuma posição ativa ou bot não inicializado'})

if __name__ == '__main__':
    # Não iniciar o bot automaticamente no startup
    # Deixar para o usuário decidir via interface
    
    # Iniciar o servidor Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
