import requests
import xml.etree.ElementTree as ET
from collections import defaultdict
from Utils.logger import get_logger
from PaloAlto.Panorama import api_request_with_target

# Deshabilita advertencias SSL solo para entornos de prueba/laboratorio
requests.packages.urllib3.disable_warnings()

logger = get_logger(__name__)


def safe_findtext(element, tag, default=''):
    """
    Retorna el texto limpio del hijo 'tag' si está presente, o el valor 'default' si no.
    """
    if element is None:
        return default
    text = element.findtext(tag)
    if text is None:
        return default
    return text.strip()


def update_interface_data(data_dict, name, updates):
    """
    Actualiza el diccionario 'data_dict' para la interfaz 'name' con los valores de 'updates'.
    No actualiza si 'name' está vacío ni si los valores son None o vacíos.
    """
    if not name:
        return
    for key, value in updates.items():
        if value:
            data_dict[name][key] = value


def get_firewall_interfaces_data(
    firewall_ip: str,
    api_key: str,
    target_serial: str | None = None
) -> dict:
    """
    Recopila información detallada de interfaces de un firewall Palo Alto Networks.

    Soporta modo directo (target_serial=None) y modo Panorama (target_serial=<serial>).

    Realiza dos llamadas a la API:
    1. Estado operativo de interfaces: nombre, estado, MAC, zona, VR y tipo.
    2. Configuración para obtener perfil de gestión (MGMT Profile).

    Args:
        firewall_ip (str): IP del firewall o Panorama.
        api_key (str): Clave API para autenticación.
        target_serial (str | None): Serial del FW destino si se usa Panorama.

    Returns:
        dict: Diccionario de interfaces. Retorna {} si falla.
    """
    all_interfaces_data = defaultdict(lambda: {
        'name': '',
        'state': '',
        'ip': '',
        'mac': '',
        'zone': '',
        'mgmt_profile': 'N/A',
        'virtual_router': '',
        'interface_type': ''
    })

    try:
        # --- Primera llamada: estado operativo de interfaces ---
        params_op = {
            'type': 'op',
            'cmd': '<show><interface>all</interface></show>',
            'key': api_key,
        }

        logger.info("Inicio llamada API: estado operativo de interfaces")
        root_op = api_request_with_target(firewall_ip, api_key, params_op, target_serial)

        if root_op is None:
            logger.error("No se obtuvo respuesta para estado de interfaces.")
            return {}

        if root_op.attrib.get('status') != 'success':
            logger.error("La respuesta API para estado interfaces no fue exitosa")
            return {}

        # --- Procesar sección <hw>: nombre, estado, MAC ---
        for entry in root_op.findall('.//hw/entry'):
            name = safe_findtext(entry, 'name')
            update_interface_data(all_interfaces_data, name, {
                'name':  name,
                'state': safe_findtext(entry, 'state'),
                'mac':   safe_findtext(entry, 'mac'),
            })

        # --- Procesar sección <ifnet>: zona, IP, VR y tipo de interfaz ---
        for entry in root_op.findall('.//ifnet/entry'):
            name     = safe_findtext(entry, 'name')
            zone     = safe_findtext(entry, 'zone')
            ip       = safe_findtext(entry, 'ip')
            fwd_text = safe_findtext(entry, 'fwd')

            vr = ''
            if fwd_text.startswith('vr:'):
                vr = fwd_text.replace('vr:', '')
            elif fwd_text == 'N/A':
                vr = 'N/A'

            # Determinar tipo de interfaz según nombre e IP
            interface_type = ''
            if 'ethernet' in name.lower() or name.startswith('ae'):
                interface_type = 'Layer3' if ip and ip != 'N/A' else 'Layer2/Physical'
            elif name.startswith('vlan'):
                interface_type = 'VLAN'
            elif name.startswith('loopback'):
                interface_type = 'Loopback'
            elif name.startswith('tunnel'):
                interface_type = 'Tunnel'
            elif name.startswith('sdwan'):
                interface_type = 'SD-WAN/AE'
            else:
                interface_type = 'Otro'

            update_interface_data(all_interfaces_data, name, {
                'name':           name,
                'zone':           zone,
                'ip':             ip if ip and ip != 'N/A' else '',
                'virtual_router': vr,
                'interface_type': interface_type,
            })

        # --- Segunda llamada: configuración para perfiles de gestión (MGMT Profile) ---
        params_config = {
            'type':   'config',
            'action': 'get',
            'xpath':  "/config/devices/entry[@name='localhost.localdomain']/network/interface",
            'key':    api_key,
        }

        logger.info("Inicio llamada API: configuración interfaces para MGMT Profiles")
        root_config = api_request_with_target(firewall_ip, api_key, params_config, target_serial)

        if root_config is None:
            logger.error("No se obtuvo respuesta para configuración de interfaces.")
            return {}

        if root_config.attrib.get('status') != 'success':
            logger.error("Respuesta API para configuración interfaces no fue exitosa")
        else:
            for entry in root_config.findall('.//interface//entry'):
                name = entry.attrib.get('name', '').strip()
                if not name:
                    continue
                mgmt_profile_node = entry.find('.//interface-management-profile')
                if mgmt_profile_node is not None and mgmt_profile_node.text:
                    if name in all_interfaces_data:
                        all_interfaces_data[name]['mgmt_profile'] = mgmt_profile_node.text.strip()

        logger.info(f"Recopiladas {len(all_interfaces_data)} interfaces")
        return all_interfaces_data

    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión con el firewall: {e}")
        return {}
    except ET.ParseError as e:
        logger.error(f"Error al analizar XML de la API: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error inesperado en la recopilación de datos: {e}")
        return {}
