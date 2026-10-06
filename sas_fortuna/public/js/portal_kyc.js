/* sas_fortuna: Customer / Supplier KYC pages (/customer, /supplier).
 *
 * Markup: templates/includes/kyc_form.html (shared by both pages). The page calls
 *     SASPortalKyc.initPage({ party: "supplier", label: "Supplier" })
 * which loads the record from sas_fortuna.api.<party>, draws the address / contact rows, wires the
 * TDS / MSME toggles and saves the form back with update_<party>. Server side: api/party_kyc.py.
 */
window.SASPortalKyc = (function () {
	// ---------------------------------------------------------------------------------------------
	// Generic helpers
	// ---------------------------------------------------------------------------------------------

	// Show / hide the full-screen overlay and lock the Save button while busy.
	function setLoading(overlayId, button, isLoading, message) {
		var overlay = document.getElementById(overlayId);
		if (overlay) {
			overlay.style.display = isLoading ? "flex" : "none";
			overlay.setAttribute("aria-busy", isLoading ? "true" : "false");
			var label = overlay.querySelector("[data-loading-message]");
			if (label) label.textContent = message || (isLoading ? "Saving..." : "Loading...");
		}

		if (button) {
			button.disabled = isLoading;
			button.innerHTML = isLoading
				? '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> Saving...'
				: "Save";
		}
	}

	// Normalise and validate GSTIN / PAN / Aadhaar; shows a message and returns false on the first error.
	function validateIdentityFields(form) {
		var gstinField = form.querySelector('[name="gstin"]');
		var panField = form.querySelector('[name="pan"]');
		var aadhaarField = form.querySelector('[name="custom_aadhaar_number"]');
		var gstin = gstinField ? gstinField.value.trim().toUpperCase() : "";
		var pan = panField ? panField.value.trim().toUpperCase() : "";
		var aadhaar = aadhaarField ? aadhaarField.value.replace(/\s+/g, "") : "";

		if (gstinField) gstinField.value = gstin;
		if (panField) panField.value = pan;
		if (aadhaarField) aadhaarField.value = aadhaar;

		// GSTIN check digit: mod-36 checksum over the first 14 characters
		function hasValidGstinCheckDigit(value) {
			var characters = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
			var factor = 1;
			var total = 0;

			for (var i = 0; i < value.length - 1; i++) {
				var digit = factor * characters.indexOf(value[i]);
				total += Math.floor(digit / 36) + (digit % 36);
				factor = factor === 1 ? 2 : 1;
			}

			var expected = characters[(36 - (total % 36)) % 36];
			return value[value.length - 1] === expected;
		}

		var checks = [
			{
				value: gstin,
				field: gstinField,
				pattern: /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/,
				title: "Invalid GSTIN",
				message: "GSTIN must contain exactly 15 characters in a valid format.",
			},
			{
				value: pan,
				field: panField,
				pattern: /^[A-Z]{5}[0-9]{4}[A-Z]$/,
				title: "Invalid PAN",
				message:
					"PAN must contain 10 characters in a valid format, for example ABCDE1234F.",
			},
			{
				value: aadhaar,
				field: aadhaarField,
				pattern: /^\d{12}$/,
				title: "Invalid Aadhaar Number",
				message: "Aadhaar Number must contain exactly 12 digits.",
			},
		];

		for (var i = 0; i < checks.length; i++) {
			var check = checks[i];
			if (check.value && !check.pattern.test(check.value)) {
				frappe.msgprint({ title: check.title, indicator: "red", message: check.message });
				if (check.field) check.field.focus();
				return false;
			}
		}

		if (gstin && !hasValidGstinCheckDigit(gstin)) {
			frappe.msgprint({
				title: "Invalid GSTIN",
				indicator: "red",
				message: "GSTIN check digit is invalid. Please verify the GSTIN and try again.",
			});
			if (gstinField) gstinField.focus();
			return false;
		}

		return true;
	}

	// Show the server's validation messages (plain text) instead of a generic error.
	function showApiError(xhr, subject) {
		var response = (xhr && xhr.responseJSON) || {};
		var messages = [];
		try {
			(JSON.parse(response._server_messages || "[]") || []).forEach(function (entry) {
				var parsed = typeof entry === "string" ? JSON.parse(entry) : entry;
				if (parsed && parsed.message) {
					messages.push({
						title: parsed.title || "Unable to save " + subject,
						message: parsed.message,
					});
				}
			});
		} catch (error) {
			// Use the generic message below when the response is not JSON.
		}
		if (!messages.length) {
			messages.push({
				title: "Unable to save " + subject,
				message: "Please check the entered values and try again.",
			});
		}
		var items = messages
			.map(function (item) {
				var clean = String(item.message)
					.replace(/<[^>]*>/g, " ")
					.replace(/\s+/g, " ")
					.trim();
				return "<li>" + frappe.utils.escape_html(clean) + "</li>";
			})
			.join("");
		frappe.msgprint({
			title: messages[0].title,
			indicator: "red",
			message: '<ul class="mb-0 pl-3">' + items + "</ul>",
		});
	}

	function resetSubmitState(overlayId, button) {
		setLoading(overlayId, button, false, "Loading...");
	}

	// Upload each chosen file (private) and put its URL into data[<field>].
	// Returns the field names whose upload failed, so the caller can stop before saving.
	function uploadFiles(fieldNames, data) {
		var failed = [];
		fieldNames.forEach(function (fieldName) {
			var input = document.getElementById(fieldName);
			if (!input || !input.files.length) return;
			var formData = new FormData();
			formData.append("file", input.files[0]);
			formData.append("is_private", 1);
			$.ajax({
				url: "/api/method/upload_file",
				data: formData,
				async: false, // keeps uploads before the save call without restructuring the flow
				processData: false,
				contentType: false,
				type: "POST",
				beforeSend: function (xhr) {
					xhr.setRequestHeader("X-Frappe-CSRF-Token", frappe.csrf_token);
				},
				success: function (response) {
					if (response.message && response.message.file_url)
						data[fieldName] = response.message.file_url;
					else failed.push(fieldName);
				},
				error: function () {
					failed.push(fieldName);
				},
			});
		});
		return failed;
	}

	// ---------------------------------------------------------------------------------------------
	// Address / contact rows
	// ---------------------------------------------------------------------------------------------

	// Each repeating row type: its container, the record-name attribute and its inputs.
	var ROW_TYPES = {
		address: {
			label: "Address",
			container: "address-rows-container",
			nameKey: "address_name",
			fieldAttr: "data-addr-field",
			lines: [
				[
					{ field: "address_line1", placeholder: "Address Line 1", col: 6 },
					{ field: "address_line2", placeholder: "Address Line 2", col: 6 },
				],
				[
					{ field: "city", placeholder: "City", col: 4 },
					{ field: "state", placeholder: "State", col: 4 },
					{ field: "pincode", placeholder: "PIN Code", col: 4 },
				],
			],
		},
		contact: {
			label: "Contact",
			container: "contact-rows-container",
			nameKey: "contact_name",
			fieldAttr: "data-contact-field",
			lines: [
				[
					{ field: "first_name", placeholder: "Contact Person Name", col: 3 },
					{ field: "designation", placeholder: "Designation", col: 3 },
					{ field: "phone", placeholder: "Phone", col: 3 },
					{ field: "mobile", placeholder: "Mobile", col: 3 },
					{ field: "email", placeholder: "Email", col: 3, type: "email" },
					{ field: "website", placeholder: "Website", col: 3, type: "url" },
				],
			],
		},
	};

	function rowsOf(type) {
		return document.querySelectorAll("." + type + "-row");
	}

	// Add one row, pre-filled from `data` (a record from the API, or {} for a blank row).
	// Values are set through the DOM, never concatenated into HTML.
	function addRow(type, data) {
		var spec = ROW_TYPES[type];
		data = data || {};
		var row = document.createElement("div");
		row.className = type + "-row";
		if (data[spec.nameKey]) row.setAttribute("data-record-name", data[spec.nameKey]);

		var label = document.createElement("div");
		label.className = type + "-row-label";
		row.appendChild(label);

		spec.lines.forEach(function (line) {
			var wrap = document.createElement("div");
			wrap.className = "row";
			line.forEach(function (input) {
				var col = document.createElement("div");
				col.className = "col-md-" + input.col + " mb-2";
				var el = document.createElement("input");
				el.type = input.type || "text";
				el.className = "form-control form-control-sm";
				el.placeholder = input.placeholder;
				el.setAttribute(spec.fieldAttr, input.field);
				el.value = data[input.field] || "";
				col.appendChild(el);
				wrap.appendChild(col);
			});
			row.appendChild(wrap);
		});

		document.getElementById(spec.container).appendChild(row);
		renumberRows(type);
	}

	// Labels read "Address 1 [Primary]", "Address 2", ...; every row but the first can be removed.
	function renumberRows(type) {
		var spec = ROW_TYPES[type];
		rowsOf(type).forEach(function (row, index) {
			var label = row.querySelector("." + type + "-row-label");
			label.textContent = spec.label + " " + (index + 1);
			if (index === 0) {
				var badge = document.createElement("span");
				badge.className = "badge badge-info";
				badge.textContent = "Primary";
				label.appendChild(document.createTextNode(" "));
				label.appendChild(badge);
			}

			var removeBtn = row.querySelector(".remove-" + type + "-btn");
			if (index === 0 && removeBtn) {
				removeBtn.remove();
			} else if (index > 0 && !removeBtn) {
				removeBtn = document.createElement("button");
				removeBtn.type = "button";
				removeBtn.className = "remove-" + type + "-btn";
				removeBtn.title = "Remove";
				removeBtn.innerHTML = "&#x2715;";
				removeBtn.setAttribute("data-kyc-remove", type);
				row.insertBefore(removeBtn, label.nextSibling);
			}
		});
	}

	function setRows(type, records) {
		document.getElementById(ROW_TYPES[type].container).innerHTML = "";
		(records && records.length ? records : [{}]).forEach(function (record) {
			addRow(type, record);
		});
	}

	// Rows in the shape update_<party> expects; row 1 is primary.
	function readRows(type) {
		var spec = ROW_TYPES[type];
		return Array.from(rowsOf(type)).map(function (row, index) {
			var record = {};
			row.querySelectorAll("[" + spec.fieldAttr + "]").forEach(function (el) {
				record[el.getAttribute(spec.fieldAttr)] = el.value || "";
			});
			record[spec.nameKey] = row.getAttribute("data-record-name") || "";
			record.is_primary = index === 0 ? 1 : 0;
			return record;
		});
	}

	// ---------------------------------------------------------------------------------------------
	// Page controller
	// ---------------------------------------------------------------------------------------------

	var OVERLAY_ID = "kyc-form-loading";
	var FILE_FIELDS = [
		"custom_gst_certificate",
		"custom_pan_card",
		"custom_certificate_of_incorporation__partnership_deed",
		"custom_cancelled_cheque",
		"custom_last_itr__acknowledgement",
		"custom_msme_certificate",
	];

	function setValue(name, value) {
		var field = document.querySelector('#kyc-form [name="' + name + '"]');
		if (field) field.value = value || "";
	}

	function fillSelect(id, options) {
		var select = document.getElementById(id);
		if (!select || !options) return;
		select.innerHTML = '<option value=""></option>';
		options.forEach(function (value) {
			var option = document.createElement("option");
			option.value = value;
			option.textContent = value;
			select.appendChild(option);
		});
	}

	// MSME = Yes shows the registration details.
	function toggleMSME() {
		var select = document.getElementById("custom_msme");
		var box = document.getElementById("msme_fields");
		if (select && box) box.style.display = select.value === "Yes" ? "block" : "none";
	}

	// TDS = Yes shows the withholding category; anything else clears it so it is not saved.
	function toggleTDS() {
		var select = document.getElementById("custom_tds_applicable");
		var section = document.getElementById("tds_section");
		if (!select || !section) return;
		var on = select.value === "Yes";
		section.style.display = on ? "flex" : "none";
		if (!on) {
			var category = document.getElementById("tax_withholding_category");
			if (category) category.value = "";
		}
	}

	// Fill the form from get_<party>_doc.
	function populate(data) {
		Object.keys(data).forEach(function (key) {
			if (typeof data[key] !== "object" || data[key] === null) setValue(key, data[key]);
		});

		setRows("address", data.addresses);
		setRows("contact", data.contacts);

		FILE_FIELDS.forEach(function (fieldName) {
			var link = document.getElementById("link_" + fieldName);
			if (link && data[fieldName]) {
				link.href = data[fieldName];
				link.style.display = "block";
			}
		});

		// A stored withholding category implies TDS applies, even if the Yes/No was never saved.
		var tds = document.getElementById("custom_tds_applicable");
		if (tds)
			tds.value = data.tax_withholding_category ? "Yes" : data.custom_tds_applicable || "";
		toggleTDS();
		setValue("tax_withholding_category", data.tax_withholding_category);
		toggleMSME();
	}

	function initPage(config) {
		var party = config.party;
		var api = "sas_fortuna.api." + party + ".";

		frappe.ready(function () {
			var form = document.getElementById("kyc-form");
			var submitButton = form.querySelector("button[type='submit']");

			// Overlay stays up until both the record and the withholding categories are in.
			var pending = { record: true, categories: true };
			function done(key) {
				pending[key] = false;
				if (!pending.record && !pending.categories) setLoading(OVERLAY_ID, null, false);
			}

			// GST categories must be in the select before the record's value is set.
			var recordLoadStarted = false;
			function loadRecord() {
				if (recordLoadStarted) return;
				recordLoadStarted = true;
				frappe.call({
					method: api + "get_" + party + "_doc",
					callback: function (r) {
						if (r.message) populate(r.message);
						done("record");
					},
					error: function () {
						done("record");
					},
				});
			}
			frappe.call({
				method: api + "get_gst_category_options",
				callback: function (r) {
					fillSelect("gst_category", r.message || []);
					loadRecord();
				},
				error: loadRecord,
			});
			frappe.call({
				method: api + "get_tax_withholding_category_options",
				callback: function (r) {
					fillSelect("tax_withholding_category", r.message);
					done("categories");
				},
				error: function () {
					done("categories");
				},
			});

			// Add / remove rows (buttons are in the markup or drawn by renumberRows).
			form.addEventListener("click", function (event) {
				var add = event.target.closest("[data-kyc-add]");
				if (add) addRow(add.getAttribute("data-kyc-add"));
				var remove = event.target.closest("[data-kyc-remove]");
				if (remove) {
					var type = remove.getAttribute("data-kyc-remove");
					remove.closest("." + type + "-row").remove();
					renumberRows(type);
				}
			});
			document.getElementById("custom_msme").addEventListener("change", toggleMSME);
			document.getElementById("custom_tds_applicable").addEventListener("change", toggleTDS);

			// Save: validate, upload files, then send everything in one update_<party> call.
			form.addEventListener("submit", function (event) {
				event.preventDefault();
				if (!validateIdentityFields(form)) return;
				setLoading(OVERLAY_ID, submitButton, true);

				var data = {};
				$(form)
					.serializeArray()
					.forEach(function (field) {
						data[field.name] = field.value;
					});
				data.addresses = readRows("address");
				data.contacts = readRows("contact");

				var failedUploads = uploadFiles(FILE_FIELDS, data);
				if (failedUploads.length) {
					setLoading(OVERLAY_ID, submitButton, false);
					frappe.msgprint({
						title: "Upload failed",
						indicator: "red",
						message: "Some files could not be uploaded. Please try again.",
					});
					return;
				}

				frappe.call({
					method: api + "update_" + party,
					args: { data: data },
					callback: function (r) {
						var skipped = (r.message && r.message.skipped) || [];
						var message = config.label + " details saved successfully";
						if (skipped.length) {
							message +=
								"<br><br>These values were not saved, please contact us: " +
								skipped.map(frappe.utils.escape_html).join(", ");
						}

						// Reload to show the saved state, whichever way the dialog is closed.
						var actionClicked = false;
						var dialog = frappe.msgprint({
							message: message,
							primary_action: {
								label: "OK",
								action: function () {
									actionClicked = true;
									dialog.hide();
									location.reload();
								},
							},
						});
						dialog.$wrapper.on("hidden.bs.modal", function () {
							if (!actionClicked) location.reload();
						});
					},
					error: function (xhr) {
						showApiError(xhr, config.label + " details");
					},
					always: function () {
						setLoading(OVERLAY_ID, submitButton, false);
					},
				});
			});
		});
	}

	return {
		setLoading,
		validateIdentityFields,
		showApiError,
		resetSubmitState,
		uploadFiles,
		initPage,
	};
})();
