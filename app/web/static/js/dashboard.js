/**
 * Dashboard operativo — UI (sparklines KPI, tendencias, sidebar, Lucide).
 * Solo presentación; no altera datos del servidor.
 * Fase 1: tokens & shell unificados vía gaman-ui.css + base_dash.html.
 */
(function () {
    "use strict";

    function initSidebar() {
        var sidebar = document.getElementById("dashSidebar");
        var backdrop = document.getElementById("dashSidebarBackdrop");
        var toggle = document.getElementById("dashSidebarToggle");
        if (!sidebar || !toggle) return;

        function open() {
            sidebar.classList.add("is-open");
            if (backdrop) backdrop.classList.add("is-visible");
        }

        function close() {
            sidebar.classList.remove("is-open");
            if (backdrop) backdrop.classList.remove("is-visible");
        }

        toggle.addEventListener("click", function () {
            if (sidebar.classList.contains("is-open")) close();
            else open();
        });
        if (backdrop) backdrop.addEventListener("click", close);
        window.addEventListener("resize", function () {
            if (window.innerWidth > 991) close();
        });
    }

    function syntheticSeries(current, seed, isPercent) {
        var n = Math.max(0, Number(current) || 0);
        if (isPercent) n = Math.min(100, Math.max(n, 40));
        var base = Math.max(0, n - 4 + (seed % 4));
        var pts = [];
        for (var i = 0; i < 6; i++) {
            var t = i / 5;
            pts.push(Math.round(base + (n - base) * t + ((seed + i) % 3) - 1));
        }
        pts.push(n);
        return pts.map(function (v) {
            return isPercent ? Math.max(0, Math.min(100, v)) : Math.max(0, v);
        });
    }

    function buildLineChart(canvas, values, color, fillColor) {
        if (!canvas || typeof Chart === "undefined") return;
        new Chart(canvas, {
            type: "line",
            data: {
                labels: values.map(function () {
                    return "";
                }),
                datasets: [
                    {
                        data: values,
                        borderColor: color,
                        backgroundColor: fillColor,
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
                scales: {
                    x: { display: false },
                    y: { display: false, min: 0 },
                },
            },
        });
    }

    function buildBarChart(canvas, values, color, fillColor) {
        if (!canvas || typeof Chart === "undefined") return;
        new Chart(canvas, {
            type: "bar",
            data: {
                labels: values.map(function () {
                    return "";
                }),
                datasets: [
                    {
                        data: values,
                        backgroundColor: color,
                        borderRadius: 3,
                        barPercentage: 0.7,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
                scales: {
                    x: { display: false },
                    y: { display: false, min: 0 },
                },
            },
        });
    }

    function buildDoughnutChart(canvas, value, colors) {
        if (!canvas || typeof Chart === "undefined") return;
        var v = Math.min(100, Math.max(0, Number(value) || 0));
        new Chart(canvas, {
            type: "doughnut",
            data: {
                labels: ["OK", "Resto"],
                datasets: [
                    {
                        data: [v, 100 - v],
                        backgroundColor: colors || ["#22c55e", "#e2e8f0"],
                        borderWidth: 0,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "68%",
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
            },
        });
    }

    function initHeroSparklines() {
        if (typeof Chart === "undefined") return;
        var cards = document.querySelectorAll(".dash-hero-kpi[data-spark-value]");
        cards.forEach(function (card, idx) {
            var canvas = card.querySelector(".dash-hero-spark-canvas");
            if (!canvas) return;
            var current = Number(card.getAttribute("data-spark-value")) || 0;
            var color = card.getAttribute("data-spark-color") || "#3b82f6";
            var fill = card.getAttribute("data-spark-fill") || "rgba(59, 130, 246, 0.2)";
            var series = syntheticSeries(current, idx + 3, false);
            buildLineChart(canvas, series, color, fill);
        });
    }

    function initTrendCharts() {
        var root = document.getElementById("dashTrendCharts");
        if (!root || typeof Chart === "undefined") return;

        var charts = [];
        try {
            charts = JSON.parse(root.getAttribute("data-charts") || "[]");
        } catch (e) {
            charts = [];
        }

        charts.forEach(function (ch, idx) {
            var canvas = document.getElementById("chartTrend-" + ch.key);
            if (!canvas) return;
            var current = ch.value != null ? ch.value : 0;
            var ctype = ch.chart_type || canvas.getAttribute("data-chart-type") || "line";
            var color = ch.color || "#3b82f6";
            var fill = ch.fill || "rgba(59, 130, 246, 0.15)";

            if (ctype === "doughnut") {
                buildDoughnutChart(canvas, current, [color, "#e2e8f0"]);
            } else if (ctype === "bar") {
                buildBarChart(canvas, syntheticSeries(current, idx + 2, false), color, fill);
            } else {
                buildLineChart(
                    canvas,
                    syntheticSeries(current, idx + 2, !!ch.is_percent),
                    color,
                    fill
                );
            }
        });
    }

    function initLucide() {
        // Lucide init centralized in gaman-ui.js (Fase 1)
        // if (typeof lucide !== "undefined" && lucide.createIcons) { lucide.createIcons(); }
    }

    document.addEventListener("DOMContentLoaded", function () {
        initSidebar();
        initHeroSparklines();
        initTrendCharts();
        initLucide();
    });
})();
