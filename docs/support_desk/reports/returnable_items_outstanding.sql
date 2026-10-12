-- N2  Returnable Items Outstanding  (Query Report on "Returnable Gate Pass")
-- Every loaner still with a customer, oldest due date first.
SELECT
    gp.name                  AS "Gate Pass:Link/Returnable Gate Pass:140",
    gp.customer              AS "Customer:Link/Customer:180",
    gp.item_code             AS "Item:Link/Item:140",
    gp.serial_no             AS "Serial No:Link/Serial No:140",
    gp.issue_date            AS "Issued On:Date:100",
    gp.expected_return_date  AS "Due On:Date:100",
    GREATEST(DATEDIFF(CURDATE(), gp.expected_return_date), 0) AS "Days Overdue:Int:100",
    gp.repair_order          AS "Repair Order:Link/Repair Order:140"
FROM `tabReturnable Gate Pass` gp
WHERE gp.docstatus = 1
  AND gp.status IN ('Open', 'Overdue')
ORDER BY gp.expected_return_date
