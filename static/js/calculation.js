async function loadLogs() {
    const moduleSelect = document.getElementById("logModuleFilter");
    const tableBody = document.getElementById("logTableBody");
    if (!moduleSelect || !tableBody) {
        return;
    }


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
            } catch (error) {
                meta.textContent = `匯出失敗：${error}`;
            } finally {
                exportDraftBtn.disabled = false;
            }
        });
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCalculationPage);
} else {
    initCalculationPage();
}
