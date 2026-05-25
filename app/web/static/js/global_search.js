/** P41 — debounce búsqueda global en navbar */
(function () {
    "use strict";
    var input = document.getElementById("globalSearchInput");
    if (!input) return;
    var timer;
    input.addEventListener("input", function () {
        clearTimeout(timer);
        var q = input.value.trim();
        if (q.length < 2) return;
        timer = setTimeout(function () {
            window.location.href = "/search?q=" + encodeURIComponent(q);
        }, 400);
    });
    input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            e.preventDefault();
            var q = input.value.trim();
            if (q.length >= 2) {
                window.location.href = "/search?q=" + encodeURIComponent(q);
            }
        }
    });
})();
