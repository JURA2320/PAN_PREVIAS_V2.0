import requests
import xml.etree.ElementTree as ET
from Utils.logger import get_logger
from PaloAlto.Panorama import api_request_with_target

# Deshabilita advertencias SSL solo para entornos de prueba/laboratorio
requests.packages.urllib3.disable_warnings()

logger = get_logger(__name__)


def get_firewall_HighAviability_data(
    firewall_ip: str,
    api_key: str,
    target_serial: str | None = None
) -> dict:
    """
    Obtiene el estado de High Availability (HA) de un firewall Palo Alto.

    Soporta modo directo (target_serial=None) y modo Panorama (target_serial=<serial>).

    Args:
        firewall_ip (str): IP del firewall o Panorama.
        api_key (str): Clave API para autenticación.
        target_serial (str | None): Serial del FW destino si se usa Panorama.

    Returns:
        dict: local_mode, local_state, peer_ip, peer_state.
              Devuelve diccionario vacío si ocurre algún error.
    """
    params = {
        'type': 'op',
        'cmd': '<show><high-availability><state/></high-availability></show>',
        'key': api_key,
    }

    try:
        logger.info("Solicitando estado de High Availability (HA)")
        root = api_request_with_target(firewall_ip, api_key, params, target_serial)

        if root is None:
            logger.error("No se obtuvo respuesta para estado HA.")
            return {}

        if root.attrib.get('status') != 'success':
            logger.error("Error en respuesta API al obtener información de HA")
            return {}

        ha_info = {
            'local_mode':  root.findtext('.//local-info/mode',  'N/A'),
            'local_state': root.findtext('.//local-info/state', 'N/A'),
            'peer_ip':     root.findtext('.//peer-info/ip',     'N/A'),
            'peer_state':  root.findtext('.//peer-info/state',  'N/A'),
        }

        logger.info(f"Información de HA obtenida: {ha_info}")
        return ha_info

    except Exception as e:
        logger.error(f"Error inesperado obteniendo HA: {e}")
        return {}
