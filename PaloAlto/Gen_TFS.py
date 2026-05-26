import requests
import xml.etree.ElementTree as ET
from Utils.logger import get_logger
from PaloAlto.Panorama import api_request_with_target

# Deshabilitar warnings SSL solo para entornos de prueba/laboratorio
requests.packages.urllib3.disable_warnings()

logger = get_logger(__name__)


def generate_tech_support_file(
    firewall_ip: str,
    api_key: str,
    target_serial: str | None = None
) -> bool:
    """
    Solicita al firewall Palo Alto la generación de un archivo Tech Support File (TFS).

    Soporta modo directo (target_serial=None) y modo Panorama (target_serial=<serial>).

    Nota: Este comando solo inicia la generación. La descarga del archivo debe realizarse
    posteriormente desde la GUI o con una llamada API adicional si está disponible.

    Args:
        firewall_ip (str): IP del firewall o Panorama.
        api_key (str): Clave API para autenticación.
        target_serial (str | None): Serial del FW destino si se usa Panorama.

    Returns:
        bool: True si la solicitud de generación fue exitosa, False en caso contrario.
    """
    params = {
        'type': 'op',
        'cmd':  '<request><tech-support><dump></dump></tech-support></request>',
        'key':  api_key,
    }

    logger.info("Solicitando generación del archivo TFS (Tech Support File)")

    try:
        root = api_request_with_target(firewall_ip, api_key, params, target_serial, timeout=600)

        if root is None:
            logger.error("No se obtuvo respuesta al solicitar TFS.")
            return False

        if root.get('status') == 'success':
            logger.info("Archivo TFS en proceso de generación en el firewall.")
            return True

        logger.error("La solicitud de generación de TFS no fue exitosa.")
        return False

    except Exception as e:
        logger.error(f"Error inesperado al solicitar generación de TFS: {e}")
        return False
