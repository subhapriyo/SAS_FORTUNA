/* sas_fortuna: Customer / Supplier KYC pages (/customer, /supplier).
 *
 * Markup: templates/includes/kyc_form.html (shared by both pages), which calls
 *     SASPortalKyc.initPage({ party: "supplier", label: "Supplier", controls_bundle: "..." })
 * This loads the record from sas_fortuna.api.<party>, draws the address / contact rows, wires the
 * TDS / MSME toggles, checks the form and saves it with update_<party>.
 *
 * Validation: validate() below runs the same checks as validate_kyc() in api/party_kyc.py. Both
 * produce a list of {field, message, row_type?, row?}; showErrors() marks those boxes in red, writes
 * the message under each one and puts the cursor in the first. Keep the two in step.
 */
window.SASPortalKyc = (function () {
	var form; // #kyc-form, set by initPage

	// ---------------------------------------------------------------------------------------------
	// Validation rules (same as validate_kyc in api/party_kyc.py; formats in sf_validation.js)
	// ---------------------------------------------------------------------------------------------

	var check = window.sfValidation;
	var NO_GSTIN_CATEGORIES = ["Unregistered", "Overseas"];
	var BANK_FIELDS = {
		custom_bank_name: "Enter the bank name.",
		custom_account_no: "Enter the account number.",
		custom_ifsc_code: "Enter the IFSC.",
	};
	var ADDRESS_REQUIRED = {
		address_line1: "Enter the address.",
		city: "Enter the city.",
		state: "Enter the state.",
		pincode: "Enter the PIN code.",
	};
	var MAX_FILE_MB = 10;

	// Check the collected form data; returns [{field, message, row_type?, row?}], empty when fine.
	// IDs are tidied in `data` (and on screen) on the way, as the server does.
	function validate(data) {
		var errors = [];
		function problem(field, message, rowType, row) {
			errors.push({ field: field, message: message, row_type: rowType, row: row });
		}

		// Formats: GSTIN (+ check digit, + PAN match), PAN, TAN, Aadhaar, Udyam, IFSC, account number
		check.checkFormats(data, Object.keys(check.FORMATS), problem, setValue);

		// Required, depending on other answers
		var gstin = data.gstin;
		if (!data.gst_category) problem("gst_category", "Choose the GST category.");
		else if (NO_GSTIN_CATEGORIES.indexOf(data.gst_category) < 0 && !gstin) {
			problem("gstin", "This GST category needs a GSTIN. Enter it, or choose Unregistered.");
		}
		if (data.custom_tds_applicable === "Yes" && !data.tax_withholding_category) {
			problem("tax_withholding_category", "Choose the tax withholding category.");
		}
		if (data.custom_msme === "Yes" && !data.custom_udyam_registration_number) {
			problem("custom_udyam_registration_number", "Enter the Udyam registration number.");
		}
		var bankKeys = Object.keys(BANK_FIELDS);
		if (
			bankKeys.some(function (f) {
				return data[f];
			})
		) {
			bankKeys.forEach(function (f) {
				if (!data[f]) problem(f, BANK_FIELDS[f]);
			});
		}

		// Address rows: a started row needs the full address
		data.addresses.forEach(function (row, i) {
			var started = ROW_TYPES.address.fields.some(function (f) {
				return row[f.field];
			});
			if (!started) return; // an empty row is simply not saved
			Object.keys(ADDRESS_REQUIRED).forEach(function (f) {
				if (!row[f]) problem(f, ADDRESS_REQUIRED[f], "address", i + 1);
			});
			if (row.pincode && !check.PINCODE.test(row.pincode)) {
				problem("pincode", "Enter the 6-digit PIN code.", "address", i + 1);
			}
		});

		// Contact rows: e-mail and phone numbers (the server re-checks numbers more strictly)
		data.contacts.forEach(function (row, i) {
			if (row.email && !check.EMAIL.test(row.email)) {
				problem(
					"email",
					"Enter a valid e-mail address, for example name@company.com.",
					"contact",
					i + 1,
				);
			}
			["phone", "mobile"].forEach(function (f) {
				var message = row[f] && check.phoneProblem(row[f], f === "mobile");
				if (message) problem(f, message, "contact", i + 1);
			});
		});

		// Attachments: type and size
		FILE_FIELDS.forEach(function (f) {
			var input = document.getElementById(f);
			var file = input && input.files[0];
			if (!file) return;
			if (!/^image\/|\/pdf$/.test(file.type)) problem(f, "Attach a PDF or an image.");
			else if (file.size > MAX_FILE_MB * 1024 * 1024) {
				problem(
					f,
					"This file is larger than " + MAX_FILE_MB + " MB. Attach a smaller copy.",
				);
			}
		});
		return errors;
	}

	// ---------------------------------------------------------------------------------------------
	// Showing errors: red box + message under it, cursor in the first, count next to Save
	// ---------------------------------------------------------------------------------------------

	// The input (or phone box) an error points to
	function fieldFor(error) {
		if (error.row_type) {
			var spec = ROW_TYPES[error.row_type];
			var row = rowsOf(error.row_type)[error.row - 1];
			return row && row.querySelector("[" + spec.fieldAttr + '="' + error.field + '"]');
		}
		return document.getElementById(error.field);
	}

	function clearErrors(scope) {
		scope.querySelectorAll(".is-invalid").forEach(function (el) {
			el.classList.remove("is-invalid");
		});
		scope.querySelectorAll(".kyc-error").forEach(function (el) {
			el.remove();
		});
	}

	function showErrors(errors) {
		clearErrors(form);
		var first = null;
		errors.forEach(function (error) {
			var field = fieldFor(error);
			var box = field && field.closest(".kyc-field");
			if (!box) return;
			field.classList.add("is-invalid");
			if (!box.querySelector(".kyc-error")) {
				var note = document.createElement("div");
				note.className = "kyc-error";
				note.textContent = error.message;
				box.appendChild(note);
			}
			// first on the page (the errors come in the order the checks ran)
			if (!first || first.compareDocumentPosition(field) & Node.DOCUMENT_POSITION_PRECEDING)
				first = field;
		});
		setSummary(errors.length);
		if (first) {
			var target = first.kycPhone ? first.kycPhone.$input[0] : first;
			target.scrollIntoView({ behavior: "smooth", block: "center" });
			target.focus({ preventScroll: true });
		}
		return !!first;
	}

	function setSummary(count) {
		var summary = document.getElementById("kyc-error-summary");
		summary.textContent = count
			? count === 1
				? "Please correct the highlighted field."
				: "Please correct the " + count + " highlighted fields."
			: "";
	}

	// Errors the server raises outside validate_kyc (e.g. from ERPNext or India Compliance): shown
	// under the field they mention when we can tell which, otherwise in a dialog, in plain words.
	var FIELD_HINTS = [
		[/gstin/i, "gstin"],
		[/\bpan\b/i, "pan"],
		[/gst category/i, "gst_category"],
	];
	var FRIENDLY_ERRORS = [
		[
			/TimestampMismatchError|modified after you have opened it/i,
			"Your details were changed by someone else while you were editing. Please reload the page and enter your changes again.",
		],
		[
			/PermissionError|not permitted|insufficient permission/i,
			"Your account cannot change these details. Please contact Fortuna and we will update them for you.",
		],
		[
			/InvalidPhoneNumberError|country code/i,
			"Please check the phone numbers: choose the country from the flag, then type the number.",
		],
	];

	function showServerError(response) {
		response = response && (response.responseJSON || response); // a jQuery request or the reply
		var message = "";
		try {
			var entries = JSON.parse((response && response._server_messages) || "[]");
			message = entries
				.map(function (entry) {
					return JSON.parse(entry).message || "";
				})
				.join(" ");
		} catch (e) {
			// not a Frappe error reply: the generic message below
		}
		message = message
			.replace(/<[^>]*>/g, "")
			.replace(/\s+/g, " ")
			.trim();
		var type = (response && response.exc_type) || "";

		for (var i = 0; i < FRIENDLY_ERRORS.length; i++) {
			if (FRIENDLY_ERRORS[i][0].test(type + " " + message)) {
				message = FRIENDLY_ERRORS[i][1];
				break;
			}
		}
		for (var j = 0; j < FIELD_HINTS.length && message; j++) {
			if (
				FIELD_HINTS[j][0].test(message) &&
				showErrors([{ field: FIELD_HINTS[j][1], message: message }])
			) {
				return;
			}
		}
		frappe.msgprint({
			title: "Could not save",
			indicator: "red",
			message: frappe.utils.escape_html(
				message ||
					"Something went wrong while saving. Please try again; if it keeps happening, contact Fortuna.",
			),
		});
	}

	// ---------------------------------------------------------------------------------------------
	// Address / contact rows
	// ---------------------------------------------------------------------------------------------

	// Each repeating row type: its container, the record-name key and its inputs.
	var ROW_TYPES = {
		address: {
			label: "Address",
			container: "address-rows-container",
			nameKey: "address_name",
			fieldAttr: "data-addr-field",
			fields: [
				{ field: "address_line1", label: "Address Line 1", col: 6 },
				{ field: "address_line2", label: "Address Line 2", col: 6 },
				{ field: "city", label: "City", col: 4 },
				{ field: "state", label: "State", col: 4 },
				{ field: "pincode", label: "PIN Code", col: 4, type: "tel" },
			],
		},
		contact: {
			label: "Contact",
			container: "contact-rows-container",
			nameKey: "contact_name",
			fieldAttr: "data-contact-field",
			fields: [
				{ field: "first_name", label: "Contact Person", col: 4 },
				{ field: "designation", label: "Designation", col: 4 },
				{ field: "email", label: "E-mail", col: 4, type: "email" },
				// `phone`: Frappe's Phone control (country picker), see makePhoneInput
				{ field: "phone", label: "Phone", col: 4, phone: true },
				{ field: "mobile", label: "Mobile", col: 4, phone: true },
				{ field: "website", label: "Website", col: 4, type: "url" },
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
		row.className = "kyc-row " + type + "-row";
		if (data[spec.nameKey]) row.setAttribute("data-record-name", data[spec.nameKey]);
		row.innerHTML = '<div class="kyc-row__head"></div><div class="row"></div>';

		var grid = row.querySelector(".row");
		spec.fields.forEach(function (input) {
			var box = document.createElement("div");
			box.className = "col-md-" + input.col + " kyc-field";
			var label = document.createElement("label");
			label.className = "kyc-label";
			label.textContent = input.label;
			box.appendChild(label);

			var el;
			if (input.phone) {
				el = makePhoneInput(input, data[input.field]);
			} else {
				el = document.createElement("input");
				el.type = input.type || "text";
				el.className = "form-control";
				el.value = data[input.field] || "";
			}
			el.setAttribute(spec.fieldAttr, input.field);
			box.appendChild(el);
			grid.appendChild(box);
		});

		document.getElementById(spec.container).appendChild(row);
		renumberRows(type);
	}

	// Headings read "Address 1 · Primary", "Address 2", ...; every row but the first can be removed.
	function renumberRows(type) {
		var spec = ROW_TYPES[type];
		rowsOf(type).forEach(function (row, index) {
			var head = row.querySelector(".kyc-row__head");
			head.innerHTML = "";
			var title = document.createElement("span");
			title.textContent = spec.label + " " + (index + 1);
			head.appendChild(title);
			if (index === 0) {
				head.insertAdjacentHTML("beforeend", '<span class="kyc-badge">Primary</span>');
			} else {
				head.insertAdjacentHTML(
					"beforeend",
					'<button type="button" class="kyc-remove" data-kyc-remove="' +
						type +
						'">Remove</button>',
				);
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
				var value = el.kycPhone ? check.phoneValue(el.kycPhone) : el.value;
				record[el.getAttribute(spec.fieldAttr)] = (value || "").trim();
			});
			record[spec.nameKey] = row.getAttribute("data-record-name") || "";
			record.is_primary = index === 0 ? 1 : 0;
			return record;
		});
	}

	// ---------------------------------------------------------------------------------------------
	// Phone / Mobile inputs: Frappe's own Phone control (the one Desk uses), a flag + dial-code
	// picker in front of the number. Its value is "+91-9830012345", as Frappe's Phone fields store it.
	// ---------------------------------------------------------------------------------------------

	function hasPhoneControl() {
		return !!(frappe.ui && frappe.ui.form && frappe.ui.form.ControlPhone);
	}

	// Load Frappe's controls bundle. Resolves even if it fails: the boxes then fall back to plain
	// text inputs, and the server still checks the numbers.
	function loadControls(url) {
		if (!url || hasPhoneControl()) return Promise.resolve();
		return new Promise(function (resolve) {
			var script = document.createElement("script");
			script.src = url;
			script.onload = script.onerror = resolve;
			document.head.appendChild(script);
		});
	}

	// The control builds its input asynchronously (it first loads the country list), so wait for it.
	function whenPhoneReady(control, callback, tries) {
		tries = tries || 0;
		if (control.$input && control.country_code_picker && control.$isd) return callback();
		if (tries < 100) setTimeout(whenPhoneReady, 50, control, callback, tries + 1);
	}

	function makePhoneInput(input, value) {
		if (!hasPhoneControl()) {
			var plain = document.createElement("input");
			plain.type = "tel";
			plain.className = "form-control";
			plain.value = value || "";
			return plain;
		}
		var holder = document.createElement("div");
		holder.className = "kyc-phone";
		var control = frappe.ui.form.make_control({
			df: { fieldtype: "Phone", fieldname: input.field, placeholder: input.label },
			parent: holder,
			render_input: true, // full control (not only_input): Frappe's flag styles need its wrapper
		});
		holder.kycPhone = control;
		whenPhoneReady(control, function () {
			control.$input.attr("type", "tel");
			// Older records hold just "9830012345": the control adds the default country (India).
			if (value) control.set_value(value);
		});
		return holder;
	}

	// ---------------------------------------------------------------------------------------------
	// Page: load, fill, toggles, save
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

	// Overlay over the page while loading / saving; the Save button is locked meanwhile.
	function setBusy(isBusy, message) {
		var overlay = document.getElementById(OVERLAY_ID);
		overlay.style.display = isBusy ? "flex" : "none";
		overlay.setAttribute("aria-busy", isBusy ? "true" : "false");
		overlay.querySelector("[data-loading-message]").textContent = message || "Loading...";
		form.querySelector("button[type='submit']").disabled = isBusy;
	}

	function setValue(name, value) {
		var field = form.querySelector('[name="' + name + '"]');
		if (field) field.value = value || "";
	}

	function fillSelect(id, options) {
		var select = document.getElementById(id);
		select.innerHTML = '<option value="">Select</option>';
		(options || []).forEach(function (value) {
			var option = document.createElement("option");
			option.value = option.textContent = value;
			select.appendChild(option);
		});
	}

	// TDS = Yes shows the withholding category; MSME = Yes shows the registration details.
	// A hidden withholding category is cleared so it is not saved.
	function applyToggles() {
		var tds = document.getElementById("custom_tds_applicable").value === "Yes";
		document.getElementById("tds_section").hidden = !tds;
		if (!tds) setValue("tax_withholding_category", "");
		document.getElementById("msme_fields").hidden =
			document.getElementById("custom_msme").value !== "Yes";
	}

	// Fill the form from get_<party>_doc.
	function populate(data) {
		Object.keys(data).forEach(function (key) {
			if (typeof data[key] !== "object" || data[key] === null) setValue(key, data[key]);
		});
		setRows("address", data.addresses);
		setRows("contact", data.contacts);

		FILE_FIELDS.forEach(function (field) {
			var link = document.getElementById("link_" + field);
			if (data[field]) {
				link.href = data[field];
				link.hidden = false;
			}
		});
		// A stored withholding category implies TDS applies, even if the Yes/No was never saved.
		if (data.tax_withholding_category) setValue("custom_tds_applicable", "Yes");
		applyToggles();
		setValue("tax_withholding_category", data.tax_withholding_category);
	}

	// Everything the save sends: the named inputs plus the address / contact rows.
	function collect() {
		var data = {};
		$(form)
			.serializeArray()
			.forEach(function (field) {
				data[field.name] = field.value.trim();
			});
		data.addresses = readRows("address");
		data.contacts = readRows("contact");
		return data;
	}

	// Upload the chosen files (private) and put each file URL into data[<field>].
	// Resolves with the errors of the files that failed, in the same shape as validate().
	function uploadFiles(data) {
		return Promise.all(
			FILE_FIELDS.map(function (field) {
				var input = document.getElementById(field);
				if (!input.files.length) return null;
				var body = new FormData();
				body.append("file", input.files[0]);
				body.append("is_private", 1);
				return fetch("/api/method/upload_file", {
					method: "POST",
					body: body,
					headers: { "X-Frappe-CSRF-Token": frappe.csrf_token },
				})
					.then(function (r) {
						return r.ok ? r.json() : Promise.reject();
					})
					.then(function (r) {
						data[field] = r.message.file_url;
						return null;
					})
					.catch(function () {
						return {
							field: field,
							message: "This file could not be uploaded. Please try again.",
						};
					});
			}),
		).then(function (results) {
			return results.filter(Boolean);
		});
	}

	function save(config) {
		var data = collect();
		if (showErrors(validate(data))) return;

		setBusy(true, "Saving...");
		uploadFiles(data).then(function (uploadErrors) {
			if (uploadErrors.length) {
				setBusy(false);
				showErrors(uploadErrors);
				return;
			}
			frappe.call({
				method: "sas_fortuna.api." + config.party + ".update_" + config.party,
				args: { data: data },
				error_msg: $("<div>").hide(), // keep Frappe's raw dialog away; showServerError explains
				callback: function (r) {
					var result = r.message || {};
					if (result.status === "invalid") return showErrors(result.errors);
					saved(config, result.skipped || []);
				},
				error: showServerError,
				always: function () {
					setBusy(false);
				},
			});
		});
	}

	// Success: confirm, then reload to show what was stored (whichever way the dialog is closed).
	function saved(config, skipped) {
		var message = config.label + " details saved successfully.";
		if (skipped.length) {
			message +=
				"<br><br>These values could not be saved, please contact us: " +
				skipped.map(frappe.utils.escape_html).join(", ");
		}
		var dialog = frappe.msgprint({ title: "Saved", indicator: "green", message: message });
		dialog.$wrapper.on("hidden.bs.modal", function () {
			location.reload();
		});
	}

	function initPage(config) {
		var api = "sas_fortuna.api." + config.party + ".";

		frappe.ready(function () {
			form = document.getElementById("kyc-form");

			// Load: phone controls + GST categories first (both are needed to draw the record),
			// withholding categories alongside.
			var ready = Promise.all([
				loadControls(config.controls_bundle),
				frappe.xcall(api + "get_gst_category_options").then(function (options) {
					fillSelect("gst_category", options);
				}),
				frappe
					.xcall(api + "get_tax_withholding_category_options")
					.then(function (options) {
						fillSelect("tax_withholding_category", options);
					}),
			]);
			ready
				.then(function () {
					return frappe.xcall(api + "get_" + config.party + "_doc");
				})
				.then(populate)
				.catch(function () {
					frappe.msgprint({
						title: "Could not load your details",
						indicator: "red",
						message: "Please reload the page. If it keeps happening, contact Fortuna.",
					});
				})
				.finally(function () {
					setBusy(false);
				});

			// Add / remove rows
			form.addEventListener("click", function (event) {
				var add = event.target.closest("[data-kyc-add]");
				if (add) addRow(add.getAttribute("data-kyc-add"));
				var remove = event.target.closest("[data-kyc-remove]");
				if (remove) {
					var type = remove.getAttribute("data-kyc-remove");
					remove.closest(".kyc-row").remove();
					renumberRows(type);
				}
			});

			// Editing a field clears its error; the TDS / MSME answers show or hide their details
			["input", "change"].forEach(function (name) {
				form.addEventListener(name, function (event) {
					var box = event.target.closest && event.target.closest(".kyc-field");
					if (box && box.querySelector(".kyc-error")) {
						clearErrors(box);
						setSummary(form.querySelectorAll(".kyc-error").length);
					}
					if (
						event.target.id === "custom_tds_applicable" ||
						event.target.id === "custom_msme"
					) {
						applyToggles();
					}
				});
			});

			form.addEventListener("submit", function (event) {
				event.preventDefault();
				save(config);
			});
		});
	}

	return { initPage: initPage };
})();
