import json
import os
import time
import gc
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup

def setup_driver(user_agent, logger):
    """Configura e inicializa el WebDriver de Selenium."""
    logger.info(f"Configurando driver con User-Agent: {user_agent}")
    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'eager'
    # options.add_argument("--headless")
    options.add_argument(f"user-agent={user_agent}")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    options.add_argument('--ignore-certificate-errors')
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def extract_product_data(soup, main_category_name, sub_category, tipo, logger):
    """Extrae los datos de los productos de la página."""
    productos_en_pagina = []
    product_containers = soup.select('article.productCard_productCard__M0677')
    
    for item in product_containers:
        try:
            name_tag = item.select_one('h3.styles_name__qQJiK')
            name = name_tag.get_text(strip=True) if name_tag else "N/A"
            
            name_parts = name.split()
            brand_words = []
            for word in name_parts[1:]:
                if word.isupper() or (len(word) > 1 and word.replace('.', '').isupper()):
                    brand_words.append(word.replace('.', ''))
                else:
                    if brand_words: break
            brand = ' '.join(brand_words) if brand_words else (name_parts[1] if len(name_parts) > 1 else name_parts[0])

            link_tag = item.select_one('a[data-testid="product-link"]')
            url_producto = f"https://www.carulla.com{link_tag['href']}" if link_tag and link_tag.get('href') else "N/A"

            image_tag = item.select_one('img')
            url_imagen = image_tag.get('src') if image_tag else "N/A"

            price_sell_tag = item.select_one('p.ProductPrice_container__price__XmMWA')
            price_list_tag = item.select_one('p.priceSection_container-promotion_price-dashed__FJ7nI')

            precio_final_str = price_sell_tag.get_text(strip=True) if price_sell_tag else '0'
            precio_final = float(precio_final_str.replace('$', '').replace('.', '').replace(',', ''))
            
            precio_sin_descuento = precio_final
            if price_list_tag:
                precio_sin_descuento_str = price_list_tag.get_text(strip=True)
                precio_sin_descuento = float(precio_sin_descuento_str.replace('$', '').replace('.', '').replace(',', ''))
            
            descuento_porcentaje = 0
            if precio_sin_descuento > precio_final:
                descuento_porcentaje = round(((precio_sin_descuento - precio_final) / precio_sin_descuento) * 100)

            producto_data = {
                "tienda": "Carulla",
                "categoria_principal": main_category_name,
                "sub_categoria": sub_category,
                "tipo": tipo,
                "nombre_completo": name,
                "marca": brand,
                "precio_final": precio_final,
                "precio_sin_descuento": precio_sin_descuento,
                "porcentaje_descuento": descuento_porcentaje,
                "url_producto": url_producto,
                "url_imagen": url_imagen,
            }
            productos_en_pagina.append(producto_data)
        except Exception as e:
            logger.warning(f"Se omitió un producto por datos incompletos o error de parsing. Error: {e}")
            continue
    return productos_en_pagina

def append_to_json(new_data, filepath, logger):
    """Añade datos a un archivo JSON de forma segura."""
    if not new_data: return
    existing_data = []
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            try: existing_data = json.load(f)
            except json.JSONDecodeError: logger.warning(f"Archivo JSON {filepath} corrupto. Se sobreescribirá.")
    existing_data.extend(new_data)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, indent=4, ensure_ascii=False)

def collect_all_links(user_agent, fast_timeout, logger):
    """Navega el menú para recolectar todos los enlaces de subcategorías."""
    driver = None
    try:
        driver = setup_driver(user_agent, logger)
        driver.get("https://www.carulla.com/")
        try:
            WebDriverWait(driver, fast_timeout).until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
            logger.info("Banner de cookies aceptado.")
        except TimeoutException:
            logger.warning("No se encontró o no se pudo hacer clic en el banner de cookies.")

        logger.info("Abriendo menú principal para recolectar enlaces...")
        menu_button_selector = "div[data-fs-menu-icon-container='true']"
        WebDriverWait(driver, fast_timeout).until(EC.element_to_be_clickable((By.CSS_SELECTOR, menu_button_selector))).click()
        
        all_sub_categories_to_scrape = []
        main_categories_xpath = "//section[./header[text()='Categorías']]//li[contains(@class, 'Link_link-container')]"
        num_main_categories = len(WebDriverWait(driver, fast_timeout).until(EC.presence_of_all_elements_located((By.XPATH, main_categories_xpath))))

        for i in range(num_main_categories):
            main_category_name = "N/A"
            try:
                main_categories = WebDriverWait(driver, fast_timeout).until(EC.presence_of_all_elements_located((By.XPATH, main_categories_xpath)))
                category_to_click = main_categories[i]
                main_category_name = category_to_click.text.split('\n')[0].strip()
                if not main_category_name: continue

                logger.info(f"Recolectando de Categoría Principal: '{main_category_name}'")
                category_to_click.click()
                
                submenu_container_selector = "ul[data-content-list='true']"
                WebDriverWait(driver, fast_timeout).until(EC.visibility_of_element_located((By.CSS_SELECTOR, submenu_container_selector)))
                
                submenu_groups = driver.find_elements(By.CSS_SELECTOR, "li.SubMenu_subsection-item__sPPCM")
                for group in submenu_groups:
                    sub_group_title = group.find_element(By.CSS_SELECTOR, "div[data-title-section-item='true'] a b").text
                    sub_category_links = group.find_elements(By.CSS_SELECTOR, "ul[data-list-sections='true'] li[data-link='true'] a")
                    for link in sub_category_links:
                        all_sub_categories_to_scrape.append({'main_category': main_category_name, 'sub_category': sub_group_title, 'tipo': link.text.strip(), 'href': link.get_attribute('href')})
                
                WebDriverWait(driver, fast_timeout).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[data-menu-back-button='true']"))).click()
                WebDriverWait(driver, fast_timeout).until(EC.visibility_of_element_located((By.XPATH, main_categories_xpath)))
            except Exception as e:
                logger.error(f"Error procesando la categoría {i} ('{main_category_name}'): {e}", exc_info=True)
                driver.get("https://www.carulla.com/") # Intenta recuperar
                WebDriverWait(driver, fast_timeout).until(EC.element_to_be_clickable((By.CSS_SELECTOR, menu_button_selector))).click()
                continue
        return all_sub_categories_to_scrape
    finally:
        if driver: driver.quit()

def scrape_carulla(user_agent, logger):
    """Flujo principal de scraping para Carulla.com."""
    start_time = time.time()
    logger.info("--- INICIANDO PROCESO DE SCRAPING PARA CARULLA ---")
    
    FAST_TIMEOUT = 10
    PAGE_LOAD_TIMEOUT = 15

    output_dir = 'raw_data/carulla'
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'productos_carulla.json')
    if os.path.exists(output_path):
        os.remove(output_path)
        logger.info(f"Archivo de productos anterior '{output_path}' eliminado.")
    
    logger.info("--- INICIANDO FASE 1: Recolección de enlaces ---")
    all_links = collect_all_links(user_agent, FAST_TIMEOUT, logger)
    if not all_links:
        logger.critical("No se pudo recolectar ningún enlace. Abortando scraping.")
        return
        
    logger.info(f"--- FASE 1 COMPLETADA: Se recolectaron {len(all_links)} enlaces de sub-categorías. ---")
    logger.info("--- INICIANDO FASE 2: SCRAPING DE PRODUCTOS ---")

    for link_info in all_links:
        driver = None
        try:
            main_cat, sub_cat, tipo, sub_cat_href = link_info['main_category'], link_info['sub_category'], link_info['tipo'], link_info['href']
            if not all([main_cat, sub_cat, tipo, sub_cat_href]): continue

            driver = setup_driver(user_agent, logger)
            logger.info(f"\nScrapeando: {main_cat} -> {sub_cat} -> {tipo} | URL: {sub_cat_href}")
            driver.get(sub_cat_href)
            
            products_in_subcategory = [] 
            page_num = 1
            while True:
                try:
                    logger.info(f"    - Extrayendo productos de la página {page_num}...")
                    wait = WebDriverWait(driver, PAGE_LOAD_TIMEOUT)
                    gallery_xpath = "//div[contains(@class, 'product-grid_fs-product-grid')]"
                    wait.until(EC.presence_of_element_located((By.XPATH, gallery_xpath)))
                    
                    first_product_name_xpath = f"({gallery_xpath}//h3[contains(@class, 'styles_name')])[1]"
                    initial_product_name = wait.until(EC.presence_of_element_located((By.XPATH, first_product_name_xpath))).text
                    time.sleep(2) 
                    
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    products_on_page = extract_product_data(soup, main_cat, sub_cat, tipo, logger)
                    products_in_subcategory.extend(products_on_page)
                    
                    next_button_xpath = "//button[.//span[text()='Siguiente']]"
                    next_button = wait.until(EC.element_to_be_clickable((By.XPATH, next_button_xpath)))
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", next_button)
                    
                    wait.until(lambda d: d.find_element(By.XPATH, first_product_name_xpath).text != initial_product_name)
                    page_num += 1
                except TimeoutException:
                    logger.info(f"    - Fin de la paginación para '{tipo}'. {len(products_in_subcategory)} productos encontrados en esta subcategoría.")
                    break
                except Exception as e:
                    logger.error(f"    - Error inesperado en paginación: {e}", exc_info=True)
                    break
            
            logger.info(f"  -> Guardando {len(products_in_subcategory)} productos de '{tipo}'.")
            append_to_json(products_in_subcategory, output_path, logger)
        except Exception as e:
            logger.error(f"Error CRÍTICO procesando el enlace '{link_info.get('href')}': {e}", exc_info=True)
        finally:
            if driver: driver.quit()
            gc.collect()

    duration = time.time() - start_time
    logger.info("--- FASE 2 Finalizada: Proceso de scraping de productos completado. ---")

    # --- RESUMEN FINAL ---
    try:
        with open(output_path, 'r', encoding='utf-8') as f:
            final_products = json.load(f)
            logger.info(f"Resumen: Total de productos extraídos para Carulla: {len(final_products)}")
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("No se pudo leer el archivo final de productos o está vacío.")

    logger.info(f"Duración total del scraper de Carulla: {duration:.2f} segundos.")
    logger.info("--- SCRAPING PARA CARULLA FINALIZADO ---")

if __name__ == '__main__':
    # Bloque para pruebas directas
    import logging
    test_logger = logging.getLogger('test_carulla')
    test_logger.setLevel(logging.INFO)
    test_logger.addHandler(logging.StreamHandler())
    UA_for_test = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    scrape_carulla(user_agent=UA_for_test, logger=test_logger)
