/* sas_fortuna: format checks shared by the portal forms, in the browser.
 * Used by the Customer / Supplier KYC pages (portal_kyc.js) and the Supplier Registration form
 * (supplier_registration.js). Server twin: api/validation.py; keep the two in step.
 *
 * Every check reports a problem as problem(field, message), in words the person can act on.
 */
window.sfValidation = (function () {
	// Field -> [format, message]. Values are checked after upper-casing and removing spaces.
	var FORMATS = {
		gstin: [
			/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/,
			"Enter the 15-character GSTIN, for example 19AABCF1234A1ZB.",
		],
		pan: [/^[A-Z]{5}[0-9]{4}[A-Z]$/, "Enter the 10-character PAN, for example ABCDE1234F."],
		custom_tan_no: [
			/^[A-Z]{4}[0-9]{5}[A-Z]$/,
			"Enter the 10-character TAN, for example KOLA12345B.",
		],
		custom_aadhaar_number: [/^[0-9]{12}$/, "Enter the 12-digit Aadhaar number."],
		custom_udyam_registration_number: [
			/^UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}$/,
			"Enter the Udyam number as printed on the certificate, for example UDYAM-WB-10-0012345.",
		],
		custom_ifsc_code: [
			/^[A-Z]{4}0[A-Z0-9]{6}$/,
			"Enter the 11-character IFSC, for example SBIN0001234.",
		],
		custom_account_no: [/^[0-9]{9,18}$/, "Enter the account number (9 to 18 digits)."],
	};
	var PINCODE = /^[1-9][0-9]{5}$/;
	var EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

	// Tidy and check `fields` of `data` against FORMATS; `onTidy(field, value)` puts tidied values
	// back on screen. Also: GSTIN check digit, and PAN must match the GSTIN.
	function checkFormats(data, fields, problem, onTidy) {
		fields.forEach(function (field) {
			if (!data[field]) return;
			data[field] = data[field].toUpperCase().replace(/\s+/g, "");
			if (onTidy) onTidy(field, data[field]);
			if (!FORMATS[field][0].test(data[field])) problem(field, FORMATS[field][1]);
		});
		var gstin = data.gstin;
		var gstinOk = gstin && FORMATS.gstin[0].test(gstin);
		if (gstinOk && !gstinCheckDigitOk(gstin)) {
			problem(
				"gstin",
				"This GSTIN is not valid: its last character does not match. Please check it.",
			);
		}
		if (gstinOk && data.pan && gstin.slice(2, 12) !== data.pan) {
			problem(
				"pan",
				"This PAN does not match the GSTIN (characters 3 to 12 of a GSTIN are the PAN).",
			);
		}
	}

	// GSTIN's last character is a mod-36 checksum of the first 14
	function gstinCheckDigitOk(gstin) {
		var chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
		var total = 0;
		for (var i = 0; i < 14; i++) {
			var value = chars.indexOf(gstin[i]) * (i % 2 ? 2 : 1);
			total += Math.floor(value / 36) + (value % 36);
		}
		return gstin[14] === chars[(36 - (total % 36)) % 36];
	}

	// Quick phone check; "" when it looks fine (the server checks numbers strictly). `value` is
	// what Frappe's Phone control holds, "+91-98300 12345", or "+44 7911 123456" typed in full.
	function phoneProblem(value, mobileOnly) {
		if (value.charAt(0) !== "+")
			return "Choose the country from the flag, then type the number.";
		var parts = value.split("-");
		var isd = parts.length > 1 ? parts.shift() : "";
		var digits = parts.join("").replace(/[\s().+]/g, "");
		if (!/^\d+$/.test(digits)) return "This is not a phone number. Use digits only.";
		if (isd === "+91") {
			digits = digits.replace(/^0/, "");
			if (digits.length !== 10) return "An Indian number has 10 digits.";
			if (mobileOnly && !/^[6-9]/.test(digits)) {
				return "This looks like a landline number. Please enter a mobile number (Indian mobiles start with 6, 7, 8 or 9).";
			}
			return "";
		}
		var total = (isd + digits).replace(/\D/g, "").length;
		if (total < 8) return "This number is too short for the chosen country.";
		if (total > 15) return "This number is too long for the chosen country.";
		return "";
	}

	// "+91-9830012345" from what Frappe's Phone control shows (its own value updates a moment later)
	function phoneValue(control) {
		if (!control.$input) return control.value || "";
		var number = String(control.$input.val() || "").trim();
		if (!number) return "";
		if (number.charAt(0) === "+") return number; // typed with its own country code
		var isd = control.$isd ? control.$isd.text().trim() : "";
		return isd ? isd + "-" + number : number;
	}

	return {
		FORMATS: FORMATS,
		PINCODE: PINCODE,
		EMAIL: EMAIL,
		checkFormats: checkFormats,
		phoneProblem: phoneProblem,
		phoneValue: phoneValue,
	};
})();
