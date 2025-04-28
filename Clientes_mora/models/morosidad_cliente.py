from odoo import models, fields, api, tools
from datetime import date
import io
from odoo.tools import date_utils
from odoo.http import content_disposition
import base64
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

class MorosidadCliente(models.Model):
    _name = 'morosidad.cliente'
    _description = 'Reporte de Morosidad de Clientes'
    _auto = False

    partner_id = fields.Many2one('res.partner', string='Cliente')
    move_id = fields.Many2one('account.move', string='Factura')
    invoice_date = fields.Date(string='Fecha Factura')
    invoice_date_due = fields.Date(string='Fecha Vencimiento')
    currency_id = fields.Many2one('res.currency', string='Moneda')
    amount_total = fields.Char(string='Total Factura')
    importe_secundario = fields.Monetary(string='Importe Secundario (Pesos)')
    amount_residual = fields.Monetary(string='Saldo Pendiente', currency_field='currency_id')
    
    # Campos calculados para días
    dias_mora_num = fields.Integer(compute='_compute_dias', store=False)
    dias_transcurridos_num = fields.Integer(compute='_compute_dias', store=False)
    dias_mora = fields.Char(string='Días de Mora', compute='_compute_dias', store=False)
    dias_transcurridos = fields.Char(string='Días Transcurridos', compute='_compute_dias', store=False)
    
    # Campos relacionados
    salesman_id = fields.Many2one('res.users', string='Vendedor')
    invoice_payment_term_id = fields.Many2one('account.payment.term', string='Condición de Pago')
    payment_state = fields.Selection(related='move_id.payment_state', string='Estado Pago')

    @api.depends('invoice_date', 'invoice_date_due')
    def _compute_dias(self):
        today = date.today()
        for record in self:
            # Calcular días de mora
            if record.invoice_date_due:
                dias_mora = (today - record.invoice_date_due).days
                record.dias_mora_num = max(dias_mora, 0)
                record.dias_mora = f"{record.dias_mora_num} días"
            
            # Calcular días transcurridos
            if record.invoice_date:
                dias_transcurridos = (today - record.invoice_date).days
                record.dias_transcurridos_num = dias_transcurridos
                record.dias_transcurridos = f"{dias_transcurridos} días"

    @api.model
    def init(self):
        """Ejecuta consulta SQL para llenar el modelo virtual."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        query = """
            CREATE OR REPLACE VIEW {table} AS
            SELECT
                row_number() OVER () AS id,
                p.id AS partner_id,
                m.id AS move_id,
                m.invoice_date,
                m.invoice_date_due,
                m.currency_id,
                CASE 
                    WHEN m.amount_total::numeric <> 0 THEN 
                        REGEXP_REPLACE(
                            TO_CHAR(m.amount_total::numeric, 'FM9,999,999,990.00'), 
                            ',', '.', 'g'
                        ) || ' -'
                    ELSE '0,00 -'
                END AS amount_total,
                m.amount_total_signed AS importe_secundario,
                m.amount_residual,
                (CURRENT_DATE - m.invoice_date_due) AS dias_mora_num,
                (CURRENT_DATE - m.invoice_date) AS dias_transcurridos_num,
                m.invoice_user_id AS salesman_id,
                m.invoice_payment_term_id
            FROM
                account_move m
            JOIN
                res_partner p ON m.partner_id = p.id
            WHERE
                m.payment_state IN ('not_paid', 'partial')
                AND m.invoice_date_due < CURRENT_DATE
                AND m.move_type = 'out_invoice'
                AND m.state != 'draft'
            ORDER BY m.amount_residual DESC
        """.format(table=self._table)
        self.env.cr.execute(query)
        
    def action_export_to_excel(self):
        """Genera un reporte PDF de clientes morosos ordenados por mayor deuda."""
        # Obtener todos los registros
        records = self.search([])
    
        if not records:
            raise UserError("No hay registros de morosidad para exportar.")
    
        # Crear buffer para el PDF
        pdf_buffer = io.BytesIO()
    
        # Configurar documento PDF en formato horizontal con márgenes reducidos
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=landscape(letter),
            rightMargin=10,
            leftMargin=10,
            topMargin=30,
            bottomMargin=30,
            title="Reporte de Morosidad de Clientes"
        )
    
        # Estilos
        styles = getSampleStyleSheet()
        style_title = styles['Title']
        style_heading = styles['Heading2']
        style_normal = styles['Normal']
        
        # Ajustar tamaños de fuente
        style_title.fontSize = 14
        style_heading.fontSize = 10
        style_normal.fontSize = 8
    
        # Elementos del documento
        elements = []
    
        # Título del reporte
        title = Paragraph("Reporte de Morosidad de Clientes", style_title)
        elements.append(title)
    
        # Fecha de generación
        today = fields.Date.context_today(self)
        date_str = f"Generado el: {today}"
        date_paragraph = Paragraph(date_str, style_normal)
        elements.append(date_paragraph)
        elements.append(Spacer(1, 15))
    
        # Agrupar registros por cliente y calcular total por cliente
        client_totals = {}
        for record in records:
            if record.partner_id not in client_totals:
                client_totals[record.partner_id] = {
                    'records': [],
                    'total': 0.0
                }
            client_totals[record.partner_id]['records'].append(record)
            if record.importe_secundario:
                client_totals[record.partner_id]['total'] += record.importe_secundario
    
        # Ordenar clientes por total de morosidad (de mayor a menor)
        sorted_clients = sorted(client_totals.items(), 
                              key=lambda x: x[1]['total'], 
                              reverse=True)
    
        # Contador total de morosidad (convertido a ARS)
        total_mora = sum(data['total'] for partner, data in sorted_clients)
        total_text = Paragraph(f"<b>Total morosidad:</b> ARS {total_mora:,.2f}", style_normal)
        elements.append(total_text)
        elements.append(Spacer(1, 15))
    
        # Definir anchos de columnas optimizados
        col_widths = [
            80,   # Factura
            60,   # Fecha Factura
            60,   # Fecha Vencimiento
            50,   # Moneda
            70,   # Imp ppal
            70,   # Imp sec
            70,   # Saldo Pendiente
            50,   # Días de Mora
            50,   # Días Transcurridos
            70,   # Vendedor
            60    # Condición de Pago
        ]
    
        # Crear contenido para cada cliente (ordenado por morosidad)
        for partner, data in sorted_clients:
            invoices = data['records']
            cliente_mora = data['total']
    
            # Encabezado del cliente
            client_header = Paragraph(f"Cliente: {partner.name or 'Sin Nombre'}", style_heading)
            elements.append(client_header)
    
            # Total morosidad por cliente (en ARS)
            cliente_mora_text = Paragraph(f"<b>Total morosidad cliente:</b> ARS {cliente_mora:,.2f}", style_normal)
            elements.append(cliente_mora_text)
            elements.append(Spacer(1, 8))
    
            # Preparar datos para la tabla
            table_data = []
    
            # Encabezados de la tabla (con nombres abreviados)
            headers = [
                'Factura',
                'F Factura',
                'F Venc',
                'Moneda',
                'Imp ppal',
                'Imp sec',
                'Saldo Pend',
                'Días Mora',
                'Días Trans',
                'Vendedor',
                'Cond Pago'
            ]
            table_data.append(headers)
    
            # Agregar filas de facturas
            for record in invoices:
                row = [
                    record.move_id.name or '',
                    record.invoice_date.strftime('%d/%m/%Y') if record.invoice_date else '',
                    record.invoice_date_due.strftime('%d/%m/%Y') if record.invoice_date_due else '',
                    record.currency_id.name or '',
                    record.amount_total or '',
                    f"{record.importe_secundario:,.2f}" if record.importe_secundario else '0.00',
                    f"{record.amount_residual:,.2f}" if record.amount_residual else '0.00',
                    record.dias_mora or '',
                    record.dias_transcurridos or '',
                    record.salesman_id.name or '',
                    record.invoice_payment_term_id.name or ''
                ]
                table_data.append(row)
    
            # Crear tabla con los anchos definidos
            table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
            # Estilo base de la tabla
            style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 7),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#EFF2F7')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
            ])
    
            # Añadir estilos específicos para columnas monetarias
            style.add('ALIGN', (4, 1), (6, -1), 'RIGHT')  # Columnas monetarias (4-6)
    
            # Aplicar estilo alternado a las filas
            for i in range(1, len(table_data)):
                bg_color = colors.HexColor('#F8F9FA') if i % 2 == 0 else colors.white
                style.add('BACKGROUND', (0, i), (-1, i), bg_color)
    
            # Aplicar estilo a la tabla
            table.setStyle(style)
            elements.append(table)
            elements.append(Spacer(1, 15))
    
        # Construir el PDF
        doc.build(elements)
        pdf_buffer.seek(0)
    
        # Crear attachment
        attachment = self.env['ir.attachment'].create({
            'name': 'Reporte_Morosidad_Clientes.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_buffer.read()),
            'store_fname': 'Reporte_Morosidad_Clientes.pdf',
            'res_model': self._name,
            'mimetype': 'application/pdf'
        })
    
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }