from odoo import models, fields, api
from odoo.tools import float_round

import logging

_logger=logging.getLogger(__name__)

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    # Campos visibles para cargar manualmente descuentos en cascada
    discount1 = fields.Float(string='Descuento 1 (%)', digits='Discount', default=0.0)
    discount2 = fields.Float(string='Descuento 2 (%)', digits='Discount', default=0.0)
    discount3 = fields.Float(string='Descuento 3 (%)', digits='Discount', default=0.0)
    discount4 = fields.Float(string='Descuento 4 (%)', digits='Discount', default=0.0)

    # Campo original de Odoo (se calculará automáticamente)
    discount = fields.Float(string='Descuento total (%)', digits='Discount', default=0.0, readonly=True)

    @api.onchange('discount1', 'discount2', 'discount3', 'discount4')
    @api.depends('discount1', 'discount2', 'discount3', 'discount4')
    def _compute_equivalent_discount(self):
        _logger.warning(f"*"*100)
        _logger.warning(f"_compute_equivalent_discount")
        for line in self:
            discounts = [
                float(line.discount1 or 0.0) / 100.0,
                float(line.discount2 or 0.0) / 100.0,
                float(line.discount3 or 0.0) / 100.0,
                float(line.discount4 or 0.0) / 100.0
            ]
            _logger.warning(f"discounts: {discounts}")
            factor = 1.0
            for d in discounts:
                _logger.warning(f" {factor} * (1 - {d})")
                factor *= (1 - d)
                _logger.warning(f" = {factor}")
            total_discount = (1 - factor) * 100
            _logger.warning(f"total_discount: {total_discount}")
            line.discount = float_round(total_discount, precision_digits=2)

    @api.depends('product_qty', 'price_unit', 'taxes_id', 'discount')
    def _compute_amount(self):
        for line in self:
            # Usamos solo el campo "discount" (ya calculado)
            discount = float(line.discount or 0.0) / 100.0
            price = line.price_unit * (1 - discount)

            currency = line.order_id.currency_id or line.company_id.currency_id
            price = float_round(price, precision_digits=currency.decimal_places)

            taxes = line.taxes_id.compute_all(
                price,
                currency,
                line.product_qty,
                product=line.product_id,
                partner=line.order_id.partner_id
            )

            line.update({
                'price_tax': float_round(sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])), precision_digits=currency.decimal_places),
                'price_total': float_round(taxes['total_included'], precision_digits=currency.decimal_places),
                'price_subtotal': float_round(taxes['total_excluded'], precision_digits=currency.decimal_places),
            })

    def _prepare_account_move_line(self, move=False):
        res = super(PurchaseOrderLine, self)._prepare_account_move_line(move)
        res.update({
            'discount': self.discount,
            #comente porque estos campos no existen en accoun.move.line por ende no podia crear facturas desde la orden de compra
            #'discount1': self.discount1,
            #'discount2': self.discount2,
            #'discount3': self.discount3,
            #'discount4': self.discount4,
        })
        return res
