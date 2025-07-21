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
import xlsxwriter


from odoo import models, fields, api, tools
from datetime import date

from odoo import models, fields, api, tools
from datetime import date

from odoo import models, fields, api, tools
from datetime import date

class MorosidadCliente(models.Model):
    _name = 'morosidad.cliente'
    _description = 'Reporte de Morosidad de Clientes'
    _auto = False

    partner_id = fields.Many2one('res.partner', string='Cliente')
    move_id = fields.Many2one('account.move', string='Documento')
    move_type = fields.Selection([
        ('out_invoice', 'Factura'),
        ('out_refund', 'Nota de Crédito')],
        string='Tipo', readonly=True
    )
    invoice_date = fields.Date(string='Fecha Documento')
    invoice_date_due = fields.Date(string='Fecha Vencimiento')
    currency_id = fields.Many2one('res.currency', string='Moneda')
    amount_total = fields.Char(string='Total Documento')
    importe_secundario = fields.Monetary(string='Importe en Pesos')

    # Saldo pendiente
    currency_ars_id = fields.Many2one(
        'res.currency', string='Moneda ARS', compute='_compute_currency_ars', store=False
    )
    amount_residual = fields.Monetary(
        string='Saldo Pendiente', currency_field='currency_ars_id'
    )
    amount_residual_secundario = fields.Monetary(
        string='Saldo Pendiente en Pesos'
    )

    # Campos calculados para días
    dias_mora_num = fields.Integer(compute='_compute_dias', store=False)
    dias_transcurridos_num = fields.Integer(compute='_compute_dias', store=False)
    dias_mora = fields.Char(string='Días de Mora', compute='_compute_dias', store=False)
    dias_transcurridos = fields.Char(string='Días Transcurridos', compute='_compute_dias', store=False)
    esta_vencida = fields.Boolean(string='¿Está Vencida?', compute='_compute_dias', store=False)

    # Campos relacionados
    salesman_id = fields.Many2one('res.users', string='Vendedor')
    invoice_payment_term_id = fields.Many2one('account.payment.term', string='Condición de Pago')
    payment_state = fields.Selection([
        ('not_paid', 'No Pagado'),
        ('partial', 'Parcialmente Pagado'),
        ('paid', 'Pagado'),
        ('invoicing', 'Facturación'),
        ('reversed', 'Revertido')],
        string='Estado de Pago'
    )

    @api.depends()
    def _compute_currency_ars(self):
        moneda_ars = self.env.ref('base.ARS')
        for record in self:
            record.currency_ars_id = moneda_ars

    @api.depends('invoice_date', 'invoice_date_due')
    def _compute_dias(self):
        today = date.today()
        for record in self:
            record.dias_mora_num = 0
            record.dias_mora = "No vencida"
            record.esta_vencida = False

            if record.invoice_date_due:
                dias_mora = (today - record.invoice_date_due).days
                if dias_mora > 0:
                    record.dias_mora_num = dias_mora
                    record.dias_mora = f"{dias_mora} días"
                    record.esta_vencida = True
                else:
                    record.dias_mora = f"Vence en {-dias_mora} días"

            if record.invoice_date:
                dias_transcurridos = (today - record.invoice_date).days
                record.dias_transcurridos_num = dias_transcurridos
                record.dias_transcurridos = f"{dias_transcurridos} días"

    @api.model
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        query = """
            CREATE OR REPLACE VIEW {table} AS
            SELECT
                row_number() OVER () AS id,
                p.id AS partner_id,
                m.id AS move_id,
                m.move_type,
                m.invoice_date,
                m.invoice_date_due,
                m.currency_id,
                -- Importe formateado mostrando negativo para notas de crédito
                REGEXP_REPLACE(
                    TO_CHAR(
                        CASE 
                            WHEN m.move_type = 'out_refund' THEN -m.amount_total 
                            ELSE m.amount_total 
                        END, 
                        'FM9,999,999,990.00'
                    ), 
                    ',', '.', 'g'
                ) AS amount_total,
                -- Importe en moneda secundaria (con signo correcto)
                CASE
                    WHEN m.move_type = 'out_refund' THEN -m.amount_total_signed
                    ELSE m.amount_total_signed
                END AS importe_secundario,
                -- Saldo pendiente (mostrando negativo para notas de crédito)
                CASE
                    WHEN m.move_type = 'out_refund' THEN -m.amount_residual
                    ELSE m.amount_residual
                END AS amount_residual,
                -- Saldo pendiente en moneda secundaria (con signo correcto)
                CASE
                    WHEN m.move_type = 'out_refund' THEN -m.amount_residual_signed
                    ELSE m.amount_residual_signed
                END AS amount_residual_secundario,
                m.invoice_user_id AS salesman_id,
                m.invoice_payment_term_id,
                m.payment_state
            FROM
                account_move m
            JOIN
                res_partner p ON m.partner_id = p.id
            WHERE
                m.move_type IN ('out_invoice', 'out_refund')
                AND m.state = 'posted'
                AND (
                    -- Mostrar facturas con saldo pendiente
                    (m.move_type = 'out_invoice' AND (m.amount_residual > 0 OR m.payment_state IN ('not_paid', 'partial')))
                    OR
                    -- Mostrar TODAS las notas de crédito (incluso las pagadas)
                    (m.move_type = 'out_refund')
                )
            ORDER BY 
                p.name,
                CASE WHEN m.invoice_date_due IS NULL THEN 0 ELSE 1 END,
                m.invoice_date_due
        """.format(table=self._table)
        self.env.cr.execute(query)
        
    def action_export_to_pdf(self):
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
            if record.amount_residual:
                client_totals[record.partner_id]['total'] += record.amount_residual
    
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
    
            # ORDENAMIENTO CLAVE: Ordenar facturas por días de mora (de mayor a menor)
            sorted_invoices = sorted(invoices, key=lambda r: r.dias_mora_num or 0, reverse=True)
            
            # Agregar filas de facturas (ordenadas por días de mora)
            for record in sorted_invoices:
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

    
    def action_export_to_excel(self):
            """Genera un reporte Excel de clientes morosos ordenados por mayor deuda y días de mora."""
            records = self.search([])
            
            if not records:
                raise UserError("No hay registros de morosidad para exportar.")
            
            # Crear buffer para el Excel
            excel_buffer = io.BytesIO()
            
            # Crear libro de Excel
            workbook = xlsxwriter.Workbook(excel_buffer, {
                'in_memory': True,
                'strings_to_numbers': True
            })
            
            # Formato para encabezados
            header_format = workbook.add_format({
                'bold': True,
                'font_color': 'white',
                'bg_color': '#4472C4',
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'font_size': 10
            })
            
            # Formato para datos
            data_format = workbook.add_format({
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
                'font_size': 9
            })
            
            # Formato para montos (alineación derecha)
            amount_format = workbook.add_format({
                'border': 1,
                'align': 'right',
                'valign': 'vcenter',
                'font_size': 9,
                'num_format': '#,##0.00'
            })
            
            # Formato para totales
            total_format = workbook.add_format({
                'bold': True,
                'border': 1,
                'align': 'right',
                'valign': 'vcenter',
                'font_size': 9,
                'num_format': '#,##0.00'
            })
            
            # Crear hoja de cálculo
            worksheet = workbook.add_worksheet('Morosidad Clientes')
            
            # Configurar anchos de columnas
            worksheet.set_column('A:A', 20)  # Cliente
            worksheet.set_column('B:B', 15)  # Factura
            worksheet.set_column('C:C', 12)  # Fecha Factura
            worksheet.set_column('D:D', 12)  # Fecha Vencimiento
            worksheet.set_column('E:E', 10)  # Moneda
            worksheet.set_column('F:F', 15)  # Importe Principal
            worksheet.set_column('G:G', 15)  # Importe Secundario
            worksheet.set_column('H:H', 15)  # Saldo Pendiente
            worksheet.set_column('I:I', 12)  # Días de Mora
            worksheet.set_column('J:J', 12)  # Días Transcurridos
            worksheet.set_column('K:K', 20)  # Vendedor
            worksheet.set_column('L:L', 20)  # Condición de Pago
            
            # Escribir título
            today = fields.Date.context_today(self)
            title = f"Reporte de Morosidad de Clientes - Generado el {today}"
            worksheet.merge_range('A1:L1', title, workbook.add_format({
                'bold': True,
                'font_size': 14,
                'align': 'center'
            }))
            
            # Escribir encabezados
            headers = [
                'Cliente', 'Factura', 'F. Factura', 'F. Vencimiento',
                'Moneda', 'Imp. Principal', 'Imp. Secundario (ARS)', 
                'Saldo Pendiente', 'Días Mora', 'Días Transcurridos',
                'Vendedor', 'Condición de Pago'
            ]
            
            worksheet.write_row(2, 0, headers, header_format)
            
            # Agrupar registros por cliente y calcular total por cliente
            client_totals = {}
            for record in records:
                if record.partner_id not in client_totals:
                    client_totals[record.partner_id] = {
                        'records': [],
                        'total': 0.0
                    }
                client_totals[record.partner_id]['records'].append(record)
                if record.amount_residual:
                    client_totals[record.partner_id]['total'] += record.amount_residual
            
            # Ordenar clientes por total de morosidad (de mayor a menor)
            sorted_clients = sorted(client_totals.items(), 
                                  key=lambda x: x[1]['total'], 
                                  reverse=True)
            
            # Contador de fila (empezamos en la fila 3 porque 0-2 son para títulos y encabezados)
            row = 3
            
            # Total general de morosidad
            total_general = 0.0
            
            # Escribir datos para cada cliente
            for partner, data in sorted_clients:
                invoices = data['records']
                cliente_mora = data['total']
                total_general += cliente_mora
                
                # Escribir nombre del cliente (merge 12 columnas)
                worksheet.merge_range(row, 0, row, 11, 
                                     f"CLIENTE: {partner.name}", 
                                     workbook.add_format({
                                         'bold': True,
                                         'bg_color': '#EFF2F7',
                                         'border': 1
                                     }))
                row += 1
                
                # Escribir total morosidad del cliente
                worksheet.write(row, 0, "Total Morosidad:", workbook.add_format({
                    'bold': True,
                    'align': 'right',
                    'border': 1
                }))
                worksheet.write(row, 6, cliente_mora, total_format)
                row += 1
                
                # ORDENAMIENTO CLAVE: Ordenar facturas por días de mora (de mayor a menor)
                sorted_invoices = sorted(invoices, key=lambda r: r.dias_mora_num or 0, reverse=True)
                
                # Escribir facturas del cliente (ordenadas por días de mora)
                for record in sorted_invoices:
                    worksheet.write(row, 0, partner.name, data_format)
                    worksheet.write(row, 1, record.move_id.name or '', data_format)
                    worksheet.write(row, 2, record.invoice_date.strftime('%d/%m/%Y') if record.invoice_date else '', data_format)
                    worksheet.write(row, 3, record.invoice_date_due.strftime('%d/%m/%Y') if record.invoice_date_due else '', data_format)
                    worksheet.write(row, 4, record.currency_id.name or '', data_format)
                    worksheet.write(row, 5, record.amount_total or '', data_format)
                    worksheet.write(row, 6, record.importe_secundario or 0.0, amount_format)
                    worksheet.write(row, 7, record.amount_residual or 0.0, amount_format)
                    worksheet.write(row, 8, record.dias_mora_num or 0, data_format)
                    worksheet.write(row, 9, record.dias_transcurridos_num or 0, data_format)
                    worksheet.write(row, 10, record.salesman_id.name or '', data_format)
                    worksheet.write(row, 11, record.invoice_payment_term_id.name or '', data_format)
                    row += 1
                
                # Espacio entre clientes
                row += 1
            
            # Escribir total general
            worksheet.write(row, 0, "TOTAL GENERAL MOROSIDAD:", workbook.add_format({
                'bold': True,
                'align': 'right',
                'border': 1
            }))
            worksheet.write(row, 6, total_general, total_format)
            
            # Cerrar libro de Excel
            workbook.close()
            excel_buffer.seek(0)
            
            # Crear attachment
            attachment = self.env['ir.attachment'].create({
                'name': 'Reporte_Morosidad_Clientes.xlsx',
                'type': 'binary',
                'datas': base64.b64encode(excel_buffer.read()),
                'store_fname': 'Reporte_Morosidad_Clientes.xlsx',
                'res_model': self._name,
                'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            })
            
            return {
                    'type': 'ir.actions.act_url',
                    'url': '/web/content/%s?download=true' % attachment.id,
                    'target': 'self',
                }
      
