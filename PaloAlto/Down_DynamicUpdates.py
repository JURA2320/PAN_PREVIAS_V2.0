import requests
import xml.etree.ElementTree as ET
from Utils.logger import get_logger
from config import ALLOWED_UPDATE_TYPES
from PaloAlto.Panorama import api_request_with_target

# Deshabilitar warnings SSL para entornos de laboratorio/pruebas.
requests.packages.urllib3.disable_warnings()

logger = get_logger(__name__)


def download_dynamic_update(
    firewall_ip: str,
    api_key: str,
    update_type: str,
    target_serial: str | None = None
) -> bool:
    """
    Consulta y descarga la última actualización dinámica disponible para un tipo específico.

    Soporta modo directo (target_serial=None) y modo Panorama (target_serial=<serial>).

    1) Valida que el tipo de actualización esté permitido.
    2) Consulta la última versión disponible usando la API XML.
    3) Si hay versión disponible, inicia la descarga.
    4) Registra cada paso en el logger para trazabilidad.
    5) Maneja errores y excepciones de conexión y formato XML.

    Nota: Si el firewall responde que el update no está disponible (status="error"),
    la función registrará el error y devolverá False — **sin** interrumpir el flujo.
    """

    if update_type not in ALLOWED_UPDATE_TYPES:
        logger.error(f"Tipo de actualización no permitido (no está en ALLOWED_UPDATE_TYPES): {update_type}")
        return False

    url = f"https://{firewall_ip}/api/"
    logger.info(f"Verificando actualización para: {update_type}")

    check_params = {
        'type': 'op',
        'cmd': f'<request><{update_type}><upgrade><check/></upgrade></{update_type}></request>',
        'key': api_key,
    }

    root_check = api_request_with_target(firewall_ip, api_key, check_params, target_serial)
    if root_check is None:
        logger.error(f"Fallo al consultar versiones disponibles para {update_type}.")
        return False

    if root_check.attrib.get('status') != 'success':
        msg = (
            root_check.findtext('./msg/line')
            or root_check.findtext('.//line')
            or root_check.findtext('./msg')
            or 'No disponible'
        )
        logger.error(f"Dynamic Update '{update_type}' NO disponible en el firewall: {msg}")
        return False

    versions = root_check.findall('.//entry')
    if not versions:
        logger.warning(f"No hay actualizaciones disponibles para {update_type}")
        return False

    latest_version_node = versions[0].find('version')
    if latest_version_node is None or not latest_version_node.text:
        logger.warning(f"No se pudo obtener versión válida para {update_type}")
        return False

    latest_version = latest_version_node.text.strip()
    logger.info(f"Última versión para {update_type}: {latest_version}")

    download_params = {
        'type': 'op',
        'cmd': f'<request><{update_type}><upgrade><download><latest/></download></upgrade></{update_type}></request>',
        'key': api_key,
    }

    logger.info(f"Descargando actualización {update_type} versión {latest_version}")
    root_download = api_request_with_target(firewall_ip, api_key, download_params, target_serial, timeout=300)

    if root_download is None:
        logger.error(f"Falló la descarga para {update_type}.")
        return False

    if root_download.attrib.get('status') != 'success':
        msg = (
            root_download.findtext('./msg/line')
            or root_download.findtext('.//line')
            or 'Error en descarga'
        )
        logger.error(f"Error al descargar {update_type}: {msg}")
        return False

    logger.info(f"Actualización {update_type} versión {latest_version} descargada correctamente")
    return True
