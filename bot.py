import ccxt
import pandas as pd
import pandas_ta as ta
import numpy as np
import time
import logging
import os
from datetime import datetime
from typing import Tuple, Optional, Dict, Any

# ConfiguraÃ§Ã£o de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self):
        """Inicializa o bot de trading"""
        # ConfiguraÃ§Ãµes da exchange
        self.exchange = self._setup_exchange()
        self.symbol = 'ETHUSDT_UMCBL'
        self.timeframe = '15m'
        self.leverage = 10
        self.stop_loss_percentage = 0.01  # 1%
        
        # Estado da posiÃ§Ã£o
        self.current_position = None  # 'long', 'short', None
        self.entry_price = None
        self.position_size = None
        
        # ParÃ¢metros dos indicadores
        self.supertrend_period = 10
        self.supertrend_multiplier = 3.0
        self.breakout_normalization_length = 100
        self.breakout_detection_length = 14
        
        # HistÃ³rico de canais ativos
        self.active_channels = []
        
        logger.info("Bot de trading inicializado com sucesso")
    
    def _setup_exchange(self) -> ccxt.bitget:
        """Configura a conexÃ£o com a Bitget"""
        api_key = os.getenv('BITGET_API_KEY')
        secret_key = os.getenv('BITGET_API_SECRET')
        password = os.getenv('BITGET_PASSPHRASE')
        
        if not all([api_key, secret_key, password]):
            raise ValueError("Chaves da API nÃ£o encontradas nas variÃ¡veis de ambiente")
        
        exchange = ccxt.bitget({
            'apiKey': api_key,
            'secret': secret_key,
            'password': password,
            'sandbox': False,  # Mudar para True para teste
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap'  # Para futuros
            }
        })
        
        return exchange
    
    def get_ohlcv_data(self, limit: int = 200) -> pd.DataFrame:
        """ObtÃ©m dados OHLCV da exchange"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return df
        except Exception as e:
            logger.error(f"Erro ao obter dados OHLCV: {e}")
            raise
    
    def calculate_supertrend(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula o indicador Supertrend"""
        try:
            # Usando pandas_ta para calcular Supertrend - parâmetros corretos
            supertrend = ta.supertrend(
                high=df['high'],
                low=df['low'],
                close=df['close'],
                period=self.supertrend_period,
                multiplier=self.supertrend_multiplier
            )
            
            # Verificar se o resultado não é None e tem as colunas esperadas
            if supertrend is not None:
                # Tentar diferentes formatos de nomes de colunas
                supertrend_col = None
                direction_col = None
                
                # Possíveis nomes de colunas do pandas-ta
                for col in supertrend.columns:
                    if 'SUPERT' in col and 'SUPERTd' not in col:
                        supertrend_col = col
                    elif 'SUPERTd' in col:
                        direction_col = col
                
                if supertrend_col and direction_col:
                    df['supertrend'] = supertrend[supertrend_col]
                    df['supertrend_direction'] = supertrend[direction_col]
                else:
                    # Fallback: cálculo manual básico do Supertrend
                    print("Usando cálculo manual do Supertrend")
                    df = self._calculate_manual_supertrend(df)
            else:
                # Fallback: cálculo manual básico do Supertrend
                print("Supertrend retornou None, usando cálculo manual")
                df = self._calculate_manual_supertrend(df)
            
            return df
        except Exception as e:
            print(f"Erro ao calcular Supertrend, usando fallback manual: {e}")
            return self._calculate_manual_supertrend(df)
    
    def _calculate_manual_supertrend(self, df: pd.DataFrame) -> pd.DataFrame:
        """Cálculo manual simplificado do Supertrend como fallback"""
        try:
            # Calcular ATR
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            atr = true_range.rolling(window=self.supertrend_period).mean()
            
            # Calcular basic bands
            hl2 = (df['high'] + df['low']) / 2
            basic_upper_band = hl2 + (self.supertrend_multiplier * atr)
            basic_lower_band = hl2 - (self.supertrend_multiplier * atr)
            
            # Inicializar arrays
            supertrend = np.zeros(len(df))
            direction = np.zeros(len(df))
            
            # Calcular Supertrend simplificado
            for i in range(1, len(df)):
                # Direção baseada no fechamento vs supertrend anterior
                if df['close'].iloc[i] > supertrend[i-1]:
                    direction[i] = 1
                    supertrend[i] = basic_lower_band.iloc[i]
                else:
                    direction[i] = -1
                    supertrend[i] = basic_upper_band.iloc[i]
            
            df['supertrend'] = supertrend
            df['supertrend_direction'] = direction
            
            return df
        except Exception as e:
            print(f"Erro no cálculo manual do Supertrend: {e}")
            # Última tentativa: usar média móvel simples como proxy
            df['supertrend'] = df['close'].rolling(window=self.supertrend_period).mean()
            df['supertrend_direction'] = np.where(df['close'] > df['supertrend'], 1, -1)
            return df
    
    def calculate_smart_money_breakout(self, df: pd.DataFrame) -> Tuple[bool, bool]:
        """
        Implementa a lÃ³gica do Smart Money Breakout Channels corrigida
        Retorna (bullish_breakout, bearish_breakout)
        """
        try:
            if len(df) < self.breakout_normalization_length:
                return False, False
            
            # NormalizaÃ§Ã£o do preÃ§o
            lowest_low = df['low'].rolling(window=self.breakout_normalization_length, min_periods=1).min()
            highest_high = df['high'].rolling(window=self.breakout_normalization_length, min_periods=1).max()
            
            # Evitar divisÃ£o por zero
            price_range = highest_high - lowest_low
            price_range = price_range.replace(0, np.nan)
            normalized_price = (df['close'] - lowest_low) / price_range
            normalized_price = normalized_price.fillna(0.5)  # Valor padrÃ£o se divisÃ£o por zero
            
            # Volatilidade
            vol = normalized_price.rolling(window=14, min_periods=1).std()
            vol = vol.fillna(vol.mean())  # Preencher NaN com mÃ©dia
            
            # MÃ©todo simplificado para detecÃ§Ã£o de breakout
            # Usando perÃ­odos de alta e baixa volatilidade
            vol_ma = vol.rolling(window=self.breakout_detection_length, min_periods=1).mean()
            vol_std = vol.rolling(window=self.breakout_detection_length, min_periods=1).std()
            
            # Detectar formaÃ§Ã£o de canais baseado em baixa volatilidade
            low_vol_threshold = vol_ma - vol_std * 0.5
            high_vol_threshold = vol_ma + vol_std * 0.5
            
            # Verificar se estamos em um perÃ­odo de baixa volatilidade (formaÃ§Ã£o de canal)
            is_low_vol = vol.iloc[-1] < low_vol_threshold.iloc[-1]
            was_low_vol = vol.iloc[-2] < low_vol_threshold.iloc[-2] if len(vol) > 1 else False
            
            # Breakout ocorre quando saÃ­mos de baixa volatilidade para alta
            vol_breakout = (was_low_vol and vol.iloc[-1] > high_vol_threshold.iloc[-1])
            
            if not vol_breakout:
                return False, False
            
            # Determinar direÃ§Ã£o do breakout baseado no preÃ§o
            lookback_period = min(20, len(df))  # Ãšltimos 20 candles para contexto
            recent_data = df.iloc[-lookback_period:]
            
            support_level = recent_data['low'].min()
            resistance_level = recent_data['high'].max()
            current_price = df['close'].iloc[-1]
            previous_price = df['close'].iloc[-2] if len(df) > 1 else current_price
            
            # Detectar breakout baseado no movimento do preÃ§o
            price_change_pct = (current_price - previous_price) / previous_price if previous_price > 0 else 0
            
            bullish_breakout = False
            bearish_breakout = False
            
            # CritÃ©rios para breakout bullish
            if (current_price > resistance_level * 1.001 and  # 0.1% acima da resistÃªncia
                price_change_pct > 0.002):  # Movimento positivo de pelo menos 0.2%
                bullish_breakout = True
                logger.info(f"Breakout de alta detectado! PreÃ§o: {current_price:.4f}, ResistÃªncia: {resistance_level:.4f}")
            
            # CritÃ©rios para breakout bearish
            elif (current_price < support_level * 0.999 and  # 0.1% abaixo do suporte
                  price_change_pct < -0.002):  # Movimento negativo de pelo menos 0.2%
                bearish_breakout = True
                logger.info(f"Breakout de baixa detectado! PreÃ§o: {current_price:.4f}, Suporte: {support_level:.4f}")
            
            return bullish_breakout, bearish_breakout
            
        except Exception as e:
            logger.error(f"Erro ao calcular Smart Money Breakout: {e}")
            return False, False
    
    def get_position_info(self) -> Dict[str, Any]:
        """ObtÃ©m informaÃ§Ãµes da posiÃ§Ã£o atual"""
        try:
            positions = self.exchange.fetch_positions([self.symbol])
            for position in positions:
                if position['symbol'] == self.symbol and abs(float(position['contracts'] or 0)) > 0:
                    return {
                        'side': position['side'],
                        'size': abs(float(position['contracts'] or 0)),
                        'entry_price': float(position['entryPrice'] or 0),
                        'unrealized_pnl': float(position['unrealizedPnl'] or 0),
                        'percentage': float(position['percentage'] or 0)
                    }
            return None
        except Exception as e:
            logger.error(f"Erro ao obter informaÃ§Ãµes da posiÃ§Ã£o: {e}")
            return None
    
    def close_position(self) -> bool:
        """Fecha a posiÃ§Ã£o atual"""
        try:
            position_info = self.get_position_info()
            if not position_info:
                logger.info("Nenhuma posiÃ§Ã£o para fechar")
                return True
            
            side = 'buy' if position_info['side'] == 'short' else 'sell'
            
            order = self.exchange.create_market_order(
                symbol=self.symbol,
                side=side,
                amount=position_info['size'],
                params={'reduceOnly': True}
            )
            
            logger.info(f"PosiÃ§Ã£o fechada: {order['id']}")
            self.current_position = None
            self.entry_price = None
            self.position_size = None
            return True
            
        except Exception as e:
            logger.error(f"Erro ao fechar posiÃ§Ã£o: {e}")
            return False
    
    def open_position(self, side: str, amount: float) -> bool:
        """Abre uma nova posiÃ§Ã£o"""
        try:
            # Verificar saldo mÃ­nimo
            if amount <= 0:
                logger.error("Quantidade da posiÃ§Ã£o deve ser maior que zero")
                return False
            
            # Configurar alavancagem
            try:
                self.exchange.set_leverage(self.leverage, self.symbol)
            except Exception as e:
                logger.warning(f"Erro ao configurar alavancagem: {e}")
            
            # Criar ordem de mercado
            order = self.exchange.create_market_order(
                symbol=self.symbol,
                side=side,
                amount=amount,
                params={'type': 'market'}
            )
            
            # Aguardar um momento para a ordem ser processada
            time.sleep(2)
            
            # Verificar se a ordem foi executada
            if order.get('status') == 'closed' or order.get('filled', 0) > 0:
                # Atualizar estado
                self.current_position = 'long' if side == 'buy' else 'short'
                self.entry_price = float(order.get('price') or order.get('average') or 0)
                self.position_size = float(order.get('filled', amount))
                
                logger.info(f"PosiÃ§Ã£o {self.current_position} aberta: {order['id']}, PreÃ§o: {self.entry_price}")
                return True
            else:
                logger.error(f"Ordem nÃ£o foi executada completamente: {order}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao abrir posiÃ§Ã£o {side}: {e}")
            return False
    
    def check_stop_loss(self, current_price: float) -> bool:
        """Verifica se o stop loss deve ser acionado"""
        if not self.current_position or not self.entry_price:
            return False
        
        if self.current_position == 'long':
            stop_loss_price = self.entry_price * (1 - self.stop_loss_percentage)
            if current_price <= stop_loss_price:
                logger.warning(f"Stop Loss acionado para posiÃ§Ã£o LONG! PreÃ§o atual: {current_price}, Stop: {stop_loss_price}")
                return True
                
        elif self.current_position == 'short':
            stop_loss_price = self.entry_price * (1 + self.stop_loss_percentage)
            if current_price >= stop_loss_price:
                logger.warning(f"Stop Loss acionado para posiÃ§Ã£o SHORT! PreÃ§o atual: {current_price}, Stop: {stop_loss_price}")
                return True
        
        return False
    
    def calculate_position_size(self) -> float:
        """Calcula o tamanho da posiÃ§Ã£o baseado no saldo disponÃ­vel"""
        try:
            balance = self.exchange.fetch_balance()
            usdt_balance = float(balance.get('USDT', {}).get('free', 0))
            
            if usdt_balance <= 0:
                logger.error("Saldo USDT insuficiente")
                return 0
            
            # Usar 80% do saldo disponÃ­vel (mais conservador)
            position_value = usdt_balance * 0.8
            
            # Obter preÃ§o atual
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = float(ticker['last'])
            
            if current_price <= 0:
                logger.error("PreÃ§o atual invÃ¡lido")
                return 0
            
            # Calcular tamanho base da posiÃ§Ã£o (sem alavancagem)
            position_size = position_value / current_price
            
            # Aplicar limites mÃ­nimos e mÃ¡ximos
            market = self.exchange.market(self.symbol)
            min_amount = float(market.get('limits', {}).get('amount', {}).get('min', 0.001))
            max_amount = float(market.get('limits', {}).get('amount', {}).get('max', 1000))
            
            position_size = max(min_amount, min(position_size, max_amount))
            
            # Arredondar para a precisÃ£o mÃ­nima
            precision = market.get('precision', {}).get('amount', 4)
            position_size = round(position_size, precision)
            
            logger.info(f"Saldo USDT: {usdt_balance:.2f}, PreÃ§o ETH: {current_price:.4f}")
            logger.info(f"Tamanho calculado da posiÃ§Ã£o: {position_size} ETH")
            
            return position_size
            
        except Exception as e:
            logger.error(f"Erro ao calcular tamanho da posiÃ§Ã£o: {e}")
            return 0.001  # Valor padrÃ£o mÃ­nimo
    
    def run_strategy(self):
        """Executa uma iteraÃ§Ã£o da estratÃ©gia"""
        try:
            logger.info("Verificando sinais...")
            
            # Obter dados
            df = self.get_ohlcv_data()
            current_price = df['close'].iloc[-1]
            
            # Calcular indicadores
            df = self.calculate_supertrend(df)
            bullish_breakout, bearish_breakout = self.calculate_smart_money_breakout(df)
            
            # Obter sinal do Supertrend
            supertrend_trend = df['supertrend_direction'].iloc[-1]
            supertrend_signal = "ALTA" if supertrend_trend == 1 else "BAIXA"
            
            logger.info(f"PreÃ§o atual: {current_price}")
            logger.info(f"Supertrend: {supertrend_signal}")
            logger.info(f"Breakout Alta: {bullish_breakout}, Breakout Baixa: {bearish_breakout}")
            
            # Verificar stop loss primeiro
            if self.check_stop_loss(current_price):
                self.close_position()
                return
            
            # LÃ³gica de sinais combinados
            should_go_long = (supertrend_trend == 1 and bullish_breakout)
            should_go_short = (supertrend_trend == -1 and bearish_breakout)
            
            # Executar ordens apenas se houver sinal claro
            if should_go_long and self.current_position != 'long':
                logger.info("SINAL DE COMPRA DETECTADO!")
                
                # Fechar posiÃ§Ã£o short se existir
                if self.current_position == 'short':
                    if not self.close_position():
                        logger.error("Falha ao fechar posiÃ§Ã£o short")
                        return
                
                # Aguardar um momento apÃ³s fechar posiÃ§Ã£o
                time.sleep(3)
                
                # Abrir posiÃ§Ã£o long
                position_size = self.calculate_position_size()
                if position_size > 0 and self.open_position('buy', position_size):
                    logger.info("PosiÃ§Ã£o LONG aberta com sucesso")
                else:
                    logger.error("Falha ao abrir posiÃ§Ã£o LONG")
                
            elif should_go_short and self.current_position != 'short':
                logger.info("SINAL DE VENDA DETECTADO!")
                
                # Fechar posiÃ§Ã£o long se existir
                if self.current_position == 'long':
                    if not self.close_position():
                        logger.error("Falha ao fechar posiÃ§Ã£o long")
                        return
                
                # Aguardar um momento apÃ³s fechar posiÃ§Ã£o
                time.sleep(3)
                
                # Abrir posiÃ§Ã£o short
                position_size = self.calculate_position_size()
                if position_size > 0 and self.open_position('sell', position_size):
                    logger.info("PosiÃ§Ã£o SHORT aberta com sucesso")
                else:
                    logger.error("Falha ao abrir posiÃ§Ã£o SHORT")
            
            # Status da posiÃ§Ã£o atual
            if self.current_position:
                pnl_percentage = ((current_price - self.entry_price) / self.entry_price) * 100
                if self.current_position == 'short':
                    pnl_percentage *= -1
                
                logger.info(f"PosiÃ§Ã£o atual: {self.current_position.upper()}")
                logger.info(f"P&L: {pnl_percentage:.2f}%")
            else:
                logger.info("Sem posiÃ§Ã£o ativa")
                
        except Exception as e:
            logger.error(f"Erro na execuÃ§Ã£o da estratÃ©gia: {e}")
    
    def run(self):
        """Loop principal do bot"""
        logger.info("Iniciando bot de trading...")
        logger.info(f"Par: {self.symbol}")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"Alavancagem: {self.leverage}x")
        logger.info(f"Stop Loss: {self.stop_loss_percentage*100}%")
        
        while True:
            try:
                self.run_strategy()
                
                # Aguardar 5 minutos antes da prÃ³xima verificaÃ§Ã£o
                logger.info("Aguardando 5 minutos para prÃ³xima verificaÃ§Ã£o...")
                time.sleep(300)  # 5 minutos
                
            except KeyboardInterrupt:
                logger.info("Bot interrompido pelo usuÃ¡rio")
                break
            except Exception as e:
                logger.error(f"Erro no loop principal: {e}")
                logger.info("Aguardando 30 segundos antes de tentar novamente...")
                time.sleep(30)

def main():
    """FunÃ§Ã£o principal"""
    try:
        bot = TradingBot()
        bot.run()
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
        raise

if __name__ == "__main__":
    main()
