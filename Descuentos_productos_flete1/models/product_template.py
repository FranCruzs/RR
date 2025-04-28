# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    # Campos de descuentos
    d1 = fields.Float(string='Descuento 1 (%)', digits='Discount', default=0.0)
    d2 = fields.Float(string='Descuento 2 (%)', digits='Discount', default=0.0)
    d3 = fields.Float(string='Descuento 3 (%)', digits='Discount', default=0.0)
    d4 = fields.Float(string='Descuento 4 (%)', digits='Discount', default=0.0)
    flete = fields.Float(string='Flete (%)', digits='Discount', default=0.0)
    descuento_mayorista = fields.Float(string='Descuento Mayorista (%)', digits='Discount', default=0.0)
    descuento_minorista = fields.Float(string='Descuento Minorista (%)', digits='Discount', default=0.0)
    
    # Campos calculados
    descuento_total = fields.Float(
        string='Descuento Total (%)', 
        compute='_compute_descuento_total',
        digits='Discount',
        store=True,
        help="Descuento acumulado de los descuentos aplicados, sin flete"
    )
    
    porcentaje_pagado = fields.Float(
        string='Porcentaje a Pagar (%)', 
        compute='_compute_porcentaje_pagado',
        digits='Discount',
        help="Porcentaje del precio original que se paga después de descuentos y flete"
    )

    descuento_neto_final = fields.Float(
        string='Descuento Neto Final (%)', 
        compute='_compute_descuento_neto_final',
        digits='Discount',
        help="Descuento total después de aplicar descuentos y sumar flete"
    )

    @api.constrains('d1', 'd2', 'd3', 'd4', 'flete', 'descuento_mayorista', 'descuento_minorista')
    def _check_discount_values(self):
        """Validación para asegurar que los porcentajes estén entre 0 y 100"""
        for record in self:
            if any(field < 0 or field > 100 for field in [
                record.d1, record.d2, record.d3, record.d4, 
                record.flete, record.descuento_mayorista, record.descuento_minorista
            ]):
                raise ValidationError("Todos los valores porcentuales deben estar entre 0 y 100%")

    @api.depends('d1', 'd2', 'd3', 'd4')
    def _compute_descuento_total(self):
        """Calcula el descuento total acumulado, sin incluir el flete"""
        for record in self:
            descuento_acumulado = 1.0
            for descuento in [record.d1, record.d2, record.d3, record.d4]:
                if descuento:
                    descuento_acumulado *= (1 - descuento / 100.0)
            record.descuento_total = (1 - descuento_acumulado) * 100

    @api.depends('descuento_total', 'flete')
    def _compute_porcentaje_pagado(self):
        """Calcula el porcentaje final que se paga, aplicando descuentos y flete"""
        for record in self:
            factor_descuento = (100 - record.descuento_total) / 100
            factor_flete = (1 + record.flete / 100)
            record.porcentaje_pagado = factor_descuento * factor_flete * 100

    @api.depends('porcentaje_pagado')
    def _compute_descuento_neto_final(self):
        """Calcula el descuento neto final después del flete"""
        for record in self:
            record.descuento_neto_final = 100 - record.porcentaje_pagado
