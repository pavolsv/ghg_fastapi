const calculationConfig = window.calculationConfig || {};
const unitMap = calculationConfig.unitMap || {};
const elecDeviceId = calculationConfig.elecDeviceId != null
    ? String(calculationConfig.elecDeviceId)
    : null;
const gasolineDeviceId = calculationConfig.gasolineDeviceId != null
    ? String(calculationConfig.gasolineDeviceId)
    : null;
const dieselDeviceId = calculationConfig.dieselDeviceId != null
    ? String(calculationConfig.dieselDeviceId)
    : null;
const gasolineTotalUsage = Number(calculationConfig.gasolineTotalUsage || 0);
const electricityTotalUsage = Number(calculationConfig.electricityTotalUsage || 0);
const dieselTotalUsage = Number(calculationConfig.dieselTotalUsage || 0);

function isAutoUsageDevice(deviceId) {
    if (!deviceId) {
        return false;
    }
    return deviceId === elecDeviceId || deviceId === gasolineDeviceId || deviceId === dieselDeviceId;
}

function updateUnit() {
    const select = document.getElementById("deviceSelect");
    const badge = document.getElementById("unit-badge");
    const usageInput = document.getElementById("usageInput");
    if (!select || !badge) {
        return;
    }
    badge.innerText = unitMap[select.value] || "-";

    if (usageInput) {
        usageInput.readOnly = isAutoUsageDevice(select.value);
    }

    // 電費單設備選中時顯示帶入選單
    const picker = document.getElementById("elecBillPicker");
    const elecTotalUsageInput = document.getElementById("electricityTotalUsageInput");
    if (picker) {
        if (elecDeviceId && select.value === elecDeviceId) {
            picker.style.display = "";
            if (usageInput) {
                usageInput.value = electricityTotalUsage > 0 ? String(electricityTotalUsage) : "";
            }
            if (elecTotalUsageInput) {
                elecTotalUsageInput.value = `${electricityTotalUsage} 度`;
            }
        } else {
            picker.style.display = "none";
        }
    }

    // 汽油設備選中時顯示加油單帶入選單
    const gasPicker = document.getElementById("gasolineBillPicker");
    const totalUsageInput = document.getElementById("gasolineTotalUsageInput");
    if (gasPicker) {
        if (gasolineDeviceId && select.value === gasolineDeviceId) {
            gasPicker.style.display = "";
            if (usageInput) {
                usageInput.value = gasolineTotalUsage > 0 ? String(gasolineTotalUsage) : "";
            }
            if (totalUsageInput) {
                totalUsageInput.value = `${gasolineTotalUsage} 公升`;
            }
        } else {
            gasPicker.style.display = "none";
        }
    }

    // 柴油設備選中時顯示加油單帶入選單
    const dieselPicker = document.getElementById("dieselBillPicker");
    const dieselTotalUsageInput = document.getElementById("dieselTotalUsageInput");
    if (dieselPicker) {
        if (dieselDeviceId && select.value === dieselDeviceId) {
            dieselPicker.style.display = "";
            if (usageInput) {
                usageInput.value = dieselTotalUsage > 0 ? String(dieselTotalUsage) : "";
            }
            if (dieselTotalUsageInput) {
                dieselTotalUsageInput.value = `${dieselTotalUsage} 公升`;
            }
        } else {
            dieselPicker.style.display = "none";
        }
    }
}

function setupElecBillPicker() {
    const billSelect = document.getElementById("elecBillSelect");
    if (!billSelect) return;
    billSelect.addEventListener("change", function () {
        const selected = billSelect.options[billSelect.selectedIndex];
        const usageInput = document.getElementById("usageInput");
        const dateInput = document.getElementById("recordDateInput");
        if (!selected.value) return;
        if (usageInput) usageInput.value = selected.value;
        if (dateInput && selected.dataset.date) dateInput.value = selected.dataset.date;
    });
}

function setupFuelBillPicker(selectId) {
    const billSelect = document.getElementById(selectId);
    if (!billSelect) return;
    billSelect.addEventListener("change", function () {
        const selected = billSelect.options[billSelect.selectedIndex];
        const usageInput = document.getElementById("usageInput");
        const dateInput = document.getElementById("recordDateInput");
        if (!selected.value) return;
        if (usageInput) usageInput.value = selected.value;
        if (dateInput && selected.dataset.date) dateInput.value = selected.dataset.date;
    });
}

async function loadLogs() {
    const moduleSelect = document.getElementById("logModuleFilter");
    const tableBody = document.getElementById("logTableBody");
    if (!moduleSelect || !tableBody) {
        return;
    }

    tableBody.innerHTML = "<tr><td colspan='6'>載入中...</td></tr>";

    try {
        const moduleName = moduleSelect.value || "all";
        const response = await fetch(`/calculation/logs?module=${encodeURIComponent(moduleName)}&limit=100`);
        const data = await response.json();

        if (!Array.isArray(data) || data.length === 0) {
            tableBody.innerHTML = "<tr><td colspan='6'>目前沒有紀錄</td></tr>";
            return;
        }

        tableBody.innerHTML = data
            .map(
                (item) => `
                <tr>
                    <td>${item.changed_at || "-"}</td>
                    <td>${item.module || "-"}</td>
                    <td>${item.action_type || "-"}</td>
                    <td>${item.entity_name || "-"}#${item.record_key || "-"}</td>
                    <td>${item.changed_by || "-"}</td>
                    <td>${item.change_details || "-"}</td>
                </tr>
            `
            )
            .join("");
    } catch (_error) {
        tableBody.innerHTML = "<tr><td colspan='6'>載入失敗，請稍後再試</td></tr>";
    }
}

function setupLogModal() {
    const modal = document.getElementById("logModal");
    const openBtn = document.getElementById("openLogModal");
    const closeBtn = document.getElementById("closeLogModal");
    const refreshBtn = document.getElementById("refreshLogBtn");
    const moduleSelect = document.getElementById("logModuleFilter");

    if (!modal || !openBtn || !closeBtn) {
        return;
    }

    openBtn.addEventListener("click", async () => {
        modal.classList.remove("hidden");
        await loadLogs();
    });

    closeBtn.addEventListener("click", () => {
        modal.classList.add("hidden");
    });

    modal.addEventListener("click", (event) => {
        if (event.target === modal) {
            modal.classList.add("hidden");
        }
    });

    if (refreshBtn) {
        refreshBtn.addEventListener("click", loadLogs);
    }

    if (moduleSelect) {
        moduleSelect.addEventListener("change", loadLogs);
    }
}

function setupDeleteConfirm() {
    const forms = document.querySelectorAll(".delete-record-form");
    forms.forEach((form) => {
        form.addEventListener("submit", (event) => {
            const confirmed = window.confirm("確定刪除？");
            if (!confirmed) {
                event.preventDefault();
            }
        });
    });
}

function initCalculationPage() {
    const deviceSelect = document.getElementById("deviceSelect");
    if (deviceSelect) {
        deviceSelect.addEventListener("change", updateUnit);
        updateUnit();
    }
    setupDeleteConfirm();
    setupLogModal();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCalculationPage);
} else {
    initCalculationPage();
}
