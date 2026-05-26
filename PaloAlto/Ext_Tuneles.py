import requests
import xml.etree.ElementTree as ET
from Utils.logger import get_logger
from PaloAlto.Panorama import api_request_with_target

logger = get_logger(__name__)

# --------------------------------
# Constantes
# --------------------------------
STATE_ACTIVE = "active"
STATUS_UP    = "UP"
STATUS_DOWN  = "DOWN"
NA           = "N/A"

TAG_ENTRY        = "entry"
TAG_NAME         = "name"
TAG_STATE        = "state"
TAG_PEER_ADDRESS = "peer-address"
TAG_LIFE_TIME    = "life-time"
TAG_LIFE_BYTES   = "life-bytes"


# --------------------------------
# Configuración de túneles
# --------------------------------
def get_vpn_config(
    firewall_ip: str,
    api_key: str,
    target_serial: str | None = None
) -> list:
    """Obtiene la configuración de túneles IPsec."""
    params = {
        'type':   'config',
        'action': 'get',
        'xpath':  "/config/devices/entry[@name='localhost.localdomain']/network/tunnel",
        'key':    api_key,
    }
    root = api_request_with_target(firewall_ip, api_key, params, target_serial)
    tunnels = []

    if root is None or root.attrib.get('status') != 'success':
        logger.error("Error al obtener configuración de túneles VPN")
        return tunnels

    ike_gateway_cache = {}

    for tun_entry in root.findall("./result/tunnel/ipsec/entry"):
        tunnel_name = tun_entry.get('name', NA)
        if tunnel_name == NA:
            continue

        ike_entry   = tun_entry.find('auto-key/ike-gateway/entry')
        ike_name    = ike_entry.get('name') if ike_entry is not None else NA

        ipsec_profile = NA
        ipsec_node    = tun_entry.find('auto-key/ipsec-vpn')
        if ipsec_node is not None:
            ipsec_profile = ipsec_node.findtext('ipsec-crypto-profile', NA)

        tunnel_interface = tun_entry.findtext('tunnel-interface', NA)

        tunnel_info = {
            'name':                   tunnel_name,
            'ike_gateway_name':       ike_name,
            'ipsec_profile':          ipsec_profile,
            'tunnel_interface':       tunnel_interface,
            'ike_local_ip':           NA,
            'ike_local_interface':    NA,
            'ike_peer_address_config': NA,
        }

        if ike_name != NA:
            if ike_name not in ike_gateway_cache:
                ike_gateway_cache[ike_name] = _get_ike_gateway_details(
                    firewall_ip, api_key, ike_name, target_serial
                )
            tunnel_info.update(ike_gateway_cache[ike_name])

        tunnels.append(tunnel_info)

    logger.info(f"Túneles VPN configurados: {[t['name'] for t in tunnels]}")
    return tunnels


def _get_ike_gateway_details(
    firewall_ip: str,
    api_key: str,
    ike_gateway_name: str,
    target_serial: str | None = None
) -> dict:
    """Obtiene detalles de un IKE Gateway desde configuración."""
    params = {
        'type':   'config',
        'action': 'get',
        'xpath':  (
            f"/config/devices/entry[@name='localhost.localdomain']"
            f"/network/ike/gateway/entry[@name='{ike_gateway_name}']"
        ),
        'key': api_key,
    }
    root = api_request_with_target(firewall_ip, api_key, params, target_serial)
    details = {'ike_local_ip': NA, 'ike_local_interface': NA, 'ike_peer_address_config': NA}

    if root is not None and root.attrib.get('status') == 'success':
        local_ip_node  = root.find(".//local-address/ip")
        interface_node = root.find(".//interface")
        peer_node      = root.find(".//peer-address/ip")

        details['ike_local_ip']            = local_ip_node.text.strip()  if local_ip_node  is not None else NA
        details['ike_local_interface']     = interface_node.text.strip() if interface_node is not None else NA
        details['ike_peer_address_config'] = peer_node.text.strip()      if peer_node      is not None else NA

    return details


# --------------------------------
# Estado operacional SA
# --------------------------------
def _parse_sa(root: ET.Element | None, sa_type: str) -> dict:
    """Parsea IKE o IPsec SA desde XML."""
    sas = {}
    if root is None or root.attrib.get('status') != 'success':
        return sas

    for entry in root.findall(".//entry"):
        if sa_type == 'ike':
            gw_name = entry.findtext(TAG_NAME, NA)
            state   = entry.findtext(TAG_STATE, STATE_ACTIVE)
            peer    = entry.findtext(TAG_PEER_ADDRESS, NA)
            if gw_name != NA:
                sas[gw_name] = {'state': state, 'peer_address': peer}
        else:
            tunnel_name = entry.findtext('tunnel-name') or entry.findtext(TAG_NAME, NA)
            state       = entry.findtext(TAG_STATE, STATE_ACTIVE)
            life_time   = entry.findtext(TAG_LIFE_TIME,  NA)
            life_bytes  = entry.findtext(TAG_LIFE_BYTES, NA)
            if tunnel_name != NA:
                sas[tunnel_name] = {'state': state, 'life_time': life_time, 'life_bytes': life_bytes}
    return sas


def get_vpn_status(
    firewall_ip: str,
    api_key: str,
    target_serial: str | None = None
) -> tuple:
    """Obtiene estado operacional IKE y IPsec SA."""
    params_ike   = {'type': 'op', 'cmd': '<show><vpn><ike-sa/></vpn></show>',   'key': api_key}
    params_ipsec = {'type': 'op', 'cmd': '<show><vpn><ipsec-sa/></vpn></show>', 'key': api_key}

    ike_root   = api_request_with_target(firewall_ip, api_key, params_ike,   target_serial, timeout=20)
    ipsec_root = api_request_with_target(firewall_ip, api_key, params_ipsec, target_serial, timeout=20)

    return _parse_sa(ike_root, 'ike'), _parse_sa(ipsec_root, 'ipsec')


# --------------------------------
# Correlación y estado final
# --------------------------------
def correlate_vpn_status(configured_tunnels: list, ike_data: dict, ipsec_data: dict) -> list:
    """Combina configuración y estado operativo para cada túnel."""
    full_report = []

    for tunnel in configured_tunnels:
        name     = tunnel['name']
        ike_name = tunnel.get('ike_gateway_name')

        ike_status   = STATUS_DOWN
        ipsec_status = STATUS_DOWN

        if ike_name and ike_name in ike_data:
            ike_status = STATUS_UP if ike_data[ike_name]['state'] == STATE_ACTIVE else STATUS_DOWN

        ipsec_key = name if name in ipsec_data else next(
            (k for k in ipsec_data if k.startswith(f"{name}:")), None
        )
        if ipsec_key:
            ipsec_status = STATUS_UP if ipsec_data[ipsec_key]['state'] == STATE_ACTIVE else STATUS_DOWN
            tunnel['ipsec_life_time']  = ipsec_data[ipsec_key].get('life_time',  NA)
            tunnel['ipsec_life_bytes'] = ipsec_data[ipsec_key].get('life_bytes', NA)
        else:
            tunnel['ipsec_life_time']  = NA
            tunnel['ipsec_life_bytes'] = NA

        tunnel['ike_status']        = ike_status
        tunnel['ipsec_tunnel_state'] = ipsec_status
        tunnel['overall_status']    = STATUS_UP if ike_status == STATUS_UP and ipsec_status == STATUS_UP else STATUS_DOWN
        tunnel['ike_peer_ip']       = tunnel.get('ike_peer_address_config', NA)

        full_report.append(tunnel)
        logger.info(f"Túnel '{name}': Overall={tunnel['overall_status']}, IKE={ike_status}, IPsec={ipsec_status}")

    return full_report


# --------------------------------
# Función principal para la GUI
# --------------------------------
def get_vpn_full_status(
    firewall_ip: str,
    api_key: str,
    target_serial: str | None = None
) -> list:
    """Devuelve lista final de túneles con configuración y estado completo."""
    logger.info("Iniciando consulta completa de túneles VPN")
    config = get_vpn_config(firewall_ip, api_key, target_serial)
    if not config:
        logger.warning("No hay túneles configurados.")
        return []
    ike_data, ipsec_data = get_vpn_status(firewall_ip, api_key, target_serial)
    return correlate_vpn_status(config, ike_data, ipsec_data)
