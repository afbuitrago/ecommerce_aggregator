import time
import logging
import json
import os
import re
import sys
import gc # Garbage Collector
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains
from bs4 import BeautifulSoup

# Importaciones para la gestión automática del driver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options

# --- CONSTANTES ESPECiFICAS PARA ZAPATOCA ---
BASE_URL = "https://www.mercadozapatoca.com/"
STORE_NAME = "Mercado Zapatoca"
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "raw_data", "zapatoca")
LINKS_FILEPATH = os.path.join(OUTPUT_DIR, "zapatoca_links.json") # Archivo para guardar los links
PRODUCTS_FILEPATH = os.path.join(OUTPUT_DIR, "productos_zapatoca.json")

# Timeouts (en segundos)
FAST_TIMEOUT = 15
PAGE_LOAD_TIMEOUT = 25
IMPLICIT_WAIT = 5

def setup_driver(user_agent, logger):
    """Configura e inicializa una instancia de WebDriver con medidas anti-detección."""
    logger.info("Configurando una nueva instancia de WebDriver...")
    options = Options()
    options.page_load_strategy = 'eager'
    options.add_argument(f"user-agent={user_agent}")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--allow-running-insecure-content")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        logger.info("WebDriver configurado exitosamente.")
        return driver
    except Exception as e:
        logger.error(f"Error crítico al configurar WebDriver: {e}", exc_info=True)
        return None

def clean_price(price_str):
    """Limpia un string de precio, eliminando símbolos y convirtiéndolo a float."""
    if not price_str or not isinstance(price_str, str):
        return 0.0
    numbers = re.findall(r'\d+', price_str)
    return float("".join(numbers)) if numbers else 0.0

def extract_product_data(soup, category_info, logger):
    """
    Usa BeautifulSoup para parsear el HTML de la página de productos y extraer los datos.
    """
    products_on_page = []
    product_containers = soup.select("div.dpr_container") 

    for product_card in product_containers:
        try:
            name_element = product_card.select_one("div.dpr_product-name")
            full_name = name_element.text.strip() if name_element else "N/A"
            
            brand = full_name.split()[0] if full_name != "N/A" else "N/A"

            price_element = product_card.select_one("div.dpr_listprice")
            final_price = clean_price(price_element.text) if price_element else 0.0
            
            original_price_element = product_card.select_one("div.dpr_suggested_price")
            original_price = clean_price(original_price_element.text) if original_price_element else final_price
            
            if original_price < final_price: original_price = final_price

            discount = 0
            discount_ribbon = product_card.select_one(".wrapper-ribbon")
            if discount_ribbon and 'data-discount-percent' in discount_ribbon.attrs:
                discount = int(discount_ribbon['data-discount-percent'])
            elif original_price > final_price > 0:
                discount = round(((original_price - final_price) / original_price) * 100)
            
            url_element = product_card.select_one("a.dpr_listname")
            product_url = url_element['href'] if url_element and url_element.has_attr('href') else "N/A"
            if product_url.startswith('/'): product_url = BASE_URL.rstrip('/') + product_url
            
            image_element = product_card.select_one("div.dpr_imagen_thumb img")
            image_url = image_element['src'] if image_element and image_element.has_attr('src') else "N/A"
            
            products_on_page.append({
                "tienda": STORE_NAME,
                "categoria_principal": category_info.get("categoria_principal", "N/A"),
                "sub_categoria": category_info.get("sub_categoria", "N/A"),
                "tipo": category_info.get("tipo", "N/A"),
                "nombre_completo": full_name,
                "marca": brand.upper(),
                "precio_final": final_price,
                "precio_sin_descuento": original_price,
                "porcentaje_descuento": discount,
                "url_producto": product_url,
                "url_imagen": image_url,
            })
        except Exception as e:
            logger.warning(f"No se pudo procesar una tarjeta de producto. Error: {e}. Saltando...")
            continue
    return products_on_page

def append_to_json(new_data, filepath, logger):
    """Añade datos de forma segura a un archivo JSON."""
    if not new_data: return
    products = []
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                products = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        products = []
    products.extend(new_data)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(products, f, indent=4, ensure_ascii=False)
    logger.info(f"Guardados {len(new_data)} productos. Total acumulado en '{filepath}': {len(products)}.")

def collect_and_structure_links(driver, logger):
    """
    Recolecta y estructura los enlaces de categorías en un formato jerárquico.
    """
    logger.info("Iniciando recolección y estructuración de enlaces...")
    driver.get(BASE_URL)
    wait = WebDriverWait(driver, FAST_TIMEOUT)
    actions = ActionChains(driver)
    
    try:
        ingresar_button = wait.until(EC.element_to_be_clickable((By.ID, "btn_aceptar_terminos")))
        driver.execute_script("arguments[0].click();", ingresar_button)
        time.sleep(IMPLICIT_WAIT)
    except Exception:
        logger.warning("No se pudo interactuar con el modal de ubicación. Continuando...")

    links_structure = {}
    try:
        menu_button = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "div.menu-h")))
        actions.move_to_element(menu_button).perform()
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#mega-menu")))
        
        main_categories_elements = driver.find_elements(By.CSS_SELECTOR, "#mega-menu > ul > li.has-children")
        
        for i in range(len(main_categories_elements)):
            main_cat_element = driver.find_elements(By.CSS_SELECTOR, "#mega-menu > ul > li.has-children")[i]
            actions.move_to_element(main_cat_element).perform()
            time.sleep(0.2)
            main_cat_name = main_cat_element.find_element(By.XPATH, "./a").text.strip()
            if main_cat_name not in links_structure:
                links_structure[main_cat_name] = {}

            all_sub_elements = main_cat_element.find_elements(By.XPATH, "./ul/li")
            for sub_element in all_sub_elements:
                if "has-children" in sub_element.get_attribute("class"):
                    actions.move_to_element(sub_element).perform()
                    time.sleep(0.2)
                    sub_cat_a = sub_element.find_element(By.XPATH, "./a")
                    sub_cat_name = sub_cat_a.text.strip()
                    if sub_cat_name not in links_structure[main_cat_name]:
                        links_structure[main_cat_name][sub_cat_name] = []
                    
                    final_links_elements = sub_element.find_elements(By.XPATH, ".//li/a")
                    for final_link_a in final_links_elements:
                        try:
                            links_structure[main_cat_name][sub_cat_name].append({
                                "tipo_producto": final_link_a.text.strip(),
                                "link": final_link_a.get_attribute('href')
                            })
                        except StaleElementReferenceException: continue
                else:
                    try:
                        direct_link_a = sub_element.find_element(By.XPATH, "./a")
                        sub_cat_name = direct_link_a.text.strip()
                        url = direct_link_a.get_attribute('href')
                        if url and sub_cat_name:
                             links_structure[main_cat_name][sub_cat_name] = [{
                                "tipo_producto": sub_cat_name,
                                "link": url
                            }]
                    except (NoSuchElementException, StaleElementReferenceException): continue
    
    except Exception as e:
        logger.error(f"Error inesperado recolectando enlaces: {e}", exc_info=True)

    logger.info(f"Estructura de enlaces finalizada. Se encontraron {len(links_structure)} categorías principales.")
    return links_structure

def scrape_zapatoca(user_agent, logger):
    """Función principal que orquesta el scraping en dos fases."""
    start_time = time.time()
    logger.info(f"--- INICIANDO SCRAPER PARA {STORE_NAME} ---")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # --- FASE 1: RECOLECCIÓN Y ESTRUCTURACIÓN DE ENLACES ---
    if not os.path.exists(LINKS_FILEPATH):
        logger.info(f"Archivo de enlaces '{LINKS_FILEPATH}' no encontrado. Iniciando Fase 1.")
        driver = setup_driver(user_agent, logger)
        if not driver: return
        try:
            links_structure = collect_and_structure_links(driver, logger)
            with open(LINKS_FILEPATH, 'w', encoding='utf-8') as f:
                json.dump(links_structure, f, indent=4, ensure_ascii=False)
            logger.info(f"FASE 1 COMPLETADA: Estructura de enlaces guardada en '{LINKS_FILEPATH}'.")
        finally:
            if driver: driver.quit()
    else:
        logger.info(f"Archivo de enlaces '{LINKS_FILEPATH}' encontrado. Saltando Fase 1.")

    # --- FASE 2: EXTRACCIÓN DE PRODUCTOS ---
    logger.info("Iniciando Fase 2: Extracción de productos desde la estructura de enlaces.")
    try:
        with open(LINKS_FILEPATH, 'r', encoding='utf-8') as f:
            links_structure = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.error(f"No se pudo leer el archivo de enlaces '{LINKS_FILEPATH}'. Abortando Fase 2.")
        return

    if not links_structure:
        logger.warning("La estructura de enlaces está vacía. No hay nada que procesar.")
        return
        
    if os.path.exists(PRODUCTS_FILEPATH):
        os.remove(PRODUCTS_FILEPATH)
        logger.info(f"Archivo de productos anterior '{PRODUCTS_FILEPATH}' eliminado.")

    # Iterar sobre la estructura jerárquica
    for main_cat, sub_cats in links_structure.items():
        logger.info(f"\n\n===== PROCESANDO CATEGORÍA PRINCIPAL: {main_cat} =====")
        driver = setup_driver(user_agent, logger) # Reiniciar driver por cada categoría principal
        if not driver:
            logger.error(f"No se pudo reiniciar el driver para la categoría '{main_cat}'. Saltando.")
            continue
        try:
            for sub_cat, types_list in sub_cats.items():
                for type_info in types_list:
                    link_info = {
                        "categoria_principal": main_cat,
                        "sub_categoria": sub_cat,
                        "tipo": type_info["tipo_producto"],
                        "url": type_info["link"]
                    }
                    logger.info(f"\n--- Procesando: {main_cat} > {sub_cat} > {type_info['tipo_producto']} ---")
                    driver.get(link_info["url"])
                    page_num = 1
                    while True:
                        logger.info(f"Extrayendo datos de la página {page_num}...")
                        try:
                            WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(EC.visibility_of_element_located((By.ID, "productos")))
                            time.sleep(IMPLICIT_WAIT)
                        except TimeoutException:
                            logger.warning(f"No se encontró el contenedor de productos en la pág {page_num}. Finalizando este enlace.")
                            break
                        
                        soup = BeautifulSoup(driver.page_source, "html.parser")
                        new_products = extract_product_data(soup, link_info, logger)
                        if new_products: append_to_json(new_products, PRODUCTS_FILEPATH, logger)
                        
                        try:
                            next_page_button = driver.find_element(By.XPATH, "//a[contains(text(), 'Siguiente')]")
                            driver.execute_script("arguments[0].click();", next_page_button)
                            page_num += 1
                        except NoSuchElementException:
                            logger.info("No hay más páginas.")
                            break
        finally:
            if driver: driver.quit()
            gc.collect()
            logger.info(f"WebDriver para la categoría '{main_cat}' cerrado y recursos liberados.")
            
    duration = time.time() - start_time
    logger.info(f"\n--- SCRAPING PARA {STORE_NAME} FINALIZADO ---")
    
if __name__ == '__main__':
    # Bloque de prueba
    test_logger = logging.getLogger('TestZapatoca')
    test_logger.setLevel(logging.INFO)
    if not test_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        test_logger.addHandler(handler)
    
    test_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    scrape_zapatoca(user_agent=test_user_agent, logger=test_logger)