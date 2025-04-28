{
    'name': 'Tesoreria Personalizada',
    'version': '1.0',
    'summary': 'Genera un reporte de líneas de asiento con filtro por fecha de hoy',
    'description': 'Este módulo genera un reporte de líneas de asiento con filtro por fecha de hoy.',
    'author': 'Tu Nombre',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_move_line_views.xml',
        'report/report_account_move_line_template.xml',
     
    ],
    'installable': True,
    'application': True,
}