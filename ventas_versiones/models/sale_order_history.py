from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class SaleOrderHistory(models.Model):
    _name = 'sale.order.history'
    _description = 'Snapshot histórico de órdenes de venta'
    _rec_name = 'version_name'
    _order = 'change_date desc'
    
    # Referencia al SO original
    original_order_id = fields.Many2one('sale.order', string='Orden original', required=True, ondelete='cascade')
    
    # Metadatos del cambio
    user_id = fields.Many2one('res.users', string='Usuario', default=lambda self: self.env.user)
    change_date = fields.Datetime(string='Fecha de cambio', default=fields.Datetime.now)
    version_name = fields.Char(string='Versión', compute='_compute_version_name', store=True)
    version_number = fields.Float(string='Número de versión', digits=(12, 1))
    
    # Copia de campos relevantes del SO
    currency_id = fields.Many2one('res.currency', 'Moneda', required=True,
        default=lambda self: self.env.company.currency_id.id)
    partner_id = fields.Many2one('res.partner', string='Cliente')
    order_line = fields.One2many('sale.order.history.line', 'history_id', string='Líneas de orden')
    date_order = fields.Datetime(string='Fecha de orden')
    state = fields.Selection([
        ('draft', 'Cotización'),
        ('sent', 'Cotización enviada'),
        ('sale', 'Orden de venta'),
        ('done', 'Bloqueado'),
        ('cancel', 'Cancelado')
    ], string='Estado')
    
    # Campos adicionales específicos de ventas
    validity_date = fields.Date(string='Validez')
    payment_term_id = fields.Many2one('account.payment.term', string='Término de pago')
    pricelist_id = fields.Many2one('product.pricelist', string='Lista de precios')
    
    # Campos personalizados (ajustar según necesidades)
    x_campo_personalizado = fields.Char(string='Campo personalizado')
    
    @api.depends('version_number')
    def _compute_version_name(self):
        for record in self:
            record.version_name = f"Versión {record.version_number:.1f}"

    def action_restore_version(self):
        self.ensure_one()
        original = self.original_order_id
        
        if original.state in ['sale', 'done']:
            raise UserError(_("No se puede restaurar una versión en una orden confirmada o bloqueada"))
        
        # Restaurar campos principales
        vals = {
            'partner_id': self.partner_id.id,
            'date_order': self.date_order,
            'validity_date': self.validity_date,
            'payment_term_id': self.payment_term_id.id,
            'pricelist_id': self.pricelist_id.id,
    
        }
        
        original.write(vals)
        
        # Eliminar líneas existentes
        original.order_line.unlink()
        
        # Crear nuevas líneas basadas en el histórico
        for line in self.order_line:
            original.order_line.create({
                'order_id': original.id,
                'product_id': line.product_id.id,
                'product_uom_qty': line.product_uom_qty,
                'price_unit': line.price_unit,
                'tax_id': [(6, 0, line.tax_id.ids)],
                'discount': line.discount,
            })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Versión restaurada'),
                'message': _('Se ha restaurado la versión %s') % self.version_name,
                'type': 'success',
                'sticky': False,
            }
        }

class SaleOrderHistoryLine(models.Model):
    _name = 'sale.order.history.line'
    _description = 'Líneas históricas de órdenes de venta'
    
    history_id = fields.Many2one('sale.order.history', string='Historial', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Producto')
    product_uom_qty = fields.Float(string='Cantidad')
    price_unit = fields.Float(string='Precio unitario')
    tax_id = fields.Many2many('account.tax', string='Impuestos', context={'active_test': False})
    discount = fields.Float(string="Descuento (%)")
    price_subtotal = fields.Float(compute='_compute_amount', string='Subtotal', store=True)
    price_total = fields.Float(compute='_compute_amount', string='Total', store=True)
    price_tax = fields.Float(compute='_compute_amount', string='Impuesto', store=True)

    @api.depends('product_uom_qty', 'price_unit', 'tax_id', 'discount')
    def _compute_amount(self):
        for line in self:
            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            taxes = line.tax_id.compute_all(
                price,
                line.history_id.currency_id,
                line.product_uom_qty,
                product=line.product_id,
                partner=line.history_id.partner_id)
            
            line.update({
                'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                'price_total': taxes['total_included'],
                'price_subtotal': taxes['total_excluded'],
            })

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    version = fields.Float(string='Versión', default=1.0, digits=(12, 1))
    history_ids = fields.One2many('sale.order.history', 'original_order_id', string='Historial de versiones')

    def _get_next_version_number(self):
        """Calcula el siguiente número de versión basado en el estado actual"""
        self.ensure_one()
        if self.state == 'sale':
            # Versiones principales (1.0, 2.0, 3.0...)
            return float(int(self.version) + 1)
        else:
            # Versiones secundarias (1.1, 1.2, 1.3...)
            return round(self.version + 0.1, 1)

    def _create_history_record(self):
        """Crea un registro histórico con el estado actual del pedido"""
        history_vals = {
            'original_order_id': self.id,
            'partner_id': self.partner_id.id,
            'currency_id': self.currency_id.id,
            'date_order': self.date_order,
            'state': self.state,
            'validity_date': self.validity_date,
            'payment_term_id': self.payment_term_id.id,
            'pricelist_id': self.pricelist_id.id,
            'version_number': self.version,
           
        }
        
        history = self.env['sale.order.history'].create(history_vals)
        
        # Copia las líneas del pedido
        for line in self.order_line:
            self.env['sale.order.history.line'].create({
                'history_id': history.id,
                'product_id': line.product_id.id,
                'product_uom_qty': line.product_uom_qty,
                'price_unit': line.price_unit,
                'tax_id': [(6, 0, line.tax_id.ids)],
                'discount': line.discount,
            })
        return history

    def write(self, vals):
        # Crear snapshot antes de guardar cambios si no es una actualización menor
        if not vals.get('message_follower_ids'):
            for record in self:
                record._create_history_record()
                vals['version'] = record._get_next_version_number()
        
        return super().write(vals)

    def action_confirm(self):
        res = super().action_confirm()
        self.version = float(int(self.version) + 1)
        return res