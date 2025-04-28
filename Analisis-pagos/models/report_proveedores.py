from odoo import models, fields, api
from io import BytesIO
import base64
import xlsxwriter
import tempfile
import os
import subprocess


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def generate_excel(self, payments):
        """Genera un archivo Excel con los pagos, agrupados por partner (proveedor o cliente)."""
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Reporte de Pagos')
    
        # Configurar la hoja en horizontal
        worksheet.set_landscape()
    
        # Definir formatos
        title_format = workbook.add_format({'bold': True, 'font_size': 12, 'align': 'center'})
        subtitle_format = workbook.add_format({'bold': True, 'font_size': 10, 'align': 'left'})
        cell_format = workbook.add_format({'font_size': 8})
        header_format = workbook.add_format({'bold': True, 'bg_color': '#1d1d1b', 'font_color': 'white', 'align': 'center', 'font_size': 8})
        total_format = workbook.add_format({'bold': True, 'bg_color': '#f2f2f2', 'align': 'right', 'font_size': 8})
    
        # Determinar el título según el tipo de partner (proveedor o cliente)
        if payments and payments[0].partner_type == 'supplier':
            titulo = 'Análisis de Órdenes de Pago - ANALISIS DE ORDENES DE PAGO IRR'
        elif payments and payments[0].partner_type == 'customer':
            titulo = 'Análisis de Órdenes de Cobranza - ANALISIS DE ORDENES DE COBRANZA IRR'
        else:
            titulo = 'Análisis de Pagos - REPORTE GENERAL'
    
        # Agregar título
        worksheet.merge_range('A1:E1', titulo, title_format)
    
        # Obtener la fecha de la primera factura (si hay pagos)
        fecha_factura = payments[0].date.strftime('%Y-%m-%d') if payments else 'N/A'
    
        # Agregar subtítulos
        worksheet.write('A3', f'Fecha: {fecha_factura}', subtitle_format)
        worksheet.write('A4', 'Empresa-Sucursal: Ing. Ramón Russo', subtitle_format)
    
        # Escribir encabezados
        headers = ['Orden de Pago N°', 'Fecha', 'Cuenta', 'Importe (Pesos)', 'Moneda']
        for col, header in enumerate(headers):
            worksheet.write(6, col, header, header_format)  # Encabezados en la fila 7 (índice 6)
    
        # Agrupar pagos por partner (proveedor o cliente)
        grouped_payments = {}
        for payment in payments:
            if payment.partner_id.name not in grouped_payments:
                grouped_payments[payment.partner_id.name] = []
            grouped_payments[payment.partner_id.name].append(payment)
    
        # Escribir datos agrupados por partner
        row = 7  # Comenzamos después de los encabezados
        for partner, pagos in grouped_payments.items():
            # Escribir el nombre del partner (proveedor o cliente)
            worksheet.write(row, 0, partner, workbook.add_format({'bold': True, 'font_size': 8}))
            row += 1
    
            # Escribir los pagos del partner
            for pago in pagos:
                # Calcular importe en pesos (si la moneda no es ARS)
                if pago.currency_id.name == 'ARS':
                    importe_pesos = pago.amount
                else:
                    # Usar la cotización de la factura para convertir a pesos
                    importe_pesos = pago.amount * (pago.currency_rate or 1.0)

                worksheet.write(row, 0, pago.name, cell_format)  # Orden de pago
                worksheet.write(row, 1, pago.date.strftime('%Y-%m-%d'), cell_format)  # Fecha
                worksheet.write(row, 2, pago.journal_id.name, cell_format)  # Cuenta
                worksheet.write(row, 3, importe_pesos, cell_format)  # Importe total en pesos
                worksheet.write(row, 4, pago.currency_id.name, cell_format)  # Moneda
                row += 1
    
            # Calcular el total de pagos para el partner (en pesos)
            total_pagos = sum(
                pago.amount if pago.currency_id.name == 'ARS' 
                else pago.amount * (pago.currency_rate or 1.0) 
                for pago in pagos
            )
            worksheet.write(row, 2, "Total", total_format)
            worksheet.write(row, 3, total_pagos, total_format)
            row += 2  # Dejar una fila en blanco entre partners
    
        # Ajustar anchos de columnas para aprovechar el espacio
        worksheet.set_column('A:A', 25)  # Orden de Pago N°
        worksheet.set_column('B:B', 20)  # Fecha
        worksheet.set_column('C:C', 40)  # Cuenta
        worksheet.set_column('D:D', 20)  # Importe
        worksheet.set_column('E:E', 15)  # Moneda
    
        # Ajustar el tamaño de la hoja para que sea más larga
        worksheet.fit_to_pages(1, 0)  # 1 página de alto, sin límite de ancho
    
        # Cerrar libro
        workbook.close()
        output.seek(0)
        return output.read()

    def convert_xlsx_to_pdf(self, xlsx_data):
        """Convierte un archivo XLSX en PDF usando LibreOffice."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_xlsx:
            temp_xlsx.write(xlsx_data)
            temp_xlsx.flush()
            xlsx_path = temp_xlsx.name

        pdf_path = xlsx_path.replace(".xlsx", ".pdf")

        try:
            # Ejecutar LibreOffice en modo headless para convertir el archivo
            subprocess.run(
                ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", os.path.dirname(xlsx_path), xlsx_path],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Leer el archivo PDF generado
            with open(pdf_path, "rb") as pdf_file:
                pdf_data = pdf_file.read()

        finally:
            # Eliminar archivos temporales
            os.unlink(xlsx_path)
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

        return pdf_data

    def action_print_payments_report(self):
        """Genera un reporte de pagos (tanto para proveedores como para clientes) excluyendo los borradores."""
        # Filtrar solo los pagos que no están en estado 'draft' (borrador)
        confirmed_payments = self.filtered(lambda p: p.state != 'draft')
    
        if not confirmed_payments:
            raise models.ValidationError("No hay pagos confirmados para imprimir.")
    
        # Generar el archivo Excel
        excel_file = self.generate_excel(confirmed_payments)
        pdf_file = self.convert_xlsx_to_pdf(excel_file)
    
        # Crear un adjunto para descargar el archivo
        attachment = self.env['ir.attachment'].create({
            'name': 'Reporte_Pagos.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_file),
            'mimetype': 'application/pdf'
        })
    
        # Devolver la acción para descargar el archivo
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }