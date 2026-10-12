-- F7  Serial Service History  (Query Report on "Serial No")
-- Add a mandatory report filter: fieldname "serial_no", type Link, options "Serial No".
-- One timeline per unit: tickets, repairs and AMC contracts.
SELECT * FROM (
    SELECT t.opening_date AS "Date:Date:100", 'Ticket' AS "Type:Data:90",
           t.name AS "Document:Data:150", 'HD Ticket' AS "Doc Type:Data:110",
           t.status AS "Status:Data:110", t.subject AS "Details:Data:300"
    FROM `tabHD Ticket` t
    WHERE t.custom_serial_no = %(serial_no)s
  UNION ALL
    SELECT DATE(r.creation), 'Repair', r.name, 'Repair Order', r.status, r.complaint
    FROM `tabRepair Order` r
    WHERE r.serial_no = %(serial_no)s
  UNION ALL
    SELECT so.custom_amc_start_date, 'AMC', so.name, 'Sales Order', so.custom_amc_status,
           CONCAT('AMC ', so.custom_amc_start_date, ' to ', so.custom_amc_end_date, ' / site: ', IFNULL(ci.site, ''))
    FROM `tabAMC Covered Item` ci
    JOIN `tabSales Order` so ON so.name = ci.parent AND ci.parenttype = 'Sales Order'
    WHERE ci.serial_no = %(serial_no)s AND so.docstatus = 1
) history
ORDER BY 1 DESC
