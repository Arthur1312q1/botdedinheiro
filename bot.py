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
        self.symbol = 'ETHUSDT'
        self.timeframe = '15m'
        self.leverage = 10
        self.stop_loss_percentage = 0.01  # 1%
        
        # Estado da posição
        self.current_position = None  # 'long', 'short', None
        self.entry_price = None
        self.position_size = None
        
        # Parâmetros dos indicadores
        self.supertrend_period = 10
        self.supertrend_multiplier = 3.0
        self.breakout_normalization_length = 100
        self.breakout_detection_length = 14
        
        # Histórico de canais ativos
        self.active_channels = []
        
        logger.info("Bot de trading inicializado com sucesso")
    
    def _setup_exchange(self) -> ccxt.bitget:
        """Configura a conexão com a Bitget"""
        api_key = os.getenv('BITGET_API_KEY')
        secret_key = os.getenv('BITGET_SECRET_KEY')
        password = os.getenv('BITGET_PASSWORD')
        
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
            # Usando pandas_ta para calcular Supertrend
            supertrend = ta.supertrend(
                high=df['high'],
                low=df['low'],
                close=df['close'],
                length=self.supertrend_period,
                multiplier=self.supertrend_multiplier
            )
            
            df['supertrend'] = supertrend[f'SUPERT_{self.supertrend_period}_{self.supertrend_multiplier}']
            df['supertrend_direction'] = supertrend[f'SUPERTd_{self.supertrend_period}_{self.supertrend_multiplier}']
            
            return df
        except Exception as e:
            logger.error(f"Erro ao calcular Supertrend: {e}")
            raise
    
    def calculate_smart_money_breakout(self, df: pd.DataFrame) -> Tuple[bool, bool]:
        """
        Implementa a lógica do Smart Money Breakout Channels corrigida
        Retorna (bullish_breakout, bearish_breakout)
        """
        try:
            if len(df) < self.breakout_normalization_length:
                return False, False
            
            # Normalização do preço
            lowest_low = df['low'].rolling(window=self.breakout_normalization_length, min_periods=1).min()
            highest_high = df['high'].rolling(window=self.breakout_normalization_length, min_periods=1).max()
            
            # Evitar divisão por zero
            price_range = highest_high - lowest_low
            price_range = price_range.replace(0, np.nan)
            normalized_price = (df['close'] - lowest_low) / price_range
            normalized_price = normalized_price.fillna(0.5)  # Valor padrão se divisão por zero
            
            # Volatilidade
            vol = normalized_price.rolling(window=14, min_periods=1).std()
            vol = vol.fillna(vol.mean())  # Preencher NaN com média
            
            # Método simplificado para detecção de breakout
            # Usando períodos de alta e baixa volatilidade
            vol_ma = vol.rolling(window=self.breakout_detection_length, min_periods=1).mean()
            vol_std = vol.rolling(window=self.breakout_detection_length, min_periods=1).std()
            
            # Detectar formação de canais baseado em baixa volatilidade
            low_vol_threshold = vol_ma - vol_std * 0.5
            high_vol_threshold = vol_ma + vol_std * 0.5
            
            # Verificar se estamos em um período de baixa volatilidade (formação de canal)
            is_low_vol = vol.iloc[-1] < low_vol_threshold.iloc[-1]
            was_low_vol = vol.iloc[-2] < low_vol_threshold.iloc[-2] if len(vol) > 1 else False
            
            # Breakout ocorre quando saímos de baixa volatilidade para alta
            vol_breakout = (was_low_vol and vol.iloc[-1] > high_vol_threshold.iloc[-1])
            
            if not vol_breakout:
                return False, False
            
            # Determinar direção do breakout baseado no preço
            lookback_period = min(20, len(df))  # Últimos 20 candles para contexto
            recent_data = df.iloc[-lookback_period:]
            
            support_level = recent_data['low'].min()
            resistance_level = recent_data['high'].max()
            current_price = df['close'].iloc[-1]
            previous_price = df['close'].iloc[-2] if len(df) > 1 else current_price
            
            # Detectar breakout baseado no movimento do preço
            price_change_pct = (current_price - previous_price) / previous_price if previous_price > 0 else 0
            
            bullish_breakout = False
            bearish_breakout = False
            
            # Critérios para breakout bullish
            if (current_price > resistance_level * 1.001 and  # 0.1% acima da resistência
                price_change_pct > 0.002):  # Movimento positivo de pelo menos 0.2%
                bullish_breakout = True
                logger.info(f"Breakout de alta detectado! Preço: {current_price:.4f}, Resistência: {resistance_level:.4f}")
            
            # Critérios para breakout bearish
            elif (current_price < support_level * 0.999 and  # 0.1% abaixo do suporte
                  price_change_pct < -0.002):  # Movimento negativo de pelo menos 0.2%
                bearish_breakout = True
                logger.info(f"Breakout de baixa detectado! Preço: {current_price:.4f}, Suporte: {support_level:.4f}")
            
            return bullish_breakout, bearish_breakout
            
        except Exception as e:
            logger.error(f"Erro ao calcular Smart Money Breakout: {e}")
            return False, False
    
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
        """Executa uma iteração da estratégia"""
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
            
            logger.info(f"Preço atual: {current_price}")
            logger.info(f"Supertrend: {supertrend_signal}")
            logger.info(f"Breakout Alta: {bullish_breakout}, Breakout Baixa: {bearish_breakout}")
            
            # Verificar stop loss primeiro
            if self.check_stop_loss(current_price):
                self.close_position()
                return
            
            # Lógica de sinais combinados
            should_go_long = (supertrend_trend == 1 and bullish_breakout)
            should_go_short = (supertrend_trend == -1 and bearish_breakout)
            
            # Executar ordens apenas se houver sinal claro
            if should_go_long and self.current_position != 'long':
                logger.info("🟢 SINAL DE COMPRA DETECTADO!")
                
                # Fechar posição short se existir
                if self.current_position == 'short':
                    if not self.close_position():
                        logger.error("Falha ao fechar posição short")
                        return
                
                # Aguardar um momento após fechar posição
                time.sleep(3)
                
                # Abrir posição long
                position_size = self.calculate_position_size()
                if position_size > 0 and self.open_position('buy', position_size):
                    logger.info("✅ Posição LONG aberta com sucesso")
                else:
                    logger.error("❌ Falha ao abrir posição LONG")
                
            elif should_go_short and self.current_position != 'short':
                logger.info("🔴 SINAL DE VENDA DETECTADO!")
                
                # Fechar posição long se existir
                if self.current_position == 'long':
                    if not self.close_position():
                        logger.error("Falha ao fechar posição long")
                        return
                
                # Aguardar um momento após fechar posição
                time.sleep(3)
                
                # Abrir posição short
                position_size = self.calculate_position_size()
                if position_size > 0 and self.open_position('sell', position_size):
                    logger.info("✅ Posição SHORT aberta com sucesso")
                else:
                    logger.error("❌ Falha ao abrir posição SHORT")
            
            # Status da posição atual
            if self.current_position:
                pnl_percentage = ((current_price - self.entry_price) / self.entry_price) * 100
                if self.current_position == 'short':
                    pnl_percentage *= -1
                
                logger.info(f"📊 Posição atual: {self.current_position.upper()}")
                logger.info(f"💰 P&L: {pnl_percentage:.2f}%")
            else:
                logger.info("📊 Sem posição ativa")
                
        except Exception as e:
            logger.error(f"Erro na execução da estratégia: {e}")
    
    def run(self):
        """Loop principal do bot"""
        logger.info("🚀 Iniciando bot de trading...")
        logger.info(f"📈 Par: {self.symbol}")
        logger.info(f"⏰ Timeframe: {self.timeframe}")
        logger.info(f"🎯 Alavancagem: {self.leverage}x")
        logger.info(f"🛡️ Stop Loss: {self.stop_loss_percentage*100}%")
        
        while True:
            try:
                self.run_strategy()
                
                # Aguardar 5 minutos antes da próxima verificação
                logger.info("⏳ Aguardando 5 minutos para próxima verificação...")
                time.sleep(300)  # 5 minutos
                
            except KeyboardInterrupt:
                logger.info("❌ Bot interrompido pelo usuário")
                break
            except Exception as e:
                logger.error(f"❌ Erro no loop principal: {e}")
                logger.info("⏳ Aguardando 30 segundos antes de tentar novamente...")
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
