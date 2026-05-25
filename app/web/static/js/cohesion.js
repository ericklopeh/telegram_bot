/**
 * P61-P69 — realtime client, command palette, toasts, reconnect, polling fallback
 */
(function () {
    "use strict";

    var pollInterval = 15000;
    var pollBackoff = 15000;
    var maxPollBackoff = 60000;
    var wsReconnectDelay = 3000;
    var wsMaxReconnect = 8;
    var wsConnections = [];

    function showToast(message, tone) {
        var c = document.getElementById("cohToastContainer");
        if (!c) {
            c = document.createElement("div");
            c.id = "cohToastContainer";
            c.className = "coh-toast-container";
            document.body.appendChild(c);
        }
        var el = document.createElement("div");
        el.className = "coh-toast";
        if (tone === "danger") el.style.background = "#b91c1c";
        el.textContent = message;
        c.appendChild(el);
        setTimeout(function () {
            el.remove();
        }, 4500);
    }

    function setLive(ok) {
        var dot = document.getElementById("cohLiveDot");
        if (!dot) return;
        dot.style.display = "inline-block";
        dot.style.background = ok ? "#22c55e" : "#94a3b8";
    }

    function pollRealtime() {
        fetch("/api/realtime/poll?channels=activity,notifications,dashboard,jobs,ops,heartbeat")
            .then(function (r) {
                if (!r.ok) throw new Error("poll " + r.status);
                return r.json();
            })
            .then(function (data) {
                pollBackoff = pollInterval;
                setLive(true);
                if (data.notifications && data.notifications.event === "new") {
                    showToast(data.notifications.payload.title || "Nueva notificación", "info");
                    refreshNotifBadge();
                }
            })
            .catch(function () {
                setLive(false);
                pollBackoff = Math.min(pollBackoff * 1.5, maxPollBackoff);
            });
    }

    function refreshNotifBadge() {
        fetch("/api/notifications")
            .then(function (r) {
                return r.json();
            })
            .then(function (data) {
                var badge = document.getElementById("cohNotifBadge");
                if (badge) badge.setAttribute("data-count", String(data.unread || 0));
            })
            .catch(function () {});
    }

    function connectWs(url, label) {
        var attempts = 0;
        var socket = null;

        function connect() {
            if (typeof WebSocket === "undefined") return;
            try {
                var proto = location.protocol === "https:" ? "wss:" : "ws:";
                socket = new WebSocket(proto + "//" + location.host + url);
            } catch (e) {
                return;
            }
            socket.onopen = function () {
                attempts = 0;
                setLive(true);
            };
            socket.onmessage = function () {
                setLive(true);
            };
            socket.onclose = function () {
                setLive(false);
                if (attempts < wsMaxReconnect) {
                    attempts += 1;
                    setTimeout(connect, wsReconnectDelay * attempts);
                }
            };
            socket.onerror = function () {
                try {
                    socket.close();
                } catch (e) {}
            };
        }

        connect();
        wsConnections.push({ label: label, reconnect: connect });
    }

    function initCommandPalette() {
        var overlay = document.getElementById("cohCommandPalette");
        if (!overlay) return;
        var input = overlay.querySelector(".coh-palette__input");
        var results = overlay.querySelector(".coh-palette__results");

        function open() {
            overlay.classList.add("is-open");
            if (input) {
                input.value = "";
                input.focus();
            }
            renderResults("");
        }

        function close() {
            overlay.classList.remove("is-open");
        }

        function renderResults(q) {
            if (!results) return;
            fetch("/api/command-palette?q=" + encodeURIComponent(q))
                .then(function (r) {
                    return r.json();
                })
                .then(function (data) {
                    var html = "";
                    (data.actions || []).forEach(function (a) {
                        html +=
                            '<a class="list-group-item list-group-item-action" href="' +
                            a.href +
                            '">' +
                            a.label +
                            "</a>";
                    });
                    (data.groups || []).forEach(function (g) {
                        html += '<div class="px-3 py-1 small text-muted">' + g.label + "</div>";
                        (g.entries || []).forEach(function (it) {
                            html +=
                                '<a class="list-group-item list-group-item-action" href="' +
                                it.href +
                                '">' +
                                it.title +
                                "</a>";
                        });
                    });
                    results.innerHTML = html || '<div class="p-3 text-muted">Sin resultados</div>';
                })
                .catch(function () {
                    results.innerHTML = '<div class="p-3 text-muted">Búsqueda no disponible</div>';
                });
        }

        document.addEventListener("keydown", function (e) {
            if ((e.ctrlKey || e.metaKey) && e.key === "k") {
                e.preventDefault();
                open();
            }
            if (e.key === "Escape") close();
        });
        overlay.addEventListener("click", function (e) {
            if (e.target === overlay) close();
        });
        if (input) {
            input.addEventListener("input", function () {
                renderResults(input.value.trim());
            });
        }
    }

    function schedulePoll() {
        pollRealtime();
        setTimeout(schedulePoll, pollBackoff);
    }

    document.addEventListener("DOMContentLoaded", function () {
        schedulePoll();
        refreshNotifBadge();
        initCommandPalette();
        connectWs("/ws/notifications", "notifications");
        connectWs("/ws/activity", "activity");
    });

    window.CohCohesion = {
        showToast: showToast,
        pollRealtime: pollRealtime,
        reconnectAll: function () {
            wsConnections.forEach(function (c) {
                if (c.reconnect) c.reconnect();
            });
        },
    };
})();
