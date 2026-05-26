import os
import requests
import xml.etree.ElementTree as ET
from Utils.logger import get_logger
from PaloAlto.Panorama import api_request_with_target

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DEFAULT_BACKUP_FOLDER = os.path.join(BASE_DIR, "Carpeta de Actividades previas")

# Deshabilitar warnings SSL para entornos de laboratorio/pruebas
requests.packages.urllib3.disable_warnings()

logger = get_logger(__name__)


def download_running_config(
    firewall_ip: str,
    api_key: str,
    backup_folder: str = DEFAULT_BACKUP_FOLDER,
    target_serial: str | None = None
) -> bool:
    """
    Descarga el archivo running-config.xml desde el firewall Palo Alto.

    Soporta modo directo (target_serial=None) y modo Panorama (target_serial=<serial>).

    Args:
        firewall_ip (str): IP del firewall o Panorama.
        api_key (str): Clave API del firewall.
        backup_folder (str): Carpeta donde se guardará el archivo.
        target_serial (str | None): Serial del FW destino si se usa Panorama.

    Returns:
        bool: True si se descargó correctamente, False en caso de error.
    """
    logger.info("Iniciando descarga de running-config.xml")

    params_config = {
        'type':     'export',
        'category': 'configuration',
        'key':      api_key,
    }

    if not os.path.exists(backup_folder):
        os.makedirs(backup_folder)

    try:
        root = api_request_with_target(firewall_ip, api_key, params_config, target_serial, timeout=60)

        # Para exports la respuesta es XML directo (contenido), no status/success
        # Hacemos la request manual para obtener el contenido binario
        url = f"https://{firewall_ip}/api/"
        if target_serial:
            params_config['target'] = target_serial

        response = requests.get(url, params=params_config, verify=False, timeout=60)

        if response.status_code == 200:
            # Usar el hostname o serial en el nombre del archivo si viene de Panorama
            suffix = target_serial if target_serial else firewall_ip
            filepath = os.path.join(backup_folder, f'running-config_{suffix}.xml')
            with open(filepath, 'wb') as f:
                f.write(response.content)
            logger.info(f"running-config.xml guardado en {filepath}")
            return True
        else:
            logger.error(f"Fallo descarga running-config.xml. HTTP {response.status_code}")
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión al descargar running-config.xml: {e}")
        return False
    except Exception as e:
        logger.error(f"Error inesperado al guardar running-config.xml: {e}")
        return False


def download_device_state(
    firewall_ip: str,
    api_key: str,
    backup_folder: str = DEFAULT_BACKUP_FOLDER,
    target_serial: str | None = None
) -> bool:
    """
    Descarga el archivo device-state.tgz desde el firewall Palo Alto.

    Soporta modo directo (target_serial=None) y modo Panorama (target_serial=<serial>).

    Args:
        firewall_ip (str): IP del firewall o Panorama.
        api_key (str): Clave API del firewall.
        backup_folder (str): Carpeta donde se guardará el archivo.
        target_serial (str | None): Serial del FW destino si se usa Panorama.

    Returns:
        bool: True si se descargó correctamente, False en caso de error.
    """
    logger.info("Generando respaldo device-state en firewall")

    if not os.path.exists(backup_folder):
        os.makedirs(backup_folder)

    try:
        url = f"https://{firewall_ip}/api/"
        params_download = {
            'type':     'export',
            'category': 'device-state',
            'key':      api_key,
        }
        if target_serial:
            params_download['target'] = target_serial

        response = requests.get(url, params=params_download, verify=False, timeout=600)

        if response.status_code == 200:
            suffix   = target_serial if target_serial else firewall_ip
            filepath = os.path.join(backup_folder, f'device-state_{suffix}.tgz')
            with open(filepath, 'wb') as f:
                f.write(response.content)
            logger.info(f"device-state.tgz guardado en {filepath}")
            return True
        else:
            logger.error(f"Fallo descarga device-state.tgz. HTTP {response.status_code}")
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión durante descarga device-state: {e}")
        return False
    except Exception as e:
        logger.error(f"Error inesperado durante descarga device-state: {e}")
        return False
