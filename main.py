import os
import ccxt
import pandas as pd
import pandas_ta as ta
import time
import logging
from datetime import datetime

# Configuração do logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BitgetTradingBot:
    def __init__(self):
        # Configurações básicas
        self.symbol = 'ETH/USDT:USDT'
        self.timeframe = '15m'
        self.leverage = 10
        self.stop_loss_pct = 0.01  # 1%
        self.atr_period = 10
        self.atr_multiplier = 3.0
        self.ema_period = 50
        
        # Inicializar exchange
        self.exchange = self.init_exchange()
        self.current_position = None
        self.last_signal = None
        
        # Configurar alavancagem
        self.set_leverage()
        
    def init_exchange(self):
        """Inicializa a conexão com a Bitget"""
        try:
            exchange = ccxt.bitget({
                'apiKey': os.getenv('BITGET_API_KEY'),
                'secret': os.getenv('BITGET_SECRET'),
                'password': os.getenv('BITGET_PASSPHRASE'),
                'sandbox': False,  # Mude para True para usar testnet
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap'
                }
            })
            exchange.load_markets()
            logger.info("Conexão com Bitget estabelecida com sucesso")
            return exchange
        except Exception as e:
            logger.error(f"Erro ao conectar com a Bitget: {e}")
            raise
    
    def set_leverage(self):
        """Configura a alavancagem para o par"""
        try:
            self.exchange.set_leverage(self.leverage, self.symbol)
            logger.info(f"Alavancagem configurada para {self.leverage}x")
        except Exception as e:
            logger.error(f"Erro ao configurar alavancagem: {e}")
    
    def get_candles(self, limit=100):
        """Busca dados de velas"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            logger.error(f"Erro ao buscar dados de velas: {e}")
            return None
    
    def calculate_supertrend(self, df):
        """Calcula o Supertrend baseado no Pine Script"""
        # Calcular ATR
        df['tr'] = ta.true_range(df['high'], df['low'], df['close'])
        df['atr'] = df['tr'].rolling(window=self.atr_period).mean()
        
        # Calcular HL2 (fonte)
        df['hl2'] = (df['high'] + df['low']) / 2
        
        # Calcular bandas superior e inferior
        df['upper_band'] = df['hl2'] - (self.atr_multiplier * df['atr'])
        df['lower_band'] = df['hl2'] + (self.atr_multiplier * df['atr'])
        
        # Inicializar colunas
        df['final_upper_band'] = 0.0
        df['final_lower_band'] = 0.0
        df['supertrend'] = 0.0
        df['trend'] = 1
        
        # Calcular Supertrend
        for i in range(1, len(df)):
            # Final Upper Band
            if df['upper_band'].iloc[i] > df['final_upper_band'].iloc[i-1] or df['close'].iloc[i-1] < df['final_upper_band'].iloc[i-1]:
                df.loc[df.index[i], 'final_upper_band'] = df['upper_band'].iloc[i]
            else:
                df.loc[df.index[i], 'final_upper_band'] = df['final_upper_band'].iloc[i-1]
            
            # Final Lower Band
            if df['lower_band'].iloc[i] < df['final_lower_band'].iloc[i-1] or df['close'].iloc[i-1] > df['final_lower_band'].iloc[i-1]:
                df.loc[df.index[i], 'final_lower_band'] = df['lower_band'].iloc[i]
            else:
                df.loc[df.index[i], 'final_lower_band'] = df['final_lower_band'].iloc[i-1]
            
            # Trend
            if df['trend'].iloc[i-1] == -1 and df['close'].iloc[i] > df['final_lower_band'].iloc[i-1]:
                df.loc[df.index[i], 'trend'] = 1
            elif df['trend'].iloc[i-1] == 1 and df['close'].iloc[i] < df['final_upper_band'].iloc[i-1]:
                df.loc[df.index[i], 'trend'] = -1
            else:
                df.loc[df.index[i], 'trend'] = df['trend'].iloc[i-1]
            
            # Supertrend
            if df['trend'].iloc[i] == 1:
                df.loc[df.index[i], 'supertrend'] = df['final_upper_band'].iloc[i]
            else:
                df.loc[df.index[i], 'supertrend'] = df['final_lower_band'].iloc[i]
        
        return df
    
    def calculate_ema(self, df):
        """Calcula a EMA de 50 períodos"""
        df['ema_50'] = ta.ema(df['close'], length=self.ema_period)
        return df
    
    def get_current_position(self):
        """Obtém a posição atual"""
        try:
            positions = self.exchange.fetch_positions([self.symbol])
            for position in positions:
                if position['size'] != 0:
                    return position
            return None
        except Exception as e:
            logger.error(f"Erro ao buscar posição atual: {e}")
            return None
    
    def get_usdt_balance(self):
        """Obtém o saldo em USDT disponível"""
        try:
            balance = self.exchange.fetch_balance()
            return balance['USDT']['free']
        except Exception as e:
            logger.error(f"Erro ao buscar saldo: {e}")
            return 0
    
    def calculate_position_size(self, price):
        """Calcula o tamanho da posição usando 100% do USDT"""
        try:
            usdt_balance = self.get_usdt_balance()
            # Usar 99% do saldo para evitar erros de saldo insuficiente
            usable_balance = usdt_balance * 0.99
            # Calcular tamanho da posição com alavancagem
            position_value = usable_balance * self.leverage
            size = position_value / price
            
            # Arredondar para o número de decimais suportado pelo par
            market = self.exchange.markets[self.symbol]
            size = self.exchange.amount_to_precision(self.symbol, size)
            
            logger.info(f"Saldo USDT: {usdt_balance}, Tamanho da posição: {size} ETH")
            return float(size)
        except Exception as e:
            logger.error(f"Erro ao calcular tamanho da posição: {e}")
            return 0
    
    def close_position(self):
        """Fecha a posição atual"""
        try:
            position = self.get_current_position()
            if position and position['size'] != 0:
                side = 'sell' if position['side'] == 'long' else 'buy'
                size = abs(position['size'])
                
                order = self.exchange.create_market_order(
                    self.symbol, 
                    side, 
                    size,
                    params={'reduceOnly': True}
                )
                
                logger.info(f"Posição fechada: {order}")
                return True
        except Exception as e:
            logger.error(f"Erro ao fechar posição: {e}")
            return False
    
    def open_position(self, side, price):
        """Abre uma nova posição"""
        try:
            size = self.calculate_position_size(price)
            if size <= 0:
                logger.warning("Tamanho da posição inválido")
                return False
            
            order = self.exchange.create_market_order(self.symbol, side, size)
            logger.info(f"Nova posição {side}: {order}")
            return True
        except Exception as e:
            logger.error(f"Erro ao abrir posição {side}: {e}")
            return False
    
    def check_stop_loss(self, position, current_price):
        """Verifica se deve executar o stop loss"""
        if not position:
            return False
        
        entry_price = position['entryPrice']
        side = position['side']
        
        if side == 'long':
            stop_price = entry_price * (1 - self.stop_loss_pct)
            if current_price <= stop_price:
                logger.info(f"Stop Loss acionado - Long: Preço atual {current_price} <= Stop {stop_price}")
                return True
        else:  # short
            stop_price = entry_price * (1 + self.stop_loss_pct)
            if current_price >= stop_price:
                logger.info(f"Stop Loss acionado - Short: Preço atual {current_price} >= Stop {stop_price}")
                return True
        
        return False
    
    def analyze_signals(self, df):
        """Analisa os sinais de compra e venda"""
        if len(df) < 2:
            return None, None
        
        # Obter valores atuais e anteriores
        current_trend = df['trend'].iloc[-1]
        previous_trend = df['trend'].iloc[-2]
        current_price = df['close'].iloc[-1]
        current_ema = df['ema_50'].iloc[-1]
        
        # Detectar mudança de tendência
        buy_signal = current_trend == 1 and previous_trend == -1 and current_price > current_ema
        sell_signal = current_trend == -1 and previous_trend == 1 and current_price < current_ema
        
        return buy_signal, sell_signal
    
    def run_strategy(self):
        """Executa a estratégia de trading"""
        try:
            # Buscar dados
            df = self.get_candles()
            if df is None or len(df) < self.ema_period + self.atr_period:
                logger.warning("Dados insuficientes para análise")
                return
            
            # Calcular indicadores
            df = self.calculate_supertrend(df)
            df = self.calculate_ema(df)
            
            # Obter posição atual
            current_position = self.get_current_position()
            current_price = df['close'].iloc[-1]
            
            # Verificar stop loss primeiro
            if current_position and self.check_stop_loss(current_position, current_price):
                logger.info("Executando Stop Loss")
                if self.close_position():
                    self.current_position = None
                    return
            
            # Analisar sinais
            buy_signal, sell_signal = self.analyze_signals(df)
            
            logger.info(f"Preço atual: {current_price:.2f}")
            logger.info(f"EMA 50: {df['ema_50'].iloc[-1]:.2f}")
            logger.info(f"Trend: {df['trend'].iloc[-1]}")
            logger.info(f"Supertrend: {df['supertrend'].iloc[-1]:.2f}")
            
            # Executar ordens baseadas nos sinais
            if buy_signal:
                logger.info("SINAL DE COMPRA detectado!")
                if current_position:
                    if current_position['side'] == 'short':
                        logger.info("Fechando posição short e abrindo long")
                        if self.close_position():
                            time.sleep(2)  # Aguardar fechamento
                            self.open_position('buy', current_price)
                    else:
                        logger.info("Já em posição long")
                else:
                    logger.info("Abrindo nova posição long")
                    self.open_position('buy', current_price)
                    
            elif sell_signal:
                logger.info("SINAL DE VENDA detectado!")
                if current_position:
                    if current_position['side'] == 'long':
                        logger.info("Fechando posição long e abrindo short")
                        if self.close_position():
                            time.sleep(2)  # Aguardar fechamento
                            self.open_position('sell', current_price)
                    else:
                        logger.info("Já em posição short")
                else:
                    logger.info("Abrindo nova posição short")
                    self.open_position('sell', current_price)
            else:
                logger.info("Nenhum sinal detectado - mantendo posição atual")
                
        except Exception as e:
            logger.error(f"Erro na execução da estratégia: {e}")
    
    def run(self):
        """Loop principal do bot"""
        logger.info("Bot iniciado!")
        logger.info(f"Par: {self.symbol}")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"Alavancagem: {self.leverage}x")
        logger.info(f"Stop Loss: {self.stop_loss_pct*100}%")
        
        while True:
            try:
                logger.info("=" * 50)
                logger.info(f"Executando análise - {datetime.now()}")
                self.run_strategy()
                logger.info("Aguardando 5 minutos para próxima análise...")
                time.sleep(300)  # 5 minutos
                
            except KeyboardInterrupt:
                logger.info("Bot interrompido pelo usuário")
                break
            except Exception as e:
                logger.error(f"Erro no loop principal: {e}")
                logger.info("Aguardando 1 minuto antes de tentar novamente...")
                time.sleep(60)

if __name__ == "__main__":
    bot = BitgetTradingBot()
    bot.run()
