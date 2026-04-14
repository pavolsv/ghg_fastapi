async function deleteFactor(factorId) {
    const confirmed = confirm("Are you sure you want to delete this factor?");
    if (confirmed) {
        try {
            const response = await fetch(`/test2/api/factors/${factorId}`, {method: "DELETE"});
            if (response.ok) {
                alert("Factor deleted successfully!");
                window.location.reload();
            } else {
                let errorText;
                try {
                    const errJson = await response.json();
                    errorText = errJson.detail || JSON.stringify(errJson);
                } catch {
                    errorText = await response.text().catch(() => null) || response.statusText || "Unknown error";
                }
                alert("Failed to delete the factor: " + errorText);
            }
        } catch (error) {
            alert("An error occurred.");
            console.error("Error:", error);
        }
    }
    
}

function editFactor(button) {
    const row = button.closest("tr");
    const fields = row.querySelectorAll("[contenteditable]");
    fields.forEach((field) => {
        field.contentEditable = "true";
        field.style.border = "1px solid #007bff";
        field.style.padding = "4px";
    });
    button.style.display = "none";
    row.querySelector('[onclick="saveFactor(this)"]').style.display = "inline-block";
}

async function saveFactor(button) {
    const row = button.closest("tr");
    const factorId = row.dataset.factorId;
    const fields = row.querySelectorAll("[contenteditable]");

    // helper to safely read and parse values
    const getText = (selector) => {
        const el = row.querySelector(selector);
        return el ? el.textContent.trim() : "";
    };

    const parsedInt = (v) => {
        const n = parseInt(v, 10);
        return Number.isFinite(n) ? n : null;
    };
    const parsedFloat = (v) => {
        const n = parseFloat(v);
        return Number.isFinite(n) ? n : null;
    };

    const updatedData = {
        utility_id: parsedInt(row.querySelector('[data-utility-id]')?.dataset.utilityId ?? ""),
        utility_factor_year: parsedInt(getText('[data-field="utility_factor_year"]')),
        utility_factor_value: parsedFloat(getText('[data-field="utility_factor_value"]')),
        utility_factor_unit: getText('[data-field="utility_factor_unit"]'),
        utility_factor_source: getText('[data-field="utility_factor_source"]'),
    };

    try {
        button.disabled = true;
        const response = await fetch(`/test2/api/factors/${factorId}`, {
            method: "PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(updatedData),
        });

        if (response.ok) {
            alert("Factor updated successfully!");
            fields.forEach((field) => {
                field.contentEditable = "false";
                field.style.border = "none";
                field.style.padding = "8px";
            });
            button.style.display = "none";
            row.querySelector('[onclick="editFactor(this)"]').style.display = "inline-block";
        } else {
            let errorText;
            try {
                const errJson = await response.json();
                errorText = errJson.detail || JSON.stringify(errJson);
            } catch {
                errorText = await response.text().catch(() => null) || response.statusText || "Unknown error";
            }
            alert("Failed to update factor: " + errorText);
        }
    } catch (error) {
        alert("An error occurred while updating.");
        console.error("Error:", error);
    } finally {
        button.disabled = false;
    }
}