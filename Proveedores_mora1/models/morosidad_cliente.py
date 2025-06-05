from odoo import models, fields, api, tools  # Asegúrate de incluir tools aquí
from datetime import date
import io
from odoo.tools import date_utils
from odoo.http import content_disposition
import base64
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from odoo.exceptions import UserError
import xlsxwriter

from odoo import models, fields, api, tools
from datetime import date

class MorosidadProveedor(models.Model):
    _name = 'morosidad.proveedor'
    _description = 'Reporte de Morosidad de Proveedores'
    _auto = False

    partner_id = fields.Many2one('res.partner', string='Proveedor')
    move_id = fields.Many2one('account.move', string='Factura')
    invoice_date = fields.Date(string='Fecha Factura')
    invoice_date_due = fields.Date(string='Fecha Vto.')
    currency_id = fields.Many2one('res.currency', string='Moneda', invisible=True)
    amount_total = fields.Char(string='Importe Factura')
    importe_secundario = fields.Monetary(string='Importe en Pesos')
    amount_residual = fields.Monetary(
        string='Saldo Pendiente',
        currency_field='currency_id'
    )
    move_type = fields.Selection([
        ('in_invoice', 'Factura'),
        ('in_refund', 'Nota de Crédito'),
        ('in_debit', 'Nota de Débito')], 
        string='Tipo')
    
    # Campos calculados
    dias_mora_num = fields.Integer(compute='_compute_dias', store=False)
    dias_transcurridos_num = fields.Integer(compute='_compute_dias', store=False)
    dias_mora = fields.Char(string='Días de Mora', compute='_compute_dias', store=False)
    dias_transcurridos = fields.Char(string='Días Transcurridos', compute='_compute_dias', store=False)
    esta_vencida = fields.Boolean(string='Vencida', compute='_compute_dias', store=False)
    
    # Campos relacionados
    invoice_payment_term_id = fields.Many2one('account.payment.term', string='Término de Pago')
    payment_state = fields.Selection([
        ('not_paid', 'No Pagado'),
        ('partial', 'Parcialmente Pagado'),
        ('paid', 'Pagado')], 
        string='Estado de Pago')

    @api.depends('invoice_date', 'invoice_date_due')
    def _compute_dias(self):
        today = date.today()
        for record in self:
            # Inicializar valores
            record.dias_mora_num = 0
            record.dias_mora = "No vencida"
            record.esta_vencida = False
            
            # Solo calcular si tiene fecha de vencimiento
            if record.invoice_date_due:
                dias_mora = (today - record.invoice_date_due).days
                if dias_mora > 0:
                    record.dias_mora_num = dias_mora
                    record.dias_mora = f"{dias_mora} días"
                    record.esta_vencida = True
                else:
                    record.dias_mora = f"Vence en {-dias_mora} días"
            
            # Calcular días transcurridos desde emisión
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
                p.name AS partner_name,
                m.id AS move_id,
                m.name AS move_name,
                m.invoice_date,
                m.invoice_date_due,
                m.currency_id,
                -- Importe Principal (formateado)
                REGEXP_REPLACE(
                    TO_CHAR(
                        CASE 
                            WHEN m.move_type = 'in_refund' THEN -m.amount_total 
                            WHEN m.move_type = 'in_debit' THEN m.amount_total
                            ELSE m.amount_total 
                        END, 
                        'FM9,999,999,990.00'
                    ), 
                    ',', '.', 'g'
                ) AS amount_total,
                -- Saldo Pendiente (en moneda original)
                CASE
                    WHEN m.move_type = 'in_refund' THEN -m.amount_residual
                    ELSE m.amount_residual
                END AS amount_residual,
                -- Saldo Pendiente en Pesos (para reporte)
                CASE
                    WHEN m.move_type = 'in_refund' THEN -m.amount_residual_signed
                    ELSE m.amount_residual_signed
                END AS importe_secundario,
                m.move_type,
                CASE
                    WHEN m.invoice_date_due IS NOT NULL THEN (CURRENT_DATE - m.invoice_date_due)
                    ELSE 0
                END AS dias_mora_num,
                m.invoice_payment_term_id,
                m.payment_state
            FROM
                account_move m
            JOIN
                res_partner p ON m.partner_id = p.id
            WHERE
                m.move_type IN ('in_invoice', 'in_refund', 'in_debit')
                AND m.state = 'posted'
                AND (m.amount_residual > 0 OR m.payment_state IN ('not_paid', 'partial'))
            ORDER BY
                m.invoice_date_due,
                CASE
                    WHEN m.move_type = 'in_refund' THEN -m.amount_residual_signed
                    ELSE m.amount_residual_signed
                END DESC
        """.format(table=self._table)
        self.env.cr.execute(query)

    def action_export_to_excel(self):
        """Genera un reporte PDF de proveedores morosos ordenados por mayor deuda."""
        try:
            # Obtener todos los registros
            records = self.search([])
            
            if not records:
                raise UserError("No hay registros de morosidad para exportar.")
            
            # Crear buffer para el PDF
            pdf_buffer = io.BytesIO()
            
            # Configurar documento PDF en formato horizontal
            doc = SimpleDocTemplate(
                pdf_buffer,
                pagesize=landscape(letter),
                rightMargin=20,
                leftMargin=20,
                topMargin=40,
                bottomMargin=30,
                title="Reporte de Morosidad de Proveedores"
            )
            
            # Estilos
            styles = getSampleStyleSheet()
            style_title = styles['Title']
            style_heading = styles['Heading2']
            style_normal = styles['Normal']
            
            # Ajustar tamaños de fuente
            style_title.fontSize = 16
            style_heading.fontSize = 12
            style_normal.fontSize = 9
            
            # Elementos del documento
            elements = []
            
            # Título del reporte
            title = Paragraph("<b>Reporte de Morosidad de Proveedores</b>", style_title)
            elements.append(title)
            
            # Fecha de generación
            today = fields.Date.context_today(self)
            date_str = f"<b>Generado el:</b> {today.strftime('%d/%m/%Y')}"
            date_paragraph = Paragraph(date_str, style_normal)
            elements.append(date_paragraph)
            elements.append(Spacer(1, 20))
            
            # Agrupar registros por proveedor y calcular total por proveedor
            supplier_totals = {}
            for record in records:
                if record.partner_id not in supplier_totals:
                    supplier_totals[record.partner_id] = {
                        'name': record.partner_id.name or 'Sin Nombre',
                        'records': [],
                        'total': 0.0
                    }
                supplier_totals[record.partner_id]['records'].append(record)
                if record.importe_secundario:
                    supplier_totals[record.partner_id]['total'] += record.importe_secundario
            
            # Ordenar proveedores por total de morosidad (de MENOR a mayor - cambio realizado aquí)
            sorted_suppliers = sorted(supplier_totals.items(), 
                                    key=lambda x: x[1]['total'])  # Eliminado reverse=True
            
            # Contador total de morosidad (convertido a ARS)
            total_mora = sum(data['total'] for partner, data in sorted_suppliers)
            total_text = Paragraph(f"<b>Total morosidad:</b> ARS {total_mora:,.2f}", style_heading)
            elements.append(total_text)
            elements.append(Spacer(1, 20))
            
            # Definir anchos de columnas optimizados (sin columna de proveedor)
            col_widths = [
                90,   # Comprobante
                60,   # Fecha Factura
                60,   # Fecha Vencimiento
                50,   # Moneda
                70,   # Imp ppal
                80,   # Imp sec (ARS)
                50,   # Días de Mora
                50,   # Días Transcurridos
                60    # Condición de Pago
            ]
            
            # Crear contenido para cada proveedor (ordenado por morosidad de MENOR a MAYOR)
            for partner, data in sorted_suppliers:  # Ya está ordenado correctamente
                invoices = data['records']
                supplier_mora = data['total']
                
                # Encabezado del proveedor
                supplier_header = Paragraph(f"<b>Proveedor:</b> {partner.name or 'Sin Nombre'}", style_heading)
                elements.append(supplier_header)
                
                # Total morosidad por proveedor (en ARS)
                supplier_mora_text = Paragraph(f"<b>Total morosidad proveedor:</b> ARS {supplier_mora:,.2f}", style_normal)
                elements.append(supplier_mora_text)
                elements.append(Spacer(1, 10))
                
                # Preparar datos para la tabla (sin columna de proveedor)
                table_data = []
                
                # Encabezados de la tabla (con nombres abreviados)
                headers = [
                    'Comprobante',
                    'F Factura',
                    'F Venc',
                    'Moneda',
                    'Imp ppal',
                    'Imp sec (ARS)',
                    'Días Mora',
                    'Días Trans',
                    'Cond Pago'
                ]
                table_data.append(headers)
                
                # Agregar filas de facturas (sin columna de proveedor)
                for record in invoices:
                    row = [
                        record.move_id.name or '-',
                        record.invoice_date.strftime('%d/%m/%Y') if record.invoice_date else '-',
                        record.invoice_date_due.strftime('%d/%m/%Y') if record.invoice_date_due else '-',
                        record.currency_id.name or '-',
                        record.amount_total or '0.00',
                        f"{record.importe_secundario:,.2f}" if record.importe_secundario else '0.00',
                        record.dias_mora or '-',
                        record.dias_transcurridos or '-',
                        record.invoice_payment_term_id.name or '-'
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
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#EFF2F7')),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('LEFTPADDING', (0, 0), (-1, -1), 3),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 3),
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
                elements.append(Spacer(1, 20))
            
            # Construir el PDF
            doc.build(elements)
            pdf_buffer.seek(0)
            
            # Crear attachment
            today = fields.Date.context_today(self)
            attachment = self.env['ir.attachment'].create({
                'name': f'Reporte_Morosidad_Proveedores_{today.strftime("%Y%m%d")}.pdf',
                'type': 'binary',
                'datas': base64.b64encode(pdf_buffer.read()),
                'store_fname': f'Reporte_Morosidad_Proveedores_{today.strftime("%Y%m%d")}.pdf',
                'res_model': self._name,
                'mimetype': 'application/pdf'
            })
            
            # Retornar acción para descargar el PDF
            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}?download=true',
                'target': 'new',
            }
            
        except Exception as e:
            raise UserError(f"Error al generar el reporte: {str(e)}")


    def action_export_to_excel_proveedores(self):
        """Genera un reporte Excel de proveedores morosos ordenados por mayor deuda."""
        try:
            # Obtener todos los registros
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
            
            # Formato para títulos de proveedor
            supplier_title_format = workbook.add_format({
                'bold': True,
                'bg_color': '#EFF2F7',
                'border': 1,
                'font_size': 10
            })
            
            # Crear hoja de cálculo
            worksheet = workbook.add_worksheet('Morosidad Proveedores')
            
            # Configurar anchos de columnas
            worksheet.set_column('A:A', 25)  # Proveedor
            worksheet.set_column('B:B', 15)  # Comprobante
            worksheet.set_column('C:C', 12)  # Fecha Factura
            worksheet.set_column('D:D', 12)  # Fecha Vencimiento
            worksheet.set_column('E:E', 10)  # Moneda
            worksheet.set_column('F:F', 15)  # Importe Principal
            worksheet.set_column('G:G', 15)  # Importe Secundario (ARS)
            worksheet.set_column('H:H', 12)  # Días de Mora
            worksheet.set_column('I:I', 12)  # Días Transcurridos
            worksheet.set_column('J:J', 20)  # Condición de Pago
            
            # Escribir título
            today = fields.Date.context_today(self)
            title = f"Reporte de Morosidad de Proveedores - Generado el {today.strftime('%d/%m/%Y')}"
            worksheet.merge_range('A1:J1', title, workbook.add_format({
                'bold': True,
                'font_size': 14,
                'align': 'center'
            }))
            
            # Escribir encabezados (fila 2)
            headers = [
                'Proveedor', 'Comprobante', 'F. Factura', 'F. Vencimiento',
                'Moneda', 'Imp. Principal', 'Imp. Secundario (ARS)', 
                'Días Mora', 'Días Transcurridos', 'Condición de Pago'
            ]
            
            worksheet.write_row(2, 0, headers, header_format)
            
            # Agrupar registros por proveedor y calcular total por proveedor
            supplier_totals = {}
            for record in records:
                if record.partner_id not in supplier_totals:
                    supplier_totals[record.partner_id] = {
                        'name': record.partner_id.name or 'Sin Nombre',
                        'records': [],
                        'total': 0.0
                    }
                supplier_totals[record.partner_id]['records'].append(record)
                if record.importe_secundario:
                    supplier_totals[record.partner_id]['total'] += record.importe_secundario
            
            # Ordenar proveedores por total de morosidad (de MENOR a mayor)
            sorted_suppliers = sorted(supplier_totals.items(), 
                                    key=lambda x: x[1]['total'])  # Orden ascendente
            
            # Contador de fila (empezamos en la fila 3 porque 0-2 son para títulos y encabezados)
            row = 3
            
            # Total general de morosidad
            total_general = 0.0
            
            # Escribir datos para cada proveedor
            for partner, data in sorted_suppliers:
                invoices = data['records']
                supplier_mora = data['total']
                total_general += supplier_mora
                
                # Escribir nombre del proveedor (merge 10 columnas)
                worksheet.merge_range(row, 0, row, 9, 
                                    f"PROVEEDOR: {data['name']}", 
                                    supplier_title_format)
                row += 1
                
                # Escribir total morosidad del proveedor
                worksheet.write(row, 0, "Total Morosidad:", workbook.add_format({
                    'bold': True,
                    'align': 'right',
                    'border': 1
                }))
                worksheet.merge_range(row, 1, row, 5, "", data_format)  # Celdas vacías para alinear
                worksheet.write(row, 6, supplier_mora, total_format)
                row += 1
                
                # Escribir facturas del proveedor
                for record in invoices:
                    worksheet.write(row, 0, data['name'], data_format)
                    worksheet.write(row, 1, record.move_id.name or '-', data_format)
                    worksheet.write(row, 2, record.invoice_date.strftime('%d/%m/%Y') if record.invoice_date else '-', data_format)
                    worksheet.write(row, 3, record.invoice_date_due.strftime('%d/%m/%Y') if record.invoice_date_due else '-', data_format)
                    worksheet.write(row, 4, record.currency_id.name or '-', data_format)
                    worksheet.write(row, 5, record.amount_total or '0.00', data_format)
                    worksheet.write(row, 6, record.importe_secundario or 0.0, amount_format)
                    worksheet.write(row, 7, record.dias_mora_num or 0, data_format)
                    worksheet.write(row, 8, record.dias_transcurridos_num or 0, data_format)
                    worksheet.write(row, 9, record.invoice_payment_term_id.name or '-', data_format)
                    row += 1
                
                # Espacio entre proveedores
                row += 1
            
            # Escribir total general
            worksheet.write(row, 0, "TOTAL GENERAL MOROSIDAD:", workbook.add_format({
                'bold': True,
                'align': 'right',
                'border': 1
            }))
            worksheet.merge_range(row, 1, row, 5, "", data_format)  # Celdas vacías para alinear
            worksheet.write(row, 6, total_general, total_format)
            
            # Cerrar libro de Excel
            workbook.close()
            excel_buffer.seek(0)
            
            # Crear attachment con fecha en el nombre
            today_str = fields.Date.context_today(self).strftime('%Y%m%d')
            attachment = self.env['ir.attachment'].create({
                'name': f'Reporte_Morosidad_Proveedores_{today_str}.xlsx',
                'type': 'binary',
                'datas': base64.b64encode(excel_buffer.read()),
                'store_fname': f'Reporte_Morosidad_Proveedores_{today_str}.xlsx',
                'res_model': self._name,
                'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            })
            
            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}?download=true',
                'target': 'self',
            }
            
        except Exception as e:
            raise UserError(f"Error al generar el reporte Excel: {str(e)}")


