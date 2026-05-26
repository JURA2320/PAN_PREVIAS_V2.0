import re
import requests
import xml.etree.ElementTree as ET
from Utils.logger import get_logger
from PaloAlto.Panorama import api_request_with_target

requests.packages.urllib3.disable_warnings()
logger = get_logger(__name__)


# ----------------------------------------------------------------
# Helpers de parseo de versión
# ----------------------------------------------------------------
def parse_version(version_str: str) -> tuple[int, int, int]:
    """
    Extrae (major, minor, patch) de un string de versión PAN-OS.
    '10.2.8-h3' → (10, 2, 8) | '11.1.0' → (11, 1, 0)
    Retorna (0, 0, 0) si no se puede parsear.
    """
    match = re.match(r'(\d+)\.(\d+)\.(\d+)', version_str.strip())
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    logger.warning(f"No se pudo parsear la versión: '{version_str}'")
    return (0, 0, 0)


def needs_base_image(current_version: str, target_version: str) -> tuple[bool, str | None]:
    """
    Determina si se necesita imagen base antes de la versión destino.
    Retorna (True, 'X.Y.0') si aplica, (False, None) si no.
    """
    cur_major, cur_minor, _          = parse_version(current_version)
    tgt_major, tgt_minor, tgt_patch  = parse_version(target_version)

    if tgt_patch == 0:
        return False, None  # Ya es una base

    if (tgt_major, tgt_minor) != (cur_major, cur_minor):
        return True, f"{tgt_major}.{tgt_minor}.0"

    return False, None


# ----------------------------------------------------------------
# Descarga de una versión concreta (interna)
# ----------------------------------------------------------------
def _get_job_id(root: ET.Element) -> str | None:
    """Extrae el job ID de una respuesta de descarga."""
    job_id = root.findtext('.//job')
    if job_id:
        return job_id.strip()
    return None


def _poll_job_until_done(
    firewall_ip: str,
    api_key: str,
    job_id: str,
    target_serial: str | None = None,
    poll_interval: int = 30,
    timeout_minutes: int = 60,
    log_callback=None,
) -> bool:
    """
    Hace polling del estado de un job hasta que termine (FIN) o falle.

    Args:
        poll_interval  (int): Segundos entre cada consulta.
        timeout_minutes(int): Tiempo máximo de espera total.
        log_callback   (callable|None): Función para loguear progreso en la GUI.

    Returns:
        bool: True si el job terminó exitosamente, False si falló o timeout.
    """
    import time

    def log(msg):
        logger.info(msg)
        if log_callback:
            log_callback(msg)

    max_polls = (timeout_minutes * 60) // poll_interval
    params = {
        'type': 'op',
        'cmd':  f'<show><jobs><id>{job_id}</id></jobs></show>',
        'key':  api_key,
    }

    log(f"Esperando descarga (job {job_id})...")

    for attempt in range(max_polls):
        time.sleep(poll_interval)
        root = api_request_with_target(firewall_ip, api_key, params, target_serial, timeout=15)

        if root is None:
            log(f"No se pudo consultar el estado del job {job_id}. Reintentando...")
            continue

        status   = root.findtext('.//status',   '').strip().upper()
        result   = root.findtext('.//result',   '').strip().upper()
        progress = root.findtext('.//progress', '').strip()

        if progress:
            log(f"Descarga en progreso: {progress}%")

        if status == 'FIN' or status == 'FINISH':
            if result in ('OK', 'SUCCESS', ''):
                log(f"✔ Descarga completada (job {job_id}).")
                return True
            else:
                log(f"✖ Job {job_id} terminó con error: {result}")
                return False

        if status in ('FAIL', 'ERROR'):
            log(f"✖ Job {job_id} falló: {result}")
            return False

    log(f"⚠️  Timeout esperando job {job_id} después de {timeout_minutes} minutos.")
    return False


def _download_single_version(
    firewall_ip: str,
    api_key: str,
    version: str,
    target_serial: str | None = None,
    log_callback=None,
) -> bool:
    """
    Refresca catálogo, inicia descarga y espera a que termine via polling.
    Retorna True solo cuando la descarga está completamente finalizada.
    """
    def log(msg):
        logger.info(msg)
        if log_callback:
            log_callback(msg)

    log(f"Refrescando catálogo de versiones...")
    check_params = {
        'type': 'op',
        'cmd':  '<request><system><software><check></check></software></system></request>',
        'key':  api_key,
    }
    api_request_with_target(firewall_ip, api_key, check_params, target_serial, timeout=60)

    log(f"Iniciando descarga de PAN-OS {version}...")
    download_params = {
        'type': 'op',
        'cmd': (
            f'<request><system><software>'
            f'<download><version>{version}</version></download>'
            f'</software></system></request>'
        ),
        'key': api_key,
    }
    root = api_request_with_target(firewall_ip, api_key, download_params, target_serial, timeout=60)

    if root is None:
        log(f"✖ Sin respuesta al iniciar descarga de {version}.")
        return False

    if root.attrib.get('status') != 'success':
        log(f"✖ Error al iniciar descarga de {version}.")
        return False

    job_id = _get_job_id(root)
    if not job_id:
        # Algunos firmwares no retornan job_id — asumir éxito
        log(f"✔ Descarga de {version} iniciada (sin job_id, no se puede hacer polling).")
        return True

    # Polling hasta que termine
    return _poll_job_until_done(
        firewall_ip, api_key, job_id, target_serial,
        poll_interval=30, log_callback=log_callback
    )


def get_downloaded_versions(
    firewall_ip: str,
    api_key: str,
    target_serial: str | None = None,
) -> list[str]:
    """
    Consulta la lista de versiones PAN-OS ya descargadas en el firewall.
    Retorna lista de strings de versión, ej: ['11.1.0', '10.2.7-h3'].
    """
    params = {
        'type': 'op',
        'cmd':  '<request><system><software><info></info></software></system></request>',
        'key':  api_key,
    }
    root = api_request_with_target(firewall_ip, api_key, params, target_serial, timeout=30)
    if root is None or root.attrib.get('status') != 'success':
        logger.warning("No se pudo obtener lista de versiones descargadas.")
        return []

    versions = []
    for entry in root.findall('.//versions/entry'):
        ver       = entry.findtext('version', '').strip()
        downloaded = entry.findtext('downloaded', 'no').strip().lower()
        if ver and downloaded == 'yes':
            versions.append(ver)

    logger.info(f"Versiones ya descargadas en el equipo: {versions}")
    return versions


# ----------------------------------------------------------------
# Función principal
# ----------------------------------------------------------------
def download_panos_version(
    firewall_ip: str,
    api_key: str,
    version_to_download: str,
    current_version: str,
    target_serial: str | None = None,
    log_callback=None,
) -> dict:
    """
    Descarga la versión PAN-OS solicitada con la siguiente lógica:

    1. Sin salto de major.minor → descarga directo la versión destino.
    2. Con salto de major.minor:
       a. Base YA descargada → descarga directo la versión destino.
       b. Base NO descargada → descarga base, polling cada 30s hasta que
          termine, luego descarga automáticamente la versión final.
          Todo en una sola ejecución sin intervención del usuario.

    Args:
        log_callback (callable|None): fn(msg) para mostrar progreso en la GUI.

    Returns:
        dict:
          'success'         (bool)
          'base_downloaded' (bool) → True si se tuvo que descargar la base
          'base_version'    (str|None)
    """
    def log(msg):
        logger.info(msg)
        if log_callback:
            log_callback(msg)

    required, base_version = needs_base_image(current_version, version_to_download)

    if required and base_version:
        log(f"Salto de versión detectado: {current_version} → {version_to_download}.")
        log(f"Verificando si la base {base_version} ya está descargada...")
        downloaded = get_downloaded_versions(firewall_ip, api_key, target_serial)

        base_major, base_minor, _ = parse_version(base_version)
        base_already_present = any(
            (parse_version(v)[0], parse_version(v)[1]) == (base_major, base_minor)
            and parse_version(v)[2] == 0
            for v in downloaded
        )

        if base_already_present:
            log(f"✔ Base {base_version} ya descargada. Descargando {version_to_download}...")
            ok = _download_single_version(
                firewall_ip, api_key, version_to_download, target_serial, log_callback=log)
            return {'success': ok, 'base_downloaded': False, 'base_version': None}

        # Base no descargada → descargar base, esperar, luego descargar final
        log(f"Base {base_version} no encontrada. Paso 1/2: descargando base...")
        ok_base = _download_single_version(
            firewall_ip, api_key, base_version, target_serial, log_callback=log)

        if not ok_base:
            log(f"✖ Falló la descarga de {base_version}. Se cancela {version_to_download}.")
            return {'success': False, 'base_downloaded': True, 'base_version': base_version}

        log(f"✔ Base {base_version} lista. Paso 2/2: descargando {version_to_download}...")
        ok_final = _download_single_version(
            firewall_ip, api_key, version_to_download, target_serial, log_callback=log)
        return {'success': ok_final, 'base_downloaded': True, 'base_version': base_version}

    # Sin salto → descarga directa
    log(f"No se requiere imagen base. Descargando {version_to_download}...")
    ok = _download_single_version(
        firewall_ip, api_key, version_to_download, target_serial, log_callback=log)
    return {'success': ok, 'base_downloaded': False, 'base_version': None}

