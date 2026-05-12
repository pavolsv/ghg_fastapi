function initFactorSubmenu() {
    const menu = document.querySelector(".fm-overview-menu");
    const toggle = document.getElementById("overviewToggle");
    const submenu = document.getElementById("overviewSubmenu");

    if (!menu || !toggle || !submenu) return;

    toggle.addEventListener("click", () => {
        const isOpen = menu.classList.toggle("is-open");
        toggle.setAttribute("aria-expanded", String(isOpen));
        submenu.setAttribute("aria-hidden", String(!isOpen));
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initFactorSubmenu);
} else {
    initFactorSubmenu();
}
