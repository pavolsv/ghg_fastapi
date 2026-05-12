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
        "factor_source", "factor_calculation_method",
        "factor_lhv_value", "factor_lhv_unit"
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

async function updateLhv() {
    const originalCode = document.getElementById('factor_original_code')?.value;
    const year = document.getElementById('factor_year')?.value;
    const emissionType = document.getElementById('factor_emission_type')?.value;
    const lhvValue = document.getElementById('factor_lhv_value')?.value;
    const lhvUnit = document.getElementById('factor_lhv_unit')?.value;

    if (!originalCode || !year || !emissionType || !lhvValue || !lhvUnit) {
        alert('請填寫完整的 LHV 資訊');
        return;
    }

    const formData = new FormData();
    formData.append('original_code', originalCode);
    formData.append('year', year);
    formData.append('emission_type', emissionType);
    formData.append('lower_heating_value', lhvValue);
    formData.append('lhv_unit', lhvUnit);

    try {
        const response = await fetch('/etl/factor/lhv/update', {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            alert('LHV 更新成功');
            window.location.reload();
        } else {
            alert('LHV 更新失敗');
        }
    } catch (error) {
        console.error('LHV 更新錯誤:', error);
        alert('系統錯誤');
    }
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
