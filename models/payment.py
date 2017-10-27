# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.tools.float_utils import float_compare
from odoo.tools.translate import _

import logging
import pprint
import qrcode
import tempfile

import base64

_logger = logging.getLogger(__name__)

class PromptpayPaymentAcquirer(models.Model):
    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[('promptpayqr', 'Promptpay QR')])

    def promptpayqr_get_form_action_url(self):
        _logger.info("getting URL for promptpay")
        return '/payment/promptpay/feedback'

    def _format_transfer_data(self):
        _logger.info("Thank msg")
        company_id = self.env.user.company_id.id
        # filter only bank accounts marked as visible
        journals = self.env['account.journal'].search([('type', '=', 'bank'), ('display_on_footer', '=', True), ('company_id', '=', company_id)])
        accounts = journals.mapped('bank_account_id').name_get()
        bank_title = _('Bank Accounts') if len(accounts) > 1 else _('Bank Account')
        bank_accounts = ''.join(['<ul>'] + ['<li>%s</li>' % name for id, name in accounts] + ['</ul>'])
        post_msg = _('''<div>
<h3>Please use the following transfer details</h3>
<h4>%(bank_title)s</h4>
%(bank_accounts)s
<h4>Communication</h4>
<p>Please use the order name as communication reference.</p>
</div>''') % {
            'bank_title': bank_title,
            'bank_accounts': bank_accounts,
        }
        return post_msg

    @api.model
    def create(self, values):
        """ Hook in create to create a default post_msg. This is done in create
        to have access to the name and other creation values. If no post_msg
        or a void post_msg is given at creation, generate a default one. """
        if values.get('provider') == 'promptpayqr' and not values.get('post_msg'):
            values['post_msg'] = self._format_transfer_data()
        return super(PromptpayPaymentAcquirer, self).create(values)


class PromptpayPaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    @api.model
    def _promptpayqr_form_get_tx_from_data(self, data):
        reference, amount, currency_name = data.get('reference'), data.get('amount'), data.get('currency_name')
        tx = self.search([('reference', '=', reference)])
        if not tx or len(tx) > 1:
            error_msg = _('received data for reference %s') % (pprint.pformat(reference))
            if not tx:
                error_msg += _('; no order found')
            else:
                error_msg += _('; multiple order found')
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        _logger.info("Successed getting tx")
        lf ='\n'
        qr_string = lf.join([str(reference),str(amount),str(currency_name)])
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=5,
            border=4,
        )
        _logger.info("Successed saving...QR___1?")
        qr.add_data(qr_string)
        qr.make(fit=True)
        qr_pic = qr.make_image()
        f = tempfile.TemporaryFile(mode="r+")
        qr_pic.save('/tmp/generated_qrcode.png','png')
        f.seek(0)
        _logger.info("Successed saving...QR? /tmp/generated_qrcode.png")
        
        qr_pic1 = base64.encodestring(f.read())            

        return tx

    def _promptpayqr_form_get_invalid_parameters(self, data):
        invalid_parameters = []
        _logger.info("try to invalid")
        if float_compare(float(data.get('amount', '0.0')), self.amount, 2) != 0:
            invalid_parameters.append(('amount', data.get('amount'), '%.2f' % self.amount))
        if data.get('currency') != self.currency_id.name:
            invalid_parameters.append(('currency', data.get('currency'), self.currency_id.name))

        return invalid_parameters

    def _promptpayqr_form_validate(self, data):
        _logger.info('Validated transfer payment for tx %s: set as pending' % (self.reference))
        return self.write({'state': 'pending'})