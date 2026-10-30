/* sas_fortuna: public Supplier Registration form (/supplier-registration).
 *
 * The Web Form "supplier-registration" (fixtures/web_form.json) only loads this file, plus
 * sf_validation.js and supplier_registration.css, from its Client Script. On Submit:
 *   1. the browser checks required fields and formats (instantly);
 *   2. the server checks the same plus GSTIN / state / PIN code agreement and "already registered?"
 *      (check_registration in api/supplier_registration.py);
 *   3. only then does Frappe save the application.
 * Problems are written under each field in red, and the cursor goes to the first one.
 */
(function () {
	var wf = frappe.web_form;
	var CHECK_METHOD = "sas_fortuna.api.supplier_registration.check_registration";
	var REQUIRED = {
		supplier_name: "Enter your company's name.",
		gstin: "Enter your company's GSTIN.",
		first_name: "Enter the contact person's first name.",
		last_name: "Enter the contact person's last name.",
		email: "Enter the contact person's e-mail address.",
	};

	function check() {
		return window.sfValidation; // loaded just before this file
	}

	// ---------------------------------------------------------------------------------------------
	// Reading and checking the form
	// ---------------------------------------------------------------------------------------------

	// The form's values, trimmed; the mobile as "+91-9830012345" (country picked from the flag)
	function collect() {
		var data = {};
		Object.keys(wf.fields_dict).forEach(function (name) {
			var field = wf.fields_dict[name];
			if (!field.$input) return; // section / column breaks
			var value =
				field.df.fieldtype === "Phone" ? check().phoneValue(field) : field.get_value();
			data[name] = typeof value === "string" ? value.trim() : value || "";
		});
		if (data.email) data.email = data.email.toLowerCase();
		return data;
	}

	// Same rules as validate_registration() on the server, minus the database ones
	function validate(data) {
		var errors = [];
		function problem(field, message) {
			if (
				!errors.some(function (e) {
					return e.field === field;
				})
			) {
				errors.push({ field: field, message: message });
			}
		}
		Object.keys(REQUIRED).forEach(function (field) {
			if (!data[field]) problem(field, REQUIRED[field]);
		});
		if (data.supplier_name.toLowerCase() === "supplier")
			problem("supplier_name", "Enter your company's actual name.");

		if (!data.country || data.country === "India") {
			check().checkFormats(data, ["gstin", "pan"], problem, setIfChanged);
			if (data.pincode && !check().PINCODE.test(data.pincode))
				problem("pincode", "Enter the 6-digit PIN code.");
		}
		if (data.email && !check().EMAIL.test(data.email)) {
			problem("email", "Enter a valid e-mail address, for example name@company.com.");
		}
		var mobile = data.mobile && check().phoneProblem(data.mobile, true);
		if (mobile) problem("mobile", mobile);
		return errors;
	}

	function setIfChanged(field, value) {
		if (wf.get_value(field) !== value) wf.set_value(field, value);
	}

	// ---------------------------------------------------------------------------------------------
	// Showing problems: red field + message under it, cursor in the first, count next to Submit
	// ---------------------------------------------------------------------------------------------

	var $summary = $('<span class="sf-error-summary" role="alert"></span>').insertBefore(
		".web-form-footer .submit-btn",
	);

	function setSummary() {
		var count = $(".web-form .sf-error").length;
		$summary.text(
			count
				? count === 1
					? "Please correct the highlighted field."
					: "Please correct the " + count + " highlighted fields."
				: "",
		);
	}

	function clearProblem($control) {
		$control.removeClass("sf-invalid").find(".sf-error").remove();
	}

	function showErrors(errors) {
		$(".web-form .frappe-control").each(function () {
			clearProblem($(this));
		});
		var first = null;
		errors.forEach(function (error) {
			var field = wf.fields_dict[error.field];
			if (!field) return;
			field.$wrapper.addClass("sf-invalid");
			field.$wrapper
				.find(".control-input-wrapper")
				.first()
				.append($('<div class="sf-error"></div>').text(error.message));
			// first on the page (the errors come in the order the checks ran)
			if (
				!first ||
				first.$wrapper[0].compareDocumentPosition(field.$wrapper[0]) &
					Node.DOCUMENT_POSITION_PRECEDING
			) {
				first = field;
			}
		});
		setSummary();
		if (first) {
			first.$input[0].scrollIntoView({ behavior: "smooth", block: "center" });
			first.$input[0].focus({ preventScroll: true });
		}
	}

	// Editing a field clears its message
	$(".web-form").on("input change", ".frappe-control", function () {
		if ($(this).hasClass("sf-invalid")) {
			clearProblem($(this));
			setSummary();
		}
	});

	// A valid GSTIN contains the PAN: fill the PAN in when it is still empty
	wf.on("gstin", function (field, value) {
		var gstin = String(value || "")
			.trim()
			.toUpperCase();
		if (check().FORMATS.gstin[0].test(gstin) && !wf.get_value("pan"))
			wf.set_value("pan", gstin.slice(2, 12));
	});

	// ---------------------------------------------------------------------------------------------
	// Submit: browser checks, then the server's, then Frappe's own save
	// ---------------------------------------------------------------------------------------------

	var frappeSave = wf.save.bind(wf);
	wf.save = function () {
		var data = collect();
		var errors = validate(data);
		if (errors.length) {
			showErrors(errors);
			return false;
		}
		frappe.call({
			method: CHECK_METHOD,
			args: { data: data },
			freeze: true,
			freeze_message: "Checking your details...",
			callback: function (r) {
				if (r.message && r.message.length) showErrors(r.message);
				else frappeSave();
			},
		});
		return false;
	};
})();
