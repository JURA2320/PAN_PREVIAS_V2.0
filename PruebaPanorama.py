
import requests
import urllib3
import xml.etree.ElementTree as ET

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PANORAMA_IP = "10.182.72.40"
API_KEY = "LUFRPT1OUWErdGJsVUpTL3J5dCttY0Q5a0JOOGJTMnc9NnhXQlpxYXlVclRCRXRpWm9WSGtmaFFaOXRZeFlmZEhySlhscVg3UXlHVGFpSmxoUWRuNjJSeU8yL2tNT3lnU2N5UFF2b2laVWdSSEt4Q0UwMkJNa1pJZXphbi9scDQ3eTA0aVZJTllLT2c9"

def panorama_op(cmd_xml: str, target_serial: str | None = None) -> ET.Element:
    """Llama al API op de Panorama. Si target_serial no es None, envía el comando al firewall."""
    params = {
        "type": "op",
        "cmd": cmd_xml,
        "key": API_KEY,
    }
    if target_serial:
        params["target"] = target_serial  # OJO: aquí va el target, no dentro del XML
    url = f"https://{PANORAMA_IP}/api/"
    r = requests.get(url, params=params, verify=False, timeout=30)
    r.raise_for_status()
    return ET.fromstring(r.text)

# 1) Obtener lista de dispositivos desde Panorama
root = panorama_op("<show><devices><all></all></devices></show>")

devices = []
for entry in root.findall(".//devices/entry"):
    hostname = entry.findtext("hostname") or entry.get("name")
    serial = entry.findtext("serial")
    ip_addr = entry.findtext("ip-address")
    connected = entry.findtext("connected")
    sw_version = entry.findtext("sw-version")

    if hostname and serial:
        devices.append({
            "hostname": hostname,
            "serial": serial,
            "ip": ip_addr,
            "connected": connected,
            "version": sw_version,
        })

print("========= LISTA DE FIREWALLS (DESDE PANORAMA) =========")
for idx, dev in enumerate(devices, start=1):
    print(f"{idx}. {dev['hostname']}  |  Serial: {dev['serial']}  | IP: {dev['ip']}  | Conectado: {dev['connected']}")

if not devices:
    print("No se encontraron dispositivos en Panorama.")
    raise SystemExit

# 2) Seleccionar firewall
while True:
    try:
        opcion = int(input("\nSeleccione el número del firewall: "))
        if 1 <= opcion <= len(devices):
            break
        else:
            print("Número inválido, inténtelo de nuevo.")
    except ValueError:
        print("Entrada no válida, ingrese un número.")

selected_fw = devices[opcion - 1]
print(f"\nSeleccionado: {selected_fw['hostname']} (Serial: {selected_fw['serial']})")

# 3) Llamar al firewall usando target=<serial> para show system info
cmd_status = "<show><system><info></info></system></show>"

status_root = panorama_op(cmd_status, target_serial=selected_fw["serial"])

print("\n========= STATUS DEL FIREWALL =========")
system_info = status_root.find(".//system")
if system_info is not None:
    for child in system_info:
        print(f"{child.tag}: {child.text}")
else:
    # Si la ruta no coincide, imprime XML completo para ver qué devolvió
    import xml.dom.minidom as minidom
    print(minidom.parseString(ET.tostring(status_root)).toprettyxml())
