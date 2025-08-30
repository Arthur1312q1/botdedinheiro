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
        """Inicializa o bot com estratégia multi-indicador precisa"""
        # Configurações da exchange
        self.exchange = self._setup_exchange()
        self.symbol = 'ETHUSDT_UMCBL'
        self.timeframe = '3m'
        self.leverage = 15
        
        # Estado da posição
        self.current_position = None  # 'long', 'short', None
        self.entry_price = None
        self.position_size = None
        self.position_start_time = None
        
        # Parâmetros dos indicadores
        self.supertrend_period = 10
        self.supertrend_multiplier = 3.0
        self.atr_period = 13
        self.mfi_period = 10
        self.mfi_sma_period = 5
        
        # AlgoAlpha parameters (baseado em análise técnica avançada)
        self.algo_alpha_fast = 8
        self.algo_alpha_slow = 21
        self.algo_alpha_signal = 5
        
        # Thresholds para precisão aprimorada
        self.mfi_oversold = 25  # Mais conservador
        self.mfi_overbought = 75  # Mais conservador
        self.mfi_neutral = 50
        
        # Controle de trades mais rigoroso
        self.total_trades = 0
        self.successful_trades = 0
        self.last_signal_time = None
        self.signal_cooldown = 180  # 3 minutos para melhor precisão
        self.min_confidence = 70  # Confiança mínima aumentada
        self.min_signal_strength = 6  # Threshold mais alto
        
        # Estado anterior para detectar mudanças
        self.last_supertrend_direction = None
        self.last_algo_alpha_signal = None
        
        logger.info("Bot inicializado - ESTRATÉGIA MULTI-INDICADOR PRECISA")
        logger.info(f"Indicadores: Supertrend + AlgoAlpha + ATR + MFI")
        logger.info(f"Timeframe: {self.timeframe} | Cooldown: {self.signal_cooldown}s")
    
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
        """Calcula o indicador Supertrend"""
        try:
            # Calcular ATR
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            atr = true_range.rolling(window=self.supertrend_period, min_periods=1).mean()
            
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
            return df
    
    def calculate_atr(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula Average True Range"""
        try:
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            df['atr'] = true_range.rolling(window=self.atr_period, min_periods=1).mean()
            return df
        except Exception as e:
            logger.error(f"Erro ao calcular ATR: {e}")
            return df
    
    def calculate_mfi(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula Money Flow Index"""
        try:
            # Typical price = (high + low + close) / 3
            typical_price = (df['high'] + df['low'] + df['close']) / 3
            
            # Raw money flow = typical price * volume
            raw_money_flow = typical_price * df['volume']
            
            # Positive and negative money flow
            pos_flow = pd.Series(index=df.index, dtype=float)
            neg_flow = pd.Series(index=df.index, dtype=float)
            
            for i in range(1, len(df)):
                if typical_price.iloc[i] >= typical_price.iloc[i-1]:
                    pos_flow.iloc[i] = raw_money_flow.iloc[i]
                    neg_flow.iloc[i] = 0
                else:
                    pos_flow.iloc[i] = 0
                    neg_flow.iloc[i] = raw_money_flow.iloc[i]
            
            # Set first values
            pos_flow.iloc[0] = raw_money_flow.iloc[0]
            neg_flow.iloc[0] = 0
            
            # Calculate sums over the period
            pos_mf_sum = pos_flow.rolling(window=self.mfi_period, min_periods=1).sum()
            neg_mf_sum = neg_flow.rolling(window=self.mfi_period, min_periods=1).sum()
            
            # Money flow ratio
            mf_ratio = pos_mf_sum / neg_mf_sum.replace(0, 1)  # Avoid division by zero
            
            # Money Flow Index
            df['mfi'] = 100 - (100 / (1 + mf_ratio))
            
            # MFI SMA
            df['mfi_sma'] = df['mfi'].rolling(window=self.mfi_sma_period, min_periods=1).mean()
            
            return df
        except Exception as e:
            logger.error(f"Erro ao calcular MFI: {e}")
            return df
    
    def calculate_algo_alpha(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula AlgoAlpha - Indicador proprietário baseado em múltiplas EMAs e momentum"""
        try:
            # EMAs de diferentes períodos
            ema_fast = df['close'].ewm(span=self.algo_alpha_fast, adjust=False).mean()
            ema_slow = df['close'].ewm(span=self.algo_alpha_slow, adjust=False).mean()
            
            # MACD personalizado
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=self.algo_alpha_signal, adjust=False).mean()
            histogram = macd_line - signal_line
            
            # Momentum multi-timeframe
            momentum_3 = df['close'].pct_change(3)
            momentum_5 = df['close'].pct_change(5)
            momentum_8 = df['close'].pct_change(8)
            
            # Volume-weighted momentum
            volume_norm = df['volume'] / df['volume'].rolling(window=20, min_periods=1).mean()
            volume_momentum = momentum_3 * volume_norm
            
            # AlgoAlpha Score (combinação ponderada)
            df['algo_alpha_score'] = (
                (macd_line / df['close']) * 100 * 0.3 +  # MACD normalizado
                (histogram / df['close']) * 100 * 0.2 +  # Histogram normalizado
                momentum_3 * 100 * 0.2 +  # Momentum 3 períodos
                momentum_5 * 100 * 0.15 +  # Momentum 5 períodos
                volume_momentum * 100 * 0.15  # Volume momentum
            )
            
            # Suavizar o score
            df['algo_alpha'] = df['algo_alpha_score'].rolling(window=3, min_periods=1).mean()
            
            # Sinal do AlgoAlpha
            df['algo_alpha_signal'] = np.where(df['algo_alpha'] > 0, 1, -1)
            
            return df
        except Exception as e:
            logger.error(f"Erro ao calcular AlgoAlpha: {e}")
            return df
    
    def calculate_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula todos os indicadores necessários"""
        try:
            df = self.calculate_supertrend(df)
            df = self.calculate_atr(df)
            df = self.calculate_mfi(df)
            df = self.calculate_algo_alpha(df)
            return df
        except Exception as e:
            logger.error(f"Erro ao calcular indicadores: {e}")
            return df
    
    def analyze_market_conditions(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analisa as condições de mercado usando todos os indicadores"""
        try:
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else latest
            
            analysis = {
                'supertrend_bullish': latest['supertrend_direction'] == 1,
                'supertrend_changed': False,
                'algo_alpha_bullish': latest['algo_alpha_signal'] == 1,
                'algo_alpha_changed': False,
                'mfi_oversold': latest['mfi'] <= self.mfi_oversold,
                'mfi_overbought': latest['mfi'] >= self.mfi_overbought,
                'mfi_bullish': latest['mfi'] > latest['mfi_sma'],
                'atr_high': False,
                'volatility_level': 'normal',
                'overall_signal': 'neutral',
                'signal_strength': 0,
                'reasons': []
            }
            
            # Detectar mudanças no Supertrend
            if self.last_supertrend_direction is not None:
                if latest['supertrend_direction'] != self.last_supertrend_direction:
                    analysis['supertrend_changed'] = True
            
            # Detectar mudanças no AlgoAlpha
            if self.last_algo_alpha_signal is not None:
                if latest['algo_alpha_signal'] != self.last_algo_alpha_signal:
                    analysis['algo_alpha_changed'] = True
            
            # Analisar volatilidade com ATR
            atr_sma = df['atr'].rolling(window=20, min_periods=1).mean().iloc[-1]
            atr_current = latest['atr']
            if atr_current > atr_sma * 1.5:
                analysis['atr_high'] = True
                analysis['volatility_level'] = 'high'
            elif atr_current < atr_sma * 0.7:
                analysis['volatility_level'] = 'low'
            
            return analysis
            
        except Exception as e:
            logger.error(f"Erro na análise de mercado: {e}")
            return {'overall_signal': 'neutral', 'signal_strength': 0, 'reasons': []}
    
    def generate_trading_signal(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Gera sinal de trading baseado na análise multi-indicador com maior precisão"""
        try:
            analysis = self.analyze_market_conditions(df)
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else latest
            
            signal = {
                'action': 'hold',
                'direction': None,
                'strength': 0,
                'reasons': [],
                'confidence': 0
            }
            
            long_score = 0
            short_score = 0
            reasons = []
            
            # 1. Supertrend (peso muito alto - 50%)
            if analysis['supertrend_bullish']:
                long_score += 5
                reasons.append("Supertrend BULLISH")
            else:
                short_score += 5
                reasons.append("Supertrend BEARISH")
            
            # Bonus substancial para mudança de direção do Supertrend
            if analysis['supertrend_changed']:
                if analysis['supertrend_bullish']:
                    long_score += 4
                    reasons.append("Supertrend VIROU BULL (forte)")
                else:
                    short_score += 4
                    reasons.append("Supertrend VIROU BEAR (forte)")
            
            # 2. AlgoAlpha (peso alto - 30%)
            algo_alpha_strength = abs(latest['algo_alpha'])
            if analysis['algo_alpha_bullish']:
                # Força baseada na intensidade do AlgoAlpha
                if algo_alpha_strength > 0.5:
                    long_score += 4
                    reasons.append("AlgoAlpha BULL forte")
                elif algo_alpha_strength > 0.2:
                    long_score += 3
                    reasons.append("AlgoAlpha BULL médio")
                else:
                    long_score += 2
                    reasons.append("AlgoAlpha BULL fraco")
            else:
                if algo_alpha_strength > 0.5:
                    short_score += 4
                    reasons.append("AlgoAlpha BEAR forte")
                elif algo_alpha_strength > 0.2:
                    short_score += 3
                    reasons.append("AlgoAlpha BEAR médio")
                else:
                    short_score += 2
                    reasons.append("AlgoAlpha BEAR fraco")
            
            # Bonus para mudança do AlgoAlpha
            if analysis['algo_alpha_changed']:
                if analysis['algo_alpha_bullish']:
                    long_score += 2
                    reasons.append("AlgoAlpha virou BULL")
                else:
                    short_score += 2
                    reasons.append("AlgoAlpha virou BEAR")
            
            # 3. MFI com lógica aprimorada (peso médio - 15%)
            mfi_value = latest['mfi']
            mfi_sma_value = latest['mfi_sma']
            
            # Condições mais específicas do MFI
            if mfi_value <= self.mfi_oversold and mfi_value > prev['mfi']:
                long_score += 3
                reasons.append("MFI saindo de oversold")
            elif mfi_value >= self.mfi_overbought and mfi_value < prev['mfi']:
                short_score += 3
                reasons.append("MFI saindo de overbought")
            elif analysis['mfi_bullish']:
                if mfi_value > 60:
                    long_score += 2
                    reasons.append("MFI bullish forte")
                else:
                    long_score += 1
                    reasons.append("MFI bullish")
            else:
                if mfi_value < 40:
                    short_score += 2
                    reasons.append("MFI bearish forte")
                else:
                    short_score += 1
                    reasons.append("MFI bearish")
            
            # 4. ATR/Volatilidade refinado (peso baixo - 5%)
            if analysis['volatility_level'] == 'high':
                # Alta volatilidade - ser mais cauteloso
                long_score = int(long_score * 0.9)
                short_score = int(short_score * 0.9)
                reasons.append("Volatilidade alta - reduzindo confiança")
            elif analysis['volatility_level'] == 'low':
                # Baixa volatilidade - pode indicar breakout iminente
                if long_score > short_score:
                    long_score += 1
                    reasons.append("Volatilidade baixa - possível breakout BULL")
                elif short_score > long_score:
                    short_score += 1
                    reasons.append("Volatilidade baixa - possível breakout BEAR")
            
            # 5. Confluência de sinais (bonus por alinhamento)
            if long_score >= 8 and short_score <= 2:
                long_score += 2
                reasons.append("CONFLUÊNCIA BULLISH forte")
            elif short_score >= 8 and long_score <= 2:
                short_score += 2
                reasons.append("CONFLUÊNCIA BEARISH forte")
            
            # Determinar sinal final com critérios mais rigorosos
            signal['reasons'] = reasons
            total_score = max(long_score, short_score)
            signal['strength'] = total_score
            
            if long_score > short_score and long_score >= self.min_signal_strength:
                signal['action'] = 'buy'
                signal['direction'] = 'long'
                signal['confidence'] = min(100, (long_score / 15) * 100)  # Máximo 15 pontos
            elif short_score > long_score and short_score >= self.min_signal_strength:
                signal['action'] = 'sell'
                signal['direction'] = 'short'
                signal['confidence'] = min(100, (short_score / 15) * 100)  # Máximo 15 pontos
            
            return signal
            
        except Exception as e:
            logger.error(f"Erro crítico ao gerar sinal: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {'action': 'hold', 'direction': None, 'strength': 0, 'reasons': []}
    
    def should_enter_position(self, df: pd.DataFrame) -> Tuple[bool, str, int]:
        """Decide se deve entrar em posição com critérios rigorosos"""
        try:
            # Verificar cooldown rigoroso
            current_time = time.time()
            if self.last_signal_time and (current_time - self.last_signal_time) < self.signal_cooldown:
                time_left = self.signal_cooldown - (current_time - self.last_signal_time)
                logger.debug(f"Cooldown ativo - {time_left:.0f}s restantes")
                return False, None, 0
            
            # Gerar sinal com análise aprimorada
            signal = self.generate_trading_signal(df)
            
            # Critérios muito rigorosos para entrada
            if (signal['action'] in ['buy', 'sell'] and 
                signal['confidence'] >= self.min_confidence and 
                signal['strength'] >= self.min_signal_strength):
                
                logger.info(f"SINAL {signal['direction'].upper()} QUALIFICADO")
                logger.info(f"Força: {signal['strength']} | Confiança: {signal['confidence']:.1f}%")
                logger.info(f"Principais razões: {', '.join(signal['reasons'][:3])}")
                
                self.last_signal_time = current_time
                return True, signal['direction'], signal['strength']
            else:
                # Log detalhado para debug
                if signal['strength'] >= 3:
                    logger.info(f"Sinal detectado mas não qualificado:")
                    logger.info(f"- Força: {signal['strength']} (min: {self.min_signal_strength})")
                    logger.info(f"- Confiança: {signal['confidence']:.1f}% (min: {self.min_confidence}%)")
                    logger.info(f"- Ação: {signal['action']}")
                
                return False, None, signal['strength']
            
        except Exception as e:
            logger.error(f"Erro crítico na análise de entrada: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False, None, 0
    
    def should_close_position(self, df: pd.DataFrame, current_price: float) -> bool:
        """Verifica se deve fechar posição atual"""
        try:
            if not self.current_position or not self.entry_price:
                return False
            
            # Gerar análise atual
            analysis = self.analyze_market_conditions(df)
            
            # 1. Supertrend mudou de direção (principal critério)
            if analysis['supertrend_changed']:
                if self.current_position == 'long' and not analysis['supertrend_bullish']:
                    logger.info("Fechando LONG - Supertrend virou BEARISH")
                    return True
                elif self.current_position == 'short' and analysis['supertrend_bullish']:
                    logger.info("Fechando SHORT - Supertrend virou BULLISH")
                    return True
            
            # 2. AlgoAlpha forte contrário
            signal = self.generate_trading_signal(df)
            if signal['confidence'] >= 80:
                if self.current_position == 'long' and signal['direction'] == 'short':
                    logger.info("Fechando LONG - AlgoAlpha forte BEARISH")
                    return True
                elif self.current_position == 'short' and signal['direction'] == 'long':
                    logger.info("Fechando SHORT - AlgoAlpha forte BULLISH")
                    return True
            
            # 3. Tempo máximo (30 minutos)
            if self.position_start_time:
                position_duration = time.time() - self.position_start_time
                if position_duration > 1800:  # 30 minutos
                    logger.info(f"Fechando por tempo limite: {position_duration/60:.1f} min")
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
                self._reset_position_state()
                return True
            
            side = 'buy' if position_info['side'] == 'short' else 'sell'
            
            order = self.exchange.create_market_order(
                symbol=self.symbol,
                side=side,
                amount=position_info['size'],
                params={'reduceOnly': True}
            )
            
            # Estatísticas
            if position_info['percentage'] > 0:
                self.successful_trades += 1
            
            logger.info(f"POSIÇÃO {self.current_position.upper()} FECHADA")
            logger.info(f"P&L: {position_info['percentage']:.2f}%")
            
            self._reset_position_state()
            return True
            
        except Exception as e:
            logger.error(f"Erro ao fechar posição: {e}")
            return False
    
    def open_position(self, side: str, amount: float) -> bool:
        """Abre uma nova posição com verificações aprimoradas"""
        try:
            if amount <= 0:
                logger.error(f"Quantidade inválida: {amount}")
                return False
            
            logger.info(f"Tentando abrir posição {side.upper()} com {amount} ETH")
            
            # Configurar alavancagem com retry
            leverage_set = False
            for attempt in range(3):
                try:
                    result = self.exchange.set_leverage(self.leverage, self.symbol)
                    logger.info(f"Alavancagem {self.leverage}x configurada: {result}")
                    leverage_set = True
                    break
                except Exception as e:
                    logger.warning(f"Tentativa {attempt + 1} falhou ao configurar alavancagem: {e}")
                    time.sleep(1)
            
            if not leverage_set:
                logger.warning("Não foi possível configurar alavancagem, continuando...")
            
            # Criar ordem de mercado com parâmetros otimizados
            order_params = {
                'type': 'market',
                'timeInForce': 'IOC'  # Immediate or Cancel
            }
            
            logger.info(f"Criando ordem {side} para {amount} ETH...")
            order = self.exchange.create_market_order(
                symbol=self.symbol,
                side=side,
                amount=amount,
                params=order_params
            )
            
            logger.info(f"Ordem criada: {order.get('id', 'N/A')}")
            
            # Aguardar processamento com verificação
            time.sleep(2)
            
            # Verificar status da ordem
            if order.get('id'):
                try:
                    order_status = self.exchange.fetch_order(order['id'], self.symbol)
                    logger.info(f"Status da ordem: {order_status.get('status', 'N/A')}")
                except Exception as e:
                    logger.warning(f"Não foi possível verificar status da ordem: {e}")
            
            # Verificar execução
            filled_amount = float(order.get('filled', 0))
            avg_price = float(order.get('average', 0)) or float(order.get('price', 0))
            
            if (order.get('status') == 'closed' or filled_amount > 0) and avg_price > 0:
                # Atualizar estado
                self.current_position = 'long' if side == 'buy' else 'short'
                self.entry_price = avg_price
                self.position_size = filled_amount
                self.position_start_time = time.time()
                self.total_trades += 1
                
                logger.info(f"POSIÇÃO {self.current_position.upper()} ABERTA COM SUCESSO!")
                logger.info(f"Preço de entrada: ${self.entry_price:.4f}")
                logger.info(f"Quantidade preenchida: {self.position_size} ETH")
                logger.info(f"Valor da posição: ${self.position_size * self.entry_price:.2f}")
                logger.info(f"Trade #{self.total_trades}")
                
                return True
            else:
                logger.error(f"Ordem não executada adequadamente:")
                logger.error(f"- Status: {order.get('status', 'N/A')}")
                logger.error(f"- Preenchido: {filled_amount} ETH")
                logger.error(f"- Preço médio: ${avg_price:.4f}")
                logger.error(f"- Ordem completa: {order}")
                return False
                
        except Exception as e:
            logger.error(f"Erro crítico ao abrir posição {side}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def calculate_position_size(self) -> float:
        """Calcula tamanho da posição com verificação aprimorada"""
        try:
            # Obter saldo com retry
            balance = None
            for attempt in range(3):
                try:
                    balance = self.exchange.fetch_balance()
                    break
                except Exception as e:
                    logger.warning(f"Tentativa {attempt + 1} falhou ao obter saldo: {e}")
                    time.sleep(1)
            
            if not balance:
                logger.error("Não foi possível obter saldo após 3 tentativas")
                return 0
            
            # Verificar diferentes tipos de saldo USDT
            usdt_free = float(balance.get('USDT', {}).get('free', 0))
            usdt_total = float(balance.get('USDT', {}).get('total', 0))
            
            logger.info(f"Saldo USDT - Livre: ${usdt_free:.2f}, Total: ${usdt_total:.2f}")
            
            # Usar o saldo disponível
            available_balance = usdt_free
            
            if available_balance < 1:
                logger.error(f"Saldo muito baixo: ${available_balance:.2f}")
                return 0
            
            # Obter preço atual com retry
            current_price = None
            for attempt in range(3):
                try:
                    ticker = self.exchange.fetch_ticker(self.symbol)
                    current_price = float(ticker['last'])
                    break
                except Exception as e:
                    logger.warning(f"Tentativa {attempt + 1} falhou ao obter preço: {e}")
                    time.sleep(1)
            
            if not current_price or current_price <= 0:
                logger.error("Não foi possível obter preço atual")
                return 0
            
            # Calcular valor da posição com alavancagem
            # Com alavancagem 15x, cada $1 pode controlar $15 em posição
            position_value_usd = available_balance * 0.8 * self.leverage  # 80% do saldo com alavancagem
            
            # Converter para quantidade de ETH
            position_size = position_value_usd / current_price
            
            # Obter limites da exchange
            market = self.exchange.market(self.symbol)
            limits = market.get('limits', {})
            amount_limits = limits.get('amount', {})
            
            min_amount = float(amount_limits.get('min', 0.001))
            max_amount = float(amount_limits.get('max', 100))
            
            # Aplicar limites
            position_size = max(min_amount, min(position_size, max_amount))
            
            # Aplicar precisão
            precision = market.get('precision', {}).get('amount', 4)
            position_size = round(position_size, precision)
            
            logger.info(f"Cálculo da posição:")
            logger.info(f"- Saldo disponível: ${available_balance:.2f}")
            logger.info(f"- Alavancagem: {self.leverage}x")
            logger.info(f"- Valor da posição: ${position_value_usd:.2f}")
            logger.info(f"- Preço ETH: ${current_price:.4f}")
            logger.info(f"- Tamanho calculado: {position_size} ETH")
            logger.info(f"- Limites: min={min_amount}, max={max_amount}")
            
            return position_size
            
        except Exception as e:
            logger.error(f"Erro crítico no cálculo da posição: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return 0
    
    def _reset_position_state(self):
        """Reseta o estado da posição"""
        self.current_position = None
        self.entry_price = None
        self.position_size = None
        self.position_start_time = None
    
    def run_strategy(self):
        """Executa uma iteração da estratégia"""
        try:
            logger.info("=" * 70)
            logger.info("ANÁLISE MULTI-INDICADOR PRECISA")
            
            # Obter dados
            df = self.get_ohlcv_data(limit=100)
            if df is None or len(df) < 50:
                logger.error("Dados insuficientes")
                return
            
            # Calcular todos os indicadores
            df = self.calculate_all_indicators(df)
            
            # Informações atuais
            current_price = df['close'].iloc[-1]
            latest = df.iloc[-1]
            
            logger.info(f"Preço ETH: ${current_price:.4f}")
            logger.info(f"Supertrend: {'BULL' if latest['supertrend_direction'] == 1 else 'BEAR'} (${latest['supertrend']:.2f})")
            logger.info(f"AlgoAlpha: {latest['algo_alpha']:.3f} ({'BULL' if latest['algo_alpha_signal'] == 1 else 'BEAR'})")
            logger.info(f"MFI: {latest['mfi']:.1f} | ATR: {latest['atr']:.4f}")
            
            # 1. Verificar fechamento de posição existente
            if self.current_position and self.should_close_position(df, current_price):
                self.close_position()
                return
            
            # 2. Procurar entrada em nova posição
            if not self.current_position:
                should_enter, direction, strength = self.should_enter_position(df)
                
                if should_enter and direction:
                    logger.info(f"ENTRADA {direction.upper()} DETECTADA - Força: {strength}")
                    
                    position_size = self.calculate_position_size()
                    if position_size > 0:
                        side = 'buy' if direction == 'long' else 'sell'
                        success = self.open_position(side, position_size)
                        
                        if success:
                            logger.info("POSIÇÃO ABERTA COM SUCESSO!")
                        else:
                            logger.error("FALHA AO ABRIR POSIÇÃO")
                    else:
                        logger.error("SALDO INSUFICIENTE")
                else:
                    if strength >= 3:
                        logger.info(f"Sinal detectado (força: {strength}) mas abaixo do threshold")
                    else:
                        logger.info("Aguardando sinais mais fortes")
            
            # 3. Status da posição atual
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
            
            # 4. Atualizar estados anteriores para próxima iteração
            self.last_supertrend_direction = latest['supertrend_direction']
            self.last_algo_alpha_signal = latest['algo_alpha_signal']
            
            # 5. Estatísticas
            if self.total_trades > 0:
                win_rate = (self.successful_trades / self.total_trades) * 100
                logger.info(f"Trades: {self.total_trades} | Win Rate: {win_rate:.1f}%")
            
            logger.info("=" * 70)
                
        except Exception as e:
            logger.error(f"Erro na execução da estratégia: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    def run(self):
        """Loop principal do bot"""
        logger.info("=" * 80)
        logger.info("INICIANDO BOT - ESTRATÉGIA MULTI-INDICADOR PRECISA")
        logger.info("=" * 80)
        logger.info(f"Par: {self.symbol}")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"Alavancagem: {self.leverage}x")
        logger.info("INDICADORES:")
        logger.info(f"- Supertrend: P{self.supertrend_period}, M{self.supertrend_multiplier} (Principal)")
        logger.info(f"- AlgoAlpha: Fast{self.algo_alpha_fast}, Slow{self.algo_alpha_slow} (Complemento)")
        logger.info(f"- ATR: {self.atr_period} períodos (Volatilidade)")
        logger.info(f"- MFI: {self.mfi_period} períodos (Fluxo de dinheiro)")
        logger.info("CONFIGURAÇÕES APRIMORADAS:")
        logger.info(f"- Threshold mínimo: {self.min_signal_strength} pontos")
        logger.info(f"- Confiança mínima: {self.min_confidence}%")
        logger.info(f"- Cooldown: {self.signal_cooldown}s")
        logger.info(f"- Tempo máximo posição: 30 min")
        logger.info(f"- Alavancagem: {self.leverage}x")
        logger.info("=" * 80)
        
        while True:
            try:
                self.run_strategy()
                
                # Aguardar 90 segundos
                logger.info("Próxima análise em 90 segundos...\n")
                time.sleep(90)
                
            except KeyboardInterrupt:
                logger.info("Bot interrompido pelo usuário")
                if self.current_position:
                    logger.warning("ATENÇÃO: Posição ativa! Considere fechar manualmente.")
                break
            except Exception as e:
                logger.error(f"Erro crítico: {e}")
                logger.info("Recuperando em 30 segundos...")
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
