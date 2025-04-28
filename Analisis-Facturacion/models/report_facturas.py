from odoo import models, fields, api
from io import BytesIO
import base64
import xlsxwriter
import tempfile
import os
import subprocess

class AccountMove(models.Model):
    _inherit = 'account.move'

    def generate_excel(self, invoices):
        """Genera un archivo Excel con las facturas, agrupadas por partner (cliente o proveedor)."""
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Reporte de Facturas')

        # Configurar la hoja en horizontal
        worksheet.set_landscape()

        # Definir formatos
        title_format = workbook.add_format({'bold': True, 'font_size': 12, 'align': 'center'})
        subtitle_format = workbook.add_format({'bold': True, 'font_size': 10, 'align': 'left'})
        cell_format = workbook.add_format({'font_size': 8})
        header_format = workbook.add_format({'bold': True, 'bg_color': '#1d1d1b', 'font_color': 'white', 'align': 'center', 'font_size': 8})
        total_format = workbook.add_format({'bold': True, 'bg_color': '#f2f2f2', 'align': 'right', 'font_size': 8})

        # Determinar el título y el nombre de la columna según el tipo de factura
        if invoices and invoices[0].move_type in ('out_invoice', 'out_refund'):
            titulo = 'Análisis de Facturas de Clientes - ANALISIS DE FACTURACION DE CLIENTES IRR'
            columna_partner = 'Cliente'
        elif invoices and invoices[0].move_type in ('in_invoice', 'in_refund'):
            titulo = 'Análisis de Facturas de Proveedores - ANALISIS DE FACTURACION DE PROVEEDORES IRR'
            columna_partner = 'Proveedor'
        else:
            titulo = 'Análisis de Facturas - REPORTE GENERAL'
            columna_partner = 'Partner'

        # Agregar título
        worksheet.merge_range('A1:H1', titulo, title_format)

        # Obtener la fecha de la primera factura (si hay facturas)
        fecha_factura = invoices[0].invoice_date.strftime('%Y-%m-%d') if invoices and invoices[0].invoice_date else 'N/A'

        # Agregar subtítulos
        worksheet.write('A3', f'Fecha: {fecha_factura}', subtitle_format)
        worksheet.write('A4', 'Empresa-Sucursal: Ing. Ramón Russo', subtitle_format)

        # Escribir encabezados
        headers = [
            columna_partner, 'Comprobante', 'Tipo de Documento', 'Condición de Pago',
            'Vendedor', 'Importe (Pesos)', 'Cotización', 'Moneda'
        ]
        for col, header in enumerate(headers):
            worksheet.write(6, col, header, header_format)  # Encabezados en la fila 7 (índice 6)

        # Agrupar facturas por partner (cliente o proveedor)
        grouped_invoices = {}
        for invoice in invoices:
            if invoice.partner_id.name not in grouped_invoices:
                grouped_invoices[invoice.partner_id.name] = []
            grouped_invoices[invoice.partner_id.name].append(invoice)

        # Escribir datos agrupados por partner
        row = 7  # Comenzamos después de los encabezados
        for partner, facturas in grouped_invoices.items():
            # Escribir el nombre del partner
            worksheet.write(row, 0, partner, workbook.add_format({'bold': True, 'font_size': 8}))
            row += 1

            # Escribir las facturas del partner
            for factura in facturas:
                # Calcular importe en pesos (si la moneda no es ARS)
                if factura.currency_id.name == 'ARS':
                    importe_pesos = factura.amount_total
                else:
                    # Usar la cotización de la factura para convertir a pesos
                    importe_pesos = factura.amount_total * (factura.computed_currency_rate or 1.0)

                worksheet.write(row, 0, partner, cell_format)  # Partner (Cliente o Proveedor)
                worksheet.write(row, 1, factura.name, cell_format)  # Comprobante
                worksheet.write(row, 2, 'Factura' if factura.move_type in ('out_invoice', 'in_invoice') else 'Sin definir', cell_format)  # Tipo de Documento
                worksheet.write(row, 3, factura.invoice_payment_term_id.name or 'No definido', cell_format)  # Condición de Pago
                worksheet.write(row, 4, factura.invoice_user_id.name or 'Sin Vendedor', cell_format)  # Vendedor
                worksheet.write(row, 5, importe_pesos, cell_format)  # Importe en pesos
                worksheet.write(row, 6, factura.computed_currency_rate or 1.0, cell_format)  # Cotización
                worksheet.write(row, 7, factura.currency_id.name, cell_format)  # Moneda
                row += 1

            # Calcular el total de facturas para el partner (en pesos)
            total_facturas = sum(
                factura.amount_total if factura.currency_id.name == 'ARS' 
                else factura.amount_total * (factura.computed_currency_rate or 1.0) 
                for factura in facturas
            )
            worksheet.write(row, 4, "Total", total_format)
            worksheet.write(row, 5, total_facturas, total_format)
            row += 2  # Dejar una fila en blanco entre partners

        # Ajustar anchos de columnas para aprovechar el espacio
        worksheet.set_column('A:A', 25)  # Partner (Cliente o Proveedor)
        worksheet.set_column('B:B', 20)  # Comprobante
        worksheet.set_column('C:C', 20)  # Tipo de Documento
        worksheet.set_column('D:D', 25)  # Condición de Pago
        worksheet.set_column('E:E', 20)  # Vendedor
        worksheet.set_column('F:F', 15)  # Importe
        worksheet.set_column('G:G', 15)  # Cotización
        worksheet.set_column('H:H', 15)  # Moneda

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

    def action_print_invoices_report(self):
        """Genera un reporte de facturas (tanto para proveedores como para clientes) excluyendo las borradores."""
        # Filtrar solo las facturas que no están en estado 'draft' (borrador)
        confirmed_invoices = self.filtered(lambda inv: inv.state != 'draft')

        if not confirmed_invoices:
            raise models.ValidationError("No hay facturas confirmadas para imprimir.")

        # Generar el archivo Excel
        excel_file = self.generate_excel(confirmed_invoices)
        pdf_file = self.convert_xlsx_to_pdf(excel_file)

        # Crear un adjunto para descargar el archivo
        attachment = self.env['ir.attachment'].create({
            'name': 'Reporte_Facturas.pdf',
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