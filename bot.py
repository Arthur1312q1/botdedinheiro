import ccxt
import pandas as pd
import pandas_ta as ta
import numpy as np
import time
import logging
import os
from datetime import datetime
from typing import Tuple, Optional, Dict, Any

# Configuração de logging
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
        # Configurações da exchange
        self.exchange = self._setup_exchange()
        self.symbol = 'ETHUSDT_UMCBL'
        self.timeframe = '5m'  # Mudando para 5min para melhor precisão
        self.leverage = 10
        self.stop_loss_percentage = 0.015  # 1.5% stop loss mais conservador
        
        # Estado da posição
        self.current_position = None  # 'long', 'short', None
        self.entry_price = None
        self.position_size = None
        
        # Parâmetros dos indicadores melhorados
        self.supertrend_period = 14  # Período mais padrão
        self.supertrend_multiplier = 2.5  # Multiplicador mais sensível
        self.ema_fast = 12
        self.ema_slow = 26
        self.rsi_period = 14
        self.volume_sma_period = 20
        
        # Controle de sinais
        self.min_volume_multiplier = 1.5  # Volume mínimo para considerar sinal
        self.last_signal_time = None
        self.signal_cooldown = 300  # 5 minutos entre sinais
        
        logger.info("Bot de trading inicializado com estratégia melhorada")
        logger.info(f"Timeframe: {self.timeframe}, Stop Loss: {self.stop_loss_percentage*100}%")
    
    def _setup_exchange(self) -> ccxt.bitget:
        """Configura a conexão com a Bitget"""
        api_key = os.getenv('BITGET_API_KEY')
        secret_key = os.getenv('BITGET_API_SECRET')
        password = os.getenv('BITGET_PASSPHRASE')
        
        if not all([api_key, secret_key, password]):
            raise ValueError("Chaves da API não encontradas nas variáveis de ambiente")
        
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
        """Obtém dados OHLCV da exchange"""
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

    def calculate_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula múltiplos indicadores técnicos para melhor precisão"""
        try:
            # Supertrend
            df = self.calculate_supertrend(df)
            
            # EMAs
            df['ema_fast'] = ta.ema(df['close'], length=self.ema_fast)
            df['ema_slow'] = ta.ema(df['close'], length=self.ema_slow)
            
            # RSI
            df['rsi'] = ta.rsi(df['close'], length=self.rsi_period)
            
            # Volume SMA
            df['volume_sma'] = df['volume'].rolling(window=self.volume_sma_period).mean()
            df['volume_ratio'] = df['volume'] / df['volume_sma']
            
            # MACD
            macd = ta.macd(df['close'])
            df['macd'] = macd['MACD_12_26_9']
            df['macd_signal'] = macd['MACDs_12_26_9']
            df['macd_histogram'] = macd['MACDh_12_26_9']
            
            # Bollinger Bands
            bb = ta.bbands(df['close'], length=20)
            df['bb_upper'] = bb['BBU_20_2.0']
            df['bb_lower'] = bb['BBL_20_2.0']
            df['bb_middle'] = bb['BBM_20_2.0']
            
            return df
        except Exception as e:
            logger.error(f"Erro ao calcular indicadores técnicos: {e}")
            # Retornar pelo menos o Supertrend
            return self.calculate_supertrend(df)
    
    def analyze_market_conditions(self, df: pd.DataFrame) -> dict:
        """Analisa condições do mercado para melhor tomada de decisão"""
        try:
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            analysis = {
                'trend_strength': 0,
                'momentum': 0,
                'volume_confirmation': False,
                'market_regime': 'ranging',
                'signal_quality': 0
            }
            
            # Análise de tendência (Supertrend + EMAs)
            supertrend_bullish = latest['supertrend_direction'] == 1
            ema_bullish = latest['ema_fast'] > latest['ema_slow']
            price_above_ema = latest['close'] > latest['ema_fast']
            
            if supertrend_bullish and ema_bullish and price_above_ema:
                analysis['trend_strength'] = 1  # Bullish
                analysis['market_regime'] = 'uptrend'
            elif not supertrend_bullish and not ema_bullish and not price_above_ema:
                analysis['trend_strength'] = -1  # Bearish
                analysis['market_regime'] = 'downtrend'
            else:
                analysis['trend_strength'] = 0  # Neutro/ranging
            
            # Análise de momentum (RSI + MACD)
            rsi = latest['rsi']
            macd_bullish = latest['macd'] > latest['macd_signal']
            macd_increasing = latest['macd_histogram'] > prev['macd_histogram']
            
            momentum_score = 0
            if rsi > 60 and macd_bullish and macd_increasing:
                momentum_score = 1
            elif rsi < 40 and not macd_bullish and not macd_increasing:
                momentum_score = -1
            
            analysis['momentum'] = momentum_score
            
            # Confirmação de volume
            volume_ratio = latest['volume_ratio']
            analysis['volume_confirmation'] = volume_ratio > self.min_volume_multiplier
            
            # Qualidade geral do sinal (0-100)
            signal_quality = 0
            if analysis['trend_strength'] != 0:
                signal_quality += 30  # Tendência clara
            if analysis['momentum'] == analysis['trend_strength']:
                signal_quality += 25  # Momentum alinhado
            if analysis['volume_confirmation']:
                signal_quality += 20  # Volume confirmando
            if 30 < rsi < 70:  # RSI não em extremos
                signal_quality += 15
            if abs(latest['close'] - latest['bb_middle']) < (latest['bb_upper'] - latest['bb_lower']) * 0.3:
                signal_quality += 10  # Preço próximo da média das Bollinger
                
            analysis['signal_quality'] = signal_quality
            
            return analysis
            
        except Exception as e:
            logger.error(f"Erro na análise de mercado: {e}")
            return {
                'trend_strength': 0,
                'momentum': 0,
                'volume_confirmation': False,
                'market_regime': 'ranging',
                'signal_quality': 0
            }

    def should_enter_position(self, df: pd.DataFrame, side: str) -> bool:
        """Lógica melhorada para decisão de entrada em posição"""
        try:
            # Verificar cooldown entre sinais
            current_time = time.time()
            if self.last_signal_time and (current_time - self.last_signal_time) < self.signal_cooldown:
                return False
            
            # Análise completa do mercado
            analysis = self.analyze_market_conditions(df)
            
            # Critérios mínimos para qualquer entrada
            if analysis['signal_quality'] < 60:  # Qualidade mínima de 60%
                return False
            
            if not analysis['volume_confirmation']:  # Volume deve confirmar
                return False
            
            latest = df.iloc[-1]
            
            if side == 'long':
                # Condições para entrada LONG
                conditions = [
                    analysis['trend_strength'] == 1,  # Tendência bullish
                    analysis['momentum'] >= 0,        # Momentum positivo ou neutro
                    latest['rsi'] < 70,              # RSI não sobrecomprado
                    latest['close'] > latest['supertrend'],  # Preço acima do Supertrend
                    latest['macd'] > latest['macd_signal'],  # MACD bullish
                    latest['ema_fast'] > latest['ema_slow']  # EMAs bullish
                ]
                
                # Pelo menos 4 das 6 condições devem ser atendidas
                score = sum(conditions)
                if score >= 4:
                    logger.info(f"Condições LONG atendidas: {score}/6")
                    self.last_signal_time = current_time
                    return True
                    
            elif side == 'short':
                # Condições para entrada SHORT
                conditions = [
                    analysis['trend_strength'] == -1, # Tendência bearish
                    analysis['momentum'] <= 0,        # Momentum negativo ou neutro
                    latest['rsi'] > 30,              # RSI não sobrevendido
                    latest['close'] < latest['supertrend'],  # Preço abaixo do Supertrend
                    latest['macd'] < latest['macd_signal'],  # MACD bearish
                    latest['ema_fast'] < latest['ema_slow']  # EMAs bearish
                ]
                
                # Pelo menos 4 das 6 condições devem ser atendidas
                score = sum(conditions)
                if score >= 4:
                    logger.info(f"Condições SHORT atendidas: {score}/6")
                    self.last_signal_time = current_time
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Erro na análise de entrada: {e}")
            return False
    
    def get_position_info(self) -> Dict[str, Any]:
        """Obtém informações da posição atual"""
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
            logger.error(f"Erro ao obter informações da posição: {e}")
            return None
    
    def close_position(self) -> bool:
        """Fecha a posição atual"""
        try:
            position_info = self.get_position_info()
            if not position_info:
                logger.info("Nenhuma posição para fechar")
                return True
            
            side = 'buy' if position_info['side'] == 'short' else 'sell'
            
            order = self.exchange.create_market_order(
                symbol=self.symbol,
                side=side,
                amount=position_info['size'],
                params={'reduceOnly': True}
            )
            
            logger.info(f"Posição fechada: {order['id']}")
            self.current_position = None
            self.entry_price = None
            self.position_size = None
            return True
            
        except Exception as e:
            logger.error(f"Erro ao fechar posição: {e}")
            return False
    
    def open_position(self, side: str, amount: float) -> bool:
        """Abre uma nova posição"""
        try:
            # Verificar saldo mínimo
            if amount <= 0:
                logger.error("Quantidade da posição deve ser maior que zero")
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
                
                logger.info(f"Posição {self.current_position} aberta: {order['id']}, Preço: {self.entry_price}")
                return True
            else:
                logger.error(f"Ordem não foi executada completamente: {order}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao abrir posição {side}: {e}")
            return False
    
    def check_stop_loss(self, current_price: float) -> bool:
        """Verifica se o stop loss deve ser acionado"""
        if not self.current_position or not self.entry_price:
            return False
        
        if self.current_position == 'long':
            stop_loss_price = self.entry_price * (1 - self.stop_loss_percentage)
            if current_price <= stop_loss_price:
                logger.warning(f"Stop Loss acionado para posição LONG! Preço atual: {current_price}, Stop: {stop_loss_price}")
                return True
                
        elif self.current_position == 'short':
            stop_loss_price = self.entry_price * (1 + self.stop_loss_percentage)
            if current_price >= stop_loss_price:
                logger.warning(f"Stop Loss acionado para posição SHORT! Preço atual: {current_price}, Stop: {stop_loss_price}")
                return True
        
        return False
    
    def calculate_position_size(self) -> float:
        """Calcula o tamanho da posição baseado no saldo disponível"""
        try:
            balance = self.exchange.fetch_balance()
            usdt_balance = float(balance.get('USDT', {}).get('free', 0))
            
            if usdt_balance <= 0:
                logger.error("Saldo USDT insuficiente")
                return 0
            
            # Usar 80% do saldo disponível (mais conservador)
            position_value = usdt_balance * 0.8
            
            # Obter preço atual
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = float(ticker['last'])
            
            if current_price <= 0:
                logger.error("Preço atual inválido")
                return 0
            
            # Calcular tamanho base da posição (sem alavancagem)
            position_size = position_value / current_price
            
            # Aplicar limites mínimos e máximos
            market = self.exchange.market(self.symbol)
            min_amount = float(market.get('limits', {}).get('amount', {}).get('min', 0.001))
            max_amount = float(market.get('limits', {}).get('amount', {}).get('max', 1000))
            
            position_size = max(min_amount, min(position_size, max_amount))
            
            # Arredondar para a precisão mínima
            precision = market.get('precision', {}).get('amount', 4)
            position_size = round(position_size, precision)
            
            logger.info(f"Saldo USDT: {usdt_balance:.2f}, Preço ETH: {current_price:.4f}")
            logger.info(f"Tamanho calculado da posição: {position_size} ETH")
            
            return position_size
            
        except Exception as e:
            logger.error(f"Erro ao calcular tamanho da posição: {e}")
            return 0.001  # Valor padrão mínimo
    
    def run_strategy(self):
        """Executa uma iteração da estratégia melhorada"""
        try:
            logger.info("Verificando sinais com estratégia melhorada...")
            
            # Obter dados com mais histórico para indicadores
            df = self.get_ohlcv_data(limit=200)
            if df is None or len(df) < 50:
                logger.error("Dados OHLCV insuficientes ou inválidos")
                return
            
            current_price = df['close'].iloc[-1]
            
            # Calcular todos os indicadores técnicos
            df = self.calculate_technical_indicators(df)
            
            # Verificar se os indicadores foram calculados corretamente
            if 'supertrend_direction' not in df.columns:
                logger.error("Erro no cálculo dos indicadores")
                return
            
            # Análise do mercado
            market_analysis = self.analyze_market_conditions(df)
            
            # Log das condições atuais
            latest = df.iloc[-1]
            logger.info(f"Preço atual: ${current_price:.4f}")
            logger.info(f"Regime de mercado: {market_analysis['market_regime']}")
            logger.info(f"Qualidade do sinal: {market_analysis['signal_quality']}%")
            logger.info(f"Volume confirmação: {market_analysis['volume_confirmation']}")
            logger.info(f"RSI: {latest['rsi']:.2f}")
            
            # Verificar stop loss primeiro
            if self.check_stop_loss(current_price):
                self.close_position()
                return
            
            # Lógica de entrada em posições com nova estratégia
            if self.current_position is None:
                # Verificar entrada LONG
                if self.should_enter_position(df, 'long'):
                    logger.info("SINAL DE COMPRA DETECTADO - Estratégia Melhorada!")
                    position_size = self.calculate_position_size()
                    if position_size > 0 and self.open_position('buy', position_size):
                        logger.info("Posição LONG aberta com sucesso")
                    else:
                        logger.error("Falha ao abrir posição LONG")
                
                # Verificar entrada SHORT
                elif self.should_enter_position(df, 'short'):
                    logger.info("SINAL DE VENDA DETECTADO - Estratégia Melhorada!")
                    position_size = self.calculate_position_size()
                    if position_size > 0 and self.open_position('sell', position_size):
                        logger.info("Posição SHORT aberta com sucesso")
                    else:
                        logger.error("Falha ao abrir posição SHORT")
            
            # Lógica de saída - fechar posição se condições mudaram
            elif self.current_position == 'long':
                # Fechar LONG se tendência virou bearish com alta confiança
                if (market_analysis['trend_strength'] == -1 and 
                    market_analysis['signal_quality'] > 70 and
                    latest['rsi'] > 65):  # RSI alto indica possível reversão
                    
                    logger.info("Fechando posição LONG - reversão de tendência detectada")
                    self.close_position()
                    
            elif self.current_position == 'short':
                # Fechar SHORT se tendência virou bullish com alta confiança
                if (market_analysis['trend_strength'] == 1 and 
                    market_analysis['signal_quality'] > 70 and
                    latest['rsi'] < 35):  # RSI baixo indica possível reversão
                    
                    logger.info("Fechando posição SHORT - reversão de tendência detectada")
                    self.close_position()
            
            # Status da posição atual
            if self.current_position:
                pnl_percentage = ((current_price - self.entry_price) / self.entry_price) * 100
                if self.current_position == 'short':
                    pnl_percentage *= -1
                
                logger.info(f"Posição atual: {self.current_position.upper()}")
                logger.info(f"P&L: {pnl_percentage:.2f}%")
            else:
                logger.info("Sem posição ativa - aguardando sinal de alta qualidade")
                
        except Exception as e:
            logger.error(f"Erro na execução da estratégia: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
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
                
                # Aguardar 2 minutos antes da próxima verificação
                logger.info("Aguardando 2 minutos para próxima verificação...")
                time.sleep(120)  # 2 minutos
                
            except KeyboardInterrupt:
                logger.info("Bot interrompido pelo usuário")
                break
            except Exception as e:
                logger.error(f"Erro no loop principal: {e}")
                logger.info("Aguardando 30 segundos antes de tentar novamente...")
                time.sleep(30)

def main():
    """Função principal"""
    try:
        bot = TradingBot()
        bot.run()
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
        raise

if __name__ == "__main__":
    main()
