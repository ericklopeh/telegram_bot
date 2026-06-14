/**
 * Gaman UI — Interactive Components
 * Dark mode, toasts, skeleton loading, drag-and-drop upload, table tools.
 * Vanilla JS, no dependencies required.
 * Fase 1: central design tokens in gaman-ui.css.
 */

/* ─── 1. DARK MODE ─────────────────────────────────────────────── */
const GamanDark = (() => {
  const KEY = "gaman-theme";
  const root = document.documentElement;

  function apply(theme) {
    root.setAttribute("data-theme", theme);
    localStorage.setItem(KEY, theme);
    // Update toggle icons
    document.querySelectorAll("[data-dm-sun]").forEach(el => {
      el.style.display = theme === "dark" ? "none" : "";
    });
    document.querySelectorAll("[data-dm-moon]").forEach(el => {
      el.style.display = theme === "dark" ? "" : "none";
    });
  }

  function init() {
    const saved = localStorage.getItem(KEY);
    const pref  = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    apply(saved || pref);

    document.querySelectorAll("[data-dm-toggle]").forEach(btn => {
      btn.addEventListener("click", () => {
        const current = root.getAttribute("data-theme") || "light";
        apply(current === "dark" ? "light" : "dark");
      });
    });
  }

  return { init, apply };
})();

/* ─── 2. TOAST NOTIFICATIONS ────────────────────────────────────── */
const GamanToast = (() => {
  let container = null;

  const ICONS = {
    success: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`,
    error:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`,
    warn:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>`,
    info:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`,
    close:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>`,
  };

  function ensureContainer() {
    if (!container) {
      container = document.getElementById("g-toast-container");
      if (!container) {
        container = document.createElement("div");
        container.id = "g-toast-container";
        document.body.appendChild(container);
      }
    }
  }

  function show({ type = "info", title = "", message = "", duration = 4500 }) {
    ensureContainer();
    const el = document.createElement("div");
    el.className = `g-toast g-toast--${type}`;
    el.innerHTML = `
      <div class="g-toast__icon">${ICONS[type] || ICONS.info}</div>
      <div class="g-toast__body">
        ${title ? `<div class="g-toast__title">${title}</div>` : ""}
        ${message ? `<div class="g-toast__msg">${message}</div>` : ""}
      </div>
      <button class="g-toast__close" aria-label="Cerrar">${ICONS.close}</button>
    `;
    container.appendChild(el);

    const dismiss = () => {
      el.classList.add("is-exiting");
      el.addEventListener("animationend", () => el.remove(), { once: true });
    };

    el.querySelector(".g-toast__close").addEventListener("click", dismiss);
    if (duration > 0) setTimeout(dismiss, duration);
    return el;
  }

  return {
    show,
    success: (msg, title)  => show({ type: "success", title: title || "Listo", message: msg }),
    error:   (msg, title)  => show({ type: "error",   title: title || "Error",  message: msg }),
    warn:    (msg, title)  => show({ type: "warn",     title: title || "Aviso",  message: msg }),
    info:    (msg, title)  => show({ type: "info",     title: title || "",       message: msg }),
  };
})();

// Expose globally
window.GamanToast = GamanToast;

/* ─── 3. AUTO-UPGRADE Bootstrap ALERTS → TOASTS ──────────────────── */
function upgradeBootstrapAlerts() {
  document.querySelectorAll(".alert.alert-success, .alert.alert-danger, .alert.alert-warning").forEach(el => {
    if (el.dataset.upgraded) return;
    el.dataset.upgraded = "1";

    const text = el.innerText.trim().replace(/^(Éxito:|Error:|Aviso:)\s*/i, "");
    const type = el.classList.contains("alert-success") ? "success"
               : el.classList.contains("alert-danger")  ? "error"
               : "warn";

    // Show as toast
    GamanToast.show({ type, message: text });

    // Hide inline alert
    el.style.display = "none";
  });
}

/* ─── 4. SKELETON LOADING ────────────────────────────────────────── */
const GamanSkeleton = (() => {
  function show(containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.dataset.realContent = el.innerHTML;
    el.innerHTML = `
      <div style="padding:1.25rem">
        <div class="g-skeleton g-skeleton-text g-skeleton-text--md" style="margin-bottom:.75rem"></div>
        <div class="g-skeleton g-skeleton-row" style="margin-bottom:4px"></div>
        <div class="g-skeleton g-skeleton-row" style="margin-bottom:4px"></div>
        <div class="g-skeleton g-skeleton-row"></div>
      </div>
    `;
  }

  function hide(containerId) {
    const el = document.getElementById(containerId);
    if (!el || !el.dataset.realContent) return;
    el.innerHTML = el.dataset.realContent;
    delete el.dataset.realContent;
  }

  return { show, hide };
})();

/* ─── 5. DRAG-AND-DROP UPLOAD ZONES ──────────────────────────────── */
function initDropzones() {
  document.querySelectorAll(".g-dropzone").forEach(zone => {
    if (zone.dataset.dzInit) return;
    zone.dataset.dzInit = "1";

    const input = zone.querySelector("input[type='file']");

    zone.addEventListener("dragover", e => {
      e.preventDefault();
      zone.classList.add("is-over");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("is-over"));
    zone.addEventListener("drop", e => {
      e.preventDefault();
      zone.classList.remove("is-over");
      if (!input) return;
      const files = e.dataTransfer.files;
      if (files.length) {
        input.files = files;
        updateDropzoneLabel(zone, files[0].name);
        // Trigger change event so any existing handlers fire
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });

    if (input) {
      input.addEventListener("change", () => {
        if (input.files.length) updateDropzoneLabel(zone, input.files[0].name);
      });
    }
  });
}

function updateDropzoneLabel(zone, name) {
  const title = zone.querySelector(".g-dropzone__title");
  const sub   = zone.querySelector(".g-dropzone__sub");
  if (title) title.textContent = name;
  if (sub)   sub.textContent   = "Clic para cambiar";
  zone.style.borderStyle = "solid";
}

/* ─── 6. TABLE: ROW CLICK NAVIGATION ─────────────────────────────── */
function initTableNav() {
  document.querySelectorAll("tr[data-href]").forEach(row => {
    row.style.cursor = "pointer";
    row.addEventListener("click", e => {
      if (e.target.closest("a, button, .g-table__actions")) return;
      window.location.href = row.dataset.href;
    });
  });
}

/* ─── 7. REALTIME DOT ────────────────────────────────────────────── */
function initRealtimeDot() {
  const dot = document.getElementById("cohLiveDot");
  if (!dot) return;
  dot.style.display = "";

  // Ping health every 30s and toggle "online/offline" indicator
  async function pingHealth() {
    try {
      const res = await fetch("/health", { cache: "no-store" });
      dot.style.background = res.ok ? "#10b981" : "#ef4444";
    } catch {
      dot.style.background = "#ef4444";
    }
  }
  pingHealth();
  setInterval(pingHealth, 30000);
}

/* ─── 8. STATUS BADGE MAPPER ─────────────────────────────────────── */
const STATUS_MAP = {
  // Pedido states
  recibido:          { cls: "g-badge--recibido",   label: "Recibido" },
  correccion:        { cls: "g-badge--correccion",  label: "Corrección" },
  prep_autorizacion: { cls: "g-badge--prep",        label: "Prep. aut." },
  autorizacion:      { cls: "g-badge--autorizado",  label: "Autorización" },
  en_compulsa:       { cls: "g-badge--compulsa",    label: "En compulsa" },
  compulsa_ok:       { cls: "g-badge--aprobado",    label: "Compulsa OK" },
  rechazado:         { cls: "g-badge--rechazado",   label: "Rechazado" },
  cerrado:           { cls: "g-badge--cerrado",     label: "Cerrado" },
  // Sale states
  draft:             { cls: "g-badge--draft",       label: "Borrador" },
  pending_validation:{ cls: "g-badge--pending",     label: "Pendiente" },
  validated:         { cls: "g-badge--aprobado",    label: "Validado" },
  registered:        { cls: "g-badge--success",     label: "Registrado" },
  failed:            { cls: "g-badge--error",       label: "Error" },
};

/**
 * Converts all .badge.bg-secondary / .badge.bg-primary elements to semantic g-badges.
 * Reads current text to pick the right style.
 */
function upgradeBadges() {
  document.querySelectorAll(".badge.bg-secondary, .badge.bg-primary, .badge.bg-warning").forEach(el => {
    if (el.dataset.upgraded) return;
    el.dataset.upgraded = "1";

    const raw  = el.textContent.trim().toLowerCase().replace(/\s+/g, "_");
    const info = STATUS_MAP[raw];

    if (info) {
      el.className = `g-badge ${info.cls}`;
    } else {
      // Generic upgrade: just apply g-badge styling
      el.classList.add("g-badge", "g-badge--neutral");
      el.classList.remove("badge", "bg-secondary", "bg-primary", "bg-warning");
    }
  });
}

/* ─── 9. ALERT DISMISS ────────────────────────────────────────────── */
function initAlertDismiss() {
  document.querySelectorAll(".g-alert .g-alert__close").forEach(btn => {
    btn.addEventListener("click", () => {
      const alert = btn.closest(".g-alert");
      if (alert) alert.remove();
    });
  });
}

/* ─── 10. SIDEBAR MOBILE TOGGLE ──────────────────────────────────── */
function initSidebarMobile() {
  const toggles = document.querySelectorAll("[data-sidebar-toggle]");
  const sidebar = document.querySelector(".dash-sidebar");
  const backdrop = document.getElementById("dashSidebarBackdrop");
  if (!sidebar) return;

  function open()  {
    sidebar.classList.add("is-open");
    if (backdrop) { backdrop.style.display = "block"; backdrop.style.opacity = "1"; }
    document.body.style.overflow = "hidden";
  }
  function close() {
    sidebar.classList.remove("is-open");
    if (backdrop) { backdrop.style.opacity = "0"; setTimeout(() => { backdrop.style.display = "none"; }, 250); }
    document.body.style.overflow = "";
  }

  toggles.forEach(btn => btn.addEventListener("click", () =>
    sidebar.classList.contains("is-open") ? close() : open()
  ));
  if (backdrop) backdrop.addEventListener("click", close);
}

/* ─── 11. INIT ────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  GamanDark.init();
  initDropzones();
  initTableNav();
  initRealtimeDot();
  upgradeBadges();
  initAlertDismiss();
  initSidebarMobile();

  // Run Lucide icons if available
  if (typeof lucide !== "undefined") lucide.createIcons();

  // Convert Bootstrap alerts to toasts (opt-in via data attribute)
  if (document.body.dataset.toastAlerts === "true") {
    upgradeBootstrapAlerts();
  }
});

/* ─── Copy to clipboard helper (for mensaje de talón etc.) ───────────── */
function copyToClipboard(text, buttonEl) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => {
      if (buttonEl) {
        const orig = buttonEl.innerHTML;
        buttonEl.innerHTML = '✓ Copiado';
        setTimeout(() => { buttonEl.innerHTML = orig; }, 1500);
      }
    }).catch(() => fallbackCopy(text, buttonEl));
  } else {
    fallbackCopy(text, buttonEl);
  }
}

function fallbackCopy(text, buttonEl) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'fixed';
  document.body.appendChild(textarea);
  textarea.select();
  try {
    document.execCommand('copy');
    if (buttonEl) {
      const orig = buttonEl.innerHTML;
      buttonEl.innerHTML = '✓ Copiado';
      setTimeout(() => { buttonEl.innerHTML = orig; }, 1500);
    }
  } catch (e) {
    alert('No se pudo copiar automáticamente. Selecciona y copia manualmente:\n\n' + text);
  }
  document.body.removeChild(textarea);
}
