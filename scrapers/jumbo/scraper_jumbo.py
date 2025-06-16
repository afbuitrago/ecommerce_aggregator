import time
import json
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService

def initialize_driver(user_agent, logger):
    """Configura e inicializa una nueva instancia de WebDriver con webdriver-manager."""
    logger.info("Configurando WebDriver...")
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    # options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    if user_agent:
        options.add_argument(f"user-agent={user_agent}")
    
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        logger.info("WebDriver configurado con éxito.")
        return driver
    except Exception as e:
        logger.error(f"Error al configurar WebDriver: {e}", exc_info=True)
        return None

def _parse_product_data(page_source, category_info, logger):
    """Usa BeautifulSoup para parsear el HTML de la página y extraer datos de productos."""
    soup = BeautifulSoup(page_source, 'html.parser')
    products_on_page = []
    product_cards = soup.select("section.vtex-product-summary-2-x-container")

    for card in product_cards:
        try:
            name_element = card.select_one("span.vtex-product-summary-2-x-productBrand")
            full_name = name_element.text.strip() if name_element else "N/A"

            brand_element = card.select_one("span.vtex-product-summary-2-x-productBrandName")
            brand = brand_element.text.strip() if brand_element else "N/A"

            price_element = card.select_one("div.tiendasjumboqaio-jumbo-minicart-2-x-price")
            price_str = price_element.text.strip() if price_element else '0'
            final_price = float(price_str.replace('$', '').replace('.', '').replace(',', ''))
            
            original_price = final_price
            
            discount_percentage = 0
            if original_price > final_price:
                discount_percentage = round(((original_price - final_price) / original_price) * 100)

            product_url_element = card.select_one("a.vtex-product-summary-2-x-clearLink")
            product_url = "https://www.jumbocolombia.com" + product_url_element['href'] if product_url_element else "N/A"

            image_element = card.select_one("img.vtex-product-summary-2-x-imageNormal")
            image_url = image_element['src'] if image_element else "N/A"
            
            product_data = {
                "tienda": "Jumbo",
                "categoria_principal": category_info.get("categoria_principal", "N/A"),
                "sub_categoria": category_info.get("sub_categoria", "N/A"),
                "tipo": category_info.get("item", "N/A"),
                "nombre_completo": full_name,
                "marca": brand,
                "precio_final": final_price,
                "precio_sin_descuento": original_price,
                "porcentaje_descuento": discount_percentage,
                "url_producto": product_url,
                "url_imagen": image_url,
            }
            products_on_page.append(product_data)
        except (AttributeError, ValueError, KeyError, IndexError) as e:
            logger.warning(f"No se pudo procesar una tarjeta de producto. Error: {e}. Saltando.")
            continue
    return products_on_page

def scrape_jumbo(user_agent, logger):
    """Función principal que implementa la arquitectura de 2 fases con paginación y guardado persistente."""
    start_time = time.time()
    logger.info("--- INICIANDO PROCESO DE SCRAPING PARA JUMBO ---")

    output_dir = os.path.join("raw_data", "jumbo")
    os.makedirs(output_dir, exist_ok=True)
    links_filepath = os.path.join(output_dir, "jumbo_links.json")
    products_filepath = os.path.join(output_dir, "jumbo_products.json")
    
    links_to_visit = []
    # --- FASE 1: RECOLECCIÓN DE ENLACES ---
    if not os.path.exists(links_filepath):
        driver = initialize_driver(user_agent, logger)
        if not driver:
            logger.critical("No se pudo inicializar el driver para la Fase 1. Abortando.")
            return

        try:
            logger.info("--- FASE 1: Iniciando recolección de enlaces del menú ---")
            driver.get("https://www.jumbocolombia.com/")
            wait = WebDriverWait(driver, 20)
            actions = ActionChains(driver)
            
            menu_button_xpath = "//button[.//span[text()='Todas las categorías']]"
            menu_button = wait.until(EC.element_to_be_clickable((By.XPATH, menu_button_xpath)))
            driver.execute_script("arguments[0].click();", menu_button)
            
            main_menu_container_selector = "div.tiendasjumboqaio-jumbo-main-menu-2-x-first_level_menu_wrapper"
            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, main_menu_container_selector)))
            
            main_category_items_selector = "li.tiendasjumboqaio-jumbo-main-menu-2-x-menu_item--header-submenu-item"
            num_main_categories = len(driver.find_elements(By.CSS_SELECTOR, main_category_items_selector))

            for i in range(num_main_categories):
                main_categories = driver.find_elements(By.CSS_SELECTOR, main_category_items_selector)
                category_element = main_categories[i]
                try:
                    main_category_name = category_element.find_element(By.TAG_NAME, 'a').text.strip()
                    if not main_category_name: continue
                    actions.move_to_element(category_element).perform()
                    time.sleep(0.5)
                except (NoSuchElementException, StaleElementReferenceException): continue

                submenu_container = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "div.tiendasjumboqaio-jumbo-main-menu-2-x-submenus_wrapper")))
                sub_category_columns = submenu_container.find_elements(By.CSS_SELECTOR, "li.tiendasjumboqaio-jumbo-main-menu-2-x-second_li")

                for column in sub_category_columns:
                    try:
                        sub_category_name = column.find_element(By.CSS_SELECTOR, "a.tiendasjumboqaio-jumbo-main-menu-2-x-second_level_link").text.strip()
                        final_items = column.find_elements(By.CSS_SELECTOR, "a.tiendasjumboqaio-jumbo-main-menu-2-x-item_node_inner_third_level")
                        for item in final_items:
                            link_data = {"categoria_principal": main_category_name, "sub_categoria": sub_category_name, "item": item.text.strip(), "url": item.get_attribute('href')}
                            if link_data["url"] and link_data not in links_to_visit:
                                links_to_visit.append(link_data)
                    except (NoSuchElementException, StaleElementReferenceException): continue
            
            with open(links_filepath, 'w', encoding='utf-8') as f:
                json.dump(links_to_visit, f, indent=4, ensure_ascii=False)
            logger.info(f"--- FASE 1 Finalizada: Se recolectaron y guardaron {len(links_to_visit)} enlaces en '{links_filepath}'. ---")

        finally:
            if driver: driver.quit()
    else:
        logger.info(f"--- FASE 1 Omitida: Usando archivo de enlaces existente en '{links_filepath}'. ---")
        with open(links_filepath, 'r', encoding='utf-8') as f:
            links_to_visit = json.load(f)

    # --- FASE 2: EXTRACCIÓN DE PRODUCTOS ---
    if not links_to_visit:
        logger.warning("No hay enlaces para procesar en la Fase 2.")
        return

    if os.path.exists(products_filepath):
        os.remove(products_filepath)
        logger.info(f"Archivo de productos anterior '{products_filepath}' eliminado.")

    for link_info in links_to_visit:
        driver = initialize_driver(user_agent, logger)
        if not driver: continue
        
        products_from_this_link = []
        try:
            logger.info(f"\nProcesando: {link_info['categoria_principal']} > {link_info['item']} | URL: {link_info['url']}")
            driver.get(link_info['url'])
            wait = WebDriverWait(driver, 20)
            
            gallery_selector = "#gallery-layout-container"
            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, gallery_selector)))
            time.sleep(4)
            
            logger.info("  - Extrayendo productos de la página 1...")
            products_on_page = _parse_product_data(driver.page_source, link_info, logger)
            if products_on_page:
                products_from_this_link.extend(products_on_page)
                logger.info(f"    > Se encontraron {len(products_on_page)} productos.")

            try:
                dropdown_selector = "div.vtex-styleguide-9-x-dropdown select"
                select_element = driver.find_element(By.CSS_SELECTOR, dropdown_selector)
                select = Select(select_element)
                total_pages = len(select.options)

                if total_pages > 1:
                    logger.info(f"  - Se detectaron {total_pages} páginas.")
                    for page_num in range(2, total_pages + 1):
                        logger.info(f"  - Navegando a página {page_num}...")
                        first_product_name_selector = f"{gallery_selector} section:first-child span.vtex-product-summary-2-x-productBrand"
                        anchor_text = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, first_product_name_selector))).text
                        select_element = driver.find_element(By.CSS_SELECTOR, dropdown_selector)
                        Select(select_element).select_by_value(str(page_num))
                        wait.until(lambda d: d.find_element(By.CSS_SELECTOR, first_product_name_selector).text != anchor_text)
                        time.sleep(4)

                        products_on_page = _parse_product_data(driver.page_source, link_info, logger)
                        if products_on_page:
                            products_from_this_link.extend(products_on_page)
                            logger.info(f"    > Se encontraron {len(products_on_page)} productos.")
            
            except (NoSuchElementException, TimeoutException):
                logger.info("  - No se encontró paginador o es de una sola página.")
        
        except Exception as e:
            logger.error(f"Error CRÍTICO procesando la URL {link_info['url']}: {e}", exc_info=True)
        finally:
            if driver: driver.quit()

        if products_from_this_link:
            all_products = []
            if os.path.exists(products_filepath):
                with open(products_filepath, 'r', encoding='utf-8') as f:
                    try:
                        all_products = json.load(f)
                    except json.JSONDecodeError:
                        all_products = []
            
            all_products.extend(products_from_this_link)
            with open(products_filepath, 'w', encoding='utf-8') as f:
                json.dump(all_products, f, indent=4, ensure_ascii=False)
            logger.info(f"  > Guardados {len(products_from_this_link)} productos. Total acumulado: {len(all_products)}.")

    duration = time.time() - start_time
    logger.info(f"--- FASE 2 Finalizada: Proceso de scraping de productos completado. ---")
    
    # --- RESUMEN FINAL ---
    try:
        with open(products_filepath, 'r', encoding='utf-8') as f:
            final_products = json.load(f)
            logger.info(f"Resumen: Total de productos extraídos para Jumbo: {len(final_products)}")
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("No se pudo leer el archivo final de productos o está vacío.")
    
    logger.info(f"Duración total del scraper de Jumbo: {duration:.2f} segundos.")
    logger.info("--- SCRAPING PARA JUMBO FINALIZADO ---")

if __name__ == '__main__':
    # Este bloque es solo para pruebas directas del script
    import logging
    test_logger = logging.getLogger('test_jumbo')
    test_logger.setLevel(logging.INFO)
    test_logger.addHandler(logging.StreamHandler())
    test_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
    scrape_jumbo(user_agent=test_user_agent, logger=test_logger)
