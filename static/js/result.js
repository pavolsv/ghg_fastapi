function getResultData() {
    return window.resultPageData || {
        totalCo2e: 0,
        scopeLabels: [],
        scopeValues: [],
        emissionTypeLabels: [],
        emissionTypeValues: [],
        deviceLabels: [],
        deviceValues: [],
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

let scopeChart = null;
let typeChart = null;
let deviceChart = null;

function renderCharts() {
    if (typeof window.Chart === "undefined") {
        return false;
    }

    const scopeCanvas = document.getElementById("scopeDonut");
    const typeCanvas = document.getElementById("typePie");
    if (!scopeCanvas && !typeCanvas) {
        return false;
    }

    const resultData = getResultData();

    if (scopeCanvas) {
        if (scopeChart) {
            scopeChart.destroy();
        }
        const sLabels = resultData.scopeLabels || [];
        const sValues = resultData.scopeValues || [];
        const scopeColors = ["#059669", "#2563eb"];
        if (sLabels.length === 0) {
            sLabels.push("暫無資料");
            sValues.push(1);
        }
        scopeChart = new window.Chart(scopeCanvas, {
            type: "doughnut",
            data: {
                labels: sLabels,
                datasets: [{
                    data: sValues,
                    backgroundColor: sLabels.map((_, i) => scopeColors[i % scopeColors.length]),
                    borderWidth: 2,
                    borderColor: "#ffffff",
                }],
            },
            options: {
                cutout: "55%",
                plugins: {
                    legend: { position: "bottom" },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                                const pct = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
                                return `${ctx.label}: ${ctx.formattedValue} kg CO₂e (${pct}%)`;
                            },
                        },
                    },
                },
            },
        });
    }

    const labels = [...(resultData.emissionTypeLabels || [])];
    const values = [...(resultData.emissionTypeValues || [])];
    if (labels.length === 0) {
        labels.push("暫無資料");
        values.push(1);
    }

    if (typeCanvas) {
        if (typeChart) {
            typeChart.destroy();
        }
        typeChart = new window.Chart(typeCanvas, {
            type: "pie",
            data: {
                labels,
                datasets: [{
                    data: values,
                    backgroundColor: labels.map((_, index) => palette[index % palette.length]),
                    borderWidth: 2,
                    borderColor: "#ffffff",
                }],
            },
            options: {
                plugins: {
                    legend: { position: "bottom" },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                                const pct = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
                                return `${ctx.label}: ${ctx.formattedValue} kg CO₂e (${pct}%)`;
                            },
                        },
                    },
                },
            },
        });
    }

    const deviceCanvas = document.getElementById("deviceBar");
    if (deviceCanvas) {
        if (deviceChart) {
            deviceChart.destroy();
        }
        const devLabels = resultData.deviceLabels || [];
        const devValues = resultData.deviceValues || [];
        if (devLabels.length > 0) {
            const barHeight = Math.max(280, devLabels.length * 40);
            deviceCanvas.parentElement.style.height = barHeight + "px";
            deviceChart = new window.Chart(deviceCanvas, {
                type: "bar",
                data: {
                    labels: devLabels,
                    datasets: [{
                        label: "kg CO₂e",
                        data: devValues,
                        backgroundColor: devLabels.map((_, i) => palette[i % palette.length]),
                        borderWidth: 1,
                        borderRadius: 4,
                    }],
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => `${ctx.parsed.x.toLocaleString()} kg CO₂e`,
                            },
                        },
                    },
                    scales: {
                        x: {
                            beginAtZero: true,
                            title: { display: true, text: "kg CO₂e", font: { weight: "bold" } },
                            ticks: {
                                callback: (v) => v.toLocaleString(),
                            },
                        },
                        y: {
                            ticks: {
                                font: { size: 12 },
                            },
                        },
                    },
                },
            });
        }
    }

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
    const hasResultCanvas = !!document.getElementById("scopeDonut") || !!document.getElementById("typePie");
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
