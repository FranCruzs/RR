{
    'name': 'Reporte de Morosidad de Clientes',
    'version': '1.0',
    'summary': 'Genera un informe de clientes morosos con facturas vencidas',
    'description': '''
        Muestra clientes con saldos pendientes, días de mora y comprobantes asociados.
    ''',
    'author': 'Tu Nombre',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'views/morosidad_proveedor_views.xml',
   
    ],
    'installable': True,
    'application': True,
}