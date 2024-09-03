# Copyright (c) 2024, alaalsalam Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import  cint,flt, get_link_to_form
from frappe import _, msgprint, throw
import erpnext

from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice,make_regional_gl_entries
from erpnext.accounts.utils import  get_account_currency
from erpnext.assets.doctype.asset.depreciation import (
	depreciate_asset,
	get_disposal_account_and_cost_center,
	get_gl_entries_on_asset_disposal,
	get_gl_entries_on_asset_regain,
	reset_depreciation_schedule,
	reverse_depreciation_entry_made_after_disposal,
)
from erpnext.assets.doctype.asset_activity.asset_activity import add_asset_activity

class CustomSalesInvoice(SalesInvoice):

	def get_gl_entries(self, warehouse_account=None):
		from erpnext.accounts.general_ledger import merge_similar_entries

		gl_entries = []

		self.make_customer_gl_entry(gl_entries)

		self.make_tax_gl_entries(gl_entries)
		self.make_commission_gl_entries( gl_entries)
		self. make_sales_team_commission_gl_entries(gl_entries)

		self.make_internal_transfer_gl_entries(gl_entries)

		self.make_item_gl_entries(gl_entries)
		self.make_precision_loss_gl_entry(gl_entries)
		self.make_discount_gl_entries(gl_entries)

		gl_entries = make_regional_gl_entries(gl_entries, self)

		# merge gl entries before adding pos entries
		gl_entries = merge_similar_entries(gl_entries)

		self.make_loyalty_point_redemption_gle(gl_entries)
		self.make_pos_gl_entries(gl_entries)

		self.make_write_off_gl_entry(gl_entries)
		self.make_gle_for_rounding_adjustment(gl_entries)

		return gl_entries


	def make_commission_gl_entries(self, gl_entries):
			if self.sales_partner and flt(self.total_commission):
				commission_settings = frappe.get_cached_doc('Commission Settings', 'Commission Settings')
				if not commission_settings.make_gl == 1:
					return
				account_currency = get_account_currency(commission_settings.commission_account)
				total_sales_after_commission = flt(self.amount_eligible_for_commission ) - flt(self.total_commission)
				frappe.msgprint(f"Net Sales (After Commission): {total_sales_after_commission}")
				gl_entries.append(
					self.get_gl_dict(
						{
							"account": commission_settings.commission_account,  # 
							"against": commission_settings.sales_account,  
							"credit": flt(self.total_commission),  
							#"credit":flt(self.total_commission)
							#"party_type ":commission_settings.party_type,
							#
							# "party":self.sales_partner,
							
							#"debit_in_account_currency": flt(self.total_commission), ب
							"cost_center": commission_settings.cost_center,  
						},
						
						account_currency,
						item=self, 
					)
				)
		# 		gl_entries.append(
        #    			 self.get_gl_dict(
		# 			{
		# 				"account": commission_settings.sales_account, 
		# 				"against": self.customer,
		# 				"credit": flt(self.total_commission),  
		# 				#"credit_in_account_currency": flt(self.commission), 
		# 				"cost_center": commission_settings.cost_center, 
		# 			},
        #         account_currency,
        #         item=self,  
        #     )
        # )
		# 		gl_entries.append(
        #    			 self.get_gl_dict(
		# 			{
		# 				"account":self.customer, 
		# 				"against":  commission_settings.sales_account,
		# 				"credit":self.amount_eligible_for_commission ,  
		# 				#"credit_in_account_currency": flt(self.commission), 
		# 				"cost_center": commission_settings.cost_center,  
		# 			},
        #         account_currency,
        #         item=self,  # المستند المرتبط
        #     )
        # )
				frappe.msgprint(f"Commission journal entry created for you {self.sales_partner}")

				
	def make_sales_team_commission_gl_entries(self, gl_entries):
		commission_settings = frappe.get_cached_doc('Commission Settings', 'Commission Settings')

		
		if not commission_settings.make_gl == 1:
					return

		for team_member in self.get("sales_team"):
			sales_person = team_member.sales_person
			commission_rate = team_member.commission_rate
			commission_amount = team_member.incentives
			frappe.msgprint(f"Commission journal entry created for you {team_member}")


			if commission_amount > 0:
				account_currency = get_account_currency(commission_settings.commission_account)
				
				gl_entries.append(
					self.get_gl_dict(
						{
							"account": commission_settings.sales_team_account,
							"cost_center": commission_settings.cost_center,
							"credit": flt(commission_amount),
							"credit_in_account_currency": flt(commission_amount),
							"against": commission_settings.sales_account,
							"party_type": "Sales Person", 
							"party":sales_person 
,
							#"user_remark": _("Commission for {0}: {1}").format(sales_person, commission_amount)
							"user_remark": _("Commission for {0}: {1}").format(sales_person, commission_amount),
							#"remarks": _("Commission for Sales Person {0}: {1} on Sales Invoice {2}").format(sales_person, commission_amount, self.name)
						},
						account_currency,
						item=self,
					)
				)

			
				

		if self.is_internal_transfer() and flt(self.base_total_taxes_and_charges):
			account_currency = get_account_currency(self.unrealized_profit_loss_account)
			gl_entries.append(
				self.get_gl_dict(
					{
						"account": self.unrealized_profit_loss_account,
						"against": self.customer,
						"debit": flt(self.total_taxes_and_charges),
						"debit_in_account_currency": flt(self.base_total_taxes_and_charges),
						"cost_center": self.cost_center,
					},
					account_currency,
					item=self,
				)
			)

	def make_item_gl_entries(self, gl_entries):
		# income account gl entries
		enable_discount_accounting = cint(
			frappe.db.get_single_value("Selling Settings", "enable_discount_accounting")
		)
		commission_settings = frappe.get_cached_doc('Commission Settings', 'Commission Settings')
		if  commission_settings.make_gl == 1:
			total_commission=self.get("total_commission" ,0 )
			frappe.msgprint(f"commision (After Commission): {total_commission}")

		for team_member in self.get("sales_team"):
			
			commission_amount  = team_member.incentives
		
		total_commissions=commission_amount 
		frappe.msgprint(f"commision : {total_commissions}")
		
		for item in self.get("items"):
			if flt(item.base_net_amount, item.precision("base_net_amount")):
				# Do not book income for transfer within same company
				if self.is_internal_transfer():
					continue

				if item.is_fixed_asset:
					asset = self.get_asset(item)

					if self.is_return:
						fixed_asset_gl_entries = get_gl_entries_on_asset_regain(
							asset,
							item.base_net_amount,
							item.finance_book,
							self.get("doctype"),
							self.get("name"),
							self.get("posting_date"),
						)
						asset.db_set("disposal_date", None)
						add_asset_activity(asset.name, _("Asset returned"))

						if asset.calculate_depreciation:
							posting_date = frappe.db.get_value(
								"Sales Invoice", self.return_against, "posting_date"
							)
							reverse_depreciation_entry_made_after_disposal(asset, posting_date)
							notes = _(
								"This schedule was created when Asset {0} was returned through Sales Invoice {1}."
							).format(
								get_link_to_form(asset.doctype, asset.name),
								get_link_to_form(self.doctype, self.get("name")),
							)
							reset_depreciation_schedule(asset, self.posting_date, notes)
							asset.reload()

					else:
						if asset.calculate_depreciation:
							notes = _(
								"This schedule was created when Asset {0} was sold through Sales Invoice {1}."
							).format(
								get_link_to_form(asset.doctype, asset.name),
								get_link_to_form(self.doctype, self.get("name")),
							)
							depreciate_asset(asset, self.posting_date, notes)
							asset.reload()

						fixed_asset_gl_entries = get_gl_entries_on_asset_disposal(
							asset,
							item.base_net_amount,
							item.finance_book,
							self.get("doctype"),
							self.get("name"),
							self.get("posting_date"),
						)
						asset.db_set("disposal_date", self.posting_date)
						add_asset_activity(asset.name, _("Asset sold"))

					for gle in fixed_asset_gl_entries:
						gle["against"] = self.customer
						gl_entries.append(self.get_gl_dict(gle, item=item))

					self.set_asset_status(asset)

				else:
					income_account = (
						item.income_account
						if (not item.enable_deferred_revenue or self.is_return)
						else item.deferred_revenue_account
					)

					amount, base_amount = self.get_amount_and_base_amount(item, enable_discount_accounting)
					##################
				if  commission_settings.make_gl == 1:	
					if total_commission:
								base_amount -= total_commission / len(self.get("items"))  
					if total_commissions:
								base_amount -= total_commissions / len(self.get("items"))  
					

				account_currency = get_account_currency(income_account)
				gl_entries.append(
						self.get_gl_dict(
							{
								"account": income_account,
								"against": self.customer,
								"credit": flt(base_amount, item.precision("base_net_amount")),
								"credit_in_account_currency": (
									flt(base_amount, item.precision("base_net_amount"))
									if account_currency == self.company_currency
									else flt(amount, item.precision("net_amount"))
								),
								"cost_center": item.cost_center,
								"project": item.project or self.project,
							},
							account_currency,
							item=item,
						)
					)

		# expense account gl entries
		if cint(self.update_stock) and erpnext.is_perpetual_inventory_enabled(self.company):
			gl_entries += super().get_gl_entries()

