function initFactorManagementPage() {
    setupFactorModal();
    setupDeleteConfirm();
    const logBtn = document.getElementById("openLogModal");
    if (logBtn) {
        logBtn.addEventListener("click", () => LogModal.open("factor_management"));
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initFactorManagementPage);
} else {
    initFactorManagementPage();
}

function setupFactorModal() {
    const modal = document.getElementById("factorModal");
    const openBtn = document.getElementById("openCreateModal");
    const closeBtn = document.getElementById("factorModalClose");
    const cancelBtn = document.getElementById("factorModalClose2");

    if (!modal) return;

    openBtn?.addEventListener("click", () => {
        resetFactorForm();
        document.getElementById("factorModalTitle").textContent = "新增排放因子";
        modal.classList.remove("hidden");
    });

    closeBtn?.addEventListener("click", () => modal.classList.add("hidden"));
    cancelBtn?.addEventListener("click", () => modal.classList.add("hidden"));

    modal.addEventListener("click", (e) => {
        if (e.target === modal) modal.classList.add("hidden");
    });
}

function editFactor(data) {
    const modal = document.getElementById("factorModal");
    if (!modal) return;

    document.getElementById("factorModalTitle").textContent = "編輯排放因子";

    const fields = [
        "factor_code", "factor_gas_type", "factor_original_code",
        "factor_name", "factor_value", "factor_unit",
        "factor_year", "factor_emission_type",
        "factor_source", "factor_calculation_method"
    ];

    fields.forEach(fieldId => {
        const el = document.getElementById(fieldId);
        if (el && data[fieldId] !== undefined) {
            el.value = data[fieldId];
        }
    });

    modal.classList.remove("hidden");
}

function resetFactorForm() {
    const form = document.getElementById("factorForm");
    if (form) form.reset();
    const methodField = document.getElementById("factor_calculation_method");
    if (methodField) methodField.value = "total_co2e = activity_data × emission_factor";
}

function setupDeleteConfirm() {
    document.querySelectorAll(".btn-factor-delete").forEach(btn => {
        btn.addEventListener("click", (e) => {
            if (!confirm("確定刪除此排放因子？此操作無法復原。")) {
                e.preventDefault();
            }
        });
    });
}
