
// frappe.ui.form.on('Purchase Invoice', {
//     validate: function(frm) {
//         frm.set_value('custom_paid_amount_by_party', frm.doc.base_rounded_total);
//         // frm.refresh_field('custom_paid_amount_by_party');
//     },
// });

frappe.ui.form.on('Purchase Invoice Item', {
    item_code: function(frm, cdt, cdn) {
        frm.trigger('calculate_custom_paid_amount');
    },
    qty: function(frm, cdt, cdn) {
        frm.trigger('calculate_custom_paid_amount');
    },
    rate: function(frm, cdt, cdn) {
        frm.trigger('calculate_custom_paid_amount');
    }
});

frappe.ui.form.on('Purchase Invoice', {
    calculate_custom_paid_amount: function(frm) {
        frm.set_value('custom_paid_amount_by_party', frm.doc.base_rounded_total);
    }
});


frappe.ui.form.on('Purchase Invoice', {
    onload: function(frm) {
        frm.set_query('custom_party_type', function() {
            return {
                doctype: 'Party Type',
                filters: {}
            };
        });
    }
});

frappe.ui.form.on('Purchase Invoice ', {

    onload: function(frm) {
        frm.set_value('custom_paid_amount_by_party', 80 );
    },
    refresh: function(frm) {
        frm.set_value('custom_paid_amount_by_party', 80);
    }
});
frappe.ui.form.on('Purchase Invoice', {
    onload: function(frm) {
        frm.set_value('custom_paid_amount_by_party',frm.doc.base_rounded_total);
        frm.refresh_field('custom_paid_amount_by_party');
    },
    refresh: function(frm) {
        frm.set_value('custom_paid_amount_by_party', frm.doc.base_rounded_total);
        frm.refresh_field('custom_paid_amount_by_party');   
    }
});
frappe.ui.form.on('Purchase Invoice', {
    custom_party_type: function(frm) {
        frm.set_query('custom_account', function() {
            let filters = {};
            switch (frm.doc.custom_party_type) {
                case 'Customer':
                    filters = { account_type: 'Receivable' };
                    break;
                case 'Sales Partner':
                case 'Sales Person':
                case 'Shareholder':
                case 'Employee':
                case 'Supplier':
                    filters = { account_type: 'Payable' };
                    break;
                default:
                    filters = {}; // No filter
                    break;
            }
            return {
                filters: filters
            };
        });
    }
});


