-- F1  Warranty Ending (next 30 days)  (Query Report on "Serial No")
SELECT
    sn.name                AS "Serial No:Link/Serial No:140",
    sn.item_code           AS "Item:Link/Item:140",
    sn.custom_sold_to      AS "Customer:Link/Customer:180",
    sn.custom_invoice_no   AS "Invoice:Link/Sales Invoice:140",
    sn.custom_warranty_end AS "Warranty End:Date:110",
    sn.custom_amc_enquiry_sent AS "Enquiry Sent:Check:90"
FROM `tabSerial No` sn
WHERE sn.custom_warranty_end BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)
  AND IFNULL(sn.custom_amc_status, '') != 'Active'
ORDER BY sn.custom_warranty_end
