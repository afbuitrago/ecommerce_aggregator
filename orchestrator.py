# orchestrator.py

import argparse
import logging
import sys
import os
import time

# --- AJUSTE CRUCIAL DE RUTA ---
# Añade el directorio raíz del proyecto al path de Python.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
# --- FIN DEL AJUSTE ---

# --- IMPORTACIÓN DE LOS SCRAPERS ---
from scrapers.carulla.scraper_carulla import scrape_carulla
from scrapers.jumbo.scraper_jumbo import scrape_jumbo
from scrapers.zapatoca.scraper_zapatoca import scrape_zapatoca
#from scrapers.exito.scraper_exito import scrape_exito


# User-Agent centralizado para todos los scrapers.
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

def get_logger(name, log_file, level=logging.INFO):
    """
    Crea y configura un logger para escribir en un archivo y en la consola.
    Garantiza que el logger no tenga handlers duplicados.
    """
    # Asegurarse de que el directorio de logs exista
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevenir handlers duplicados si el script se llama múltiples veces
    if not logger.handlers:
        # Handler para el archivo (modo 'w' para limpiar en cada ejecución)
        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Handler para la consola
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger

# Mapeo de tiendas a sus funciones de scraping.
SCRAPERS = {
    "carulla": scrape_carulla,
    "jumbo": scrape_jumbo,
    "zapatoca": scrape_zapatoca
    #"exito": scrape_exito
}

def main():
    """
    Función principal que lee los argumentos, configura los loggers y ejecuta
    el o los scrapers correspondientes, midiendo el tiempo de ejecución.
    """
    parser = argparse.ArgumentParser(description="Orquestador de scrapers para el agregador de e-commerce.")
    
    parser.add_argument(
        '--tienda', 
        type=str, 
        help='Ejecuta el scraper de una tienda específica.', 
        choices=SCRAPERS.keys()
    )
    
    args = parser.parse_args()
    
    # Logger principal para el orquestador
    orchestrator_logger = get_logger('Orchestrator', 'logs/orchestrator.log')

    if args.tienda:
        orchestrator_logger.info(f"Ejecución solicitada para una sola tienda: {args.tienda}")
        scraper_func = SCRAPERS.get(args.tienda)
        if scraper_func:
            tienda_logger = get_logger(args.tienda, f'logs/{args.tienda}.log')
            orchestrator_logger.info(f"Iniciando scraper para la tienda: {args.tienda}")
            start_time = time.time()
            try:
                scraper_func(user_agent=USER_AGENT, logger=tienda_logger)
                orchestrator_logger.info(f"Scraper para {args.tienda} finalizado con éxito.")
            except Exception as e:
                orchestrator_logger.error(f"Falló el scraper para {args.tienda}: {e}", exc_info=True)
            finally:
                duration = time.time() - start_time
                orchestrator_logger.info(f"Tiempo de ejecución para {args.tienda}: {duration:.2f} segundos.")
    else:
        orchestrator_logger.info("Ejecutando todos los scrapers disponibles.")
        total_start_time = time.time()
        for tienda, scraper_func in SCRAPERS.items():
            tienda_logger = get_logger(tienda, f'logs/{tienda}.log')
            orchestrator_logger.info(f"--- Iniciando scraper para {tienda} ---")
            start_time = time.time()
            try:
                scraper_func(user_agent=USER_AGENT, logger=tienda_logger)
                orchestrator_logger.info(f"--- Scraper para {tienda} finalizado con éxito ---")
            except Exception as e:
                orchestrator_logger.error(f"--- Falló el scraper para {tienda}: {e} ---", exc_info=True)
            finally:
                duration = time.time() - start_time
                orchestrator_logger.info(f"--- Tiempo de ejecución para {tienda}: {duration:.2f} segundos. ---")
        
        total_duration = time.time() - total_start_time
        orchestrator_logger.info(f"\nProceso de orquestación completado. Tiempo total: {total_duration:.2f} segundos.")

if __name__ == '__main__':
    main()
