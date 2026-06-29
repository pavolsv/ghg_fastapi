/**
 * Shared Audit Log Modal
 * Usage: include this script, then call LogModal.open(defaultModule)
 */
const LogModal = (() => {
    let _modal = null;

    function _buildHtml() {
        const el = document.createElement("div");
        el.id = "sharedLogModal";
        el.className = "log-modal hidden";
        el.innerHTML = `
            <div class="log-modal-content">
                <div class="log-modal-header">
                    <h3>資料變更紀錄</h3>
                    <button type="button" id="logModalClose" class="log-modal-close">×</button>
                </div>
                <div class="log-modal-toolbar">
                    <div class="log-filter-row">
                        <select id="logFilterModule" class="log-filter-select">
                            <option value="all">全部模組</option>
                            <option value="calculation">排放計算</option>
                            <option value="factor_management">排放因子</option>
                            <option value="devices">排放源</option>
                            <option value="company_info">公司資料</option>
                        </select>
                        <select id="logFilterAction" class="log-filter-select">
                            <option value="all">全部操作</option>
                            <option value="CREATE">新增</option>
                            <option value="UPDATE">編輯</option>
                            <option value="DELETE">刪除</option>
                            <option value="UPSERT">匯入(無變更)</option>
                        </select>
                        <input type="date" id="logFilterStartDate" class="log-filter-input" placeholder="開始日期">
                        <input type="date" id="logFilterEndDate" class="log-filter-input" placeholder="結束日期">
                        <button type="button" id="logRefreshBtn" class="btn-log-secondary">重新整理</button>
                        <button type="button" id="logExportBtn" class="btn-log-export">⬇ 匯出 CSV</button>
                    </div>
                    <div id="logPaginationInfo" class="log-pagination-info"></div>
                </div>
                <div class="log-table-wrap">
                    <table class="log-table">
                        <thead>
                            <tr>
                                <th>時間</th>
                                <th>模組</th>
                                <th>操作</th>
                                <th>實體 / 主鍵</th>
                                <th>操作者</th>
                                <th>變更內容</th>
                            </tr>
                        </thead>
                        <tbody id="logTableBody"></tbody>
                    </table>
                </div>
                <div class="log-modal-footer">
                    <button type="button" id="logPrevPage" class="btn-log-secondary">上一頁</button>
                    <span id="logPageLabel" class="log-page-label">第 1 頁</span>
                    <button type="button" id="logNextPage" class="btn-log-secondary">下一頁</button>
                </div>
            </div>`;
        document.body.appendChild(el);
        return el;
    }

    let _page = 1;
    const _pageSize = 50;

    function _getFilters() {
        return {
            module: document.getElementById("logFilterModule")?.value || "all",
            action_type: document.getElementById("logFilterAction")?.value || "all",
            start_date: document.getElementById("logFilterStartDate")?.value || "",
            end_date: document.getElementById("logFilterEndDate")?.value || "",
        };
    }

    function _buildQuery(page) {
        const f = _getFilters();
        const params = new URLSearchParams({ page, page_size: _pageSize });
        if (f.module !== "all") params.set("module", f.module);
        if (f.action_type !== "all") params.set("action_type", f.action_type);
        if (f.start_date) params.set("start_date", f.start_date);
        if (f.end_date) params.set("end_date", f.end_date);
        return params.toString();
    }

    async function _load(page) {
        _page = page;
        const tbody = document.getElementById("logTableBody");
        const info = document.getElementById("logPaginationInfo");
        const pageLabel = document.getElementById("logPageLabel");
        tbody.innerHTML = '<tr><td colspan="6" class="log-loading">載入中…</td></tr>';

        try {
            const res = await fetch(`/logs/?${_buildQuery(page)}`);
            const json = await res.json();
            const { total, data } = json;

            if (!data || data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="log-empty">目前沒有符合條件的紀錄</td></tr>';
                if (info) info.textContent = "共 0 筆";
                if (pageLabel) pageLabel.textContent = "第 1 頁";
                return;
            }

            const actionLabels = {
                CREATE: '<span class="log-badge log-badge-create">新增</span>',
                UPDATE: '<span class="log-badge log-badge-update">編輯</span>',
                DELETE: '<span class="log-badge log-badge-delete">刪除</span>',
                UPSERT: '<span class="log-badge log-badge-upsert">匯入</span>',
            };

            tbody.innerHTML = data.map(row => `
                <tr>
                    <td class="log-td-time">${row.changed_at || "-"}</td>
                    <td>${row.module || "-"}</td>
                    <td>${actionLabels[row.action_type] || row.action_type}</td>
                    <td>${row.entity_name || "-"} <small class="log-key">#${row.record_key || "-"}</small></td>
                    <td>${row.changed_by || "-"}</td>
                    <td class="log-td-detail">${row.change_details || "-"}</td>
                </tr>`).join("");

            const totalPages = Math.ceil(total / _pageSize);
            if (info) info.textContent = `共 ${total} 筆`;
            if (pageLabel) pageLabel.textContent = `第 ${page} / ${totalPages} 頁`;

            const prevBtn = document.getElementById("logPrevPage");
            const nextBtn = document.getElementById("logNextPage");
            if (prevBtn) prevBtn.disabled = page <= 1;
            if (nextBtn) nextBtn.disabled = page >= totalPages;
        } catch (_) {
            tbody.innerHTML = '<tr><td colspan="6" class="log-empty">載入失敗，請稍後再試</td></tr>';
        }
    }

    function _exportCsv() {
        const f = _getFilters();
        const params = new URLSearchParams();
        if (f.module !== "all") params.set("module", f.module);
        if (f.action_type !== "all") params.set("action_type", f.action_type);
        if (f.start_date) params.set("start_date", f.start_date);
        if (f.end_date) params.set("end_date", f.end_date);
        window.location.href = `/logs/export/csv?${params.toString()}`;
    }

    function open(defaultModule) {
        if (!_modal) {
            _modal = _buildHtml();

            document.getElementById("logModalClose").addEventListener("click", close);
            _modal.addEventListener("click", e => { if (e.target === _modal) close(); });
            document.getElementById("logRefreshBtn").addEventListener("click", () => _load(1));
            document.getElementById("logExportBtn").addEventListener("click", _exportCsv);
            document.getElementById("logPrevPage").addEventListener("click", () => _load(_page - 1));
            document.getElementById("logNextPage").addEventListener("click", () => _load(_page + 1));
            ["logFilterModule", "logFilterAction", "logFilterStartDate", "logFilterEndDate"].forEach(id => {
                document.getElementById(id)?.addEventListener("change", () => _load(1));
            });
        }

        if (defaultModule) {
            const sel = document.getElementById("logFilterModule");
            if (sel) sel.value = defaultModule;
        }

        _modal.classList.remove("hidden");
        _load(1);
    }

    function close() {
        _modal?.classList.add("hidden");
    }

    return { open, close };
})();
