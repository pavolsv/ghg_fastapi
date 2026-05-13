function getResultData() {
    return window.resultPageData || {
        totalCo2e: 0,
        emissionTypeLabels: [],
        emissionTypeValues: [],
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

let totalChart = null;
let typeChart = null;

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

function initResultPage() {
    const hasResultCanvas = !!document.getElementById("totalPie") || !!document.getElementById("typePie");
    if (!hasResultCanvas) {
        return;
    }

    waitForChartLibrary(() => {
        renderCharts();
    });
}

document.addEventListener("DOMContentLoaded", initResultPage);
document.addEventListener("htmx:afterSettle", initResultPage);
document.addEventListener("htmx:afterHeadMerge", initResultPage);

// Handle initial execution when script is injected after DOM is already ready.
initResultPage();
