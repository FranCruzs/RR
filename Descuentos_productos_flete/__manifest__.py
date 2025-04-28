# -*- coding: utf-8 -*-
{
    'name': "Campos Adicionales para Productos",
    'summary': """
        Añade campos d1, d2, d3, d4, flete, descuentos y cálculo de descuento total""",
    'description': """
        Este módulo añade campos adicionales para gestión de descuentos en productos:
        - Campos d1, d2, d3, d4 (float)
        - Campo flete (float)
        - Descuento mayorista y minorista (float)
        - Cálculo automático del porcentaje de descuento total en cadena
    """,
    'author': "Francisco",
    'website': "http://www.tusitio.com",
    'depends': ['product'],
    'data': [
        'views/product_template_views.xml',
    ],
    'installable': True,
   
}