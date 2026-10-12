-- N10  SIM Recharge Due  (Query Report on "Serial No")
-- Add a report filter: fieldname "days", type Int, default 60.
SELECT
    sn.name                   AS "Serial No:Link/Serial No:140",
    sn.item_code              AS "Item:Link/Item:140",
    sn.custom_sold_to         AS "Customer:Link/Customer:180",
    sn.custom_sim_no          AS "SIM No:Data:130",
    sn.custom_sim_operator    AS "Operator:Data:100",
    sn.custom_sim_valid_till  AS "Valid Till:Date:100",
    DATEDIFF(sn.custom_sim_valid_till, CURDATE()) AS "Days Left:Int:90",
    sn.custom_sim_order       AS "Service Order:Link/Sales Order:140"
FROM `tabSerial No` sn
WHERE sn.custom_sim_no IS NOT NULL AND sn.custom_sim_no != ''
  AND sn.custom_sim_valid_till <= DATE_ADD(CURDATE(), INTERVAL %(days)s DAY)
ORDER BY sn.custom_sim_valid_till
