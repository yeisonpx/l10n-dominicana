# © 2019 Yasmany Castillo <yasmany003@gmail.com>

# This file is part of NCF Manager.

# NCF Manager is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# NCF Manager is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with NCF Manager.  If not, see <https://www.gnu.org/licenses/>.

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
READONLY_STATES = {
    'draft': [('readonly', False)],
    'done': [('readonly', True)],
    'cancel': [('readonly', True)],
}

NCF_TYPE = {
    'normal': ('01', 'Compras Fiscales'),
    'fiscal': ('01', 'Crédito Fiscal'),
    'final': ('02', 'Consumo'),
    'debit_note': ('03', 'Nota de Débito'),
    'credit_note': ('04', 'Nota de Crédito'),
    'informal': ('11', 'Comprobante de Compras'),
    'unico': ('12', 'Registro Único de Ingresos'),
    'minor': ('13', 'Comprobante para Gastos Menores'),
    'special': ('14', 'Comprobante para Regímenes Especiales'),
    'gov': ('15', 'Comprobantes Gubernamentales'),
    'export': ('16', 'Comprobantes para Exportaciones'),
    'exterior': ('17', 'Comprobantes de Pagos al Exterior'),
    'import': ('E', 'Comprobante Fiscal Electrónico'),
}


class NcfManager(models.Model):
    _name = 'ncf.manager'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "NCF Structure"
    _order = "number_next desc, id desc"

    @api.multi
    @api.depends('sequence_id')
    def _compute_has_sequence(self):
        for ncf in self:
            ncf.has_sequence = bool(ncf.sequence_id)

    @api.multi
    @api.depends('state', 'sequence_id')
    def _compute_sequence_next(self):
        ''' Set the number_next on the sequence related to the invoice/bill/refund'''
        for ncf in self:
            if ncf.state == 'done' and ncf.sequence_id:
                seq = ncf.sequence_id._get_current_sequence()
                number_next = seq.number_next_actual
                sequence = '%%0%sd' % seq.padding % number_next
                ncf.number_next = seq.prefix + sequence

    name = fields.Char(
        string='Name',
        required=True,
        readonly=True,
        store=True,
        copy=False,
        default=lambda self: _('New'),
    )
    number_next = fields.Char(
        string='Next Number',
        readonly=True,
        store=True,
        copy=False,
        compute="_compute_sequence_next",
    )
    ncf_control = fields.Boolean(
        string='Control de NCF',
        default=False,
        copy=False,
        readonly=True,
        states=READONLY_STATES,
    )
    type = fields.Selection(
        string='NCF for',
        selection=[
            ("sale", "Sale"),
            ("purchase", "Purchase"),
        ],
        default="",
        required=True,
        readonly=True,
        states=READONLY_STATES,
    )
    sale_type = fields.Selection(
        string='Sale type',
        selection=[
            ("final", "Consumo"),
            ("fiscal", u"Crédito Fiscal"),
            ("gov", "Gubernamentales"),
            ("special", u"Regímenes Especiales"),
            ("unico", u"Único Ingreso"),
            ("export", u"Exportaciones"),
            ("credit_note", "Credit Note"),
        ],
        default="",
        copy=False,
        readonly=True,
        states=READONLY_STATES,
    )
    purchase_type = fields.Selection(
        string="Purchase type",
        selection=[
            ("normal", "Compras Fiscales"),
            ("minor", "Gastos Menores"),
            ("informal", "Comprobante de Compras"),
            ("exterior", "Pagos al Exterior"),
            ("import", "Importaciones"),
        ],
        default="",
        readonly=True,
        states=READONLY_STATES,
        copy=False,
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        required=True,
        readonly=True,
        states=READONLY_STATES,
    )
    sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Sequence',
        readonly=True,
        required=False,
    )
    has_sequence = fields.Boolean(
        help="Technical field used for usability purposes",
        compute="_compute_has_sequence",
    )
    state = fields.Selection(
        string="State",
        selection=[
            ("draft", "Draft"),
            ("done", "Done"),
            ("cancel", "Cancel"),
        ],
        default="draft",
        copy=False,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        change_default=True,
        required=True,
        readonly=True,
        default=lambda self: self.env['res.company']._company_default_get(
            'ncf.manager'),
    )
    active = fields.Boolean(string='Active', default=True, )
    invoice_ids = fields.One2many(
        comodel_name='account.invoice',
        inverse_name='ncf_id',
        string='Invoices',
        required=False,
        readonly=True,
    )

    @api.onchange('journal_id', 'type')
    def _onchange_journal_id(self):
        journal_domain = [
            ('active', '=', True),
            ('company_id', '=', self.env.user.company_id.id),
        ]

        if self.type:
            if self.type == 'sale':
                journal_domain.append(('type', '=', 'sale'))
                journals = self.journal_id.search(journal_domain)
            else:
                journal_domain.append(('type', '=', 'purchase'))
                journals = self.journal_id.search(journal_domain)

            return {
                'domain': {
                    'journal_id': [('id', 'in', journals.ids)]
                }
            }

    @api.multi
    @api.depends('type', 'sale_type', 'purchase_type', 'credit_note_control')
    def name_get(self):
        result = []
        for record in self:
            type = record.sale_type or record.purchase_type
            name = NCF_TYPE.get(type)[1]
            result.append((record.id, name))
        return result

    @api.model
    def create(self, values):
        type = values.get('sale_type') or values.get('purchase_type')
        values['name'] = NCF_TYPE.get(type)[1]
        return super(NcfManager, self).create(values)

    @api.multi
    def unlink(self):
        """Allow to remove ncf."""
        for record in self:
            if record.state != 'draft':
                raise UserError(
                    _("You only can delete a record in draft state."))
            record.unlink()

    @api.multi
    def action_done(self):
        return self.write({'state': 'done'})

    @api.multi
    def action_cancel(self):
        return self.write({'state': 'cancel'})

    @api.multi
    def create_sequence(self):
        """Create a new sequence if not exist for this ncf."""
        sequence_obj = self.env['ir.sequence']
        sequence = sequence_obj.search(
            [
                ('company_id', '=', self.company_id.id),
                ('ncf_id', '=', self.id)
            ],
        )
        if sequence:
            return self.write({'sequence_id': sequence.id})

        sequence_values = {
            'implementation': 'no_gap',
            'padding': 8,
            'number_increment': 1,
            'use_date_range': False,
            'company_id': self.company_id.id,
            'ncf_id': self.id,
        }

        type = self.sale_type or self.purchase_type
        sequence_values['name'] = NCF_TYPE.get(type)[1]
        sequence_values['prefix'] = "B%s" % NCF_TYPE.get(type)[0]

        sequence_id = sequence_obj.create(sequence_values)
        return self.write({
            'sequence_id': sequence_id.id,
            'has_sequence': True,
        })


