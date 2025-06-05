{
    'name': 'Historial de Versiones de Órdenes de Venta',
    'version': '17.0.1.0.0',
    'summary': 'Registra el historial de cambios en órdenes de venta',
    'description': """
        Este módulo permite llevar un control de versiones de las órdenes de venta,
        registrando todos los cambios realizados y permitiendo restaurar versiones anteriores.
    """,
    'category': 'Sales',
    'author': 'Tu Nombre',
    'website': 'https://www.tuempresa.com',
    'license': 'LGPL-3',
    'depends': ['sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_history_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}