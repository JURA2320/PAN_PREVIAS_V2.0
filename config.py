import os

# --------------------------------------------------------------------------
# Configuración principal del firewall y salida de informes
# --------------------------------------------------------------------------
# IP del firewall a consultar. Se puede sobrescribir con variable de entorno.
FIREWALL_IP = os.environ.get("FIREWALL_IP", "192.168.1.74")

# Clave API para autenticación en el firewall. Se puede sobrescribir con variable de entorno.
API_KEY = os.environ.get("API_KEY", "0")

# Ruta o nombre del archivo PDF de salida. Se puede sobrescribir con variable de entorno.
PDF_OUTPUT = os.environ.get("PDF_OUTPUT", "informe_interfaces_paloalto.pdf")

# --------------------------------------------------------------------------
# Actualizaciones dinámicas de seguridad
# --------------------------------------------------------------------------
# Lista de servicios que pueden actualizarse dinámicamente (ej: antivirus, Wildfire, contenido)
DYNAMIC_UPDATES = [
    "anti-virus",
    "wildfire",
    "content",
    "IoT",
    "global-protect-clientless-vpn",
]

# Conjunto para validación rápida de tipos permitidos de actualización
ALLOWED_UPDATE_TYPES = set(DYNAMIC_UPDATES)

# --------------------------------------------------------------------------
# Flags de control para activar/desactivar funcionalidades del script
# --------------------------------------------------------------------------
# Este diccionario centraliza qué módulos o acciones se ejecutan
FLAGS = {
    "ENABLE_SW_DOWNLOAD": True,       # Permite descarga de nuevas versiones de PAN-OS
    "SOFTWARE_VERSION": "0",          # Versión específica a descargar si ENABLE_SW_DOWNLOAD=True
    "ENABLE_BACKUPS": True,           # Activa la generación de backups (running-config y device-state)
    "ENABLE_VPN_CHECK": True,         # Habilita la recolección automática de estado de túneles VPN
    "ENABLE_TFS": True,               # Habilita la generación de Tech Support File (TFS)
    "ENABLE_DYNAMIC_UPDATES": True,   # Permite actualizar dinámicamente servicios de seguridad
}
