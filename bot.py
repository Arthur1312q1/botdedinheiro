import ccxt
import pandas as pd
import pandas_ta as ta
import numpy as np
import time
import logging
import os
import asyncio
import websocket
import json
import threading
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

class RealTimePriceManager:
    """Gerenciador de preços em tempo real via WebSocket"""
    
    def __init__(self, symbol: str = 'ETHUSDT'):
        self.symbol = symbol
        self.current_price = None
        self.price_history = []
        self.last_update = None
        self.ws = None
        self.ws_thread = None
        self.running = False
        self.price_callbacks = []
        
        # Configurações Bitget WebSocket
        self.ws_url = "wss://ws.bitget.com/spot/v1/stream"
        
    def add_price_callback(self, callback):
        """Adiciona callback para ser chamado quando preço mudar"""
        self.price_callbacks.append(callback)
        
    def on_message(self, ws, message):
        """Processa mensagens do WebSocket"""
        try:
            data = json.loads(message)
            
            if 'data' in data and isinstance(data['data'], list):
                for item in data['data']:
                    if 'c' in item:  # 'c' é o preço atual (close)
                        new_price = float(item['c'])
                        old_price = self.current_price
                        
                        self.current_price = new_price
                        self.last_update = time.time()
                        
                        # Manter histórico dos últimos 100 preços
                        self.price_history.append({
                            'price': new_price,
                            'timestamp': time.time()
                        })
                        if len(self.price_history) > 100:
                            self.price_history.pop(0)
                        
                        # Chamar callbacks apenas se preço mudou
                        if old_price and abs(new_price - old_price) >= 0.01:
                            logger.debug(f"Preço mudou: ${old_price:.4f} -> ${new_price:.4f}")
                            for callback in self.price_callbacks:
                                try:
                                    callback(new_price, old_price)
                                except Exception as e:
                                    logger.error(f"Erro no callback de preço: {e}")
                        
        except Exception as e:
            logger.error(f"Erro ao processar mensagem WebSocket: {e}")
            
    def on_error(self, ws, error):
        """Trata erros do WebSocket"""
        logger.error(f"Erro WebSocket: {error}")
        
    def on_close(self, ws, close_status_code, close_msg):
        """WebSocket fechado"""
        logger.warning("WebSocket fechado, tentando reconectar...")
        if self.running:
            time.sleep(2)
            self.connect()
            
    def on_open(self, ws):
        """WebSocket conectado"""
        logger.info("WebSocket conectado - iniciando subscrição de preços")
        
        # Subscrever ao ticker do ETH/USDT
        subscribe_msg = {
            "op": "subscribe",
            "args": [{
                "channel": "ticker",
                "instId": "ETHUSDT"
            }]
        }
        
        ws.send(json.dumps(subscribe_msg))
        logger.info("Subscrito aos tickers ETHUSDT")
        
    def connect(self):
        """Conecta ao WebSocket"""
        try:
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close,
                on_open=self.on_open
            )
            
            self.running = True
            self.ws.run_forever()
            
        except Exception as e:
            logger.error(f"Erro ao conectar WebSocket: {e}")
            
    def start(self):
        """Inicia o WebSocket em thread separada"""
        if not self.ws_thread or not self.ws_thread.is_alive():
            self.ws_thread = threading.Thread(target=self.connect, daemon=True)
            self.ws_thread.start()
            logger.info("WebSocket de preços iniciado em thread separada")
            
    def stop(self):
        """Para o WebSocket"""
        self.running = False
        if self.ws:
            self.ws.close()
        logger.info("WebSocket de preços parado")
        
    def get_current_price(self) -> Optional[float]:
        """Obtém o preço atual"""
        return self.current_price
        
    def get_price_change_rate(self, seconds: int = 60) -> float:
        """Calcula taxa de mudança de preço por período"""
        if len(self.price_history) < 2:
            return 0.0
            
        now = time.time()
        recent_prices = [p for p in self.price_history if now - p['timestamp'] <= seconds]
        
        if len(recent_prices) < 2:
            return 0.0
            
        oldest_price = recent_prices[0]['price']
        newest_price = recent_prices[-1]['price']
        
        return ((newest_price - oldest_price) / oldest_price) * 100


class TradingBot:
    def __init__(self):
        """Inicializa o bot com estratégia de reversão contínua"""
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
        
        # AlgoAlpha parameters
        self.algo_alpha_fast = 8
        self.algo_alpha_slow = 21
        self.algo_alpha_signal = 5
        
        # Thresholds para MFI
        self.mfi_oversold = 25
        self.mfi_overbought = 75
        self.mfi_neutral = 50
        
        # Controle de trades - estratégia de reversão contínua
        self.total_trades = 0
        self.successful_trades = 0
        self.last_signal_time = None
        self.signal_cooldown = 60  # 1 minuto apenas para evitar trades repetidos
        self.min_confidence = 60  # Confiança moderada
        self.min_signal_strength = 3  # Threshold mais baixo para facilitar trades
        
        # Estado anterior para detectar mudanças
        self.last_supertrend_direction = None
        self.last_algo_alpha_signal = None
        
        # Inicializar gerenciador de preços em tempo real
        self.price_manager = RealTimePriceManager(symbol='ETHUSDT')
        
        logger.info("Bot inicializado - ESTRATÉGIA DE REVERSÃO CONTÍNUA")
        logger.info(f"Indicadores: Supertrend (principal) + AlgoAlpha + ATR + MFI (confirmação)")
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
        """Gera sinal de trading baseado no Supertrend como indicador principal"""
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
            
            # SUPERTREND É O INDICADOR PRINCIPAL - decide a direção
            if analysis['supertrend_bullish']:
                signal['direction'] = 'long'
                signal['strength'] = 5  # Base forte do Supertrend
                signal['reasons'].append("Supertrend BULLISH (principal)")
            else:
                signal['direction'] = 'short'
                signal['strength'] = 5  # Base forte do Supertrend
                signal['reasons'].append("Supertrend BEARISH (principal)")
            
            # INDICADORES SECUNDÁRIOS para confirmação (não para decidir direção)
            confirmation_score = 0
            
            # AlgoAlpha como confirmação
            if signal['direction'] == 'long' and analysis['algo_alpha_bullish']:
                confirmation_score += 2
                signal['reasons'].append("AlgoAlpha confirma BULL")
            elif signal['direction'] == 'short' and not analysis['algo_alpha_bullish']:
                confirmation_score += 2
                signal['reasons'].append("AlgoAlpha confirma BEAR")
            
            # MFI como confirmação
            mfi_value = latest['mfi']
            if signal['direction'] == 'long':
                if mfi_value <= 40:  # Oversold favorece compra
                    confirmation_score += 2
                    signal['reasons'].append("MFI oversold confirma BULL")
                elif mfi_value <= 60:  # Neutro ainda OK
                    confirmation_score += 1
                    signal['reasons'].append("MFI neutro OK para BULL")
            else:  # short
                if mfi_value >= 60:  # Overbought favorece venda
                    confirmation_score += 2
                    signal['reasons'].append("MFI overbought confirma BEAR")
                elif mfi_value >= 40:  # Neutro ainda OK
                    confirmation_score += 1
                    signal['reasons'].append("MFI neutro OK para BEAR")
            
            # ATR para volatilidade (não bloqueia, apenas ajusta confiança)
            if analysis['volatility_level'] == 'high':
                signal['reasons'].append("Alta volatilidade detectada")
            elif analysis['volatility_level'] == 'low':
                confirmation_score += 1
                signal['reasons'].append("Volatilidade adequada")
            
            # Força final = Supertrend + confirmações
            signal['strength'] += confirmation_score
            
            # Calcular confiança baseada na força total
            signal['confidence'] = min(100, (signal['strength'] / 8) * 100)
            
            # SEMPRE GERAR SINAL (Supertrend decide)
            signal['action'] = 'buy' if signal['direction'] == 'long' else 'sell'
            
            return signal
            
        except Exception as e:
            logger.error(f"Erro crítico ao gerar sinal: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {'action': 'hold', 'direction': None, 'strength': 0, 'reasons': []}
    
    def should_enter_position(self, df: pd.DataFrame) -> Tuple[bool, str, int]:
        """Decide se deve mudar de posição baseado no Supertrend + confirmação"""
        try:
            # Verificar cooldown apenas para evitar spam
            current_time = time.time()
            if self.last_signal_time and (current_time - self.last_signal_time) < self.signal_cooldown:
                return False, None, 0
            
            # Gerar sinal baseado no Supertrend
            signal = self.generate_trading_signal(df)
            
            # Se o Supertrend mudou de direção OU temos confirmação suficiente
            supertrend_direction = 'long' if signal['direction'] == 'long' else 'short'
            
            # Verificar se precisa mudar de posição
            needs_change = False
            
            if not self.current_position:
                # Sem posição - entrar na direção do Supertrend
                needs_change = True
                logger.info(f"SEM POSIÇÃO - Seguindo Supertrend para {supertrend_direction.upper()}")
            elif self.current_position != supertrend_direction:
                # Posição contrária ao Supertrend - precisa reverter
                needs_change = True
                logger.info(f"REVERSÃO DETECTADA - {self.current_position.upper()} -> {supertrend_direction.upper()}")
            
            if needs_change and signal['strength'] >= self.min_signal_strength:
                logger.info(f"SINAL DE MUDANÇA CONFIRMADO")
                logger.info(f"Direção: {supertrend_direction.upper()}")
                logger.info(f"Força: {signal['strength']} | Confiança: {signal['confidence']:.1f}%")
                logger.info(f"Razões: {', '.join(signal['reasons'][:3])}")
                
                self.last_signal_time = current_time
                return True, supertrend_direction, signal['strength']
            
            return False, None, signal['strength']
            
        except Exception as e:
            logger.error(f"Erro crítico na análise de entrada: {e}")
            return False, None, 0
    
    def should_close_position(self, df: pd.DataFrame, current_price: float) -> bool:
        """Esta função não é mais necessária - a estratégia sempre reverte posições"""
        # Com a estratégia de reversão contínua, não fechamos posições
        # Apenas revertemos quando o Supertrend mudar
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
        """Fecha a posição atual (usado apenas para fechamento manual via interface)"""
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
            
            logger.info(f"POSIÇÃO {self.current_position.upper()} FECHADA MANUALMENTE")
            logger.info(f"P&L: {position_info['percentage']:.2f}%")
            
            self._reset_position_state()
            return True
            
        except Exception as e:
            logger.error(f"Erro ao fechar posição: {e}")
            return False
    
    def reverse_position(self, new_direction: str, position_size: float) -> bool:
        """Reverte a posição atual para a nova direção"""
        try:
            logger.info(f"INICIANDO REVERSÃO: {self.current_position.upper()} -> {new_direction.upper()}")
            
            # 1. Fechar posição atual
            if self.current_position:
                position_info = self.get_position_info()
                if position_info:
                    close_side = 'buy' if position_info['side'] == 'short' else 'sell'
                    
                    # Usar ordem limit para fechar
                    ticker = self.exchange.fetch_ticker(self.symbol)
                    current_price = float(ticker['last'])
                    
                    if close_side == 'buy':
                        close_price = current_price * 1.001  # 0.1% acima
                    else:
                        close_price = current_price * 0.999  # 0.1% abaixo
                    
                    close_order = self.exchange.create_order(
                        symbol=self.symbol,
                        type='limit',
                        side=close_side,
                        amount=position_info['size'],
                        price=close_price,
                        params={'reduceOnly': True, 'timeInForce': 'IOC'}
                    )
                    
                    # Aguardar fechamento
                    time.sleep(2)
                    
                    # Verificar se fechou
                    try:
                        close_status = self.exchange.fetch_order(close_order['id'], self.symbol)
                        if close_status.get('status') == 'closed':
                            # Calcular resultado do trade
                            if position_info['percentage'] > 0:
                                self.successful_trades += 1
                                logger.info(f"TRADE LUCRO: +{position_info['percentage']:.2f}%")
                            else:
                                logger.info(f"TRADE PREJUÍZO: {position_info['percentage']:.2f}%")
                            
                            logger.info(f"Posição {self.current_position.upper()} fechada")
                        else:
                            logger.warning("Posição pode não ter fechado completamente")
                    except Exception as e:
                        logger.warning(f"Erro ao verificar fechamento: {e}")
                    
                    time.sleep(1)  # Aguardar processamento
            
            # 2. Abrir nova posição na direção oposta
            new_side = 'buy' if new_direction == 'long' else 'sell'
            
            # Usar mesma lógica do open_position
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = float(ticker['last'])
            
            if new_side == 'buy':
                limit_price = current_price * 1.001
            else:
                limit_price = current_price * 0.999
            
            open_order = self.exchange.create_order(
                symbol=self.symbol,
                type='limit',
                side=new_side,
                amount=position_size,
                price=limit_price,
                params={'timeInForce': 'IOC'}
            )
            
            # Aguardar execução
            time.sleep(3)
            
            # Verificar execução
            try:
                open_status = self.exchange.fetch_order(open_order['id'], self.symbol)
                filled_amount = float(open_status.get('filled', 0))
                avg_price = float(open_status.get('average', 0))
                
                if open_status.get('status') == 'closed' and filled_amount > 0 and avg_price > 0:
                    # Atualizar estado
                    self.current_position = new_direction
                    self.entry_price = avg_price
                    self.position_size = filled_amount
                    self.position_start_time = time.time()
                    self.total_trades += 1
                    
                    logger.info(f"REVERSÃO COMPLETA!")
                    logger.info(f"Nova posição {new_direction.upper()}: {filled_amount:.6f} ETH @ ${avg_price:.4f}")
                    logger.info(f"Trade #{self.total_trades}")
                    
                    return True
                else:
                    logger.error("Falha na abertura da nova posição")
                    # Tentar fallback
                    return self._try_market_order_fallback(new_side, position_size)
                    
            except Exception as e:
                logger.error(f"Erro ao verificar abertura: {e}")
                return self._try_market_order_fallback(new_side, position_size)
                
        except Exception as e:
            logger.error(f"Erro crítico na reversão: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def open_position(self, side: str, amount: float) -> bool:
        """Abre uma nova posição usando ordens limit"""
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
                    logger.info(f"Alavancagem {self.leverage}x configurada")
                    leverage_set = True
                    break
                except Exception as e:
                    logger.warning(f"Tentativa {attempt + 1} falhou ao configurar alavancagem: {e}")
                    time.sleep(1)
            
            if not leverage_set:
                logger.warning("Não foi possível configurar alavancagem, continuando...")
            
            # Obter preço atual para ordem limit
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = float(ticker['last'])
            
            # Ajustar preço para ordem limit (pequeno spread para execução rápida)
            if side == 'buy':
                limit_price = current_price * 1.001  # 0.1% acima do mercado
            else:  # sell
                limit_price = current_price * 0.999  # 0.1% abaixo do mercado
            
            logger.info(f"Preço limite: ${limit_price:.4f} (mercado: ${current_price:.4f})")
            
            # Criar ordem limit
            order = self.exchange.create_order(
                symbol=self.symbol,
                type='limit',
                side=side,
                amount=amount,
                price=limit_price,
                params={
                    'timeInForce': 'IOC'  # Immediate or Cancel
                }
            )
            
            logger.info(f"Ordem limit criada: {order.get('id', 'N/A')}")
            
            # Aguardar execução
            time.sleep(3)
            
            # Verificar se foi executada
            if order.get('id'):
                try:
                    order_status = self.exchange.fetch_order(order['id'], self.symbol)
                    filled_amount = float(order_status.get('filled', 0))
                    avg_price = float(order_status.get('average', 0))
                    
                    if order_status.get('status') == 'closed' and filled_amount > 0 and avg_price > 0:
                        # Ordem executada com sucesso
                        self.current_position = 'long' if side == 'buy' else 'short'
                        self.entry_price = avg_price
                        self.position_size = filled_amount
                        self.position_start_time = time.time()
                        self.total_trades += 1
                        
                        logger.info(f"POSIÇÃO {self.current_position.upper()} ABERTA COM SUCESSO!")
                        logger.info(f"Preço de entrada: ${self.entry_price:.4f}")
                        logger.info(f"Quantidade: {self.position_size:.6f} ETH")
                        logger.info(f"Trade #{self.total_trades}")
                        
                        return True
                    else:
                        # Ordem não executada - tentar ordem market como fallback
                        logger.warning("Ordem limit não executada, tentando market...")
                        try:
                            # Cancelar ordem limit pendente
                            self.exchange.cancel_order(order['id'], self.symbol)
                        except:
                            pass
                        
                        # Tentar ordem market via API direta se disponível
                        return self._try_market_order_fallback(side, amount)
                        
                except Exception as e:
                    logger.error(f"Erro ao verificar status da ordem: {e}")
                    return False
            
            return False
                
        except Exception as e:
            logger.error(f"Erro crítico ao abrir posição {side}: {e}")
            # Tentar fallback para market order
            return self._try_market_order_fallback(side, amount)
    
    def _try_market_order_fallback(self, side: str, amount: float) -> bool:
        """Tenta executar ordem market como fallback"""
        try:
            logger.info("Tentando fallback com ordem market...")
            
            # Obter preço atual
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = float(ticker['last'])
            
            # Calcular valor aproximado
            notional_value = amount * current_price
            
            # Tentar diferentes variações de parâmetros
            market_params_variants = [
                {'type': 'market'},
                {'orderType': 'market'},
                {'force': True},
                {'reduceOnly': False},
                {}  # Sem parâmetros extras
            ]
            
            for params in market_params_variants:
                try:
                    order = self.exchange.create_order(
                        symbol=self.symbol,
                        type='market',
                        side=side,
                        amount=amount,
                        price=None,
                        params=params
                    )
                    
                    if order and order.get('id'):
                        time.sleep(2)
                        order_status = self.exchange.fetch_order(order['id'], self.symbol)
                        
                        filled_amount = float(order_status.get('filled', 0))
                        avg_price = float(order_status.get('average', 0))
                        
                        if filled_amount > 0 and avg_price > 0:
                            self.current_position = 'long' if side == 'buy' else 'short'
                            self.entry_price = avg_price
                            self.position_size = filled_amount
                            self.position_start_time = time.time()
                            self.total_trades += 1
                            
                            logger.info(f"POSIÇÃO {self.current_position.upper()} ABERTA (fallback)!")
                            logger.info(f"Preço: ${avg_price:.4f} | Quantidade: {filled_amount:.6f} ETH")
                            
                            return True
                    
                except Exception as e:
                    logger.debug(f"Fallback tentativa falhou: {e}")
                    continue
            
            logger.error("Todas as tentativas de fallback falharam")
            return False
            
        except Exception as e:
            logger.error(f"Erro no fallback market order: {e}")
            return False
    
    def calculate_position_size(self) -> float:
        """Calcula tamanho da posição usando alavancagem corretamente"""
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
            
            # Obter saldo USDT disponível
            usdt_free = float(balance.get('USDT', {}).get('free', 0))
            
            logger.info(f"Saldo USDT disponível: ${usdt_free:.2f}")
            
            # Verificar saldo mínimo
            if usdt_free < 1:
                logger.error(f"Saldo insuficiente: ${usdt_free:.2f} (mínimo: $1.00)")
                return 0
            
            # Obter preço atual do ETH
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
                logger.error("Não foi possível obter preço atual do ETH")
                return 0
            
            # CÁLCULO CORRETO COM ALAVANCAGEM:
            # Com alavancagem 15x: cada $1 permite controlar $15 em posição
            # Position Size ETH = (Saldo USDT * Alavancagem) / Preço ETH
            
            # Usar 95% do saldo para deixar margem para taxas
            usable_balance = usdt_free * 0.95
            
            # Calcular tamanho da posição em ETH
            position_size_eth = (usable_balance * self.leverage) / current_price
            
            logger.info(f"Cálculo da posição:")
            logger.info(f"- Saldo utilizável: ${usable_balance:.2f}")
            logger.info(f"- Alavancagem: {self.leverage}x")
            logger.info(f"- Preço ETH: ${current_price:.4f}")
            logger.info(f"- Valor total controlado: ${usable_balance * self.leverage:.2f}")
            logger.info(f"- Tamanho calculado: {position_size_eth:.6f} ETH")
            
            # Obter limites da exchange
            try:
                market = self.exchange.market(self.symbol)
                limits = market.get('limits', {})
                amount_limits = limits.get('amount', {})
                
                # Tratamento seguro dos limites - valores padrão se None
                min_amount_raw = amount_limits.get('min')
                max_amount_raw = amount_limits.get('max')
                
                # Usar valores padrão seguros se não conseguir obter da exchange
                min_amount = 0.001 if min_amount_raw is None else float(min_amount_raw)
                max_amount = 100.0 if max_amount_raw is None else float(max_amount_raw)
                
                logger.info(f"Limites da exchange - Min: {min_amount} ETH, Max: {max_amount} ETH")
                
            except Exception as e:
                logger.warning(f"Erro ao obter limites: {e}")
                min_amount = 0.001  # Valor padrão seguro
                max_amount = 100.0
                logger.info(f"Usando limites padrão - Min: {min_amount} ETH, Max: {max_amount} ETH")
            
            # Aplicar limites
            if position_size_eth < min_amount:
                logger.error(f"Posição calculada {position_size_eth:.6f} ETH menor que mínimo {min_amount} ETH")
                logger.error(f"Necessário pelo menos ${min_amount * current_price / self.leverage:.2f} de saldo")
                return 0
            
            # Limitar ao máximo permitido
            position_size_eth = min(position_size_eth, max_amount)
            
            # Aplicar precisão (usar método mais simples e seguro)
            try:
                # Tentar obter precisão da exchange
                precision_info = market.get('precision', {})
                amount_precision = precision_info.get('amount')
                
                if amount_precision is not None and isinstance(amount_precision, (int, float)):
                    # Arredondar para baixo com a precisão especificada
                    precision = int(amount_precision)
                    multiplier = 10 ** precision
                    position_size_eth = int(position_size_eth * multiplier) / multiplier
                else:
                    # Fallback para 4 casas decimais
                    position_size_eth = int(position_size_eth * 10000) / 10000
                    
            except Exception as e:
                logger.warning(f"Erro ao aplicar precisão: {e}")
                # Fallback simples - 4 casas decimais
                position_size_eth = int(position_size_eth * 10000) / 10000
            
            # Verificação final
            position_value_usd = position_size_eth * current_price
            logger.info(f"POSIÇÃO FINAL:")
            logger.info(f"- Tamanho: {position_size_eth:.6f} ETH")
            logger.info(f"- Valor da posição: ${position_value_usd:.2f}")
            logger.info(f"- Margem necessária: ${position_value_usd / self.leverage:.2f}")
            
            if position_size_eth >= min_amount:
                logger.info("✅ Posição válida calculada!")
                return position_size_eth
            else:
                logger.error("❌ Posição inválida após aplicar limites")
                return 0
                
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
        """Executa estratégia de reversão contínua baseada no Supertrend"""
        try:
            logger.info("=" * 70)
            logger.info("ESTRATÉGIA DE REVERSÃO CONTÍNUA")
            
            # Obter dados históricos
            df = self.get_ohlcv_data(limit=100)
            if df is None or len(df) < 50:
                logger.error("Dados insuficientes")
                return
            
            # Calcular todos os indicadores
            df = self.calculate_all_indicators(df)
            
            # Usar preço em tempo real se disponível
            realtime_price = self.price_manager.get_current_price()
            if realtime_price:
                current_price = realtime_price
                logger.info(f"Preço TEMPO REAL: ${current_price:.4f}")
            else:
                current_price = df['close'].iloc[-1]
                logger.info(f"Preço histórico: ${current_price:.4f}")
                
            latest = df.iloc[-1]
            
            # Status dos indicadores
            supertrend_direction = 'BULL' if latest['supertrend_direction'] == 1 else 'BEAR'
            algo_alpha_direction = 'BULL' if latest['algo_alpha_signal'] == 1 else 'BEAR'
            
            logger.info(f"Supertrend: {supertrend_direction} (${latest['supertrend']:.2f})")
            logger.info(f"AlgoAlpha: {algo_alpha_direction} ({latest['algo_alpha']:.3f})")
            logger.info(f"MFI: {latest['mfi']:.1f} | ATR: {latest['atr']:.4f}")
            
            # Status da posição atual
            if self.current_position:
                pnl_pct = 0
                if self.entry_price:
                    pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100
                    if self.current_position == 'short':
                        pnl_pct *= -1
                
                position_time = 0
                if self.position_start_time:
                    position_time = (time.time() - self.position_start_time) / 60
                
                logger.info(f"POSIÇÃO ATUAL: {self.current_position.upper()}")
                logger.info(f"P&L: {pnl_pct:+.2f}% | Tempo: {position_time:.1f} min")
            else:
                logger.info("SEM POSIÇÃO ATIVA")
            
            # Verificar se precisa mudar/iniciar posição
            should_change, target_direction, strength = self.should_enter_position(df)
            
            if should_change and target_direction:
                position_size = self.calculate_position_size()
                
                if position_size > 0:
                    if self.current_position and self.current_position != target_direction:
                        # Reversão de posição
                        success = self.reverse_position(target_direction, position_size)
                        if success:
                            logger.info("REVERSÃO EXECUTADA COM SUCESSO!")
                    elif not self.current_position:
                        # Primeira posição
                        side = 'buy' if target_direction == 'long' else 'sell'
                        success = self.open_position(side, position_size)
                        if success:
                            logger.info("PRIMEIRA POSIÇÃO ABERTA!")
                else:
                    logger.error("SALDO INSUFICIENTE PARA OPERAR")
            else:
                # Log do status
                supertrend_dir = 'LONG' if latest['supertrend_direction'] == 1 else 'SHORT'
                if self.current_position:
                    if self.current_position.upper() == supertrend_dir:
                        logger.info(f"Posição {self.current_position.upper()} alinhada com Supertrend - mantendo")
                    else:
                        logger.info(f"Aguardando confirmação para reverter {self.current_position.upper()} -> {supertrend_dir}")
                        logger.info(f"Força atual: {strength} (mín: {self.min_signal_strength})")
                else:
                    logger.info(f"Aguardando confirmação para entrar em {supertrend_dir}")
                    logger.info(f"Força atual: {strength} (mín: {self.min_signal_strength})")
            
            # Estatísticas
            if self.total_trades > 0:
                win_rate = (self.successful_trades / self.total_trades) * 100
                logger.info(f"TRADES: {self.total_trades} | SUCESSOS: {self.successful_trades} | WIN RATE: {win_rate:.1f}%")
            
            # Atualizar estados anteriores
            self.last_supertrend_direction = latest['supertrend_direction']
            self.last_algo_alpha_signal = latest['algo_alpha_signal']
            
            logger.info("=" * 70)
                
        except Exception as e:
            logger.error(f"Erro na execução da estratégia: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    def run(self):
        """Loop principal do bot com estratégia de reversão contínua"""
        logger.info("=" * 80)
        logger.info("INICIANDO BOT - ESTRATÉGIA DE REVERSÃO CONTÍNUA")
        logger.info("=" * 80)
        logger.info(f"Par: {self.symbol}")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"Alavancagem: {self.leverage}x")
        logger.info("ESTRATÉGIA:")
        logger.info("- Supertrend como indicador PRINCIPAL")
        logger.info("- AlgoAlpha, MFI, ATR como CONFIRMAÇÃO")
        logger.info("- SEM stop loss ou take profit")
        logger.info("- Reversão automática quando Supertrend mudar")
        logger.info("- SEMPRE em posição (long ou short)")
        logger.info("INDICADORES:")
        logger.info(f"- Supertrend: P{self.supertrend_period}, M{self.supertrend_multiplier} (DECISOR)")
        logger.info(f"- AlgoAlpha: Fast{self.algo_alpha_fast}, Slow{self.algo_alpha_slow} (Confirmação)")
        logger.info(f"- ATR: {self.atr_period} períodos (Volatilidade)")
        logger.info(f"- MFI: {self.mfi_period} períodos (Fluxo de dinheiro)")
        logger.info("CONFIGURAÇÕES:")
        logger.info(f"- Threshold mínimo: {self.min_signal_strength} pontos")
        logger.info(f"- Confiança mínima: {self.min_confidence}%")
        logger.info(f"- Cooldown: {self.signal_cooldown}s")
        logger.info("=" * 80)
        
        # Iniciar WebSocket de preços
        logger.info("Iniciando WebSocket para preços em tempo real...")
        self.price_manager.start()
        
        # Aguardar conexão inicial
        time.sleep(5)
        
        # Verificar se WebSocket conectou
        if self.price_manager.get_current_price():
            logger.info(f"WebSocket conectado! Preço inicial: ${self.price_manager.get_current_price():.4f}")
        else:
            logger.warning("WebSocket não conectou, usando preços da API REST")
        
        try:
            while True:
                try:
                    self.run_strategy()
                    
                    # Aguardar 90 segundos para próxima análise
                    logger.info("Próxima análise em 90 segundos...\n")
                    time.sleep(90)
                    
                except KeyboardInterrupt:
                    logger.info("Bot interrompido pelo usuário")
                    break
                except Exception as e:
                    logger.error(f"Erro crítico: {e}")
                    logger.info("Recuperando em 30 segundos...")
                    time.sleep(30)
                    
        finally:
            # Parar WebSocket ao finalizar
            logger.info("Parando WebSocket...")
            self.price_manager.stop()
            
            if self.current_position:
                logger.warning("ATENÇÃO: Posição ativa! Considere fechar manualmente.")


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
