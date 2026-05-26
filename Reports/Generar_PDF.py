from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from datetime import datetime
from collections import defaultdict

# Helper para asegurar que los valores vacíos sean "N/A"
def _get_value_or_na(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return 'N/A'
    return value


# ============================
#   FUNCIÓN PARA ZEBRA STRIPING
# ============================
def apply_zebra_style(table_style, num_rows):
    for row in range(1, num_rows):
        if row % 2 == 0:
            table_style.add('BACKGROUND', (0, row), (-1, row), colors.HexColor('#f2f2f2'))


def generate_interface_report_pdf(
    interfaces_data: dict, 
    dashboard_info: dict,
    ha_info: dict,
    vpn_tunnels_data: list, 
    firewall_ip: str, 
    pdf_filename: str = "estado_interfaces_firewall.pdf"
):

    cell_style = ParagraphStyle(name='cell', fontSize=7, leading=9)
    
    styles = getSampleStyleSheet()
    h2_bold_style = ParagraphStyle(
        name='h2_bold',
        parent=styles['h2'],
        fontSize=14,
        leading=16,
        spaceAfter=6,
        fontName='Helvetica-Bold'
    )
    normal_style = styles['Normal']
    h3_style = styles['h3']

    doc = SimpleDocTemplate(pdf_filename, pagesize=landscape(letter))
    elements = []

    # TÍTULO
    title = Paragraph("📄 Informe de Estado del Firewall Palo Alto", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))

    info = (
        f"Fecha de Generación: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br/>"
        f"IP del Firewall: {firewall_ip}"
    )
    elements.append(Paragraph(info, normal_style))
    elements.append(Spacer(1, 18))


    # ============================
    #   DASHBOARD
    # ============================
    elements.append(Paragraph("🚀 Información General del Firewall", h2_bold_style))
    elements.append(Spacer(1, 6))

    if dashboard_info:
        dashboard_data = [
            ["Atributo", "Valor"],
            ["Hostname", _get_value_or_na(dashboard_info.get('hostname'))],
            ["Modelo", _get_value_or_na(dashboard_info.get('model'))],
            ["Número de Serie", _get_value_or_na(dashboard_info.get('serial'))],
            ["Versión PAN-OS", _get_value_or_na(dashboard_info.get('version'))],
            ["Uptime", _get_value_or_na(dashboard_info.get('uptime'))],
            ["IP de Gestión", _get_value_or_na(dashboard_info.get('mgmt_ip'))]
        ]

        ts = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#d3d3d3')),
            ('TEXTCOLOR',(0,0),(-1,0), colors.black),
            ('GRID',(0,0),(-1,-1),0.5, colors.gray),
            ('ALIGN',(0,0),(-1,-1),'LEFT'),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('FONTNAME',(0,1),(-1,-1),'Helvetica'),
            ('FONTSIZE',(0,0),(-1,0),10),
            ('FONTSIZE',(0,1),(-1,-1),9)
        ])

        apply_zebra_style(ts, len(dashboard_data))

        dashboard_table = Table(dashboard_data, colWidths=[2.5*inch, 6*inch])
        dashboard_table.setStyle(ts)
        elements.append(dashboard_table)
    else:
        elements.append(Paragraph("⚠️ No se pudo obtener el dashboard.", normal_style))

    elements.append(Spacer(1, 18))


    # ============================
    #   HA
    # ============================
    elements.append(PageBreak())
    elements.append(Paragraph("🔄 Estado de High Availability (HA)", h2_bold_style))
    elements.append(Spacer(1, 6))

    if ha_info:
        ha_data = [
            ["Atributo", "Valor"],
            ["Modo Local", _get_value_or_na(ha_info.get('local_mode'))],
            ["Estado Local", _get_value_or_na(ha_info.get('local_state'))],
            ["IP Peer", _get_value_or_na(ha_info.get('peer_ip'))],
            ["Estado Peer", _get_value_or_na(ha_info.get('peer_state'))]
        ]

        ts = TableStyle([
            ('BACKGROUND',(0,0),(-1,0), colors.HexColor('#d3d3d3')),
            ('GRID',(0,0),(-1,-1),0.5, colors.gray),
            ('ALIGN',(0,0),(-1,-1),'LEFT'),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('FONTSIZE',(0,0),(-1,0),10)
        ])

        apply_zebra_style(ts, len(ha_data))

        ha_table = Table(ha_data, colWidths=[2.5*inch, 6*inch])
        ha_table.setStyle(ts)
        elements.append(ha_table)
    else:
        elements.append(Paragraph("⚠ No se pudo obtener el estado HA.", normal_style))

    elements.append(Spacer(1, 18))


    # ============================
    #   VPN TUNNELS
    # ============================
    elements.append(PageBreak())
    elements.append(Paragraph("🔐 Túneles VPN IPsec", h2_bold_style))
    elements.append(Spacer(1, 6))

    if vpn_tunnels_data:
        vpn_data = [[
            "Nombre", "Estado", "IKE", "Interfaz IKE",
            "IP Local", "Peer IP", "Tunnel If"
        ]]

        for t in vpn_tunnels_data:
            overall = _get_value_or_na(t.get('overall_status'))
            ike = _get_value_or_na(t.get('ike_status'))

            vpn_data.append([
                Paragraph(_get_value_or_na(t.get('name')), cell_style),

                Paragraph(overall, ParagraphStyle(
                    name='s1', parent=cell_style,
                    textColor=colors.green if overall == "UP" else colors.red)),
                
                Paragraph(ike, ParagraphStyle(
                    name='s2', parent=cell_style,
                    textColor=colors.green if ike == "UP" else colors.red)),

                Paragraph(_get_value_or_na(t.get('ike_local_interface')), cell_style),
                Paragraph(_get_value_or_na(t.get('ike_local_ip')), cell_style),
                Paragraph(_get_value_or_na(t.get('ike_peer_ip')), cell_style),
                Paragraph(_get_value_or_na(t.get('tunnel_interface')), cell_style)
            ])

        ts = TableStyle([
            ('BACKGROUND',(0,0),(-1,0), colors.HexColor('#d3d3d3')),
            ('GRID',(0,0),(-1,-1),0.5, colors.gray),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('ALIGN',(0,0),(-1,-1),'LEFT'),
        ])

        apply_zebra_style(ts, len(vpn_data))

        vpn_table = Table(vpn_data, repeatRows=1)
        vpn_table.setStyle(ts)
        elements.append(vpn_table)
    else:
        elements.append(Paragraph("⚠ No hay túneles VPN configurados.", normal_style))


    # ============================
    #   INTERFACES
    # ============================
    elements.append(PageBreak())
    elements.append(Paragraph("📊 Estado Detallado de Interfaces", h2_bold_style))
    elements.append(Spacer(1, 6))

    # Copiar estado a subinterfaces
    main_states = {}
    updated_data = {}

    for name, d in interfaces_data.items():
        updated_data[name] = d.copy()
        if '.' not in name:
            main_states[name] = d.get("state")

    for name, d in updated_data.items():
        if '.' in name:
            base = name.split('.')[0]
            if base in main_states:
                d['state'] = main_states[base]

    # Agrupar
    groups = defaultdict(list)
    for name, d in updated_data.items():
        if name.startswith("ethernet"): t="Ethernet"
        elif name.startswith("vlan"): t="VLAN"
        elif name.startswith("loopback"): t="Loopback"
        elif name.startswith("tunnel"): t="Tunnel"
        elif name.startswith("ae") or "sdwan" in name.lower(): t="SD-WAN"
        else: t="Otro"
        groups[t].append(d)

    # Tabla por grupo
    for tipo, lst in groups.items():
        elements.append(Paragraph(f"🔹 Tipo de Interfaz: {tipo}", h3_style))
        elements.append(Spacer(1, 6))

        data = [["Nombre","Estado","IP","MAC","Zona","Perfil MGMT","VR","Tipo"]]

        for intf in sorted(lst, key=lambda x: x["name"]):
            state = _get_value_or_na(intf.get("state"))
            color_state = colors.green if state.upper()=="UP" else colors.red

            data.append([
                Paragraph(_get_value_or_na(intf.get('name')), cell_style),
                Paragraph(state, ParagraphStyle(name='s3', parent=cell_style, textColor=color_state)),
                Paragraph(_get_value_or_na(intf.get('ip')), cell_style),
                Paragraph(_get_value_or_na(intf.get('mac')), cell_style),
                Paragraph(_get_value_or_na(intf.get('zone')), cell_style),
                Paragraph(_get_value_or_na(intf.get('mgmt_profile')), cell_style),
                Paragraph(_get_value_or_na(intf.get('virtual_router')), cell_style),
                Paragraph(_get_value_or_na(intf.get('interface_type')), cell_style),
            ])

        ts = TableStyle([
            ('BACKGROUND',(0,0),(-1,0), colors.HexColor('#d3d3d3')),
            ('GRID',(0,0),(-1,-1),0.5, colors.gray),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold')
        ])

        apply_zebra_style(ts, len(data))

        t = Table(data, repeatRows=1)
        t.setStyle(ts)
        elements.append(t)
        elements.append(Spacer(1, 18))

    # Construcción del PDF
    print(f"📝 Generando informe PDF: {pdf_filename}...")
    doc.build(elements)
    print(f"✅ Informe PDF generado exitosamente: {pdf_filename}")
