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
        """Inicializa o bot de trading com estratégia mais agressiva"""
        # Configurações da exchange
        self.exchange = self._setup_exchange()
        self.symbol = 'ETHUSDT_UMCBL'
        self.timeframe = '3m'  # Timeframe menor para mais sinais
        self.leverage = 10
        self.stop_loss_percentage = 0.02  # 2% stop loss
        self.take_profit_percentage = 0.04  # 4% take profit
        
        # Estado da posição
        self.current_position = None  # 'long', 'short', None
        self.entry_price = None
        self.position_size = None
        self.position_start_time = None
        
        # Parâmetros dos indicadores otimizados para mais trades
        self.supertrend_period = 10  # Mais sensível
        self.supertrend_multiplier = 2.0  # Mais sensível
        self.ema_fast = 8
        self.ema_slow = 20
        self.rsi_period = 12
        self.volume_sma_period = 14
        
        # Controle de sinais mais permissivo
        self.min_volume_multiplier = 1.2  # Volume mínimo reduzido
        self.last_signal_time = None
        self.signal_cooldown = 180  # 3 minutos entre sinais (reduzido)
        
        # Configurações de scalping
        self.scalping_mode = True
        self.max_position_time = 1800  # 30 minutos máximo por posição
        
        logger.info("Bot de trading inicializado - MODO AGRESSIVO")
        logger.info(f"Timeframe: {self.timeframe}, Stop Loss: {self.stop_loss_percentage*100}%")
        logger.info(f"Take Profit: {self.take_profit_percentage*100}%, Scalping: {self.scalping_mode}")
    
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
            'sandbox': False,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap'
            }
        })
        
        return exchange
    
    def get_ohlcv_data(self, limit: int = 100) -> pd.DataFrame:
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
        """Calcula o indicador Supertrend de forma mais robusta"""
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
            
            # Calcular final bands
            final_upper_band = basic_upper_band.copy()
            final_lower_band = basic_lower_band.copy()
            
            for i in range(1, len(df)):
                # Final upper band
                if basic_upper_band.iloc[i] < final_upper_band.iloc[i-1] or df['close'].iloc[i-1] > final_upper_band.iloc[i-1]:
                    final_upper_band.iloc[i] = basic_upper_band.iloc[i]
                else:
                    final_upper_band.iloc[i] = final_upper_band.iloc[i-1]
                
                # Final lower band
                if basic_lower_band.iloc[i] > final_lower_band.iloc[i-1] or df['close'].iloc[i-1] < final_lower_band.iloc[i-1]:
                    final_lower_band.iloc[i] = basic_lower_band.iloc[i]
                else:
                    final_lower_band.iloc[i] = final_lower_band.iloc[i-1]
            
            # Calcular Supertrend
            supertrend = pd.Series(index=df.index, dtype=float)
            direction = pd.Series(index=df.index, dtype=float)
            
            # Inicializar primeira linha
            if df['close'].iloc[0] <= final_lower_band.iloc[0]:
                supertrend.iloc[0] = final_upper_band.iloc[0]
                direction.iloc[0] = -1
            else:
                supertrend.iloc[0] = final_lower_band.iloc[0]
                direction.iloc[0] = 1
            
            # Calcular resto
            for i in range(1, len(df)):
                if supertrend.iloc[i-1] == final_upper_band.iloc[i-1] and df['close'].iloc[i] <= final_upper_band.iloc[i]:
                    supertrend.iloc[i] = final_upper_band.iloc[i]
                    direction.iloc[i] = -1
                elif supertrend.iloc[i-1] == final_upper_band.iloc[i-1] and df['close'].iloc[i] > final_upper_band.iloc[i]:
                    supertrend.iloc[i] = final_lower_band.iloc[i]
                    direction.iloc[i] = 1
                elif supertrend.iloc[i-1] == final_lower_band.iloc[i-1] and df['close'].iloc[i] >= final_lower_band.iloc[i]:
                    supertrend.iloc[i] = final_lower_band.iloc[i]
                    direction.iloc[i] = 1
                elif supertrend.iloc[i-1] == final_lower_band.iloc[i-1] and df['close'].iloc[i] < final_lower_band.iloc[i]:
                    supertrend.iloc[i] = final_upper_band.iloc[i]
                    direction.iloc[i] = -1
                else:
                    supertrend.iloc[i] = supertrend.iloc[i-1]
                    direction.iloc[i] = direction.iloc[i-1]
            
            df['supertrend'] = supertrend
            df['supertrend_direction'] = direction
            
            return df
        except Exception as e:
            logger.error(f"Erro ao calcular Supertrend: {e}")
            # Fallback simples
            df['supertrend'] = df['close'].rolling(window=self.supertrend_period).mean()
            df['supertrend_direction'] = np.where(df['close'] > df['supertrend'], 1, -1)
            return df

    def calculate_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula indicadores técnicos otimizados para scalping"""
        try:
            # Supertrend
            df = self.calculate_supertrend(df)
            
            # EMAs rápidas
            df['ema_fast'] = df['close'].ewm(span=self.ema_fast).mean()
            df['ema_slow'] = df['close'].ewm(span=self.ema_slow).mean()
            
            # RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            
            # Volume
            df['volume_sma'] = df['volume'].rolling(window=self.volume_sma_period).mean()
            df['volume_ratio'] = df['volume'] / df['volume_sma']
            
            # MACD rápido
            exp1 = df['close'].ewm(span=8).mean()
            exp2 = df['close'].ewm(span=17).mean()
            df['macd'] = exp1 - exp2
            df['macd_signal'] = df['macd'].ewm(span=6).mean()
            df['macd_histogram'] = df['macd'] - df['macd_signal']
            
            # Bollinger Bands
            period = 15
            std = df['close'].rolling(window=period).std()
            df['bb_middle'] = df['close'].rolling(window=period).mean()
            df['bb_upper'] = df['bb_middle'] + (std * 1.8)
            df['bb_lower'] = df['bb_middle'] - (std * 1.8)
            
            # Momentum simples
            df['momentum'] = df['close'] / df['close'].shift(5) - 1
            
            # Price change momentum
            df['price_change'] = df['close'].pct_change()
            df['price_velocity'] = df['price_change'].rolling(window=3).mean()
            
            return df
        except Exception as e:
            logger.error(f"Erro ao calcular indicadores: {e}")
            return df
    
    def generate_signals(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Gera sinais de trading baseado em múltiplos critérios"""
        try:
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            signals = {
                'long': 0,
                'short': 0,
                'strength': 0,
                'reasons': []
            }
            
            # 1. Supertrend Cross (peso alto - 3 pontos)
            if prev['supertrend_direction'] == -1 and latest['supertrend_direction'] == 1:
                signals['long'] += 3
                signals['reasons'].append('Supertrend virou BULL')
            elif prev['supertrend_direction'] == 1 and latest['supertrend_direction'] == -1:
                signals['short'] += 3
                signals['reasons'].append('Supertrend virou BEAR')
            
            # 2. Price vs Supertrend (peso médio - 2 pontos)
            if latest['close'] > latest['supertrend'] and latest['supertrend_direction'] == 1:
                signals['long'] += 2
                signals['reasons'].append('Preço acima do Supertrend')
            elif latest['close'] < latest['supertrend'] and latest['supertrend_direction'] == -1:
                signals['short'] += 2
                signals['reasons'].append('Preço abaixo do Supertrend')
            
            # 3. EMA Cross (peso médio - 2 pontos)
            if prev['ema_fast'] <= prev['ema_slow'] and latest['ema_fast'] > latest['ema_slow']:
                signals['long'] += 2
                signals['reasons'].append('EMA bullish cross')
            elif prev['ema_fast'] >= prev['ema_slow'] and latest['ema_fast'] < latest['ema_slow']:
                signals['short'] += 2
                signals['reasons'].append('EMA bearish cross')
            
            # 4. EMA Alignment (peso baixo - 1 ponto)
            if latest['ema_fast'] > latest['ema_slow'] and latest['close'] > latest['ema_fast']:
                signals['long'] += 1
                signals['reasons'].append('EMAs alinhadas BULL')
            elif latest['ema_fast'] < latest['ema_slow'] and latest['close'] < latest['ema_fast']:
                signals['short'] += 1
                signals['reasons'].append('EMAs alinhadas BEAR')
            
            # 5. RSI Extremes Recovery (peso médio - 2 pontos)
            if latest['rsi'] < 30 and prev['rsi'] >= 30:  # Entrando em oversold
                signals['long'] += 1
                signals['reasons'].append('RSI oversold')
            elif latest['rsi'] > 30 and prev['rsi'] <= 30:  # Saindo de oversold
                signals['long'] += 2
                signals['reasons'].append('RSI saindo de oversold')
            elif latest['rsi'] > 70 and prev['rsi'] <= 70:  # Entrando em overbought
                signals['short'] += 1
                signals['reasons'].append('RSI overbought')
            elif latest['rsi'] < 70 and prev['rsi'] >= 70:  # Saindo de overbought
                signals['short'] += 2
                signals['reasons'].append('RSI saindo de overbought')
            
            # 6. MACD Momentum (peso baixo - 1 ponto)
            if latest['macd'] > latest['macd_signal'] and prev['macd'] <= prev['macd_signal']:
                signals['long'] += 1
                signals['reasons'].append('MACD cross bullish')
            elif latest['macd'] < latest['macd_signal'] and prev['macd'] >= prev['macd_signal']:
                signals['short'] += 1
                signals['reasons'].append('MACD cross bearish')
            
            # 7. MACD Histogram (peso baixo - 1 ponto)
            if latest['macd_histogram'] > 0 and prev['macd_histogram'] <= 0:
                signals['long'] += 1
                signals['reasons'].append('MACD histogram +')
            elif latest['macd_histogram'] < 0 and prev['macd_histogram'] >= 0:
                signals['short'] += 1
                signals['reasons'].append('MACD histogram -')
            
            # 8. Bollinger Bands Breakout (peso alto - 3 pontos)
            if latest['close'] > latest['bb_upper'] and latest['volume_ratio'] > 1.3:
                signals['long'] += 3
                signals['reasons'].append('BB breakout UP com volume')
            elif latest['close'] < latest['bb_lower'] and latest['volume_ratio'] > 1.3:
                signals['short'] += 3
                signals['reasons'].append('BB breakout DOWN com volume')
            
            # 9. Momentum Simples (peso baixo - 1 ponto)
            if latest['momentum'] > 0.003:  # 0.3% momentum positivo
                signals['long'] += 1
                signals['reasons'].append('Momentum positivo')
            elif latest['momentum'] < -0.003:  # 0.3% momentum negativo
                signals['short'] += 1
                signals['reasons'].append('Momentum negativo')
            
            # 10. Price Velocity (peso baixo - 1 ponto)
            if latest['price_velocity'] > 0.001:  # Aceleração positiva
                signals['long'] += 1
                signals['reasons'].append('Aceleração de preço +')
            elif latest['price_velocity'] < -0.001:  # Aceleração negativa
                signals['short'] += 1
                signals['reasons'].append('Aceleração de preço -')
            
            # 11. Volume Confirmation (bonus - 1 ponto se já há outros sinais)
            if latest['volume_ratio'] > self.min_volume_multiplier:
                if signals['long'] > 0:
                    signals['long'] += 1
                    signals['reasons'].append('Volume confirmando LONG')
                elif signals['short'] > 0:
                    signals['short'] += 1
                    signals['reasons'].append('Volume confirmando SHORT')
            
            # Calcular força geral do sinal
            signals['strength'] = max(signals['long'], signals['short'])
            
            return signals
            
        except Exception as e:
            logger.error(f"Erro ao gerar sinais: {e}")
            return {'long': 0, 'short': 0, 'strength': 0, 'reasons': []}
    
    def should_enter_position(self, df: pd.DataFrame) -> Tuple[bool, str, int]:
        """Decide se deve entrar em posição com critérios flexíveis"""
        try:
            # Verificar cooldown
            current_time = time.time()
            if self.last_signal_time and (current_time - self.last_signal_time) < self.signal_cooldown:
                return False, None, 0
            
            # Gerar sinais
            signals = self.generate_signals(df)
            
            # Critérios mais flexíveis - só precisa de 3 pontos
            min_strength = 3
            
            if signals['long'] >= min_strength and signals['long'] > signals['short']:
                logger.info(f"SINAL LONG DETECTADO - Força: {signals['long']}")
                logger.info(f"Razões: {', '.join(signals['reasons'])}")
                self.last_signal_time = current_time
                return True, 'long', signals['long']
            
            elif signals['short'] >= min_strength and signals['short'] > signals['long']:
                logger.info(f"SINAL SHORT DETECTADO - Força: {signals['short']}")
                logger.info(f"Razões: {', '.join(signals['reasons'])}")
                self.last_signal_time = current_time
                return True, 'short', signals['short']
            
            # Log de sinais fracos para debugging
            if signals['strength'] > 0:
                logger.info(f"Sinal fraco - L:{signals['long']} S:{signals['short']} - {', '.join(signals['reasons'][:3])}")
            
            return False, None, max(signals['long'], signals['short'])
            
        except Exception as e:
            logger.error(f"Erro na análise de entrada: {e}")
            return False, None, 0
    
    def should_close_position(self, df: pd.DataFrame, current_price: float) -> bool:
        """Verifica se deve fechar posição atual"""
        try:
            if not self.current_position or not self.entry_price:
                return False
            
            latest = df.iloc[-1]
            
            # 1. Take Profit
            if self.current_position == 'long':
                profit_pct = (current_price - self.entry_price) / self.entry_price
                if profit_pct >= self.take_profit_percentage:
                    logger.info(f"TAKE PROFIT LONG atingido: {profit_pct*100:.2f}%")
                    return True
                    
                # Reversão de sinais
                signals = self.generate_signals(df)
                if signals['short'] >= 4:  # Sinal forte contrário
                    logger.info("Fechando LONG - sinal SHORT forte detectado")
                    return True
                    
            elif self.current_position == 'short':
                profit_pct = (self.entry_price - current_price) / self.entry_price
                if profit_pct >= self.take_profit_percentage:
                    logger.info(f"TAKE PROFIT SHORT atingido: {profit_pct*100:.2f}%")
                    return True
                    
                # Reversão de sinais
                signals = self.generate_signals(df)
                if signals['long'] >= 4:  # Sinal forte contrário
                    logger.info("Fechando SHORT - sinal LONG forte detectado")
                    return True
            
            # 2. Tempo máximo de posição (scalping)
            if self.position_start_time:
                position_duration = time.time() - self.position_start_time
                if position_duration > self.max_position_time:
                    logger.info(f"Fechando posição por tempo limite: {position_duration/60:.1f} min")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Erro na verificação de fechamento: {e}")
            return False
    
    def get_position_info(self) -> Optional[Dict[str, Any]]:
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
                self.current_position = None
                self.entry_price = None
                self.position_size = None
                self.position_start_time = None
                return True
            
            side = 'buy' if position_info['side'] == 'short' else 'sell'
            
            order = self.exchange.create_market_order(
                symbol=self.symbol,
                side=side,
                amount=position_info['size'],
                params={'reduceOnly': True}
            )
            
            logger.info(f"Posição {self.current_position} fechada: {order['id']}")
            logger.info(f"P&L realizado: {position_info['percentage']:.2f}%")
            
            # Reset estado
            self.current_position = None
            self.entry_price = None
            self.position_size = None
            self.position_start_time = None
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao fechar posição: {e}")
            return False
    
    def open_position(self, side: str, amount: float) -> bool:
        """Abre uma nova posição"""
        try:
            if amount <= 0:
                logger.error("Quantidade da posição deve ser maior que zero")
                return False
            
            # Configurar alavancagem
            try:
                self.exchange.set_leverage(self.leverage, self.symbol)
            except Exception as e:
                logger.warning(f"Aviso ao configurar alavancagem: {e}")
            
            # Criar ordem de mercado
            order = self.exchange.create_market_order(
                symbol=self.symbol,
                side=side,
                amount=amount
            )
            
            # Aguardar processamento
            time.sleep(2)
            
            # Verificar execução
            if order.get('status') == 'closed' or order.get('filled', 0) > 0:
                # Atualizar estado
                self.current_position = 'long' if side == 'buy' else 'short'
                self.entry_price = float(order.get('price') or order.get('average') or 0)
                self.position_size = float(order.get('filled', amount))
                self.position_start_time = time.time()
                
                logger.info(f"POSIÇÃO {self.current_position.upper()} ABERTA!")
                logger.info(f"Preço: ${self.entry_price:.4f}")
                logger.info(f"Tamanho: {self.position_size} ETH")
                
                return True
            else:
                logger.error(f"Ordem não executada: {order}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao abrir posição {side}: {e}")
            return False
    
    def check_stop_loss(self, current_price: float) -> bool:
        """Verifica stop loss"""
        if not self.current_position or not self.entry_price:
            return False
        
        if self.current_position == 'long':
            stop_price = self.entry_price * (1 - self.stop_loss_percentage)
            if current_price <= stop_price:
                loss_pct = (current_price - self.entry_price) / self.entry_price * 100
                logger.warning(f"STOP LOSS LONG ACIONADO! Perda: {loss_pct:.2f}%")
                return True
                
        elif self.current_position == 'short':
            stop_price = self.entry_price * (1 + self.stop_loss_percentage)
            if current_price >= stop_price:
                loss_pct = (self.entry_price - current_price) / self.entry_price * 100
                logger.warning(f"STOP LOSS SHORT ACIONADO! Perda: {loss_pct:.2f}%")
                return True
        
        return False
    
    def calculate_position_size(self) -> float:
        """Calcula tamanho da posição de forma mais agressiva"""
        try:
            balance = self.exchange.fetch_balance()
            usdt_balance = float(balance.get('USDT', {}).get('free', 0))
            
            if usdt_balance <= 10:  # Mínimo de $10
                logger.error(f"Saldo USDT insuficiente: ${usdt_balance:.2f}")
                return 0
            
            # Usar 85% do saldo para scalping agressivo
            position_value = usdt_balance * 0.85
            
            # Obter preço atual
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = float(ticker['last'])
            
            if current_price <= 0:
                logger.error("Preço atual inválido")
                return 0
            
            # Calcular tamanho
            position_size = position_value / current_price
            
            # Aplicar limites da exchange
            market = self.exchange.market(self.symbol)
            min_amount = float(market.get('limits', {}).get('amount', {}).get('min', 0.001))
            max_amount = float(market.get('limits', {}).get('amount', {}).get('max', 1000))
            
            position_size = max(min_amount, min(position_size, max_amount))
            
            # Precisão
            precision = market.get('precision', {}).get('amount', 4)
            position_size = round(position_size, precision)
            
            logger.info(f"Saldo disponível: ${usdt_balance:.2f}")
            logger.info(f"Valor da posição: ${position_value:.2f}")
            logger.info(f"Preço ETH: ${current_price:.4f}")
            logger.info(f"Tamanho calculado: {position_size} ETH")
            
            return position_size
            
        except Exception as e:
            logger.error(f"Erro ao calcular tamanho da posição: {e}")
            return 0.001
    
    def run_strategy(self):
        """Executa uma iteração da estratégia otimizada"""
        try:
            logger.info("=== ANALISANDO MERCADO ===")
            
            # Obter dados
            df = self.get_ohlcv_data(limit=100)
            if df is None or len(df) < 30:
                logger.error("Dados insuficientes")
                return
            
            # Calcular indicadores
            df = self.calculate_technical_indicators(df)
            
            # Preço atual e informações
            current_price = df['close'].iloc[-1]
            latest = df.iloc[-1]
            
            logger.info(f"Preço ETH: ${current_price:.4f}")
            logger.info(f"Supertrend: {'BULL' if latest['supertrend_direction'] == 1 else 'BEAR'} (${latest['supertrend']:.4f})")
            logger.info(f"RSI: {latest['rsi']:.1f}")
            logger.info(f"Volume: {latest['volume_ratio']:.2f}x da média")
            
            # 1. Verificar stop loss primeiro
            if self.check_stop_loss(current_price):
                self.close_position()
                return
            
            # 2. Verificar fechamento de posição existente
            if self.current_position and self.should_close_position(df, current_price):
                self.close_position()
                return
            
            # 3. Procurar entrada em nova posição
            if not self.current_position:
                should_enter, direction, strength = self.should_enter_position(df)
                
                if should_enter and direction:
                    logger.info(f"=== ENTRADA {direction.upper()} DETECTADA ===")
                    logger.info(f"Força do sinal: {strength}")
                    
                    position_size = self.calculate_position_size()
                    if position_size > 0:
                        side = 'buy' if direction == 'long' else 'sell'
                        success = self.open_position(side, position_size)
                        
                        if success:
                            logger.info("POSIÇÃO ABERTA COM SUCESSO!")
                        else:
                            logger.error("FALHA AO ABRIR POSIÇÃO")
                    else:
                        logger.error("SALDO INSUFICIENTE PARA TRADING")
                else:
                    if strength > 0:
                        logger.info(f"Sinal fraco detectado (força: {strength}) - aguardando sinal mais forte")
                    else:
                        logger.info("Mercado neutro - sem sinais claros")
            
            # 4. Status da posição atual
            if self.current_position:
                pnl_pct = 0
                position_time = 0
                
                if self.entry_price:
                    pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100
                    if self.current_position == 'short':
                        pnl_pct *= -1
                
                if self.position_start_time:
                    position_time = (time.time() - self.position_start_time) / 60
                
                logger.info(f"POSIÇÃO ATIVA: {self.current_position.upper()}")
                logger.info(f"P&L: {pnl_pct:+.2f}% | Tempo: {position_time:.1f} min")
                
                # Avisos de gerenciamento de risco
                if position_time > 25:  # Próximo do limite de 30 min
                    logger.warning("ATENÇÃO: Posição próxima do tempo limite!")
                
                if self.current_position == 'long' and pnl_pct >= 3:
                    logger.info("PRÓXIMO DO TAKE PROFIT - Monitorando...")
                elif self.current_position == 'short' and pnl_pct >= 3:
                    logger.info("PRÓXIMO DO TAKE PROFIT - Monitorando...")
            
            logger.info("=" * 40)
                
        except Exception as e:
            logger.error(f"Erro na execução da estratégia: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    def run(self):
        """Loop principal do bot otimizado para máxima eficiência"""
        logger.info("=" * 60)
        logger.info("INICIANDO BOT DE TRADING - MODO AGRESSIVO")
        logger.info("=" * 60)
        logger.info(f"Par: {self.symbol}")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"Alavancagem: {self.leverage}x")
        logger.info(f"Stop Loss: {self.stop_loss_percentage*100}%")
        logger.info(f"Take Profit: {self.take_profit_percentage*100}%")
        logger.info(f"Tempo máximo por posição: {self.max_position_time/60:.1f} min")
        logger.info(f"Cooldown entre sinais: {self.signal_cooldown/60:.1f} min")
        logger.info("=" * 60)
        
        while True:
            try:
                self.run_strategy()
                
                # Aguardar 90 segundos entre verificações
                logger.info(f"Próxima análise em 90 segundos...\n")
                time.sleep(90)
                
            except KeyboardInterrupt:
                logger.info("Bot interrompido pelo usuário")
                if self.current_position:
                    logger.warning("ATENÇÃO: Posição ativa! Considere fechar manualmente.")
                break
            except Exception as e:
                logger.error(f"Erro crítico no loop principal: {e}")
                logger.info("Tentando recuperar em 30 segundos...")
                time.sleep(30)

def main():
    """Função principal"""
    try:
        bot = TradingBot()
        bot.run()
    except Exception as e:
        logger.error(f"Erro fatal ao inicializar bot: {e}")
        raise

if __name__ == "__main__":
    main()
