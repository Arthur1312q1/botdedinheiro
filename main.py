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
        self.ema_period = 10  # Mudança para EMA de 10 períodos
        
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
        
        # Calcular bandas superior e inferior (corrigindo a lógica)
        df['basic_upper'] = df['hl2'] + (self.atr_multiplier * df['atr'])
        df['basic_lower'] = df['hl2'] - (self.atr_multiplier * df['atr'])
        
        # Inicializar colunas
        df['final_upper'] = df['basic_upper'].copy()
        df['final_lower'] = df['basic_lower'].copy()
        df['supertrend'] = 0.0
        df['trend'] = 1
        
        # Calcular Supertrend com lógica corrigida
        for i in range(1, len(df)):
            # Final Upper Band
            if pd.isna(df['basic_upper'].iloc[i]) or pd.isna(df['final_upper'].iloc[i-1]):
                df.loc[df.index[i], 'final_upper'] = df['basic_upper'].iloc[i]
            elif df['basic_upper'].iloc[i] < df['final_upper'].iloc[i-1] or df['close'].iloc[i-1] > df['final_upper'].iloc[i-1]:
                df.loc[df.index[i], 'final_upper'] = df['basic_upper'].iloc[i]
            else:
                df.loc[df.index[i], 'final_upper'] = df['final_upper'].iloc[i-1]
            
            # Final Lower Band
            if pd.isna(df['basic_lower'].iloc[i]) or pd.isna(df['final_lower'].iloc[i-1]):
                df.loc[df.index[i], 'final_lower'] = df['basic_lower'].iloc[i]
            elif df['basic_lower'].iloc[i] > df['final_lower'].iloc[i-1] or df['close'].iloc[i-1] < df['final_lower'].iloc[i-1]:
                df.loc[df.index[i], 'final_lower'] = df['basic_lower'].iloc[i]
            else:
                df.loc[df.index[i], 'final_lower'] = df['final_lower'].iloc[i-1]
            
            # Trend
            prev_supertrend = df['final_lower'].iloc[i-1] if df['trend'].iloc[i-1] == 1 else df['final_upper'].iloc[i-1]
            
            if df['trend'].iloc[i-1] == -1 and df['close'].iloc[i] > df['final_upper'].iloc[i-1]:
                df.loc[df.index[i], 'trend'] = 1
            elif df['trend'].iloc[i-1] == 1 and df['close'].iloc[i] < df['final_lower'].iloc[i-1]:
                df.loc[df.index[i], 'trend'] = -1
            else:
                df.loc[df.index[i], 'trend'] = df['trend'].iloc[i-1]
            
            # Supertrend
            if df['trend'].iloc[i] == 1:
                df.loc[df.index[i], 'supertrend'] = df['final_lower'].iloc[i]
            else:
                df.loc[df.index[i], 'supertrend'] = df['final_upper'].iloc[i]
        
        return df
    
    def calculate_ema(self, df):
        """Calcula múltiplas EMAs para filtros"""
        # EMA principal de 10 (mudança aqui)
        df['ema_10'] = ta.ema(df['close'], length=self.ema_period)
        
        # EMAs adicionais para análise mais robusta
        df['ema_5'] = ta.ema(df['close'], length=5)
        df['ema_8'] = ta.ema(df['close'], length=8)
        df['ema_13'] = ta.ema(df['close'], length=13)
        df['ema_20'] = ta.ema(df['close'], length=20)
        df['ema_21'] = ta.ema(df['close'], length=21)
        df['ema_34'] = ta.ema(df['close'], length=34)
        df['ema_50'] = ta.ema(df['close'], length=50)
        df['ema_100'] = ta.ema(df['close'], length=100)
        df['ema_200'] = ta.ema(df['close'], length=200)
        
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
            logger.info(f"💰 Saldo USDT disponível: ${usdt_balance:.2f}")
            
            if usdt_balance < 10:  # Mínimo de $10 para operar
                logger.error(f"❌ Saldo insuficiente: ${usdt_balance:.2f} (mínimo $10)")
                return 0
            
            # Usar 95% do saldo para evitar erros de saldo insuficiente
            usable_balance = usdt_balance * 0.95
            logger.info(f"💼 Saldo utilizável (95%): ${usable_balance:.2f}")
            
            # Calcular tamanho da posição com alavancagem
            position_value = usable_balance * self.leverage
            size = position_value / price
            
            logger.info(f"🔢 Cálculo: {usable_balance:.2f} * {self.leverage} / {price:.2f} = {size:.6f}")
            
            # Arredondar para o número de decimais suportado pelo par
            market = self.exchange.markets[self.symbol]
            min_size = market['limits']['amount']['min']
            size = max(size, min_size)  # Garantir tamanho mínimo
            
            size = self.exchange.amount_to_precision(self.symbol, size)
            final_size = float(size)
            
            logger.info(f"📏 Tamanho mínimo: {min_size}")
            logger.info(f"✅ Tamanho final da posição: {final_size} ETH")
            
            return final_size
        except Exception as e:
            logger.error(f"💥 Erro ao calcular tamanho da posição: {e}")
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
            logger.info(f"🎯 Tentando abrir posição {side.upper()}")
            
            size = self.calculate_position_size(price)
            if size <= 0:
                logger.error("❌ Tamanho da posição inválido ou saldo insuficiente")
                return False
            
            logger.info(f"📊 Executando ordem: {side.upper()} {size} {self.symbol}")
            
            # Parâmetros para futuros
            params = {
                'type': 'market',
                'marginMode': 'cross'  # ou 'isolated'
            }
            
            order = self.exchange.create_market_order(
                self.symbol, 
                side, 
                size,
                None,  # price (None para market order)
                params
            )
            
            logger.info(f"✅ ORDEM EXECUTADA COM SUCESSO:")
            logger.info(f"   - ID: {order.get('id', 'N/A')}")
            logger.info(f"   - Lado: {order.get('side', 'N/A').upper()}")
            logger.info(f"   - Quantidade: {order.get('amount', 'N/A')}")
            logger.info(f"   - Preço: ${order.get('price', 'N/A')}")
            logger.info(f"   - Status: {order.get('status', 'N/A')}")
            
            return True
            
        except Exception as e:
            logger.error(f"💥 ERRO ao abrir posição {side}: {e}")
            # Log detalhado do erro
            import traceback
            logger.error(f"Stacktrace completo: {traceback.format_exc()}")
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
        """Analisa os sinais de compra e venda com EMA de 10 períodos"""
        if len(df) < 2:
            return None, None
        
        # Obter valores atuais e anteriores
        current_trend = df['trend'].iloc[-1]
        previous_trend = df['trend'].iloc[-2]
        current_price = df['close'].iloc[-1]
        current_ema_10 = df['ema_10'].iloc[-1]  # Mudança para EMA 10
        current_supertrend = df['supertrend'].iloc[-1]
        
        # Verificar se temos dados válidos
        if pd.isna(current_ema_10) or pd.isna(current_supertrend):
            logger.warning("Dados de indicadores inválidos (NaN)")
            return None, None
        
        # Log detalhado dos indicadores
        logger.info(f"Trend atual: {current_trend}, anterior: {previous_trend}")
        logger.info(f"Preço: {current_price:.2f}, EMA 10: {current_ema_10:.2f}")
        logger.info(f"Supertrend: {current_supertrend:.2f}")
        logger.info(f"Preço vs EMA 10: {'ACIMA' if current_price > current_ema_10 else 'ABAIXO'}")
        
        # Lógica de sinais com EMA de 10
        buy_signal = False
        sell_signal = False
        
        # Sinal de COMPRA (mudança para trend 1 + preço acima da EMA 10)
        if current_trend == 1 and previous_trend == -1:
            logger.info("🔄 MUDANÇA DE TREND DETECTADA: Baixa -> Alta")
            if current_price > current_ema_10:
                buy_signal = True
                logger.info("✅ SINAL DE COMPRA CONFIRMADO: Preço acima EMA 10")
            else:
                logger.info("❌ Sinal de compra rejeitado: Preço abaixo EMA 10")
        
        # Sinal de VENDA (mudança para trend -1 + preço abaixo da EMA 10)
        if current_trend == -1 and previous_trend == 1:
            logger.info("🔄 MUDANÇA DE TREND DETECTADA: Alta -> Baixa")
            if current_price < current_ema_10:
                sell_signal = True
                logger.info("✅ SINAL DE VENDA CONFIRMADO: Preço abaixo EMA 10")
            else:
                logger.info("❌ Sinal de venda rejeitado: Preço acima EMA 10")
        
        # Filtros adicionais usando EMA 5 e EMA 20 para confirmação
        if buy_signal or sell_signal:
            ema_5 = df['ema_5'].iloc[-1]
            ema_20 = df['ema_20'].iloc[-1]
            
            if not pd.isna(ema_5) and not pd.isna(ema_20):
                ema_bullish = ema_5 > ema_20
                logger.info(f"Filtro EMA: EMA5({ema_5:.2f}) {'>' if ema_bullish else '<'} EMA20({ema_20:.2f})")
                
                if buy_signal and not ema_bullish:
                    logger.info("⚠️  Sinal de compra com EMA bearish - mantendo sinal")
                if sell_signal and ema_bullish:
                    logger.info("⚠️  Sinal de venda com EMA bullish - mantendo sinal")
        
        return buy_signal, sell_signal
    
    def run_strategy(self):
        """Executa a estratégia de trading"""
        try:
            # Buscar dados
            df = self.get_candles(limit=300)  # Mais dados para indicadores
            if df is None or len(df) < max(self.ema_period, self.atr_period) + 50:
                logger.warning(f"Dados insuficientes para análise. Necessário: {max(self.ema_period, self.atr_period) + 50}, Atual: {len(df) if df is not None else 0}")
                return
            
            # Calcular indicadores
            df = self.calculate_supertrend(df)
            df = self.calculate_ema(df)
            
            # Obter posição atual
            current_position = self.get_current_position()
            current_price = df['close'].iloc[-1]
            
            # Verificar stop loss primeiro
            if current_position and self.check_stop_loss(current_position, current_price):
                logger.info("🛑 EXECUTANDO STOP LOSS")
                if self.close_position():
                    self.current_position = None
                    logger.info("✅ Stop Loss executado com sucesso")
                    return
                else:
                    logger.error("❌ Falha ao executar Stop Loss")
            
            # Analisar sinais
            buy_signal, sell_signal = self.analyze_signals(df)
            
            # Logs informativos detalhados
            logger.info("=" * 60)
            logger.info(f"📊 ANÁLISE DE MERCADO - {datetime.now().strftime('%H:%M:%S')}")
            logger.info(f"💰 Preço atual: ${current_price:.2f}")
            logger.info(f"📈 EMA 10: ${df['ema_10'].iloc[-1]:.2f}")
            logger.info(f"📉 Supertrend: ${df['supertrend'].iloc[-1]:.2f}")
            logger.info(f"🎯 Trend: {df['trend'].iloc[-1]} ({'ALTA' if df['trend'].iloc[-1] == 1 else 'BAIXA'})")
            
            # Informações de posição
            if current_position and current_position.get('size', 0) != 0:
                pos_side = current_position.get('side', 'N/A')
                pos_size = current_position.get('size', 0)
                pos_entry = current_position.get('entryPrice', 0)
                pos_pnl = current_position.get('unrealizedPnl', 0)
                logger.info(f"💼 Posição atual: {pos_side.upper()} | Tamanho: {pos_size} | Entrada: ${pos_entry:.2f} | PnL: ${pos_pnl:.2f}")
            else:
                logger.info("💼 Nenhuma posição ativa")
            
            # Debug dos sinais
            logger.info(f"📶 Sinal COMPRA: {'✅ SIM' if buy_signal else '❌ NÃO'}")
            logger.info(f"📶 Sinal VENDA: {'✅ SIM' if sell_signal else '❌ NÃO'}")
            
            # Executar ordens baseadas nos sinais
            if buy_signal:
                logger.info("🚀 SINAL DE COMPRA DETECTADO!")
                if current_position and current_position.get('size', 0) != 0:
                    if current_position.get('side') == 'short':
                        logger.info("🔄 Fechando posição SHORT e abrindo LONG")
                        if self.close_position():
                            time.sleep(3)  # Aguardar fechamento
                            if self.open_position('buy', current_price):
                                logger.info("✅ Inversão para LONG executada com sucesso")
                            else:
                                logger.error("❌ Falha ao abrir posição LONG")
                        else:
                            logger.error("❌ Falha ao fechar posição SHORT")
                    else:
                        logger.info("ℹ️  Já em posição LONG - mantendo")
                else:
                    logger.info("📈 Abrindo nova posição LONG")
                    if self.open_position('buy', current_price):
                        logger.info("✅ Posição LONG aberta com sucesso")
                    else:
                        logger.error("❌ Falha ao abrir posição LONG")
                        
            elif sell_signal:
                logger.info("🔥 SINAL DE VENDA DETECTADO!")
                if current_position and current_position.get('size', 0) != 0:
                    if current_position.get('side') == 'long':
                        logger.info("🔄 Fechando posição LONG e abrindo SHORT")
                        if self.close_position():
                            time.sleep(3)  # Aguardar fechamento
                            if self.open_position('sell', current_price):
                                logger.info("✅ Inversão para SHORT executada com sucesso")
                            else:
                                logger.error("❌ Falha ao abrir posição SHORT")
                        else:
                            logger.error("❌ Falha ao fechar posição LONG")
                    else:
                        logger.info("ℹ️  Já em posição SHORT - mantendo")
                else:
                    logger.info("📉 Abrindo nova posição SHORT")
                    if self.open_position('sell', current_price):
                        logger.info("✅ Posição SHORT aberta com sucesso")
                    else:
                        logger.error("❌ Falha ao abrir posição SHORT")
            else:
                logger.info("⏸️  Nenhum sinal detectado - aguardando próxima oportunidade")
                
            # Log final
            logger.info("=" * 60)
                
        except Exception as e:
            logger.error(f"💥 Erro na execução da estratégia: {e}")
            import traceback
            logger.error(f"Stacktrace: {traceback.format_exc()}")
    
    def run(self):
        """Loop principal do bot"""
        logger.info("Bot iniciado!")
        logger.info(f"Par: {self.symbol}")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"Alavancagem: {self.leverage}x")
        logger.info(f"Stop Loss: {self.stop_loss_pct*100}%")
        logger.info(f"EMA Principal: {self.ema_period} períodos")
        
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
