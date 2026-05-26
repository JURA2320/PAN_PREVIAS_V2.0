import requests
import xml.etree.ElementTree as ET
from Utils.logger import get_logger

# Deshabilitar warnings SSL para entornos de laboratorio/pruebas
requests.packages.urllib3.disable_warnings()

logger = get_logger(__name__)

# ----------------------------------------------------------------
# Constantes
# ----------------------------------------------------------------
# Modelos que corresponden a Panorama:
# - Appliance virtual  → model = 'panorama'
# - Appliances físicos → model = 'M-100', 'M-200', 'M-500', 'M-600', 'M-700'
PANORAMA_MODELS = {
    'panorama',
    'm-100',
    'm-200',
    'm-500',
    'm-600',
    'm-700',
}


# ----------------------------------------------------------------
# Función base de request (compartida por todos los helpers)
# ----------------------------------------------------------------
def _api_request(ip: str, api_key: str, params: dict, timeout: int = 15) -> ET.Element | None:
    """
    Realiza una llamada GET a la API XML de Palo Alto / Panorama.
    Retorna el elemento XML raíz o None si falla.
    """
    url = f"https://{ip}/api/"
    try:
        response = requests.get(url, params=params, verify=False, timeout=timeout)
        if response.status_code != 200:
            logger.error(f"HTTP {response.status_code} en {url}: {response.text[:300]}")
            return None
        return ET.fromstring(response.text)
    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión a {ip}: {e}")
    except ET.ParseError as e:
        logger.error(f"Error parseando XML de {ip}: {e}")
    except Exception as e:
        logger.error(f"Error inesperado en request a {ip}: {e}")
    return None


# ----------------------------------------------------------------
# Detección automática de tipo de dispositivo
# ----------------------------------------------------------------
def detect_device_type(ip: str, api_key: str) -> str:
    """
    Detecta si la IP corresponde a un Panorama o a un Firewall directo.

    Consulta 'show system info' y evalúa el campo <model>.
    Modelos Panorama reconocidos: VM (Panorama), M-100, M-200, M-500, M-600, M-700.
    En cualquier otro caso → retorna 'firewall'.

    Args:
        ip (str): IP del dispositivo.
        api_key (str): Clave API.

    Returns:
        str: 'panorama' o 'firewall'
    """
    params = {
        'type': 'op',
        'cmd': '<show><system><info/></system></show>',
        'key': api_key,
    }

    logger.info(f"Detectando tipo de dispositivo en {ip}...")
    root = _api_request(ip, api_key, params)

    if root is None:
        logger.warning(f"No se pudo detectar el tipo de dispositivo en {ip}. Se asumirá 'firewall'.")
        return 'firewall'

    model = root.findtext('.//model', default='').strip().lower()
    logger.info(f"Modelo detectado: '{model}'")

    if model in PANORAMA_MODELS:
        logger.info(f"{ip} identificado como PANORAMA (modelo: {model}).")
        return 'panorama'

    logger.info(f"{ip} identificado como FIREWALL directo (modelo: {model}).")
    return 'firewall'


# ----------------------------------------------------------------
# Listado de firewalls gestionados por Panorama
# ----------------------------------------------------------------
def get_managed_firewalls(panorama_ip: str, api_key: str) -> list[dict]:
    """
    Obtiene la lista de firewalls gestionados por Panorama.

    Retorna solo los dispositivos con serial válido, incluyendo:
      - hostname
      - serial
      - sw_version (versión PAN-OS)
      - connected (estado de conexión: 'yes' / 'no')

    Args:
        panorama_ip (str): IP del Panorama.
        api_key (str): Clave API.

    Returns:
        list[dict]: Lista de firewalls. Vacía si hay error.
    """
    params = {
        'type': 'op',
        'cmd': '<show><devices><all></all></devices></show>',
        'key': api_key,
    }

    logger.info(f"Obteniendo firewalls gestionados desde Panorama {panorama_ip}...")
    root = _api_request(panorama_ip, api_key, params)

    if root is None or root.attrib.get('status') != 'success':
        logger.error("No se pudo obtener la lista de dispositivos desde Panorama.")
        return []

    firewalls = []
    for entry in root.findall('.//devices/entry'):
        hostname = entry.findtext('hostname') or entry.get('name', 'N/A')
        serial   = entry.findtext('serial', '').strip()
        version  = entry.findtext('sw-version', 'N/A')
        connected = entry.findtext('connected', 'no')

        # Solo incluir dispositivos con serial válido
        if not serial:
            continue

        firewalls.append({
            'hostname':  hostname,
            'serial':    serial,
            'sw_version': version,
            'connected': connected,
        })

    logger.info(f"Firewalls encontrados en Panorama: {len(firewalls)}")
    return firewalls


# ----------------------------------------------------------------
# Wrapper de API con soporte Panorama (target=serial)
# ----------------------------------------------------------------
def api_request_with_target(
    ip: str,
    api_key: str,
    params: dict,
    target_serial: str | None = None,
    timeout: int = 15
) -> ET.Element | None:
    """
    Extiende _api_request añadiendo el parámetro 'target' cuando se
    proporciona un serial (modo Panorama).

    Si target_serial es None → llamada directa al firewall (modo actual).
    Si target_serial tiene valor → Panorama redirige el comando al FW.

    Args:
        ip (str): IP del Panorama o del Firewall.
        api_key (str): Clave API.
        params (dict): Parámetros de la llamada API.
        target_serial (str | None): Serial del firewall destino (solo en modo Panorama).
        timeout (int): Timeout en segundos.

    Returns:
        ET.Element | None: XML raíz de la respuesta o None si falla.
    """
    if target_serial:
        params = {**params, 'target': target_serial}
        logger.debug(f"Modo Panorama: redirigiendo comando a serial '{target_serial}'")

    return _api_request(ip, api_key, params, timeout=timeout)
