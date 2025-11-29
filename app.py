from flask import Flask, request, jsonify, render_template
import json
import sqlite3
import threading
import time
import requests
import os
from datetime import datetime
from typing import Optional, Dict, List

app = Flask(__name__)

# Configurações
INITIAL_BALANCE = 55.0  # Saldo inicial de $55 USDT
COMMISSION_RATE = 0.0005  # 0.05%

# Tentar usar Volume Disk, se não existir usar local
if os.path.exists('/opt/render/project/src/data'):
    DB_DIR = '/opt/render/project/src/data'
else:
    DB_DIR = os.path.join(os.getcwd(), 'data')

DB_PATH = os.path.join(DB_DIR, 'trading.db')
SELF_PING_INTERVAL = 600  # 10 minutos
TRADING_PAIR = "ETH/USDT"

# Criar diretório se não existir
os.makedirs(DB_DIR, exist_ok=True)
print(f"[INFO] Database path: {DB_PATH}")
print(f"[INFO] Directory exists: {os.path.exists(DB_DIR)}")

class TradeSimulator:
    def __init__(self):
        self.init_database()
        self.current_position = None
        self.load_state()
    
    def init_database(self):
        """Inicializa o banco de dados SQLite"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Tabela de trades
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                price REAL NOT NULL,
                quantity REAL NOT NULL,
                total_value REAL NOT NULL,
                commission REAL NOT NULL,
                balance_after REAL NOT NULL,
                profit_loss REAL DEFAULT 0,
                timestamp TEXT NOT NULL
            )
        ''')
        
        # Tabela de estado da conta
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                balance REAL NOT NULL,
                position_open INTEGER DEFAULT 0,
                position_price REAL,
                position_quantity REAL,
                position_value REAL,
                total_profit REAL DEFAULT 0,
                peak_balance REAL NOT NULL,
                last_updated TEXT NOT NULL
            )
        ''')
        
        # Inicializa estado se não existir
        cursor.execute('SELECT COUNT(*) FROM account_state')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO account_state 
                (id, balance, peak_balance, last_updated) 
                VALUES (1, ?, ?, ?)
            ''', (INITIAL_BALANCE, INITIAL_BALANCE, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def load_state(self):
        """Carrega o estado atual da conta"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM account_state WHERE id = 1')
        state = cursor.fetchone()
        conn.close()
        
        if state and state[2] == 1:  # position_open
            self.current_position = {
                'price': state[3],
                'quantity': state[4],
                'value': state[5]
            }
    
    def get_balance(self) -> float:
        """Retorna o saldo atual"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT balance FROM account_state WHERE id = 1')
        balance = cursor.fetchone()[0]
        conn.close()
        return balance
    
    def update_peak_balance(self, current_balance: float):
        """Atualiza o pico de saldo se necessário"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT peak_balance FROM account_state WHERE id = 1')
        peak = cursor.fetchone()[0]
        
        if current_balance > peak:
            cursor.execute('UPDATE account_state SET peak_balance = ? WHERE id = 1', (current_balance,))
            conn.commit()
        conn.close()
    
    def open_long(self, price: float, timestamp: str) -> Dict:
        """Abre uma posição LONG com 100% do saldo"""
        if self.current_position:
            return {'status': 'error', 'message': 'Posição já está aberta'}
        
        balance = self.get_balance()
        commission = balance * COMMISSION_RATE
        available_for_trade = balance - commission
        quantity = available_for_trade / price
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Registra o trade
        cursor.execute('''
            INSERT INTO trades 
            (action, price, quantity, total_value, commission, balance_after, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', ('BUY', price, quantity, available_for_trade, commission, 0, timestamp))
        
        # Atualiza estado da conta
        cursor.execute('''
            UPDATE account_state 
            SET position_open = 1, 
                position_price = ?,
                position_quantity = ?,
                position_value = ?,
                balance = 0,
                last_updated = ?
            WHERE id = 1
        ''', (price, quantity, available_for_trade, timestamp))
        
        conn.commit()
        conn.close()
        
        self.current_position = {
            'price': price,
            'quantity': quantity,
            'value': available_for_trade
        }
        
        return {
            'status': 'success',
            'action': 'BUY',
            'price': price,
            'quantity': quantity,
            'commission': commission,
            'investment': available_for_trade
        }
    
    def close_long(self, price: float, timestamp: str) -> Dict:
        """Fecha a posição LONG"""
        if not self.current_position:
            return {'status': 'error', 'message': 'Nenhuma posição aberta'}
        
        # Salva dados da posição antes de limpar
        position_quantity = self.current_position['quantity']
        position_value = self.current_position['value']
        
        # Calcula o valor bruto da venda
        gross_value = position_quantity * price
        commission = gross_value * COMMISSION_RATE
        net_value = gross_value - commission
        
        # Calcula lucro/prejuízo
        profit_loss = net_value - position_value
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Registra o trade de fechamento
        cursor.execute('''
            INSERT INTO trades 
            (action, price, quantity, total_value, commission, balance_after, profit_loss, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', ('SELL', price, position_quantity, gross_value, commission, net_value, profit_loss, timestamp))
        
        # Atualiza estado da conta
        cursor.execute('''
            UPDATE account_state 
            SET position_open = 0,
                position_price = NULL,
                position_quantity = NULL,
                position_value = NULL,
                balance = ?,
                total_profit = total_profit + ?,
                last_updated = ?
            WHERE id = 1
        ''', (net_value, profit_loss, timestamp))
        
        conn.commit()
        conn.close()
        
        self.update_peak_balance(net_value)
        
        # Prepara resultado antes de limpar a posição
        result = {
            'status': 'success',
            'action': 'SELL',
            'price': price,
            'quantity': position_quantity,
            'gross_value': gross_value,
            'commission': commission,
            'net_value': net_value,
            'profit_loss': profit_loss,
            'profit_percentage': (profit_loss / position_value) * 100
        }
        
        # Limpa a posição atual
        self.current_position = None
        
        return result
    
    def get_statistics(self) -> Dict:
        """Retorna estatísticas do trading"""
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10.0)
            cursor = conn.cursor()
            
            # Estatísticas básicas
            cursor.execute('SELECT COUNT(*) FROM trades WHERE action = "BUY"')
            total_longs = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM trades WHERE action = "SELL"')
            total_shorts = cursor.fetchone()[0]
            
            cursor.execute('SELECT total_profit FROM account_state WHERE id = 1')
            result = cursor.fetchone()
            total_profit = result[0] if result else 0
            
            cursor.execute('SELECT balance, peak_balance FROM account_state WHERE id = 1')
            result = cursor.fetchone()
            if result:
                balance, peak = result
            else:
                balance, peak = INITIAL_BALANCE, INITIAL_BALANCE
            
            # Calcula lucro/perda em porcentagem
            profit_percentage = ((balance - INITIAL_BALANCE) / INITIAL_BALANCE) * 100
            
            # Calcula drawdown máximo
            max_drawdown = 0
            if peak > 0:
                max_drawdown = ((peak - balance) / peak) * 100 if balance < peak else 0
            
            # Taxa de vitória
            cursor.execute('SELECT COUNT(*) FROM trades WHERE action = "SELL" AND profit_loss > 0')
            winning_trades = cursor.fetchone()[0]
            
            win_rate = (winning_trades / total_shorts * 100) if total_shorts > 0 else 0
            
            # Últimos 10 trades
            cursor.execute('''
                SELECT action, price, quantity, profit_loss, timestamp 
                FROM trades 
                ORDER BY id DESC 
                LIMIT 10
            ''')
            recent_trades = cursor.fetchall()
            
            conn.close()
            
            stats = {
                'total_longs': total_longs,
                'total_shorts': total_shorts,
                'total_profit_usd': round(total_profit, 2),
                'total_profit_percentage': round(profit_percentage, 2),
                'current_balance': round(balance, 2),
                'initial_balance': INITIAL_BALANCE,
                'max_drawdown': round(max_drawdown, 2),
                'win_rate': round(win_rate, 2),
                'recent_trades': recent_trades,
                'position_open': self.current_position is not None
            }
            
            print(f"[GET_STATISTICS] Stats calculados: Longs={total_longs}, Shorts={total_shorts}, Balance={balance}")
            return stats
            
        except Exception as e:
            print(f"[GET_STATISTICS] Erro: {str(e)}")
            import traceback
            traceback.print_exc()
            # Retorna valores padrão em caso de erro
            return {
                'total_longs': 0,
                'total_shorts': 0,
                'total_profit_usd': 0.0,
                'total_profit_percentage': 0.0,
                'current_balance': INITIAL_BALANCE,
                'initial_balance': INITIAL_BALANCE,
                'max_drawdown': 0.0,
                'win_rate': 0.0,
                'recent_trades': [],
                'position_open': False
            }

# Instância global do simulador
simulator = TradeSimulator()

@app.route('/webhook', methods=['POST'])
def webhook():
    """Endpoint para receber sinais do TradingView"""
    try:
        data = request.json
        print(f"[WEBHOOK] Recebido: {data}")
        
        # Validação básica
        if not data:
            print("[WEBHOOK] Erro: Dados vazios")
            return jsonify({'status': 'error', 'message': 'Dados vazios'}), 400
        
        # Extrai informações do sinal - com fallbacks
        action = None
        price = None
        
        # Tenta extrair action de diferentes formatos
        if 'data' in data and isinstance(data['data'], dict):
            action = data['data'].get('action', '').lower()
        elif 'action' in data:
            action = data['action'].lower()
        
        # Tenta extrair price de diferentes formatos
        if 'price' in data:
            try:
                price = float(data['price'])
            except (ValueError, TypeError):
                price = None
        
        timestamp = data.get('time', datetime.now().isoformat())
        
        print(f"[WEBHOOK] Processando - Action: {action}, Price: {price}")
        
        # Validação
        if not action:
            print("[WEBHOOK] Erro: Action não encontrado")
            return jsonify({'status': 'error', 'message': 'Action não encontrado nos dados'}), 400
        
        if not price or price <= 0:
            print("[WEBHOOK] Erro: Price inválido")
            return jsonify({'status': 'error', 'message': 'Price inválido ou não encontrado'}), 400
        
        # Processa a ação
        if action == 'buy':
            result = simulator.open_long(price, timestamp)
            print(f"[TRADE] LONG aberto - Preço: ${price}, Resultado: {result}")
        elif action == 'sell':
            result = simulator.close_long(price, timestamp)
            print(f"[TRADE] LONG fechado - Preço: ${price}, Resultado: {result}")
        else:
            print(f"[WEBHOOK] Erro: Ação desconhecida: {action}")
            return jsonify({'status': 'error', 'message': f'Ação desconhecida: {action}'}), 400
        
        return jsonify(result), 200
        
    except Exception as e:
        print(f"[WEBHOOK] Erro crítico: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/')
def index():
    """Redireciona para o dashboard"""
    from flask import redirect
    return redirect('/dashboard')

@app.route('/dashboard')
def dashboard():
    """Renderiza o dashboard"""
    return render_template('index.html')

@app.route('/api/stats')
def api_stats():
    """API para obter estatísticas em tempo real"""
    try:
        stats = simulator.get_statistics()
        print(f"[API STATS] Retornando: {stats}")
        return jsonify(stats)
    except Exception as e:
        print(f"[API STATS] Erro: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/ping')
def ping():
    """Endpoint de ping para manter o serviço ativo"""
    return jsonify({
        'status': 'alive',
        'timestamp': datetime.now().isoformat(),
        'uptime': 'running'
    })

@app.route('/health')
def health():
    """Health check para o Render"""
    return jsonify({'status': 'healthy'}), 200

def self_ping():
    """Função que faz auto-ping para manter o serviço ativo"""
    # Aguarda 2 minutos antes de começar (para o app inicializar)
    time.sleep(120)
    
    while True:
        try:
            # Tenta descobrir a URL do próprio serviço
            # No Render, use a variável de ambiente RENDER_EXTERNAL_URL
            import os
            base_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
            
            response = requests.get(f'{base_url}/ping', timeout=10)
            print(f'[SELF-PING] Status: {response.status_code} - {datetime.now()}')
        except Exception as e:
            print(f'[SELF-PING ERROR] {e}')
        
        time.sleep(SELF_PING_INTERVAL)

# Inicia thread de auto-ping
ping_thread = threading.Thread(target=self_ping, daemon=True)
ping_thread.start()

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
