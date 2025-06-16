# -*- coding: utf-8 -*-

"""
Paso 1: Script para abrir el navegador, navegar a Jumbo.co,
y hacer clic en el botón "Todas las categorías" para desplegar el menú.

Este script utiliza Selenium para la automatización del navegador y
prepara el terreno para usar BeautifulSoup para el análisis del HTML.
"""

import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# --- Configuración ---
URL_TIENDA = "https://www.tiendasjumbo.co"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

# --- Selectores CSS Clave ---
# Selector del botón para abrir el menú principal de categorías
SELECTOR_MENU_PRINCIPAL = "button.tiendasjumboqaio-jumbo-general-apps-2-x-triggerButton--tigger-dropdown-mega-menu"
# Selector para el botón de cierre del modal de ubicación que aparece al inicio
SELECTOR_CIERRE_MODAL_UBICACION = "button.tiendasjumboqaio-delivery-modal-3-x-closeButton"
# Selector para el contenedor del menú (para confirmar que se desplegó)
SELECTOR_CONTENEDOR_MENU = ".tiendasjumboqaio-jumbo-general-apps-2-x-containerMegaMenu--tigger-dropdown-mega-menu"


def configurar_driver_visible(user_agent: str) -> webdriver.Chrome:
    """
    Configura e inicializa una instancia VISIBLE del WebDriver de Chrome.
    El modo visible es para que podamos observar la automatización en acción.
    """
    options = webdriver.ChromeOptions()
    options.add_argument(f"user-agent={user_agent}")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    
    # webdriver-manager se encarga de descargar y gestionar el driver de Chrome.
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def main():
    """Función principal para orquestar la automatización."""
    
    print("🚀 Iniciando el navegador...")
    driver = configurar_driver_visible(USER_AGENT)
    
    try:
        # 1. Navegar a la página de la tienda
        print(f"🧭 Navegando a: {URL_TIENDA}")
        driver.get(URL_TIENDA)
        
        # Instanciamos WebDriverWait para usar esperas explícitas y robustas
        wait = WebDriverWait(driver, 15)

        # 2. Manejar el modal de ubicación que aparece al inicio
        try:
            print("🔎 Buscando el modal de ubicación para cerrarlo...")
            # Esperamos a que el botón de cierre del modal sea clickeable
            close_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELECTOR_CIERRE_MODAL_UBICACION)))
            close_button.click()
            print("✅ Modal de ubicación cerrado exitosamente.")
            time.sleep(1) # Pequeña pausa para estabilizar la página
        except TimeoutException:
            print("👍 No se encontró el modal de ubicación o no fue necesario cerrarlo.")
        
        # 3. Encontrar y hacer clic en el botón "Todas las categorías"
        print("🔎 Buscando el botón 'Todas las categorías'...")
        
        # Esperamos a que el botón del menú sea visible y se pueda hacer clic en él
        menu_trigger = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELECTOR_MENU_PRINCIPAL)))
        
        print("✅ Botón encontrado. Haciendo clic...")
        menu_trigger.click()
        
        # 4. Confirmar que el menú se ha desplegado
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, SELECTOR_CONTENEDOR_MENU)))
        print("\n🎉 ¡Menú desplegado correctamente!")
        
        # En el próximo paso, aquí es donde usaríamos BeautifulSoup:
        # 1. Obtener el código fuente de la página con el menú desplegado.
        # page_source = driver.page_source
        # 2. Crear un objeto BeautifulSoup para analizar el HTML.
        # soup = BeautifulSoup(page_source, 'html.parser')
        # 3. Empezar a buscar y extraer los enlaces de las categorías.
        # print("Código fuente de la página capturado y listo para ser analizado por BeautifulSoup.")

        # 5. Pausa para visualización del usuario
        print("El navegador permanecerá abierto por 20 segundos para que puedas observar el resultado.")
        time.sleep(20)
        
    except Exception as e:
        print(f"❌ Ocurrió un error inesperado durante la ejecución: {e}")
        
    finally:
        # 6. Cerrar el navegador al finalizar
        print("🔚 Cerrando el navegador.")
        driver.quit()

if __name__ == "__main__":
    # Para ejecutar este script, asegúrate de tener las librerías necesarias instaladas:
    # pip install selenium beautifulsoup4 webdriver-manager testeo
    main()