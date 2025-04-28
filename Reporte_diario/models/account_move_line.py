from odoo import models, api
from collections import defaultdict
from io import BytesIO
import base64
import xlsxwriter
import subprocess
import tempfile
import os

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def action_print_pdf(self):
        # Agrupar las líneas por cuenta
        grouped_lines = defaultdict(list)
        for line in self:
            if line.move_id.state != 'draft':  # Aseguramos que no sean borradores
                grouped_lines[line.account_id].append(line)

        # Verificar si hay líneas agrupadas
        if not grouped_lines:
            raise models.ValidationError("No hay líneas para agrupar.")

        # Generar el archivo Excel
        excel_file = self.generate_excel(grouped_lines)

        # Convertir XLSX a PDF
        pdf_file = self.convert_xlsx_to_pdf(excel_file)

        # Crear un adjunto para descargar el archivo
        attachment = self.env['ir.attachment'].create({
            'name': 'Reporte_Agrupado_Por_Cuenta.pdf',
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

    def generate_excel(self, grouped_lines):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Reporte Agrupado')
    
        # Configurar la hoja en horizontal
        worksheet.set_landscape()
    
        # Expandir el ancho de la hoja
        worksheet.fit_to_pages(1, 2)  # Mantener 1 página de alto, pero 2 de ancho si es necesario
    
        # Reducir los márgenes para aprovechar el espacio
        worksheet.set_margins(left=0.2, right=0.2, top=1.0, bottom=0.5)  # Aumentamos el margen superior para el título
    
        # Definir formatos
        header_format = workbook.add_format({'bold': True, 'bg_color': '#1d1d1b', 'font_color': 'white', 'align': 'center', 'font_size': 9})
        account_format = workbook.add_format({'bold': True, 'bg_color': '#f2f2f2', 'align': 'left', 'font_size': 9})
        cell_format = workbook.add_format({'font_size': 9})  
        total_format = workbook.add_format({'bold': True, 'bg_color': '#f2f2f2', 'align': 'right', 'font_size': 9})
        currency_format = workbook.add_format({'font_size': 9, 'align': 'center'})  # Formato para la columna Moneda
        title_format = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})  # Formato para el título
        subtitle_format = workbook.add_format({'font_size': 12, 'align': 'center'})  # Formato para la fecha y empresa
    
        # Obtener la fecha del reporte (usamos la fecha de la primera línea)
        first_line_date = None
        for lines in grouped_lines.values():
            if lines:
                first_line_date = lines[0].date.strftime('%Y-%m-%d')
                break
    
        # Escribir el título
        worksheet.merge_range('A1:H1', 'Informe de Movimientos de Tesoreria - INFORME TESORERIA', title_format)
        worksheet.merge_range('A2:H2', f'Fecha: {first_line_date}', subtitle_format)
        worksheet.merge_range('A3:H3', 'Empresa - Sucursal: ING. RAMON RUSSO', subtitle_format)
    
        # Escribir encabezados de la tabla
        headers = ['Cuenta', 'Fecha', 'Comprobante', 'Diario', 'Debe', 'Haber', 'Balance', 'Moneda']
        for col, header in enumerate(headers):
            worksheet.write(3, col, header, header_format)  # Fila 3 para los encabezados
    
        # Escribir datos agrupados por cuenta
        row = 4  # Comenzar desde la fila 4
        for account, lines in grouped_lines.items():
            worksheet.write(row, 0, account.display_name, account_format)
            row += 1
    
            # Inicializar los totales
            total_debit = 0
            total_credit = 0
    
            for line in lines:
                worksheet.write(row, 1, line.date.strftime('%Y-%m-%d'), cell_format)
                worksheet.write(row, 2, line.move_id.name, cell_format)
                worksheet.write(row, 3, line.journal_id.name, cell_format)
                worksheet.write(row, 4, line.debit, cell_format)
                worksheet.write(row, 5, line.credit, cell_format)
                worksheet.write(row, 6, line.balance, cell_format)
    
                # Obtener el tipo de moneda
                currency = line.currency_id.name if line.currency_id else 'No definido'
                worksheet.write(row, 7, currency, currency_format)  # Usar currency_format para alinear el contenido
                row += 1
    
                # Acumular los totales
                total_debit += line.debit
                total_credit += line.credit
    
            # Escribir los totales por cuenta
            worksheet.write(row, 3, "Totales por Cuenta", total_format)
            worksheet.write(row, 4, total_debit, total_format)
            worksheet.write(row, 5, total_credit, total_format)
            worksheet.write(row, 6, total_debit - total_credit, total_format)
            row += 1
    
        # Aumentar los anchos de las columnas para aprovechar el espacio horizontal
        worksheet.set_column('A:A', 30)  # Cuenta
        worksheet.set_column('B:B', 15)  # Fecha
        worksheet.set_column('C:C', 25)  # Comprobante
        worksheet.set_column('D:D', 25)  # Diario
        worksheet.set_column('E:G', 18)  # Debe, Haber, Balance
        worksheet.set_column('H:H', 20)  # Moneda (aumentamos el ancho)
    
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
