import frappe
from frappe.utils import  cint,flt, get_link_to_form
from frappe import _, msgprint, throw
import erpnext
from frappe.utils import cint, cstr, flt, formatdate, get_link_to_form, getdate, nowdate
from erpnext.accounts.deferred_revenue import validate_service_stop_date
from erpnext.accounts.utils import get_account_currency, get_fiscal_year


from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice,make_regional_gl_entries
from erpnext.accounts.doctype.sales_invoice.sales_invoice import (
	check_if_return_invoice_linked_with_payment_entry,
	get_total_in_party_account_currency,
	is_overdue,
	validate_inter_company_party,
)
from erpnext.accounts.general_ledger import (
	merge_similar_entries,
)
class CustomPurchaseInvoice(PurchaseInvoice):
    def get_gl_entries(self, warehouse_account=None):
        self.auto_accounting_for_stock = erpnext.is_perpetual_inventory_enabled(self.company)

        if self.auto_accounting_for_stock:
            self.stock_received_but_not_billed = self.get_company_default("stock_received_but_not_billed")
        else:
            self.stock_received_but_not_billed = None

        self.negative_expense_to_be_booked = 0.0
        gl_entries = []

        self.make_supplier_gl_entry(gl_entries)
        self.make_item_gl_entries(gl_entries)
        self.make_precision_loss_gl_entry(gl_entries)

        self.make_tax_gl_entries(gl_entries)
        self.make_internal_transfer_gl_entries(gl_entries)
        
        self.make_payment_gl_entries_party(gl_entries)

        gl_entries = make_regional_gl_entries(gl_entries, self)

        gl_entries = merge_similar_entries(gl_entries)

        self.make_payment_gl_entries(gl_entries)
        self.make_write_off_gl_entry(gl_entries)
        self.make_gle_for_rounding_adjustment(gl_entries)
        
        return gl_entries
    
    




    def make_payment_gl_entries_party(self, gl_entries):
            if cint(self.is_paid):
             frappe.msgprint(f"Commission journal entry created for you {self.outstanding_amount}")

		# Make Cash GL Entries
            if cint(self.paid_by_party) :
                gl_entries.append(
                        self.get_gl_dict(
                            {
                                "account": self.credit_to,
                                "party_type": "Supplier",
                                "party": self.supplier,
                                "against": self.custom_account,
                                "debit": self.custom_paid_amount_by_party,
                                "debit_in_account_currency": self.custom_paid_amount_by_party

                                if self.party_account_currency == self.company_currency
                                else self.custom_paid_amount_by_part,
                                "against_voucher": self.return_against
                                if cint(self.is_return) and self.return_against
                                else self.name,
                                "against_voucher_type": self.doctype,
                            #   "cost_center": self.cost_center,
                                #"project": self.project,
                            },
                            self.party_account_currency,
                            item=self,
                        )
                    )

                gl_entries.append(
                    self.get_gl_dict(
                        {
                            "account": self.custom_account,
                            "party_type": self.custom_party_type,
                            "party":self.custom_party,


                            "against": self.supplier,
                            "credit": self.custom_paid_amount_by_party,
                            "credit_in_account_currency": self.custom_paid_amount_by_party
                            # if bank_account_currency == self.company_currency
                            # else self.paid_amount,
                            # "cost_center": self.cost_center,
                        },
                        item=self,
                    )
                )
    def validate(self):
            if not self.is_opening:
                self.is_opening = "No"

            self.validate_posting_time()

            super().validate()

            if not self.is_return:
                self.po_required()
                self.pr_required()
                self.validate_supplier_invoice()

            # validate cash purchase
            if self.is_paid == 1:
                self.validate_cash()

            # validate service stop date to lie in between start and end date
            validate_service_stop_date(self)

            self.validate_release_date()
            self.check_conversion_rate()
            self.validate_credit_to_acc()
            self.clear_unallocated_advances("Purchase Invoice Advance", "advances")
            self.check_on_hold_or_closed_status()
            self.validate_with_previous_doc()
            self.validate_uom_is_integer("uom", "qty")
            self.validate_uom_is_integer("stock_uom", "stock_qty")
            self.set_expense_account(for_validate=True)
            self.validate_expense_account()
            self.set_against_expense_account()
            self.validate_write_off_account()
            self.validate_multiple_billing("Purchase Receipt", "pr_detail", "amount")
            self.create_remarks()
            self.set_status()
            self.set_status_party()
            self.validate_purchase_receipt_if_update_stock()
            validate_inter_company_party(
                self.doctype, self.supplier, self.company, self.inter_company_invoice_reference
            )
            self.reset_default_field_value("set_warehouse", "items", "warehouse")
            self.reset_default_field_value("rejected_warehouse", "items", "rejected_warehouse")
            self.reset_default_field_value("set_from_warehouse", "items", "from_warehouse")
            self.set_percentage_received()
    def set_status(self, update=False, status=None, update_modified=True):
            if self.is_new():
                if self.get("amended_from"):
                    self.status = "Draft"
                return

            outstanding_amount = flt(self.outstanding_amount, self.precision("outstanding_amount"))
            total = get_total_in_party_account_currency(self)

            if not status:
                if self.docstatus == 2:
                    status = "Cancelled"
                elif self.docstatus == 1:
                    if self.is_internal_transfer():
                        self.status = "Internal Transfer"
                    elif is_overdue(self, total):
                        self.status = "Overdue"
                    elif 0 < outstanding_amount < total:
                        self.status = "Partly Paid"
                    elif outstanding_amount > 0 and getdate(self.due_date) >= getdate():
                        self.status = "Unpaid"
                    # Check if outstanding amount is 0 due to debit note issued against invoice
                    elif self.is_return == 0 and frappe.db.get_value(
                        "Purchase Invoice", {"is_return": 1, "return_against": self.name, "docstatus": 1}
                    ):
                        self.status = "Debit Note Issued"
                    elif self.is_return == 1:
                        self.status = "Return"
                    elif outstanding_amount <= 0:
                        self.status = "Paid"
                    else:
                        self.status = "Submitted"
                else:
                    self.status = "Draft"

            if update:
                self.db_set("status", self.status, update_modified=update_modified)
    def set_status_party(self, update=False, status=None, update_modified=True):
        if self.is_new():
            if self.get("amended_from"):
                self.status = "Draft"
            return

        
        paid_amount_by_party = flt(self.custom_paid_amount_by_party, self.precision("custom_paid_amount_by_party"))
        
        self.outstanding_amount = flt(self.outstanding_amount -paid_amount_by_party)
        outstanding_amount = flt(self.outstanding_amount, self.precision("outstanding_amount"))
        total = get_total_in_party_account_currency(self)

        if not status:
            if self.docstatus == 2:
                status = "Cancelled"
            elif self.docstatus == 1:
                if self.is_internal_transfer():
                    self.status = "Internal Transfer"
                elif is_overdue(self, total):
                    self.status = "Overdue"
                elif 0 < outstanding_amount < total:
                    self.status = "Partly Paid"
                elif paid_amount_by_party >= total:
                    self.status = "Paid"
                elif outstanding_amount > 0 and getdate(self.due_date) >= getdate():
                    self.status = "Unpaid"
                elif self.is_return == 0 and frappe.db.get_value(
                    "Purchase Invoice", {"is_return": 1, "return_against": self.name, "docstatus": 1}
                ):
                    self.status = "Debit Note Issued"
                elif self.is_return == 1:
                    self.status = "Return"
                else:
                    self.status = "Submitted"
            else:
                self.status = "Draft"

        if update:
            self.db_set("status", self.status, update_modified=update_modified) 
            frappe.msgprint(f"Commission journal entry created for you")
          

    def make_tax_gl_entries(self, gl_entries):
		# tax table gl entries
            valuation_tax = {}
            total_tax_amount = 70

            for tax in self.get("taxes"):
                amount, base_amount = self.get_tax_amounts(tax, None)
                if tax.category in ("Total", "Valuation and Total") and flt(base_amount):
                    account_currency = get_account_currency(tax.account_head)

                    dr_or_cr = "debit" if tax.add_deduct_tax == "Add" else "credit"

                    gl_entries.append(
                        self.get_gl_dict(
                            {
                                "account": tax.account_head,
                                "against": self.supplier,
                                dr_or_cr: base_amount,
                                dr_or_cr + "_in_account_currency": base_amount
                                if account_currency == self.company_currency
                                else amount,
                                "cost_center": tax.cost_center,
                            },
                            account_currency,
                            item=tax,
                        )
                    )
                         # إضافة قيمة الضريبة للمتغير الإجمالي
                    total_tax_amount += base_amount
                    self.paid_amount = total_tax_amount

                # accumulate valuation tax
                if (
                    self.is_opening == "No"
                    and tax.category in ("Valuation", "Valuation and Total")
                    and flt(base_amount)
                    and not self.is_internal_transfer()
                ):
                    if self.auto_accounting_for_stock and not tax.cost_center:
                        frappe.throw(
                            _("Cost Center is required in row {0} in Taxes table for type {1}").format(
                                tax.idx, _(tax.category)
                            )
                        )
                    valuation_tax.setdefault(tax.name, 0)
                    valuation_tax[tax.name] += (tax.add_deduct_tax == "Add" and 1 or -1) * flt(base_amount)

            if self.is_opening == "No" and self.negative_expense_to_be_booked and valuation_tax:
                # credit valuation tax amount in "Expenses Included In Valuation"
                # this will balance out valuation amount included in cost of goods sold

                total_valuation_amount = sum(valuation_tax.values())
                amount_including_divisional_loss = self.negative_expense_to_be_booked
                i = 1
                for tax in self.get("taxes"):
                    if valuation_tax.get(tax.name):
                        if i == len(valuation_tax):
                            applicable_amount = amount_including_divisional_loss
                        else:
                            applicable_amount = self.negative_expense_to_be_booked * (
                                valuation_tax[tax.name] / total_valuation_amount
                            )
                            amount_including_divisional_loss -= applicable_amount

                        gl_entries.append(
                            self.get_gl_dict(
                                {
                                    "account": tax.account_head,
                                    "cost_center": tax.cost_center,
                                    "against": self.supplier,
                                    "credit": applicable_amount,
                                    "remarks": self.remarks or _("Accounting Entry for Stock"),
                                },
                                item=tax,
                            )
                        )

                        i += 1

            if self.auto_accounting_for_stock and self.update_stock and valuation_tax:
                for tax in self.get("taxes"):
                    if valuation_tax.get(tax.name):
                        gl_entries.append(
                            self.get_gl_dict(
                                {
                                    "account": tax.account_head,
                                    "cost_center": tax.cost_center,
                                    "against": self.supplier,
                                    "credit": valuation_tax[tax.name],
                                    "remarks": self.remarks or _("Accounting Entry for Stock"),
                                },
                                item=tax,
                            )
                        )
        
