{
    'name': 'Módulo Principal',
    'version': '1.0',
    'summary': 'Descripción del módulo principal',
    'description': 'Módulo principal que incluye un submódulo.',
    'author': 'Francisco',
    'website': 'https://tusitio.com',
    'category': 'Uncategorized',
    'depends': ['base', 'account'],  # Dependencias del módulo principal
    'data': [
        'views/account_payment_views.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': True,
}