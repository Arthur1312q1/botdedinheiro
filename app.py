from flask import Flask, jsonify, render_template_string, request
import threading
import time
import os
import traceback
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
    'current_price': None,
    'signal_strength': 0,
    'position_duration': 0,
    'trades_today': 0,
    'total_trades': 0,
    'successful_trades': 0,
    'win_rate': 0.0,
    'last_trade_result': None
}

def run_bot():
    """Executa o bot em uma thread separada com melhor controle de erros"""
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
                bot_status['total_trades'] = trading_bot.total_trades
                bot_status['successful_trades'] = trading_bot.successful_trades
                bot_status['error'] = None
                
                # Calcular win rate
                if trading_bot.total_trades > 0:
                    bot_status['win_rate'] = (trading_bot.successful_trades / trading_bot.total_trades) * 100
                else:
                    bot_status['win_rate'] = 0.0
                
                # Obter preço atual sempre
                try:
                    ticker = trading_bot.exchange.fetch_ticker(trading_bot.symbol)
                    current_price = float(ticker['last'])
                    bot_status['current_price'] = current_price
                    
                    # Calcular P&L se houver posição
                    if trading_bot.current_position and trading_bot.entry_price:
                        pnl_pct = ((current_price - trading_bot.entry_price) / trading_bot.entry_price) * 100
                        if trading_bot.current_position == 'short':
                            pnl_pct *= -1
                        bot_status['pnl'] = round(pnl_pct, 2)
                        
                        # Calcular duração da posição
                        if trading_bot.position_start_time:
                            duration_minutes = (time.time() - trading_bot.position_start_time) / 60
                            bot_status['position_duration'] = round(duration_minutes, 1)
                    else:
                        bot_status['pnl'] = 0.0
                        bot_status['position_duration'] = 0
                        
                except Exception as price_error:
                    print(f"Erro ao obter preço: {price_error}")
                    bot_status['current_price'] = None
                    bot_status['pnl'] = 0.0
                
                # Aguardar 90 segundos (timeframe 3m otimizado)
                time.sleep(90)
                
            except Exception as e:
                bot_status['error'] = str(e)
                print(f"Erro na execução do bot: {e}")
                print(f"Traceback: {traceback.format_exc()}")
                time.sleep(30)  # Aguarda 30 segundos em caso de erro
                
    except Exception as e:
        bot_status['running'] = False
        bot_status['error'] = str(e)
        print(f"Erro fatal no bot: {e}")
        print(f"Traceback: {traceback.format_exc()}")

def get_current_price():
    """Função auxiliar para obter preço atual"""
    try:
        if trading_bot and trading_bot.exchange:
            ticker = trading_bot.exchange.fetch_ticker('ETHUSDT_UMCBL')
            return float(ticker['last'])
    except Exception as e:
        print(f"Erro ao obter preço atual: {e}")
    return None

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Bot - Estratégia de Reversão Contínua</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0f1419, #1e2328);
            color: white;
            min-height: 100vh;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
        }
        
        .header h1 {
            font-size: 2.2em;
            margin-bottom: 10px;
            background: linear-gradient(45deg, #f0b90b, #ff6b35);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .header p {
            opacity: 0.8;
            font-size: 1.1em;
        }
        
        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 25px;
        }
        
        .card {
            background: rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 20px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
            position: relative;
            overflow: hidden;
        }
        
        .card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, #f0b90b, #ff6b35);
        }
        
        .card h3 {
            margin-bottom: 15px;
            color: #f0b90b;
            font-size: 1.1em;
        }
        
        .status-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 8px;
        }
        
        .status-running {
            background-color: #10b981;
            animation: pulse 1.5s infinite;
        }
        
        .status-stopped {
            background-color: #ef4444;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }
        
        .control-buttons {
            display: flex;
            gap: 15px;
            justify-content: center;
            margin-bottom: 25px;
            flex-wrap: wrap;
        }
        
        .btn {
            padding: 12px 25px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
            text-align: center;
            min-width: 100px;
        }
        
        .btn-start {
            background: linear-gradient(45deg, #10b981, #059669);
            color: white;
        }
        
        .btn-start:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.4);
        }
        
        .btn-stop {
            background: linear-gradient(45deg, #ef4444, #dc2626);
            color: white;
        }
        
        .btn-stop:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(239, 68, 68, 0.4);
        }
        
        .btn-refresh {
            background: linear-gradient(45deg, #3b82f6, #2563eb);
            color: white;
        }
        
        .btn-refresh:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
        }
        
        .btn-close {
            background: linear-gradient(45deg, #f59e0b, #d97706);
            color: white;
        }
        
        .btn-close:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(245, 158, 11, 0.4);
        }
        
        .position-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 12px;
        }
        
        .info-item {
            text-align: center;
            padding: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
        }
        
        .info-label {
            font-size: 0.85em;
            opacity: 0.7;
            margin-bottom: 4px;
        }
        
        .info-value {
            font-size: 1.1em;
            font-weight: 600;
        }
        
        .pnl-positive {
            color: #10b981;
        }
        
        .pnl-negative {
            color: #ef4444;
        }
        
        .position-long {
            color: #10b981;
        }
        
        .position-short {
            color: #ef4444;
        }
        
        .error-message {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid #ef4444;
            border-radius: 8px;
            padding: 15px;
            margin-top: 20px;
            word-break: break-word;
        }
        
        .logs {
            background: rgba(0,0,0,0.4);
            border-radius: 8px;
            padding: 15px;
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
            max-height: 300px;
            overflow-y: auto;
            border: 1px solid rgba(255,255,255,0.1);
            white-space: pre-wrap;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 10px;
            margin-top: 15px;
        }
        
        .stat-item {
            text-align: center;
            padding: 10px;
            background: rgba(255,255,255,0.05);
            border-radius: 6px;
        }
        
        .win-rate-positive {
            color: #10b981;
        }
        
        .win-rate-negative {
            color: #ef4444;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .header h1 {
                font-size: 1.8em;
            }
            
            .control-buttons {
                flex-direction: column;
                align-items: center;
            }
            
            .btn {
                width: 100%;
                max-width: 250px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Trading Bot - Estratégia de Reversão Contínua</h1>
            <p>ETH/USDT Perpetual • Bitget • Supertrend (Principal) + Confirmações • SEM Stop Loss/Take Profit</p>
        </div>
        
        <div class="control-buttons">
            <button class="btn btn-start" onclick="startBot()">Iniciar Bot</button>
            <button class="btn btn-stop" onclick="stopBot()">Parar Bot</button>
            <button class="btn btn-refresh" onclick="refreshStatus()">Atualizar</button>
            <button class="btn btn-close" onclick="forceClose()">Fechar Posição</button>
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
                        <div class="info-label">Preço Entrada</div>
                        <div class="info-value" id="entry-price">-</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">Duração</div>
                        <div class="info-value" id="position-duration">-</div>
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
            
            <div class="card">
                <h3>Estatísticas de Trading</h3>
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="info-label">Total Trades</div>
                        <div class="info-value" id="total-trades">0</div>
                    </div>
                    <div class="stat-item">
                        <div class="info-label">Sucessos</div>
                        <div class="info-value" id="successful-trades">0</div>
                    </div>
                    <div class="stat-item">
                        <div class="info-label">Win Rate</div>
                        <div class="info-value" id="win-rate">0%</div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h3>Logs do Sistema</h3>
            <div class="logs" id="system-logs">Sistema iniciado. Bot de reversão contínua pronto para trading...</div>
        </div>
        
        <div id="error-container"></div>
    </div>
    
    <script>
        let logMessages = [];
        
        function addLog(message) {
            const timestamp = new Date().toLocaleTimeString();
            logMessages.push(`[${timestamp}] ${message}`);
            if (logMessages.length > 100) {
                logMessages.shift();
            }
            document.getElementById('system-logs').innerHTML = logMessages.join('\\n');
            document.getElementById('system-logs').scrollTop = document.getElementById('system-logs').scrollHeight;
        }
        
        async function startBot() {
            try {
                addLog('🚀 Iniciando bot de reversão contínua...');
                const response = await fetch('/start');
                const data = await response.json();
                addLog(`✅ ${data.message}`);
                setTimeout(refreshStatus, 2000);
            } catch (error) {
                addLog(`❌ Erro ao iniciar bot: ${error.message}`);
            }
        }
        
        async function stopBot() {
            try {
                addLog('⏹️ Parando bot...');
                const response = await fetch('/stop');
                const data = await response.json();
                addLog(`✅ ${data.message}`);
                setTimeout(refreshStatus, 2000);
            } catch (error) {
                addLog(`❌ Erro ao parar bot: ${error.message}`);
            }
        }
        
        async function forceClose() {
            try {
                addLog('🔴 Forçando fechamento de posição...');
                const response = await fetch('/force-close');
                const data = await response.json();
                if (data.error) {
                    addLog(`⚠️ ${data.error}`);
                } else {
                    addLog(`✅ ${data.message}`);
                }
                setTimeout(refreshStatus, 2000);
            } catch (error) {
                addLog(`❌ Erro ao fechar posição: ${error.message}`);
            }
        }
        
        async function refreshStatus() {
            try {
                const response = await fetch('/status');
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                
                const status = await response.json();
                
                // Atualizar indicador de status
                const indicator = document.getElementById('status-indicator');
                const statusText = document.getElementById('status-text');
                
                if (status.running) {
                    indicator.className = 'status-indicator status-running';
                    statusText.textContent = 'Bot Ativo - Reversão Contínua';
                } else {
                    indicator.className = 'status-indicator status-stopped';
                    statusText.textContent = 'Bot Parado';
                }
                
                // Atualizar informações básicas
                document.getElementById('last-update').textContent = status.last_update || '-';
                document.getElementById('entry-price').textContent = status.entry_price ? `${parseFloat(status.entry_price).toFixed(4)}` : '-';
                document.getElementById('current-price').textContent = status.current_price ? `${parseFloat(status.current_price).toFixed(4)}` : '-';
                
                // Atualizar posição
                const positionElement = document.getElementById('current-position');
                if (status.current_position) {
                    positionElement.textContent = status.current_position.toUpperCase();
                    positionElement.className = `info-value position-${status.current_position}`;
                } else {
                    positionElement.textContent = 'Nenhuma';
                    positionElement.className = 'info-value';
                }
                
                // Atualizar duração
                const durationElement = document.getElementById('position-duration');
                if (status.position_duration > 0) {
                    durationElement.textContent = `${status.position_duration} min`;
                } else {
                    durationElement.textContent = '-';
                }
                
                // Atualizar P&L
                const pnlElement = document.getElementById('pnl');
                if (status.pnl !== undefined && status.pnl !== null && status.pnl !== 0) {
                    const pnlValue = parseFloat(status.pnl);
                    pnlElement.textContent = `${pnlValue > 0 ? '+' : ''}${pnlValue.toFixed(2)}%`;
                    pnlElement.className = pnlValue > 0 ? 'info-value pnl-positive' : 'info-value pnl-negative';
                } else {
                    pnlElement.textContent = '-';
                    pnlElement.className = 'info-value';
                }
                
                // Atualizar estatísticas
                document.getElementById('total-trades').textContent = status.total_trades || 0;
                document.getElementById('successful-trades').textContent = status.successful_trades || 0;
                
                const winRateElement = document.getElementById('win-rate');
                const winRate = status.win_rate || 0;
                winRateElement.textContent = `${winRate.toFixed(1)}%`;
                winRateElement.className = winRate >= 50 ? 'info-value win-rate-positive' : 'info-value win-rate-negative';
                
                // Mostrar erros
                const errorContainer = document.getElementById('error-container');
                if (status.error) {
                    errorContainer.innerHTML = `<div class="error-message"><strong>Erro:</strong> ${status.error}</div>`;
                    addLog(`❌ Erro: ${status.error}`);
                } else {
                    errorContainer.innerHTML = '';
                }
                
                // Log apenas de trades importantes
                if (status.total_trades && status.total_trades !== window.lastTradeCount) {
                    addLog(`🎯 Novo trade executado! Total: ${status.total_trades}`);
                    window.lastTradeCount = status.total_trades;
                }
                
            } catch (error) {
                addLog(`❌ Erro ao atualizar status: ${error.message}`);
                console.error('Erro detalhado:', error);
            }
        }
        
        // Atualizar status automaticamente a cada 15 segundos
        setInterval(refreshStatus, 15000);
        
        // Carregar status inicial
        refreshStatus();
        
        // Logs iniciais
        addLog('🤖 Interface carregada - Estratégia de reversão contínua ativa');
        addLog('🔄 Supertrend como decisor principal');
        addLog('✅ AlgoAlpha + MFI + ATR como confirmação');
        addLog('🚫 SEM stop loss ou take profit - apenas reversões');
        addLog('⚡ Threshold: 3 pontos | Cooldown: 60s | Timeframe: 3m');
        addLog('🎯 Pronto para detectar sinais e executar reversões!');
    </script>
</body>
</html>
'''

@app.route('/')
def home():
    """Página inicial com interface de reversão contínua"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/status')
def status():
    """Endpoint para verificar o status do bot"""
    try:
        # Sempre tentar obter preço atual
        if not bot_status.get('current_price'):
            current_price = get_current_price()
            if current_price:
                bot_status['current_price'] = current_price
        
        # Garantir que todos os campos existam
        response_data = {
            'running': bool(bot_status.get('running', False)),
            'last_update': bot_status.get('last_update'),
            'current_position': bot_status.get('current_position'),
            'error': bot_status.get('error'),
            'pnl': float(bot_status.get('pnl', 0.0)),
            'entry_price': float(bot_status.get('entry_price', 0)) if bot_status.get('entry_price') else None,
            'current_price': float(bot_status.get('current_price', 0)) if bot_status.get('current_price') else None,
            'signal_strength': int(bot_status.get('signal_strength', 0)),
            'position_duration': float(bot_status.get('position_duration', 0)),
            'trades_today': int(bot_status.get('trades_today', 0)),
            'total_trades': int(bot_status.get('total_trades', 0)),
            'successful_trades': int(bot_status.get('successful_trades', 0)),
            'win_rate': float(bot_status.get('win_rate', 0.0))
        }
        
        return jsonify(response_data)
    except Exception as e:
        print(f"Erro no endpoint /status: {e}")
        return jsonify({
            'running': False,
            'error': f'Erro interno: {str(e)}',
            'last_update': None,
            'current_position': None,
            'pnl': 0.0,
            'entry_price': None,
            'current_price': None,
            'signal_strength': 0,
            'position_duration': 0,
            'trades_today': 0,
            'total_trades': 0,
            'successful_trades': 0,
            'win_rate': 0.0
        })

@app.route('/health')
def health():
    """Health check para o Render"""
    return jsonify({
        'status': 'healthy',
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'strategy': 'continuous_reversal',
        'indicators': 'supertrend_primary_algoalpha_mfi_atr_confirmation',
        'no_stop_loss': True,
        'no_take_profit': True
    })

@app.route('/start')
def start_bot():
    """Inicia o bot manualmente"""
    global bot_thread, bot_status
    
    if not bot_status['running']:
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        return jsonify({'message': 'Bot iniciado - Estratégia de Reversão Contínua!'})
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
                'position_duration': bot_status.get('position_duration', 0),
                'exchange_position': position_info,
                'total_trades': trading_bot.total_trades,
                'successful_trades': trading_bot.successful_trades
            })
        except Exception as e:
            return jsonify({'error': str(e)})
    else:
        return jsonify({'error': 'Bot não inicializado'})

@app.route('/force-close')
def force_close():
    """Força o fechamento da posição atual (apenas manual via interface)"""
    if trading_bot and trading_bot.current_position:
        try:
            success = trading_bot.close_position()
            if success:
                return jsonify({'message': 'Posição fechada manualmente! AVISO: Bot continuará operando normalmente.'})
            else:
                return jsonify({'error': 'Falha ao fechar posição'})
        except Exception as e:
            return jsonify({'error': str(e)})
    else:
        return jsonify({'error': 'Nenhuma posição ativa ou bot não inicializado'})

if __name__ == '__main__':
    # Não iniciar o bot automaticamente
    # Deixar para o usuário decidir via interface
    
    # Iniciar o servidor Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
