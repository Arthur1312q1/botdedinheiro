# Bot de Trading Bitget - ETH/USDT Futures

Bot automatizado de trading para futuros de ETH/USDT na Bitget usando estratégia Supertrend + EMA com inversão de posição.

## 🚀 Características

- **Estratégia**: Supertrend + EMA 50 com inversão automática de posições
- **Par**: ETH/USDT:USDT (Futuros)
- **Timeframe**: 15 minutos
- **Alavancagem**: 10x
- **Stop Loss**: 1%
- **Capital**: Usa 100% do saldo USDT disponível

## 📋 Requisitos

- Conta na Bitget com API habilitada
- Python 3.11+
- Saldo em USDT na conta de futuros

## 🔧 Configuração

### 1. Estrutura do Projeto
```
bitget-trading-bot/
├── app.py           # Ponto de entrada (para Render.com)
├── main.py          # Bot principal com toda a lógica
├── requirements.txt
├── Dockerfile
└── README.md
```

### 2. Variáveis de Ambiente

Configure as seguintes variáveis de ambiente no Render.com:

- `BITGET_API_KEY`: Sua API Key da Bitget
- `BITGET_SECRET`: Sua Secret Key da Bitget  
- `BITGET_PASSPHRASE`: Sua Passphrase da Bitget

### 3. Deploy no Render.com

1. Faça fork/clone deste repositório no GitHub
2. Conecte sua conta do Render.com ao GitHub
3. Crie um novo Web Service no Render
4. Configure as variáveis de ambiente
5. Deploy automático será feito

## 📊 Lógica da Estratégia

### Indicadores Utilizados:
- **Supertrend**: ATR período 10, multiplicador 3.0
- **EMA**: Média móvel exponencial de 50 períodos

### Regras de Entrada:
- **LONG**: Supertrend muda para alta + preço acima da EMA 50
- **SHORT**: Supertrend muda para baixa + preço abaixo da EMA 50

### Regras de Saída:
- **Stop Loss**: 1% contra a posição
- **Inversão**: Fecha posição atual e abre nova na direção oposta quando há sinal contrário

## ⚠️ Avisos Importantes

- **RISCO**: Trading com alavancagem envolve alto risco
- **TESTE**: Teste sempre em conta demo primeiro
- **CAPITAL**: Só invista o que pode perder
- **MONITORAMENTO**: Monitore o bot regularmente

## 📈 Como Funciona

1. Bot analisa os dados de velas a cada 5 minutos
2. Calcula Supertrend e EMA 50
3. Verifica se há stop loss para executar
4. Procura por sinais de entrada (mudança de tendência + filtro EMA)
5. Executa ordens de mercado para garantir preenchimento
6. Mantém sempre uma posição ativa (long ou short)

## 🔍 Logs

O bot gera logs detalhados mostrando:
- Preços atuais e indicadores
- Sinais detectados
- Execução de ordens
- Status das posições
- Erros e avisos

## 🛠️ Modificações Possíveis

Para alterar parâmetros, edite as variáveis na classe `BitgetTradingBot`:

```python
self.leverage = 10           # Alavancagem
self.stop_loss_pct = 0.01   # Stop loss (1%)
self.atr_period = 10        # Período ATR
self.atr_multiplier = 3.0   # Multiplicador ATR
self.ema_period = 50        # Período EMA
```

## 📞 Suporte

Este bot é fornecido como está. Use por sua própria conta e risco.

---

**⚡ Bom trading!**
