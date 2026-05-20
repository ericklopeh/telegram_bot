/**
 * Dashboard operativo — UI (sparklines simuladas, sidebar móvil, Lucide).
 * No altera datos del servidor; solo presentación.
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

    /** Serie de 7 puntos que converge al valor actual (tendencia simulada). */
    function syntheticSeries(current, seed) {
        var n = Math.max(0, Number(current) || 0);
        var base = Math.max(0, n - 3 + (seed % 3));
        var pts = [];
        for (var i = 0; i < 6; i++) {
            var t = i / 5;
            pts.push(Math.round(base + (n - base) * t + ((seed + i) % 2)));
        }
        pts.push(n);
        return pts;
    }

    function buildSparkline(canvas, values, color, fillColor) {
        if (!canvas || typeof Chart === "undefined") return;
        var labels = values.map(function (_, i) {
            var d = new Date();
            d.setDate(d.getDate() - (values.length - 1 - i));
            return d.toLocaleDateString("es-MX", { day: "2-digit", month: "2-digit" });
        });

        new Chart(canvas, {
            type: "line",
            data: {
                labels: labels,
                datasets: [
                    {
                        data: values,
                        borderColor: color,
                        backgroundColor: fillColor,
                        borderWidth: 2,
                        fill: true,
                        tension: 0.35,
                        pointRadius: 0,
                        pointHoverRadius: 3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: true, mode: "index", intersect: false },
                },
                scales: {
                    x: {
                        display: true,
                        grid: { display: false },
                        ticks: { maxTicksLimit: 3, font: { size: 9 }, color: "#94a3b8" },
                    },
                    y: { display: false, min: 0 },
                },
                interaction: { mode: "nearest", axis: "x", intersect: false },
            },
        });
    }

    function initSparklines() {
        var root = document.getElementById("dashSlaCharts");
        if (!root || typeof Chart === "undefined") return;

        var configs = [
            { id: "sparkAbiertos", key: "abiertos", color: "#ea580c", fill: "rgba(234, 88, 12, 0.12)" },
            { id: "sparkPrep", key: "prep", color: "#ea580c", fill: "rgba(234, 88, 12, 0.12)" },
            { id: "sparkCompulsa", key: "compulsa", color: "#16a34a", fill: "rgba(22, 163, 74, 0.12)" },
        ];

        var data = {};
        try {
            data = JSON.parse(root.getAttribute("data-sla") || "{}");
        } catch (e) {
            data = {};
        }

        configs.forEach(function (cfg, idx) {
            var canvas = document.getElementById(cfg.id);
            if (!canvas) return;
            var current = data[cfg.key] != null ? data[cfg.key] : 0;
            var series = syntheticSeries(current, idx + 1);
            buildSparkline(canvas, series, cfg.color, cfg.fill);
            canvas.parentElement.setAttribute("title", "Tendencia simulada · valor actual: " + current);
        });
    }

    function initLucide() {
        if (typeof lucide !== "undefined" && lucide.createIcons) {
            lucide.createIcons();
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        initSidebar();
        initSparklines();
        initLucide();
    });
})();
