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
        self.leverage = 10
        
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
        
        # Thresholds para precisão
        self.mfi_oversold = 20
        self.mfi_overbought = 80
        self.mfi_neutral = 50
        
        # Controle de trades
        self.total_trades = 0
        self.successful_trades = 0
        self.last_signal_time = None
        self.signal_cooldown = 120  # 2 minutos para precisão
        
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
        """Gera sinal de trading baseado na análise multi-indicador"""
        try:
            analysis = self.analyze_market_conditions(df)
            latest = df.iloc[-1]
            
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
            
            # 1. Supertrend (peso alto - 40%)
            if analysis['supertrend_bullish']:
                long_score += 4
                reasons.append("Supertrend BULLISH")
            else:
                short_score += 4
                reasons.append("Supertrend BEARISH")
            
            # Bonus para mudança de direção do Supertrend
            if analysis['supertrend_changed']:
                if analysis['supertrend_bullish']:
                    long_score += 3
                    reasons.append("Supertrend virou BULL")
                else:
                    short_score += 3
                    reasons.append("Supertrend virou BEAR")
            
            # 2. AlgoAlpha (peso médio-alto - 30%)
            if analysis['algo_alpha_bullish']:
                long_score += 3
                reasons.append("AlgoAlpha BULLISH")
            else:
                short_score += 3
                reasons.append("AlgoAlpha BEARISH")
            
            # Bonus para mudança do AlgoAlpha
            if analysis['algo_alpha_changed']:
                if analysis['algo_alpha_bullish']:
                    long_score += 2
                    reasons.append("AlgoAlpha virou BULL")
                else:
                    short_score += 2
                    reasons.append("AlgoAlpha virou BEAR")
            
            # 3. MFI (peso médio - 20%)
            if analysis['mfi_oversold'] and analysis['mfi_bullish']:
                long_score += 2
                reasons.append("MFI saindo de oversold")
            elif analysis['mfi_overbought'] and not analysis['mfi_bullish']:
                short_score += 2
                reasons.append("MFI saindo de overbought")
            elif analysis['mfi_bullish']:
                long_score += 1
                reasons.append("MFI bullish")
            else:
                short_score += 1
                reasons.append("MFI bearish")
            
            # 4. ATR/Volatilidade (peso baixo - 10%)
            if analysis['volatility_level'] == 'high':
                # Alta volatilidade - reduzir confiança
                long_score = max(0, long_score - 1)
                short_score = max(0, short_score - 1)
                reasons.append("Volatilidade alta - cautela")
            elif analysis['volatility_level'] == 'low':
                # Baixa volatilidade - pode ser breakout
                if long_score > short_score:
                    long_score += 1
                else:
                    short_score += 1
                reasons.append("Volatilidade baixa - possível breakout")
            
            # Determinar sinal final
            signal['reasons'] = reasons
            total_score = max(long_score, short_score)
            signal['strength'] = total_score
            
            if long_score > short_score and long_score >= 5:  # Threshold para LONG
                signal['action'] = 'buy'
                signal['direction'] = 'long'
                signal['confidence'] = min(100, (long_score / 10) * 100)
            elif short_score > long_score and short_score >= 5:  # Threshold para SHORT
                signal['action'] = 'sell'
                signal['direction'] = 'short'
                signal['confidence'] = min(100, (short_score / 10) * 100)
            
            return signal
            
        except Exception as e:
            logger.error(f"Erro ao gerar sinal: {e}")
            return {'action': 'hold', 'direction': None, 'strength': 0, 'reasons': []}
    
    def should_enter_position(self, df: pd.DataFrame) -> Tuple[bool, str, int]:
        """Decide se deve entrar em posição"""
        try:
            # Verificar cooldown
            current_time = time.time()
            if self.last_signal_time and (current_time - self.last_signal_time) < self.signal_cooldown:
                return False, None, 0
            
            # Gerar sinal
            signal = self.generate_trading_signal(df)
            
            if signal['action'] in ['buy', 'sell'] and signal['confidence'] >= 60:
                logger.info(f"SINAL {signal['direction'].upper()} - Força: {signal['strength']}")
                logger.info(f"Confiança: {signal['confidence']:.1f}%")
                logger.info(f"Razões: {', '.join(signal['reasons'][:5])}")
                
                self.last_signal_time = current_time
                return True, signal['direction'], signal['strength']
            
            return False, None, signal['strength']
            
        except Exception as e:
            logger.error(f"Erro na análise de entrada: {e}")
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
        """Abre uma nova posição"""
        try:
            if amount <= 0:
                logger.error("Quantidade inválida")
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
            time.sleep(3)
            
            # Verificar execução
            if order.get('status') == 'closed' or order.get('filled', 0) > 0:
                # Atualizar estado
                self.current_position = 'long' if side == 'buy' else 'short'
                self.entry_price = float(order.get('price') or order.get('average') or 0)
                self.position_size = float(order.get('filled', amount))
                self.position_start_time = time.time()
                self.total_trades += 1
                
                logger.info(f"POSIÇÃO {self.current_position.upper()} ABERTA")
                logger.info(f"Preço entrada: ${self.entry_price:.4f}")
                logger.info(f"Tamanho: {self.position_size} ETH")
                
                return True
            else:
                logger.error(f"Ordem não executada: {order}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao abrir posição {side}: {e}")
            return False
    
    def calculate_position_size(self) -> float:
        """Calcula tamanho da posição"""
        try:
            balance = self.exchange.fetch_balance()
            usdt_balance = float(balance.get('USDT', {}).get('free', 0))
            
            if usdt_balance <= 10:
                logger.error(f"Saldo insuficiente: ${usdt_balance:.2f}")
                return 0
            
            # Usar 65% do saldo para trades precisos
            position_value = usdt_balance * 0.65
            
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
            
            logger.info(f"Saldo: ${usdt_balance:.2f} | Posição: ${position_value:.2f}")
            logger.info(f"Preço ETH: ${current_price:.4f} | Tamanho: {position_size} ETH")
            
            return position_size
            
        except Exception as e:
            logger.error(f"Erro ao calcular posição: {e}")
            return 0.001
    
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
        logger.info("CONFIGURAÇÕES:")
        logger.info(f"- Threshold mínimo: 5 pontos")
        logger.info(f"- Confiança mínima: 60%")
        logger.info(f"- Cooldown: {self.signal_cooldown}s")
        logger.info(f"- Tempo máximo posição: 30 min")
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
