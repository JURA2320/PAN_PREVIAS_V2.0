import sys
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Extender path al proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configuración
from config import DYNAMIC_UPDATES
from PaloAlto.Gen_Backup import DEFAULT_BACKUP_FOLDER

# Módulos Palo Alto
from PaloAlto.Ext_Dashboard import get_firewall_dashboard_data
from PaloAlto.Ext_Interfaces import get_firewall_interfaces_data
from PaloAlto.Ext_HighAviability import get_firewall_HighAviability_data
from PaloAlto.Down_Version import download_panos_version
from PaloAlto.Gen_Backup import download_running_config, download_device_state
from PaloAlto.Ext_Tuneles import get_vpn_full_status
from PaloAlto.Gen_TFS import generate_tech_support_file
from PaloAlto.Down_DynamicUpdates import download_dynamic_update
from PaloAlto.Panorama import detect_device_type, get_managed_firewalls
from Reports.Generar_PDF import generate_interface_report_pdf

# Logger
from Utils.logger import get_logger
logger = get_logger()

MAX_FW_SELECTION = 3  # Máximo: 1 Panorama + 2 FW gestionados (contexto HA)


# ------------------------------------------------------
# ENTRY CON PLACEHOLDER
# ------------------------------------------------------
class PlaceholderEntry(ttk.Entry):
    def __init__(self, container, placeholder, color='grey', *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.placeholder = placeholder
        self.placeholder_color = color
        self.default_fg_color = 'black'
        self.is_placeholder = False
        self.bind("<FocusIn>",  self._clear_placeholder)
        self.bind("<FocusOut>", self._add_placeholder)
        self._add_placeholder()

    def _clear_placeholder(self, event=None):
        if self.is_placeholder:
            self.delete(0, 'end')
            self.config(foreground=self.default_fg_color)
            self.is_placeholder = False

    def _add_placeholder(self, event=None):
        if not super().get():
            self.insert(0, self.placeholder)
            self.config(foreground=self.placeholder_color)
            self.is_placeholder = True

    def get(self):
        value = super().get()
        return "" if self.is_placeholder else value


# ------------------------------------------------------
# DIÁLOGO SELECTOR DE FIREWALL (modo Panorama)
# Checkboxes por fila — máximo MAX_FW_SELECTION
# ------------------------------------------------------
class FirewallSelectorDialog(tk.Toplevel):
    """
    Ventana modal con checkboxes por fila.
    Al llegar al límite MAX_FW_SELECTION los demás
    checkboxes se deshabilitan automáticamente.
    """
    def __init__(self, parent, firewalls: list[dict]):
        super().__init__(parent)
        self.title("Seleccionar Firewall(s) — Panorama")
        self.geometry("740x480")
        self.resizable(False, False)
        self.grab_set()  # Modal

        self.firewalls          = firewalls
        self.selected_firewalls = []          # resultado final

        self._check_vars = {}   # serial → BooleanVar
        self._check_btns = {}   # serial → Checkbutton widget

        self._build()

    # --------------------------------------------------
    def _build(self):
        # Encabezado
        ttk.Label(
            self,
            text=(
                "Se detectó una conexión a Panorama.\n"
                "Seleccione Panorama y/o hasta 2 firewalls gestionados "
                "(máximo 3 en total):"
            ),
            justify=tk.LEFT
        ).pack(padx=20, pady=(15, 4), anchor=tk.W)

        # Contador de selección
        self._counter_var = tk.StringVar(value=f"Seleccionados: 0 / {MAX_FW_SELECTION}")
        ttk.Label(self, textvariable=self._counter_var, foreground="blue").pack(
            anchor=tk.W, padx=20, pady=(0, 8)
        )

        # Frame con scroll
        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20)

        canvas    = tk.Canvas(list_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        self._scroll_frame = ttk.Frame(canvas)

        self._scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Cabecera de columnas
        header = ttk.Frame(self._scroll_frame)
        header.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(header, text="",               width=4).pack(side=tk.LEFT)
        ttk.Label(header, text="Hostname",       width=28, anchor=tk.W, font=('', 9, 'bold')).pack(side=tk.LEFT)
        ttk.Label(header, text="Versión PAN-OS", width=18, anchor=tk.W, font=('', 9, 'bold')).pack(side=tk.LEFT)
        ttk.Label(header, text="Estado",         width=16, anchor=tk.W, font=('', 9, 'bold')).pack(side=tk.LEFT)
        ttk.Separator(self._scroll_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 6))

        # ── Fila especial: Panorama mismo ──
        panorama_fw = next((f for f in self.firewalls if f.get('is_panorama')), None)
        if panorama_fw:
            self._add_fw_row(panorama_fw, is_panorama=True)
            ttk.Separator(self._scroll_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(4, 8))

        # ── Filas de FW gestionados ──
        for fw in self.firewalls:
            if not fw.get('is_panorama'):
                self._add_fw_row(fw)

        # Botones
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=14)
        ttk.Button(btn_frame, text="Confirmar selección", command=self._confirm).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Cancelar",            command=self.destroy).pack(side=tk.LEFT, padx=8)

    # --------------------------------------------------
    def _add_fw_row(self, fw: dict, is_panorama: bool = False):
        serial    = fw['serial']
        hostname  = fw.get('hostname',   'N/A')
        version   = fw.get('sw_version', 'N/A')
        connected = fw.get('connected', 'yes').lower() == 'yes'
        estado_txt = '✔ Conectado'  if connected else '✘ Desconectado'
        color      = 'darkgreen'    if connected else 'red'

        # Panorama tiene estilo visual diferente
        if is_panorama:
            hostname   = f"⚙ {hostname}  (Panorama)"
            estado_txt = '✔ Activo'
            color      = 'navy'

        var = tk.BooleanVar(value=False)
        self._check_vars[serial] = var

        row = ttk.Frame(self._scroll_frame)
        row.pack(fill=tk.X, pady=3)

        cb = ttk.Checkbutton(
            row, variable=var,
            command=lambda s=serial: self._on_toggle(s)
        )
        cb.pack(side=tk.LEFT, padx=(0, 6))
        self._check_btns[serial] = cb

        font = ('', 9, 'bold') if is_panorama else ('', 9)
        ttk.Label(row, text=hostname,   width=32, anchor=tk.W, font=font).pack(side=tk.LEFT)
        ttk.Label(row, text=version,    width=18, anchor=tk.W).pack(side=tk.LEFT)
        ttk.Label(row, text=estado_txt, width=16, anchor=tk.W, foreground=color).pack(side=tk.LEFT)

    # --------------------------------------------------
    def _on_toggle(self, serial: str):
        """
        Al marcar/desmarcar un checkbox:
        - Actualiza el contador visible.
        - Al llegar al límite, deshabilita los no seleccionados.
        - Al bajar del límite, los vuelve a habilitar.
        """
        selected_count = sum(1 for v in self._check_vars.values() if v.get())
        self._counter_var.set(f"Seleccionados: {selected_count} / {MAX_FW_SELECTION}")

        limit_reached = selected_count >= MAX_FW_SELECTION
        for s, btn in self._check_btns.items():
            if not self._check_vars[s].get():
                btn.config(state='disabled' if limit_reached else 'normal')

    # --------------------------------------------------
    def _confirm(self):
        selected = [fw for fw in self.firewalls if self._check_vars[fw['serial']].get()]
        if not selected:
            messagebox.showwarning(
                "Sin selección",
                "Debe seleccionar al menos un firewall.",
                parent=self
            )
            return
        self.selected_firewalls = selected
        self.destroy()


# ------------------------------------------------------
# GUI PRINCIPAL
# ------------------------------------------------------
class PaloAltoGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gestión Palo Alto Firewall")
        self.geometry("720x920")

        # Variables GUI
        self.firewall_ip      = tk.StringVar()
        self.api_key          = tk.StringVar()
        self.case_id          = tk.StringVar()
        self.software_version = tk.StringVar()
        self.backup_folder    = tk.StringVar(value=DEFAULT_BACKUP_FOLDER)

        # Lista de FW seleccionados: [{serial, hostname}, ...]
        self._selected_firewalls = []
        self._device_type        = None   # 'firewall' | 'panorama'

        # Flags
        self.enable_sw_download     = tk.BooleanVar()
        self.enable_backups         = tk.BooleanVar()
        self.enable_vpn_check       = tk.BooleanVar(value=True)
        self.enable_tfs             = tk.BooleanVar()
        self.enable_dynamic_updates = tk.BooleanVar()
        self.enable_report          = tk.BooleanVar(value=True)  # Extracción de info + PDF

        # Locks para thread-safety
        self._log_lock      = threading.Lock()
        self._progress_lock = threading.Lock()

        self._build_gui()

    # --------------------------------------------------
    # Construcción GUI — flujo en dos pasos
    # --------------------------------------------------
    def _build_gui(self):
        main = ttk.Frame(self)
        main.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)

        # ── PASO 1: Conexión ──────────────────────────
        conn_box = ttk.LabelFrame(main, text="Paso 1 — Conexión")
        conn_box.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(conn_box, text="IP del Firewall o Panorama:").pack(anchor=tk.W, padx=10, pady=(8, 0))
        PlaceholderEntry(conn_box, placeholder="Ej: 192.168.1.1",
                         textvariable=self.firewall_ip).pack(fill=tk.X, padx=10)

        self.device_type_label = ttk.Label(conn_box, text="", foreground="gray")
        self.device_type_label.pack(anchor=tk.W, padx=10, pady=(2, 0))

        ttk.Label(conn_box, text="API Key:").pack(anchor=tk.W, padx=10, pady=(8, 0))
        ttk.Entry(conn_box, textvariable=self.api_key, show="*").pack(fill=tk.X, padx=10)

        self.btn_connect = ttk.Button(conn_box, text="🔌 Conectar",
                                      command=self._run_connect_threaded)
        self.btn_connect.pack(pady=10)

        # ── PASO 2: Opciones y ejecución ─────────────
        self.options_box = ttk.LabelFrame(main, text="Paso 2 — Opciones y ejecución")
        self.options_box.pack(fill=tk.X, pady=(0, 10))

        # Case ID
        ttk.Label(self.options_box, text="Número de caso:").pack(anchor=tk.W, padx=10, pady=(8, 0))
        PlaceholderEntry(self.options_box, placeholder="Ej: #SR-123456",
                         textvariable=self.case_id).pack(fill=tk.X, padx=10)

        # Carpeta de destino
        ttk.Label(self.options_box, text="Carpeta de destino:").pack(anchor=tk.W, padx=10, pady=(8, 0))
        folder_frame = ttk.Frame(self.options_box)
        folder_frame.pack(fill=tk.X, padx=10)
        ttk.Entry(folder_frame, textvariable=self.backup_folder).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(folder_frame, text="Seleccionar",
                   command=self._select_folder).pack(side=tk.LEFT, padx=(8, 0))

        # Checkboxes de opciones
        ttk.Label(self.options_box, text="Opciones a ejecutar:").pack(
            anchor=tk.W, padx=10, pady=(12, 2))

        sw_frame = ttk.Frame(self.options_box)
        sw_frame.pack(anchor=tk.W, padx=10)
        self.cb_sw = ttk.Checkbutton(sw_frame, text="Descarga de Software",
                                     variable=self.enable_sw_download,
                                     command=self._toggle_version_entry)
        self.cb_sw.pack(side=tk.LEFT)
        self.version_entry = PlaceholderEntry(sw_frame, placeholder="Versión PAN-OS",
                                              textvariable=self.software_version, width=18)
        self.version_entry.pack(side=tk.LEFT, padx=(10, 0))
        self.version_entry.config(state='disabled')

        self.cb_backups = ttk.Checkbutton(self.options_box, text="Backups",
                                          variable=self.enable_backups)
        self.cb_backups.pack(anchor=tk.W, padx=10)

        self.cb_tfs = ttk.Checkbutton(self.options_box, text="Generar Tech Support File",
                                      variable=self.enable_tfs)
        self.cb_tfs.pack(anchor=tk.W, padx=10)

        self.cb_du = ttk.Checkbutton(self.options_box, text="Dynamic Updates",
                                     variable=self.enable_dynamic_updates)
        self.cb_du.pack(anchor=tk.W, padx=10)

        self.cb_report = ttk.Checkbutton(
            self.options_box,
            text="Extracción de información y generación de PDF",
            variable=self.enable_report)
        self.cb_report.pack(anchor=tk.W, padx=10, pady=(0, 6))

        self.btn_execute = ttk.Button(self.options_box, text="▶ Ejecutar Proceso",
                                      command=self._run_threaded)
        self.btn_execute.pack(pady=(4, 12))

        # Deshabilitar todo el paso 2 hasta que se conecte
        self._set_step2_state('disabled')

        # ── Consola y progreso ────────────────────────
        self.output_text = tk.Text(main, height=18, state='disabled')
        self.output_text.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        self.progress = ttk.Progressbar(main, orient=tk.HORIZONTAL, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(8, 0))

    # --------------------------------------------------
    # Habilitar / deshabilitar Paso 2
    # --------------------------------------------------
    def _set_step2_state(self, state: str):
        """Habilita o deshabilita todos los widgets del Paso 2."""
        widgets = [
            self.cb_sw, self.cb_backups, self.cb_tfs, self.cb_du,
            self.cb_report, self.btn_execute,
        ]
        for w in widgets:
            w.config(state=state)
        # version_entry se controla por su propio toggle
        if state == 'disabled':
            self.version_entry.config(state='disabled')

    # --------------------------------------------------
    def _toggle_version_entry(self):
        if self.enable_sw_download.get():
            self.version_entry.config(state='normal')
        else:
            self.version_entry.config(state='disabled')
            self.software_version.set("")

    def _select_folder(self):
        folder = filedialog.askdirectory(title="Selecciona carpeta de destino")
        if folder:
            self.backup_folder.set(folder)

    def _run_connect_threaded(self):
        """Lanza la detección de dispositivo en hilo separado."""
        self.btn_connect.config(state='disabled')
        self._set_step2_state('disabled')
        self._selected_firewalls = []
        threading.Thread(target=self._connect_step, daemon=True).start()

    def _run_threaded(self):
        threading.Thread(target=self._start_process, daemon=True).start()

    # --------------------------------------------------
    # PASO 1 — Conexión y detección
    # --------------------------------------------------
    def _connect_step(self):
        """
        Ejecutado en hilo secundario.
        1. Valida campos.
        2. Detecta tipo de dispositivo.
        3. Si Panorama → abre diálogo de selección de FW(s).
        4. Si todo OK → habilita el Paso 2 y reactiva el botón Conectar.
        """
        ip  = self.firewall_ip.get().strip()
        key = self.api_key.get().strip()

        if not ip or not key:
            self.after(0, lambda: messagebox.showwarning(
                "Datos faltantes", "Debe ingresar IP y API Key.", parent=self))
            self.after(0, lambda: self.btn_connect.config(state='normal'))
            return

        self._log("🔍 Detectando tipo de dispositivo...")
        ok = self._detect_and_select_target(ip, key)

        if ok:
            self._log("✅ Conexión establecida. Configure las opciones y pulse Ejecutar.")
            self.after(0, lambda: self._set_step2_state('normal'))
        else:
            self._log("⚠️  Conexión cancelada o fallida.")

        self.after(0, lambda: self.btn_connect.config(state='normal'))

    # --------------------------------------------------
    # Log y progreso thread-safe
    # --------------------------------------------------
    def _log(self, msg: str, prefix: str = ""):
        """Escribe en consola GUI. prefix = hostname del FW (visible en modo paralelo)."""
        full_msg = f"[{prefix}] {msg}" if prefix else msg
        with self._log_lock:
            self.output_text.config(state='normal')
            self.output_text.insert(tk.END, full_msg + "\n")
            self.output_text.see(tk.END)
            self.output_text.config(state='disabled')
        logger.info(full_msg)

    def _increment_progress(self):
        with self._progress_lock:
            self.progress['value'] += 1
            self.update_idletasks()

    # --------------------------------------------------
    # DETECCIÓN Y SELECCIÓN
    # --------------------------------------------------
    def _detect_and_select_target(self, ip: str, key: str) -> bool:
        """
        Detecta Panorama o Firewall directo.
        Si es Panorama abre el diálogo de selección con checkboxes.
        Popula self._selected_firewalls.
        Retorna True para continuar, False si se canceló.
        """
        self._log("🔍 Detectando tipo de dispositivo...")
        device_type = detect_device_type(ip, key)
        self._device_type = device_type

        if device_type == 'panorama':
            self._log("☁️  Panorama detectado. Obteniendo información y lista de firewalls gestionados...")

            # Obtener info del propio Panorama para mostrarlo como primera fila
            from PaloAlto.Ext_Dashboard import get_firewall_dashboard_data
            panorama_info = get_firewall_dashboard_data(ip, key)
            panorama_row  = {
                'serial':     '__PANORAMA__',
                'hostname':   panorama_info.get('hostname', ip) if panorama_info else ip,
                'sw_version': panorama_info.get('version',  'N/A') if panorama_info else 'N/A',
                'connected':  'yes',
                'is_panorama': True,
                'panorama_ip': ip,       # guardamos la IP real para usarla en el pipeline
            }

            firewalls = get_managed_firewalls(ip, key)
            all_rows  = [panorama_row] + firewalls   # Panorama siempre primero

            result = {}

            def open_dialog():
                dialog = FirewallSelectorDialog(self, all_rows)
                self.wait_window(dialog)
                result['firewalls'] = dialog.selected_firewalls

            self.after(0, open_dialog)
            while 'firewalls' not in result:
                time.sleep(0.1)

            if not result['firewalls']:
                self._log("⚠️  Selección cancelada por el usuario.")
                return False

            self._selected_firewalls = result['firewalls']
            names = ', '.join(
                f['hostname'] + (' (Panorama)' if f.get('is_panorama') else '')
                for f in self._selected_firewalls
            )
            self._log(f"✔ Seleccionado(s): {names}")
            self.after(0, lambda: self.device_type_label.config(
                text=f"☁️  Panorama  →  {names}", foreground="blue"
            ))

        else:
            # Modo directo: un único FW sin serial
            self._selected_firewalls = [{'serial': None, 'hostname': ip}]
            self._log("✔ Firewall directo detectado.")
            self.after(0, lambda: self.device_type_label.config(
                text="🔥 Firewall directo", foreground="green"
            ))

        return True

    # --------------------------------------------------
    # PIPELINE COMPLETO PARA UN FIREWALL
    # --------------------------------------------------
    def _run_single_firewall(self, ip: str, key: str, caseid: str, fw: dict):
        """
        Ejecuta todas las tareas para un dispositivo.
        fw = {'serial': str|None|'__PANORAMA__', 'hostname': str, ...}

        Casos:
          - serial = None          → Firewall directo (ip = IP del FW)
          - serial = '__PANORAMA__'→ Panorama mismo (ip = IP de Panorama, target_serial = None)
          - serial = '<serial>'    → FW gestionado por Panorama (ip = IP de Panorama, target_serial = serial)
        """
        is_panorama_self = fw.get('is_panorama', False)
        serial           = None if is_panorama_self else fw['serial']
        hostname         = fw['hostname']

        def log(msg): self._log(msg, prefix=hostname)
        def inc():    self._increment_progress()

        # Obtener versión instalada (solo si se va a descargar software y no viene pre-consultada)
        current_version = fw.get('_current_version', '')
        if self.enable_sw_download.get() and not current_version:
            log("Consultando versión instalada…")
            _dash = get_firewall_dashboard_data(ip, key, serial)
            current_version = _dash.get('version', '0.0.0') if _dash else '0.0.0'
            log(f"Versión instalada: {current_version}")

        # ── Software ──
        if self.enable_sw_download.get():
            ver = self.software_version.get()
            log(f"Verificando imagen base para {ver}…")
            result = download_panos_version(
                ip, key, ver, current_version, serial,
                log_callback=log   # progreso visible en consola GUI en tiempo real
            )
            if result['success']:
                if result['base_downloaded']:
                    log(f"✔ Base {result['base_version']} + versión {ver} descargadas correctamente.")
                else:
                    log(f"✔ Versión {ver} descargada correctamente.")
            else:
                if result['base_downloaded']:
                    log(f"✖ Falló la descarga. Verifique conectividad y licencias.")
                else:
                    log(f"✖ Error al descargar {ver}. Verifique conectividad y licencias.")
            inc()

        # ── Backups ──
        if self.enable_backups.get():
            log("Realizando backups…")
            ok = download_running_config(ip, key, self.backup_folder.get(), serial)
            log("✔ running-config OK" if ok else "✖ Error running-config")
            inc()
            ok = download_device_state(ip, key, self.backup_folder.get(), serial)
            log("✔ device-state OK" if ok else "✖ Error device-state")
            inc()

        # ── TFS ──
        if self.enable_tfs.get():
            log("Generando Tech Support File…")
            ok = generate_tech_support_file(ip, key, serial)
            log("✔ TFS OK" if ok else "✖ Error generando TFS")
            inc()

        # ── Dynamic Updates ──
        if self.enable_dynamic_updates.get():
            for update in DYNAMIC_UPDATES:
                log(f"Procesando Dynamic Update: {update}")
                ok = download_dynamic_update(ip, key, update, serial)
                log("✔ OK" if ok else f"✖ Error en {update}")
                inc()

        # ── Dynamic Updates ──
        if self.enable_dynamic_updates.get():
            for update in DYNAMIC_UPDATES:
                log(f"Procesando Dynamic Update: {update}")
                ok = download_dynamic_update(ip, key, update, serial)
                log("✔ OK" if ok else f"✖ Error en {update}")
                inc()

        # ── Extracción de información y PDF ──
        if self.enable_report.get():
            log("Obteniendo dashboard…")
            dashboard = get_firewall_dashboard_data(ip, key, serial)
            inc()

            log("Obteniendo túneles VPN…")
            vpn_data = get_vpn_full_status(ip, key, serial)
            inc()

            log("Obteniendo High Availability…")
            ha_info = get_firewall_HighAviability_data(ip, key, serial)
            inc()

            log("Obteniendo interfaces…")
            interfaces = get_firewall_interfaces_data(ip, key, serial)
            inc()

            label    = serial if serial else ip
            pdf_name = f"Actividades previas firewall {hostname} - {caseid}.pdf"
            pdf_path = os.path.join(self.backup_folder.get(), pdf_name)

            folder_path = os.path.dirname(pdf_path)
            if not os.path.exists(folder_path):
                try:
                    os.makedirs(folder_path)
                    log(f"✔ Carpeta creada: {folder_path}")
                except Exception as e:
                    log(f"✖ Error al crear carpeta: {e}")
                    return

            log(f"Generando PDF: {pdf_path}")
            try:
                generate_interface_report_pdf(interfaces, dashboard, ha_info, vpn_data, label, pdf_path)
                log("✔ PDF generado correctamente.")
            except Exception as e:
                log(f"❌ Error al construir el PDF: {e}")

        log("✔ Proceso completado.")

    # --------------------------------------------------
    # COORDINACIÓN CENTRAL — Paso 2
    # --------------------------------------------------
    def _start_process(self):
        """
        La detección y selección de FW ya ocurrió en el Paso 1.
        Aquí solo se valida, calcula progreso y lanza el pipeline.
        """
        ip     = self.firewall_ip.get().strip()
        key    = self.api_key.get().strip()
        caseid = self.case_id.get().strip()

        if self.enable_sw_download.get() and not self.software_version.get().strip():
            self.after(0, lambda: messagebox.showwarning(
                "Versión requerida", "Ingrese la versión PAN-OS a descargar.", parent=self))
            return

        if not self._selected_firewalls:
            self.after(0, lambda: messagebox.showwarning(
                "Sin dispositivo", "Primero debe conectarse usando el Paso 1.", parent=self))
            return

        # Bloquear Ejecutar durante el proceso
        self.after(0, lambda: self.btn_execute.config(state='disabled'))
        self._log("▶ Iniciando proceso…")

        num_fw = len(self._selected_firewalls)

        # Calcular pasos totales (por FW × número de FW)
        steps_per_fw = 0
        if self.enable_sw_download.get():     steps_per_fw += 1
        if self.enable_backups.get():         steps_per_fw += 2
        if self.enable_tfs.get():             steps_per_fw += 1
        if self.enable_dynamic_updates.get(): steps_per_fw += len(DYNAMIC_UPDATES)
        if self.enable_report.get():          steps_per_fw += 4  # dashboard, VPN, HA, interfaces + PDF

        self.after(0, lambda: self.progress.configure(
            maximum=steps_per_fw * num_fw, value=0))

        if num_fw == 1:
            self._run_single_firewall(ip, key, caseid, self._selected_firewalls[0])
        else:
            self._log(f"🚀 Procesando {num_fw} firewalls en paralelo…")
            threads = [
                threading.Thread(
                    target=self._run_single_firewall,
                    args=(ip, key, caseid, fw),
                    daemon=True
                )
                for fw in self._selected_firewalls
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self._log("✔ Todos los firewalls procesados.")

        # Rehabilitar botón Ejecutar al terminar
        self.after(0, lambda: self.btn_execute.config(state='normal'))
