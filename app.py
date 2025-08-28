#!/usr/bin/env python3
"""
App.py - Ponto de entrada para o bot de trading Bitget
Este arquivo é usado pelo Render.com para iniciar o bot
"""

from main import BitgetTradingBot
import logging
import sys
import os

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log') if os.path.exists('/app') else logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def main():
    """Função principal para iniciar o bot"""
    try:
        logger.info("🚀 Iniciando Bot de Trading Bitget...")
        
        # Verificar se as variáveis de ambiente estão configuradas
        required_vars = ['BITGET_API_KEY', 'BITGET_SECRET', 'BITGET_PASSPHRASE']
        missing_vars = []
        
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            logger.error(f"❌ Variáveis de ambiente obrigatórias não encontradas: {missing_vars}")
            logger.error("Configure as seguintes variáveis no Render.com:")
            for var in missing_vars:
                logger.error(f"  - {var}")
            sys.exit(1)
        
        logger.info("✅ Variáveis de ambiente configuradas corretamente")
        
        # Inicializar e executar o bot
        bot = BitgetTradingBot()
        bot.run()
        
    except KeyboardInterrupt:
        logger.info("🛑 Bot interrompido pelo usuário")
        sys.exit(0)
    except Exception as e:
        logger.error(f"💥 Erro fatal ao iniciar o bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
