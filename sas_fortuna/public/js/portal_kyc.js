window.SASPortalKyc = (function () {
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

	function uploadFiles(fieldNames, data) {
		fieldNames.forEach(function (fieldName) {
			var input = document.getElementById(fieldName);
			if (!input || !input.files.length) return;
			var formData = new FormData();
			formData.append("file", input.files[0]);
			formData.append("is_private", 1);
			$.ajax({
				url: "/api/method/upload_file",
				data: formData,
				async: false,
				processData: false,
				contentType: false,
				type: "POST",
				beforeSend: function (xhr) {
					xhr.setRequestHeader("X-Frappe-CSRF-Token", frappe.csrf_token);
				},
				success: function (response) {
					if (response.message && response.message.file_url)
						data[fieldName] = response.message.file_url;
				},
			});
		});
	}

	return { setLoading, validateIdentityFields, showApiError, resetSubmitState, uploadFiles };
})();
