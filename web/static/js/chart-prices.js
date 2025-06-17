function initChart(labels, data) {
    const ctx = document.getElementById('priceChart').getContext('2d');
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Цена',
                data: data,
                fill: false,
                borderColor: '#3e95cd',
                tension: 0.1,
                pointRadius: 4,
                pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => `₽ ${ctx.raw.toLocaleString()}`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    ticks: {
                        callback: value => `₽ ${value.toLocaleString()}`
                    }
                }
            }
        }
    });
}

function updateChart(days) {
    const buttons = document.querySelectorAll('.filters button');
    buttons.forEach(btn => btn.classList.remove('active'));
    const clicked = Array.from(buttons).find(b => b.textContent.includes(days));
    if (clicked) clicked.classList.add('active');

    const newLabels = chartLabels.slice(-days);
    const newPrices = chartPrices.slice(-days);

    chart.data.labels = newLabels;
    chart.data.datasets[0].data = newPrices;
    chart.update();
}
