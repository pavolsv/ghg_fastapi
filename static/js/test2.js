async function deleteFactor(factorId) {
    const confirmed = confirm("Are you sure you want to delete this factor?");
    if (confirmed) {
        try {
            const response = await fetch(`/test2/api/factors/${factorId}`, {method: "DELETE"});
            if (response.ok) {
                alert("Factor deleted successfully!");
                window.location.reload();
            } else {
                const errorData = await response.json();
                alert("Failed to delete the factor: " + (errorData.detail || "Unknown error"));
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

    const updatedData = {
        utility_id: parseInt(row.querySelector('[data-utility-id]').dataset.utilityId),
        utility_factor_year: parseInt(row.querySelector('[data-field="utility_factor_year"]').textContent),
        utility_factor_value: parseFloat(row.querySelector('[data-field="utility_factor_value"]').textContent),
        utility_factor_unit: row.querySelector('[data-field="utility_factor_unit"]').textContent,
        utility_factor_source: row.querySelector('[data-field="utility_factor_source"]').textContent,
    };

    try {
        const response = await fetch(
            `/ test2/api/factors/${factorId}`, {
                method: "PUT",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(updatedData),
            }
        );

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
            const errorData = await response.json();
            alert("Failed to update factor: " + (errorData.detail || "Unknown error"));
        }
    } catch (error) {
        alert("An error occurred while updating.");
        console.error("Error:", error);
    }
}