import requests
import xml.etree.ElementTree as ET
from Utils.logger import get_logger
from PaloAlto.Panorama import api_request_with_target

# Deshabilita advertencias SSL solo para entornos de prueba/laboratorio
requests.packages.urllib3.disable_warnings()

logger = get_logger(__name__)


def get_firewall_dashboard_data(
    firewall_ip: str,
    api_key: str,
    target_serial: str | None = None
) -> dict:
    """
    Recopila información del dashboard (show system info) de un firewall Palo Alto Networks.

    Soporta modo directo (target_serial=None) y modo Panorama (target_serial=<serial>).

    Args:
        firewall_ip (str): IP del firewall o Panorama.
        api_key (str): Clave API para autenticación.
        target_serial (str | None): Serial del FW destino si se usa Panorama.

    Returns:
        dict: Diccionario con hostname, model, serial, version, uptime, mgmt_ip.
              Retorna diccionario vacío si ocurre algún error.
    """
    params = {
        'type': 'op',
        'cmd': '<show><system><info/></system></show>',
        'key': api_key,
    }

    try:
        logger.info("Realizando llamada API para obtener información del sistema/dashboard")
        root = api_request_with_target(firewall_ip, api_key, params, target_serial)

        if root is None:
            logger.error("No se obtuvo respuesta del firewall para el dashboard.")
            return {}

        if root.attrib.get('status') != 'success':
            logger.error("Error en la respuesta API para 'show system info'.")
            return {}

        dashboard_info = {
            'hostname': root.findtext('.//hostname', 'N/A'),
            'model':    root.findtext('.//model',     'N/A'),
            'serial':   root.findtext('.//serial',    'N/A'),
            'version':  root.findtext('.//sw-version','N/A'),
            'uptime':   root.findtext('.//uptime',    'N/A'),
            'mgmt_ip':  root.findtext('.//ip-address','N/A'),
        }

        logger.info("Información del dashboard obtenida correctamente")
        logger.debug(f"Dashboard info: {dashboard_info}")
        return dashboard_info

    except Exception as e:
        logger.error(f"Error inesperado al obtener datos del dashboard: {e}")
        return {}
