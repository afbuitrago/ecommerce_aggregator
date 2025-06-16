import json
import logging
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

# 1. Configuración de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_driver(user_agent):
    """Configura e inicializa el WebDriver de Selenium."""
    logging.info(f"Configurando driver con User-Agent: {user_agent}")
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

def extract_product_data(soup, main_category_name, sub_category, tipo):
    """Extrae los datos de los productos de la página con la estructura de datos corregida."""
    productos_en_pagina = []
    product_containers = soup.select('article.productCard_productCard__M0677')
    
    for item in product_containers:
        try:
            name_tag = item.select_one('h3.styles_name__qQJiK')
            name = name_tag.get_text(strip=True) if name_tag else "N/A"
            
            # Heurística mejorada para la marca: tomar la segunda palabra del nombre.
            name_parts = name.split()
            brand = name_parts[1] if len(name_parts) > 1 else name_parts[0]

            link_tag = item.select_one('a[data-testid="product-link"]')
            url_producto = f"https://www.carulla.com{link_tag['href']}" if link_tag and link_tag.get('href') else None

            image_tag = item.select_one('img')
            url_imagen = image_tag.get('src') if image_tag else None

            price_sell_tag = item.select_one('p.ProductPrice_container__price__XmMWA')
            price_list_tag = item.select_one('p.priceSection_container-promotion_price-dashed__FJ7nI')

            precio_final_str = price_sell_tag.get_text(strip=True) if price_sell_tag else '0'
            precio_final = float(precio_final_str.replace('$', '').replace('.', '').replace(',', ''))
            
            precio_sin_descuento = precio_final
            if price_list_tag:
                precio_sin_descuento_str = price_list_tag.get_text(strip=True)
                precio_sin_descuento = float(precio_sin_descuento_str.replace('$', '').replace('.', '').replace(',', ''))
            
            descuento_porcentaje = None
            if precio_sin_descuento > precio_final:
                descuento_porcentaje = round(((precio_sin_descuento - precio_final) / precio_sin_descuento) * 100)

            # FIX: Estructura del JSON corregida
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
        except (AttributeError, ValueError, TypeError) as e:
            logging.warning(f"Se omitió un producto por datos incompletos o error de parsing. Error: {e}")
            continue
    return productos_en_pagina

def append_to_json(new_data, filepath):
    """Añade datos a un archivo JSON de forma segura."""
    if not new_data: return
    existing_data = []
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            try: existing_data = json.load(f)
            except json.JSONDecodeError: logging.warning(f"Archivo JSON {filepath} corrupto. Se sobreescribirá.")
    existing_data.extend(new_data)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, indent=4, ensure_ascii=False)

def scrape_carulla(user_agent):
    """Flujo principal de scraping para Carulla.com."""
    logging.info("Iniciando scraper para Carulla.com")
    
    FAST_TIMEOUT = 10
    PAGE_LOAD_TIMEOUT = 15

    output_dir = 'raw_data/carulla'
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'productos_carulla.json')
    if os.path.exists(output_path):
        os.remove(output_path)

    driver = setup_driver(user_agent)
    
    try:
        # --- FASE 1: NAVEGACIÓN Y RECOLECCIÓN ITERATIVA ---
        
        driver.get("https://www.carulla.com/")
        
        try:
            cookie_button = WebDriverWait(driver, FAST_TIMEOUT).until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            cookie_button.click()
            logging.info("Banner de cookies aceptado.")
            time.sleep(2)
        except TimeoutException:
            logging.warning("No se encontró o no se pudo hacer clic en el banner de cookies.")

        logging.info("Abriendo menú principal.")
        menu_button_selector = "div[data-fs-menu-icon-container='true']"
        WebDriverWait(driver, FAST_TIMEOUT).until(EC.element_to_be_clickable((By.CSS_SELECTOR, menu_button_selector))).click()
        
        main_categories_xpath = "//section[./header[text()='Categorías']]//li[contains(@class, 'Link_link-container')]"
        main_categories_elements = WebDriverWait(driver, FAST_TIMEOUT).until(EC.presence_of_all_elements_located((By.XPATH, main_categories_xpath)))
        num_main_categories = len(main_categories_elements)
        logging.info(f"Se encontraron {num_main_categories} categorías principales para procesar.")

        for i in range(num_main_categories):
            main_categories = WebDriverWait(driver, FAST_TIMEOUT).until(EC.presence_of_all_elements_located((By.XPATH, main_categories_xpath)))
            category_to_click = main_categories[i]
            main_category_name = category_to_click.text.split('\n')[0].strip()
            
            if not main_category_name: continue
            
            logging.info(f"\n--- Procesando Categoría Principal: '{main_category_name}' ---")
            
            category_to_click.click()

            submenu_container_selector = "ul[data-content-list='true']"
            WebDriverWait(driver, FAST_TIMEOUT).until(EC.visibility_of_element_located((By.CSS_SELECTOR, submenu_container_selector)))
            
            sub_category_links_data = []
            submenu_groups = driver.find_elements(By.CSS_SELECTOR, "li.SubMenu_subsection-item__sPPCM")
            
            for group in submenu_groups:
                try:
                    sub_group_title_element = group.find_element(By.CSS_SELECTOR, "div[data-title-section-item='true'] a b")
                    sub_group_title = sub_group_title_element.text
                    
                    sub_category_links = group.find_elements(By.CSS_SELECTOR, "ul[data-list-sections='true'] li[data-link='true'] a")
                    for link in sub_category_links:
                        sub_cat_name = link.text.strip()
                        sub_cat_href = link.get_attribute('href')
                        if sub_cat_name and sub_cat_href:
                            # FIX: Estructura de datos para pasar la información correcta
                            sub_category_links_data.append({
                                'main_category': main_category_name,
                                'sub_category': sub_group_title, # El grupo es la subcategoría
                                'tipo': sub_cat_name,          # El enlace final es el tipo
                                'href': sub_cat_href
                            })
                except Exception as e:
                    logging.warning(f"No se pudo procesar un grupo de subcategoría. Error: {e}")
                    continue
            
            logging.info(f"Se recolectaron {len(sub_category_links_data)} items en '{main_category_name}'.")

            # --- CICLO INTERNO: Scrapear cada subcategoría recolectada ---
            for link_info in sub_category_links_data:
                # FIX: Desempaquetar la nueva estructura de datos
                main_cat = link_info['main_category']
                sub_cat = link_info['sub_category']
                tipo = link_info['tipo']
                sub_cat_href = link_info['href']
                
                logging.info(f"  -> Scrapeando: {sub_cat} -> {tipo}")
                driver.get(sub_cat_href)
                
                products_in_subcategory = [] 
                page_num = 1
                while True:
                    try:
                        logging.info(f"    - Extrayendo productos de la página {page_num}...")
                        wait = WebDriverWait(driver, PAGE_LOAD_TIMEOUT)
                        
                        gallery_xpath = "//div[contains(@class, 'product-grid_fs-product-grid')]"
                        wait.until(EC.presence_of_element_located((By.XPATH, gallery_xpath)))
                        
                        first_product_name_xpath = f"({gallery_xpath}//h3[contains(@class, 'styles_name')])[1]"
                        first_product_element = wait.until(EC.presence_of_element_located((By.XPATH, first_product_name_xpath)))
                        initial_product_name = first_product_element.text
                        
                        time.sleep(2) 
                        
                        soup = BeautifulSoup(driver.page_source, 'html.parser')
                        # FIX: Pasar los argumentos correctos a la función de extracción
                        products_on_page = extract_product_data(soup, main_cat, sub_cat, tipo)
                        products_in_subcategory.extend(products_on_page)
                        logging.info(f"    - Se encontraron {len(products_on_page)} productos.")

                        next_button_xpath = "//button[.//span[text()='Siguiente']]"
                        next_button = wait.until(EC.element_to_be_clickable((By.XPATH, next_button_xpath)))
                        
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", next_button)
                        
                        logging.info("    - Esperando que el contenido de la página cambie...")
                        wait.until(
                            lambda d: d.find_element(By.XPATH, first_product_name_xpath).text != initial_product_name
                        )
                        logging.info("    - Contenido de la página actualizado.")
                        page_num += 1

                    except TimeoutException:
                        logging.info(f"    - Fin de la paginación para '{tipo}'.")
                        break
                    except Exception as e:
                        logging.error(f"    - Error inesperado en paginación: {e}", exc_info=True)
                        break
                
                logging.info(f"  -> Guardando {len(products_in_subcategory)} productos de '{tipo}'.")
                append_to_json(products_in_subcategory, output_path)
                gc.collect()

            # Después de scrapear TODAS las subcategorías, volver al menú principal
            driver.get("https://www.carulla.com/")
            WebDriverWait(driver, FAST_TIMEOUT).until(EC.element_to_be_clickable((By.CSS_SELECTOR, menu_button_selector))).click()
            logging.info(f"--- Fin de '{main_category_name}'. Volviendo al menú principal. ---")

    except Exception as e:
        logging.error(f"Ocurrió un error CRÍTICO en el scraper: {e}", exc_info=True)
    finally:
        if driver: driver.quit()
        logging.info(f"Scraping de Carulla finalizado.")

if __name__ == '__main__':
    UA_for_test = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    scrape_carulla(user_agent=UA_for_test)