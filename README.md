# Bot de Trading Bitget - ETH/USDT Futures

Bot automatizado de trading para futuros de ETH/USDT na Bitget usando estratégia Supertrend + EMA com inversão de posição.

## 🚀 Características

- **Estratégia**: Supertrend + EMA 10 com inversão automática de posições
- **Par**: ETH/USDT:USDT (Futuros)
- **Timeframe**: 15 minutos
- **Alavancagem**: 10x
- **Stop Loss**: 1%
- **Capital**: Usa 100% do saldo USDT disponível
- **Monitoramento Web**: Interface HTTP para acompanhar status do bot

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
- **EMA**: Média móvel exponencial de 10 períodos (principal)
- **EMAs Auxiliares**: 5, 8, 13, 20, 21, 34, 50, 100, 200

### Regras de Entrada:
- **LONG**: Supertrend muda para alta + preço acima da EMA 10
- **SHORT**: Supertrend muda para baixa + preço abaixo da EMA 10

### Regras de Saída:
- **Stop Loss**: 1% contra a posição
- **Inversão**: Fecha posição atual e abre nova na direção oposta quando há sinal contrário

## ⚠️ Avisos Importantes

- **RISCO**: Trading com alavancagem envolve alto risco
- **TESTE**: Teste sempre em conta demo primeiro
- **CAPITAL**: Só invista o que pode perder
- **MONITORAMENTO**: Monitore o bot regularmente

## 🌐 Interface Web de Controle

O bot agora possui uma interface web completa para controle e monitoramento:

### 🎮 **Funcionalidades da Interface:**
- **▶️ Botão INICIAR BOT**: Liga o bot de trading
- **⏹️ Botão PARAR BOT**: Para o bot com segurança  
- **🔄 Botão ATUALIZAR**: Atualiza dados em tempo real
- **📊 Dashboard Visual**: Gráficos e cards informativos
- **📱 Responsivo**: Funciona em desktop e mobile

### 📊 **Informações Exibidas:**
- Status do bot (Rodando/Parado)
- Preço atual do ETH/USDT
- Posição atual (Long/Short/Nenhuma)
- Última atualização
- Contador de erros
- Dados detalhados em JSON

### 🔗 **URLs Disponíveis:**
- **Interface Principal**: `https://seu-app.onrender.com/`
- **API Status**: `https://seu-app.onrender.com/status`
- **Health Check**: `https://seu-app.onrender.com/health`
- **Iniciar Bot**: `POST https://seu-app.onrender.com/start`
- **Parar Bot**: `POST https://seu-app.onrender.com/stop`

1. Bot analisa os dados de velas a cada 5 minutos
2. Calcula Supertrend e EMA 50
3. Verifica se há stop loss para executar
4. Procura por sinais de entrada (mudança de tendência + filtro EMA)
5. Executa ordens de mercado para garantir preenchimento
6. Mantém sempre uma posição ativa (long ou short)

## 📈 Como Funciona

O bot gera logs detalhados mostrando:
- Preços atuais e indicadores
- Sinais detectados
- Execução de ordens
- Status das posições
- Erros e avisos

## 🛠️ Modificações Possíveis

## 🔧 Principais Mudanças Implementadas:

### ✅ **EMA de 10 Períodos (Principal Mudança):**
- **Filtro mais rápido**: EMA 10 ao invés de EMA 50
- **Sinais mais frequentes**: Reage mais rápido às mudanças de preço
- **Maior sensibilidade**: Mais trades em mercados voláteis

### ✅ **Sistema de Sinais Otimizado:**
- **COMPRA**: Supertrend vira alta + preço > EMA 10
- **VENDA**: Supertrend vira baixa + preço < EMA 10
- **Filtros auxiliares**: Confirmação com EMA 5 vs EMA 20
- **Logs detalhados**: Mostra exatamente porque aceita/rejeita sinais

### ✅ **Múltiplas EMAs para Confirmação:**
- **10 EMAs diferentes**: 5, 8, 10, 13, 20, 21, 34, 50, 100, 200
- **Análise robusta**: Filtros cruzados para maior precisão
- **Menos falsos sinais**: Confirmação com diferentes períodos

### ✅ **Melhor Detecção de Problemas:**
- **Logs extremamente detalhados**: Cada passo é logado
- **Verificação de saldo**: Logs de todos os cálculos
- **Status de mercado**: Preço, EMAs, trend, tudo visível
- **Debug de ordens**: Motivo de falhas nas execuções

### 🔧 **Parâmetros Configuráveis:**

```python
self.leverage = 10           # Alavancagem
self.stop_loss_pct = 0.01   # Stop loss (1%)
self.atr_period = 10        # Período ATR
self.atr_multiplier = 3.0   # Multiplicador ATR
self.ema_period = 10        # Período EMA principal (mudança aqui!)
```

## 📞 Suporte

Este bot é fornecido como está. Use por sua própria conta e risco.

---

**⚡ Bom trading!**
