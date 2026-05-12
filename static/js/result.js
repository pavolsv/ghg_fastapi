function getResultData() {
    return window.resultPageData || {
        totalCo2e: 0,
        emissionTypeLabels: [],
        emissionTypeValues: [],
        endpoints: {
            generate: "/result/generate-ai-report",
            statusBase: "/result/ai-report-status/",
        },
    };
}

const palette = [
    "#2A9D8F",
    "#E9C46A",
    "#F4A261",
    "#E76F51",
    "#457B9D",
    "#A8DADC",
    "#8D99AE",
    "#BC6C25",
];

let pollingTimer = null;
let totalChart = null;
let typeChart = null;

function getGenerateElements() {
    return {
        generateBtn: document.getElementById("generateAiReportBtn"),
        statusText: document.getElementById("aiReportStatus"),
    };
}

function setStatus(message, type = "info") {
    const { statusText } = getGenerateElements();
    if (!statusText) {
        return;
    }

    statusText.textContent = message;
    statusText.dataset.state = type;
}

function setGeneratingState(isGenerating) {
    const { generateBtn } = getGenerateElements();
    if (!generateBtn) {
        return;
    }

    generateBtn.disabled = isGenerating;
    generateBtn.textContent = isGenerating
        ? "報告生成中，請稍候..."
        : "生成 AI 溫室氣體盤查報告";
}

function renderCharts() {
    if (typeof window.Chart === "undefined") {
        return false;
    }

    const totalCanvas = document.getElementById("totalPie");
    const typeCanvas = document.getElementById("typePie");
    if (!totalCanvas || !typeCanvas) {
        return false;
    }

    const resultData = getResultData();

    if (totalChart) {
        totalChart.destroy();
    }
    totalChart = new window.Chart(totalCanvas, {
        type: "pie",
        data: {
            labels: ["總排放量"],
            datasets: [
                {
                    data: [Math.max(Number(resultData.totalCo2e || 0), 0)],
                    backgroundColor: [palette[0]],
                    borderWidth: 1,
                },
            ],
        },
        options: {
            plugins: {
                legend: { display: true, position: "bottom" },
                tooltip: {
                    callbacks: {
                        label: (context) => `${context.label}: ${context.formattedValue} kg CO₂e`,
                    },
                },
            },
        },
    });

    const labels = [...(resultData.emissionTypeLabels || [])];
    const values = [...(resultData.emissionTypeValues || [])];
    if (labels.length === 0) {
        labels.push("暫無資料");
        values.push(1);
    }

    if (typeChart) {
        typeChart.destroy();
    }
    typeChart = new window.Chart(typeCanvas, {
        type: "pie",
        data: {
            labels,
            datasets: [
                {
                    data: values,
                    backgroundColor: labels.map((_, index) => palette[index % palette.length]),
                    borderWidth: 1,
                },
            ],
        },
        options: {
            plugins: {
                legend: { position: "bottom" },
                tooltip: {
                    callbacks: {
                        label: (context) => `${context.label}: ${context.formattedValue} kg CO₂e`,
                    },
                },
            },
        },
    });

    return true;
}

function waitForChartLibrary(onReady, retry = 0) {
    if (typeof window.Chart !== "undefined") {
        onReady();
        return;
    }

    if (retry >= 40) {
        setStatus("圖表套件載入逾時，請重新整理頁面再試。", "error");
        return;
    }

    window.setTimeout(() => {
        waitForChartLibrary(onReady, retry + 1);
    }, 100);
}

function initReportGenerator() {
    const { generateBtn } = getGenerateElements();
    if (!generateBtn || generateBtn.dataset.bound === "true") {
        return;
    }

    generateBtn.dataset.bound = "true";
    generateBtn.addEventListener("click", async () => {
        setGeneratingState(true);
        setStatus("正在建立生成任務...", "info");

        try {
            const resultData = getResultData();
            const generateUrl = resultData.endpoints?.generate || "/result/generate-ai-report";
            const data = await fetchJson(generateUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
            });

            if (!data.task_id) {
                throw new Error("未取得任務編號，請稍後重試。");
            }

            setStatus(data.message || "任務已建立，開始生成報告...", "info");
            await pollTaskStatus(data.task_id);
        } catch (error) {
            setStatus(error.message || "任務建立失敗", "error");
            setGeneratingState(false);
        }
    });
}

function initResultPage() {
    const hasResultCanvas = !!document.getElementById("totalPie") || !!document.getElementById("typePie");
    if (!hasResultCanvas) {
        return;
    }

    waitForChartLibrary(() => {
        renderCharts();
    });
    initReportGenerator();
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        const detail = data.detail || data.message || "請稍後再試";
        throw new Error(detail);
    }
    return data;
}

async function pollTaskStatus(taskId) {
    const resultData = getResultData();
    const statusBase = resultData.endpoints?.statusBase || "/result/ai-report-status/";
    const statusUrl = `${statusBase}${encodeURIComponent(taskId)}`;

    if (pollingTimer) {
        clearInterval(pollingTimer);
    }

    pollingTimer = setInterval(async () => {
        try {
            const data = await fetchJson(statusUrl);
            if (data.status === "completed") {
                clearInterval(pollingTimer);
                pollingTimer = null;
                setStatus(data.message || "報告生成完成，準備下載...", "success");
                setGeneratingState(false);

                if (data.download_url) {
                    window.location.href = data.download_url;
                }
                return;
            }

            if (data.status === "failed") {
                clearInterval(pollingTimer);
                pollingTimer = null;
                setStatus(data.error || data.message || "報告生成失敗", "error");
                setGeneratingState(false);
                return;
            }

            setStatus(data.message || "報告生成中...", "info");
        } catch (error) {
            clearInterval(pollingTimer);
            pollingTimer = null;
            setStatus(error.message || "狀態查詢失敗", "error");
            setGeneratingState(false);
        }
    }, 2500);
}

document.addEventListener("DOMContentLoaded", initResultPage);
document.addEventListener("htmx:afterSettle", initResultPage);
document.addEventListener("htmx:afterHeadMerge", initResultPage);

// Handle initial execution when script is injected after DOM is already ready.
initResultPage();
