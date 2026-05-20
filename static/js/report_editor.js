function setupReportEditorPage() {
    const createDraftBtn = document.getElementById("createReportDraftBtn");
    const exportDraftBtn = document.getElementById("exportReportDraftBtn");
    const refreshDraftListBtn = document.getElementById("refreshDraftListBtn");
    const draftListEl = document.getElementById("reportDraftList");
    const editorPanel = document.getElementById("reportEditorPanel");
    const meta = document.getElementById("reportDraftMeta");

    if (!createDraftBtn || !draftListEl || !editorPanel || !meta) {
        return;
    }

    const state = {
        draftId: null,
        initialDraftId: window.reportEditorConfig?.initialDraftId || "",
    };

    const setSectionStatus = (sectionId, text) => {
        const statusEl = document.getElementById(`section-status-${sectionId}`);
        if (statusEl) {
            statusEl.textContent = text;
        }
    };

    const setEditorValue = (sectionId, value) => {
        const textarea = document.getElementById(`section-editor-${sectionId}`);
        if (textarea) {
            textarea.value = value || "";
        }
    };

    const getEditorValue = (sectionId) => {
        const textarea = document.getElementById(`section-editor-${sectionId}`);
        return textarea ? textarea.value : "";
    };

    const renderDraftList = (drafts) => {
        if (!Array.isArray(drafts) || drafts.length === 0) {
            draftListEl.innerHTML = '<div class="report-empty-state">目前沒有草稿，請先建立一份新的報告草稿。</div>';
            return;
        }

        draftListEl.innerHTML = drafts
            .map((draft) => {
                const activeClass = draft.draft_id === state.draftId ? " is-active" : "";
                return `
                    <article class="report-draft-item${activeClass}" data-draft-id="${draft.draft_id}">
                        <div class="report-draft-row">
                            <strong>${draft.title || "溫室氣體盤查報告草稿"}</strong>
                            <span class="draft-status">${draft.status || "draft"}</span>
                        </div>
                        <div class="report-draft-meta-row">草稿編號：${draft.draft_id}</div>
                        <div class="report-draft-meta-row">年度：${draft.inventory_year || "-"}｜更新：${draft.updated_at || "-"}</div>
                        <div class="report-draft-meta-row">已完成章節：${draft.completed_sections || 0}/${draft.total_sections || 0}</div>
                        <button type="button" class="btn-report-inline btn-open-draft" data-draft-id="${draft.draft_id}">續編</button>
                    </article>
                `;
            })
            .join("");
    };

    const refreshDraftList = async () => {
        const res = await fetch("/reports/drafts");
        if (!res.ok) {
            throw new Error("草稿列表載入失敗");
        }
        const payload = await res.json();
        renderDraftList(payload.drafts || []);
        return payload.drafts || [];
    };

    const loadDraft = async (draftId) => {
        const res = await fetch(`/reports/drafts/${encodeURIComponent(draftId)}`);
        if (!res.ok) {
            throw new Error("讀取草稿失敗");
        }

        const payload = await res.json();
        state.draftId = payload.draft_id;
        const sectionsPayload = JSON.parse(payload.sections_payload || "{}");

        Object.keys(sectionsPayload).forEach((sectionId) => {
            const section = sectionsPayload[sectionId] || {};
            setEditorValue(sectionId, section.content || "");
            setSectionStatus(sectionId, section.updated_at ? `最後更新：${section.updated_at}` : "尚未儲存");
        });

        meta.textContent = `草稿編號：${payload.draft_id}｜盤查年度：${payload.inventory_year || "-"}｜快照時間：${payload.snapshot_generated_at || "-"}`;
        editorPanel.classList.remove("hidden");
        if (exportDraftBtn) {
            exportDraftBtn.disabled = false;
        }

        await refreshDraftList();
    };

    draftListEl.addEventListener("click", async (event) => {
        const button = event.target.closest(".btn-open-draft");
        if (!button) {
            return;
        }
        const draftId = button.dataset.draftId;
        if (!draftId) {
            return;
        }
        button.disabled = true;
        try {
            await loadDraft(draftId);
        } catch (error) {
            meta.textContent = `續編失敗：${error}`;
        } finally {
            button.disabled = false;
        }
    });

    createDraftBtn.addEventListener("click", async () => {
        createDraftBtn.disabled = true;
        try {
            const res = await fetch("/reports/drafts", { method: "POST" });
            if (!res.ok) {
                throw new Error(await res.text());
            }
            const payload = await res.json();
            await loadDraft(payload.draft_id);
        } catch (error) {
            meta.textContent = `建立草稿失敗：${error}`;
        } finally {
            createDraftBtn.disabled = false;
        }
    });

    if (refreshDraftListBtn) {
        refreshDraftListBtn.addEventListener("click", async () => {
            refreshDraftListBtn.disabled = true;
            try {
                await refreshDraftList();
            } catch (error) {
                meta.textContent = `草稿列表更新失敗：${error}`;
            } finally {
                refreshDraftListBtn.disabled = false;
            }
        });
    }

    document.querySelectorAll(".btn-save-section").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const sectionId = btn.dataset.sectionId;
            if (!sectionId || !state.draftId) {
                return;
            }
            btn.disabled = true;
            setSectionStatus(sectionId, "儲存中...");
            try {
                const content = getEditorValue(sectionId);
                const res = await fetch(`/reports/drafts/${encodeURIComponent(state.draftId)}/sections/${encodeURIComponent(sectionId)}`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ content }),
                });
                if (!res.ok) {
                    throw new Error(await res.text());
                }
                const payload = await res.json();
                setSectionStatus(sectionId, `已儲存：${payload.updated_at || ""}`);
                await refreshDraftList();
            } catch (error) {
                setSectionStatus(sectionId, `儲存失敗：${error}`);
            } finally {
                btn.disabled = false;
            }
        });
    });

    document.querySelectorAll(".btn-insert-data").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const sectionId = btn.dataset.sectionId;
            if (!sectionId || !state.draftId) {
                return;
            }
            btn.disabled = true;
            setSectionStatus(sectionId, "插入數據中...");
            try {
                const res = await fetch(`/reports/drafts/${encodeURIComponent(state.draftId)}/sections/${encodeURIComponent(sectionId)}/insert-data`, {
                    method: "POST",
                });
                if (!res.ok) {
                    throw new Error(await res.text());
                }
                const payload = await res.json();
                setEditorValue(sectionId, payload.content || "");
                setSectionStatus(sectionId, payload.updated_at ? `已插入：${payload.updated_at}` : "已插入系統數據");
                await refreshDraftList();
            } catch (error) {
                setSectionStatus(sectionId, `插入失敗：${error}`);
            } finally {
                btn.disabled = false;
            }
        });
    });

    document.querySelectorAll(".btn-generate-ai").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const sectionId = btn.dataset.sectionId;
            if (!sectionId || !state.draftId) {
                return;
            }
            btn.disabled = true;
            setSectionStatus(sectionId, "AI 生成中...");
            try {
                const res = await fetch(`/reports/drafts/${encodeURIComponent(state.draftId)}/sections/${encodeURIComponent(sectionId)}/generate`, {
                    method: "POST",
                });
                if (!res.ok) {
                    throw new Error(await res.text());
                }
                const payload = await res.json();
                setEditorValue(sectionId, payload.content || "");
                setSectionStatus(sectionId, payload.updated_at ? `AI 更新：${payload.updated_at}` : "AI 生成完成");
                await refreshDraftList();
            } catch (error) {
                setSectionStatus(sectionId, `AI 生成失敗：${error}`);
            } finally {
                btn.disabled = false;
            }
        });
    });

    if (exportDraftBtn) {
        exportDraftBtn.addEventListener("click", async () => {
            if (!state.draftId) {
                return;
            }
            exportDraftBtn.disabled = true;
            try {
                const res = await fetch(`/reports/drafts/${encodeURIComponent(state.draftId)}/export`, {
                    method: "POST",
                });
                if (!res.ok) {
                    throw new Error(await res.text());
                }
                const blob = await res.blob();
                const link = document.createElement("a");
                const url = URL.createObjectURL(blob);
                link.href = url;
                link.download = `ai_report_${state.draftId}.docx`;
                document.body.appendChild(link);
                link.click();
                link.remove();
                URL.revokeObjectURL(url);
                meta.textContent = `${meta.textContent}｜匯出完成`;
                await refreshDraftList();
            } catch (error) {
                meta.textContent = `匯出失敗：${error}`;
            } finally {
                exportDraftBtn.disabled = false;
            }
        });
    }

    refreshDraftList()
        .then((drafts) => {
            if (state.initialDraftId) {
                return loadDraft(state.initialDraftId);
            }
            if (!state.draftId && drafts.length > 0) {
                return loadDraft(drafts[0].draft_id);
            }
            return undefined;
        })
        .catch((error) => {
            meta.textContent = `初始化失敗：${error}`;
        });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupReportEditorPage);
} else {
    setupReportEditorPage();
}
