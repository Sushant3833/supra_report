# Copyright (c) 2025, sushant and contributors
# For license information, please see license.txt

# import frappe



import copy

import frappe
from frappe import _
from frappe.query_builder.functions import IfNull, Sum
from frappe.utils import date_diff, flt, getdate


def execute(filters=None):
	if not filters:
		return [], []

	validate_filters(filters)

	columns = get_columns(filters)
	data = get_data(filters)

	if not data:
		return [], [], None, []

	update_received_amount(data)

	data, chart_data = prepare_data(data, filters)

	return columns, data, None, chart_data


def validate_filters(filters):
	from_date, to_date = filters.get("from_date"), filters.get("to_date")

	if not from_date and to_date:
		frappe.throw(_("From and To Dates are required."))
	elif date_diff(to_date, from_date) < 0:
		frappe.throw(_("To Date cannot be before From Date."))


# def get_data(filters):
# 	po = frappe.qb.DocType("Purchase Order")
# 	po_item = frappe.qb.DocType("Purchase Order Item")
# 	pi_item = frappe.qb.DocType("Purchase Invoice Item")

# 	query = (
# 		frappe.qb.from_(po)
# 		.inner_join(po_item)
# 		.on(po_item.parent == po.name)
# 		.left_join(pi_item)
# 		.on((pi_item.po_detail == po_item.name) & (pi_item.docstatus == 1))
# 		.select(
# 			po.transaction_date.as_("date"),
# 			po_item.schedule_date.as_("required_date"),
# 			po_item.project,
# 			po.name.as_("purchase_order"),
# 			po.status,
# 			po.supplier,
# 			po_item.item_code,
# 			po_item.qty,
# 			po_item.received_qty,
# 			(po_item.qty - po_item.received_qty).as_("pending_qty"),
# 			Sum(IfNull(pi_item.qty, 0)).as_("billed_qty"),
# 			po_item.base_amount.as_("amount"),
# 			(po_item.billed_amt * IfNull(po.conversion_rate, 1)).as_("billed_amount"),
# 			(po_item.base_amount - (po_item.billed_amt * IfNull(po.conversion_rate, 1))).as_(
# 				"pending_amount"
# 			),
# 			po.set_warehouse.as_("warehouse"),
# 			po.company,
# 			po_item.name,
# 		)
# 		.where((po_item.parent == po.name) & (po.status.notin(("Stopped", "Closed"))) & (po.docstatus == 1))
# 		.groupby(po_item.name)
# 		.orderby(po.transaction_date)
# 	)

# 	for field in ("company", "name"):
# 		if filters.get(field):
# 			query = query.where(po[field] == filters.get(field))

# 	if filters.get("from_date") and filters.get("to_date"):
# 		query = query.where(po.transaction_date.between(filters.get("from_date"), filters.get("to_date")))

# 	if filters.get("status"):
# 		query = query.where(po.status.isin(filters.get("status")))

# 	if filters.get("project"):
# 		query = query.where(po_item.project == filters.get("project"))

# 	data = query.run(as_dict=True)

# 	return data

def get_data(filters):
	po = frappe.qb.DocType("Purchase Order")
	po_item = frappe.qb.DocType("Purchase Order Item")
	pi_item = frappe.qb.DocType("Purchase Invoice Item")
	so = frappe.qb.DocType("Sales Order")

	query = (
		frappe.qb.from_(po)
		.inner_join(po_item).on(po_item.parent == po.name)
		.left_join(pi_item).on((pi_item.po_detail == po_item.name) & (pi_item.docstatus == 1))
		.left_join(so).on(so.name == po_item.sales_order)  # Join Sales Order
		.select(
			po.transaction_date.as_("date"),
			po_item.expected_delivery_date.as_("required_date"),
			po_item.project,
			po.name.as_("purchase_order"),
			po.status,
			po.supplier,
			po.supplier_name,
			po_item.item_code,
			po_item.item_name,
			po_item.description,
			po_item.qty,
			po_item.received_qty,
			(po_item.qty - po_item.received_qty).as_("pending_qty"),
			Sum(IfNull(pi_item.qty, 0)).as_("billed_qty"),
			po_item.base_amount.as_("amount"),
			(po_item.billed_amt * IfNull(po.conversion_rate, 1)).as_("billed_amount"),
			(po_item.base_amount - (po_item.billed_amt * IfNull(po.conversion_rate, 1))).as_("pending_amount"),
			po.set_warehouse.as_("warehouse"),
			po.company,
			po_item.name,
			po_item.sales_order.as_("so_no"),  # SO No.
			po_item.custom_so_item.as_("so_item_code"),  # SO Item Code
			so.customer.as_("customer"),
			so.customer_name.as_("customer_name"),  # Customer Name
			so.delivery_date.as_("so_delivery_date"),  # Sales Order Delivery Date
		)
		.where((po_item.parent == po.name) & (po.status.notin(("Stopped", "Closed"))) & (po.docstatus == 1))
		.groupby(po_item.name)
		.orderby(po.transaction_date)
	)
	# filters
	for field in ("company", "name"):
		if filters.get(field):
			query = query.where(po[field] == filters.get(field))

	if filters.get("from_date") and filters.get("to_date"):
		query = query.where(po.transaction_date.between(filters.get("from_date"), filters.get("to_date")))

	if filters.get("status"):
		query = query.where(po.status.isin(filters.get("status")))

	if filters.get("project"):
		query = query.where(po_item.project == filters.get("project"))

	data = query.run(as_dict=True)
	return data


def update_received_amount(data):
	pr_data = get_received_amount_data(data)

	for row in data:
		row.received_qty_amount = flt(pr_data.get(row.name))


def get_received_amount_data(data):
	pr = frappe.qb.DocType("Purchase Receipt")
	pr_item = frappe.qb.DocType("Purchase Receipt Item")

	po_items = [row.name for row in data]

	if not po_items:
		return frappe._dict()

	query = (
		frappe.qb.from_(pr)
		.inner_join(pr_item)
		.on(pr_item.parent == pr.name)
		.select(
			pr_item.purchase_order_item,
			Sum(pr_item.base_amount).as_("received_qty_amount"),
		)
		.where((pr.docstatus == 1) & (pr_item.purchase_order_item.isin(po_items)))
		.groupby(pr_item.purchase_order_item)
	)

	data = query.run()

	if not data:
		return frappe._dict()

	return frappe._dict(data)


def prepare_data(data, filters):
	completed, pending = 0, 0
	pending_field = "pending_amount"
	completed_field = "billed_amount"

	if filters.get("group_by_po"):
		purchase_order_map = {}

	for row in data:
		# sum data for chart
		completed += row[completed_field]
		pending += row[pending_field]

		# prepare data for report view
		row["qty_to_bill"] = flt(row["qty"]) - flt(row["billed_qty"])

		if filters.get("group_by_po"):
			po_name = row["purchase_order"]

			if po_name not in purchase_order_map:
				# create an entry
				row_copy = copy.deepcopy(row)
				purchase_order_map[po_name] = row_copy
			else:
				# update existing entry
				po_row = purchase_order_map[po_name]
				po_row["required_date"] = min(getdate(po_row["required_date"]), getdate(row["required_date"]))

				# sum numeric columns
				fields = [
					"qty",
					"received_qty",
					"pending_qty",
					"billed_qty",
					"qty_to_bill",
					"amount",
					"received_qty_amount",
					"billed_amount",
					"pending_amount",
				]
				for field in fields:
					po_row[field] = flt(row[field]) + flt(po_row[field])

	chart_data = prepare_chart_data(pending, completed)

	if filters.get("group_by_po"):
		data = []
		for po in purchase_order_map:
			data.append(purchase_order_map[po])
		return data, chart_data

	return data, chart_data


def prepare_chart_data(pending, completed):
	labels = [_("Amount to Bill"), _("Billed Amount")]

	return {
		"data": {"labels": labels, "datasets": [{"values": [pending, completed]}]},
		"type": "donut",
		"height": 300,
	}


def get_columns(filters):
	columns = [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 90},
		{"label": _("Expected Date"), "fieldname": "required_date", "fieldtype": "Date", "width": 90},
		{
			"label": _("Purchase Order"),
			"fieldname": "purchase_order",
			"fieldtype": "Link",
			"options": "Purchase Order",
			"width": 160,
		},
		# {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
		{
			"label": _("Supplier"),
			"fieldname": "supplier",
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 130,
		},
		{
				"label": _("Supplier Name"),
				"fieldname": "supplier_name",
				"fieldtype": "Data",
				"width": 120,
			},
		# {
		# 	"label": _("Project"),
		# 	"fieldname": "project",
		# 	"fieldtype": "Link",
		# 	"options": "Project",
		# 	"width": 130,
		# },
	]

	if not filters.get("group_by_po"):
		columns.append(
			{
				"label": _("Item Code"),
				"fieldname": "item_code",
				"fieldtype": "Link",
				"options": "Item",
				"width": 100,
			}
		)

	columns.extend(
		[
			{
				"label": _("Item Name"),
				"fieldname": "item_name",
				"fieldtype": "Data",
				"width": 120,
			},
			{
				"label": _("Item Description"),
				"fieldname": "description",
				"fieldtype": "Data",
				"width": 150,
			},
			{
				"label": _("Qty"),
				"fieldname": "qty",
				"fieldtype": "Float",
				"width": 120,
				"convertible": "qty",
			},
			{
				"label": _("Received Qty"),
				"fieldname": "received_qty",
				"fieldtype": "Float",
				"width": 120,
				"convertible": "qty",
			},
			{
				"label": _("Pending Qty"),
				"fieldname": "pending_qty",
				"fieldtype": "Float",
				"width": 80,
				"convertible": "qty",
			},
			# {
			# 	"label": _("Billed Qty"),
			# 	"fieldname": "billed_qty",
			# 	"fieldtype": "Float",
			# 	"width": 80,
			# 	"convertible": "qty",
			# },
			# {
			# 	"label": _("Qty to Bill"),
			# 	"fieldname": "qty_to_bill",
			# 	"fieldtype": "Float",
			# 	"width": 80,
			# 	"convertible": "qty",
			# },
			# {
			# 	"label": _("Amount"),
			# 	"fieldname": "amount",
			# 	"fieldtype": "Currency",
			# 	"width": 110,
			# 	"options": "Company:company:default_currency",
			# 	"convertible": "rate",
			# },
			# {
			# 	"label": _("Billed Amount"),
			# 	"fieldname": "billed_amount",
			# 	"fieldtype": "Currency",
			# 	"width": 110,
			# 	"options": "Company:company:default_currency",
			# 	"convertible": "rate",
			# },
			# {
			# 	"label": _("Pending Amount"),
			# 	"fieldname": "pending_amount",
			# 	"fieldtype": "Currency",
			# 	"width": 130,
			# 	"options": "Company:company:default_currency",
			# 	"convertible": "rate",
			# },
			# {
			# 	"label": _("Received Qty Amount"),
			# 	"fieldname": "received_qty_amount",
			# 	"fieldtype": "Currency",
			# 	"width": 130,
			# 	"options": "Company:company:default_currency",
			# 	"convertible": "rate",
			# },
			# {
			# 	"label": _("Warehouse"),
			# 	"fieldname": "warehouse",
			# 	"fieldtype": "Link",
			# 	"options": "Warehouse",
			# 	"width": 100,
			# },
			# {
			# 		"label": _("Company"),
			# 		"fieldname": "company",
			# 		"fieldtype": "Link",
			# 		"options": "Company",
			# 		"width": 100,
			# 	},
				{
				"label": _("SO No."),
				"fieldname": "so_no",
				"fieldtype": "Link",
				"options": "Sales Order",
				"width": 130,
			},
			{
				"label": _("Customer"),
				"fieldname": "customer",
				"fieldtype": "Link",
				"options": "Customer",
				"width": 150,
			},
			{
				"label": _("Customer Name"),
				"fieldname": "customer_name",
				"fieldtype": "Data",
				"width": 120,
			},
			{
				"label": _("SO Item Code"),
				"fieldname": "so_item_code",
				"fieldtype": "Data",
				"width": 120,
			},
			{
				"label": _("Sales Order Delivery Date"),
				"fieldname": "so_delivery_date",
				"fieldtype": "Date",
				"width": 130,
			},
		]
	)

	return columns

