{
    'name': 'Descuentos Adicionales en Ordenes de Compra',
    'version': '17.0.1.0.0',
    'summary': 'Agrega 3 campos adicionales de descuento en ordenes de compra',
    'description': """
        Este módulo agrega 3 campos adicionales de descuento en las líneas de ordenes de compra
        y realiza los cálculos correspondientes en el precio total.
    """,
    'category': 'Purchase',
    'author': 'Tu Nombre',
    'website': 'https://www.tusitio.com',
    'license': 'LGPL-3',
    'depends': ['purchase'],
    'data': [
        'views/purchase_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}