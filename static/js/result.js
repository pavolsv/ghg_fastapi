const resultData = window.resultPageData || {
    totalCo2e: 0,
    emissionTypeLabels: [],
    emissionTypeValues: [],
};

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

const totalCtx = document.getElementById("totalPie");
if (totalCtx) {
    new Chart(totalCtx, {
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
}

const typeCtx = document.getElementById("typePie");
if (typeCtx) {
    const labels = resultData.emissionTypeLabels || [];
    const values = resultData.emissionTypeValues || [];

    if (labels.length === 0) {
        labels.push("暂无数据");
        values.push(1);
    }

    new Chart(typeCtx, {
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
}
