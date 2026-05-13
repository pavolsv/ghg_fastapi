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
    setupDeleteConfirm();
    setupLogModal();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCalculationPage);
} else {
    initCalculationPage();
}
