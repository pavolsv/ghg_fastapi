document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("coefficientOverviewToggle");
    const submenu = document.getElementById("coefficientOverviewSubmenu");

    if (!toggle || !submenu) {
        return;
    }

    const submenuWrapper = toggle.closest(".nav-item-with-submenu");
    if (!submenuWrapper) {
        return;
    }

    // Click toggle to expand/collapse submenu
    toggle.addEventListener('click', (e) => {
        e.preventDefault();
        const isOpen = submenuWrapper.classList.contains('is-open');
        if (isOpen) {
            submenuWrapper.classList.remove('is-open');
            toggle.setAttribute('aria-expanded', 'false');
            submenu.setAttribute('aria-hidden', 'true');
        } else {
            submenuWrapper.classList.add('is-open');
            toggle.setAttribute('aria-expanded', 'true');
            submenu.setAttribute('aria-hidden', 'false');
        }
    });

    // Highlight active submenu link based on category param
    const params = new URLSearchParams(window.location.search);
    const category = params.get('category');
    if (category) {
        const link = document.getElementById(`submenu-link-${category}`);
        if (link) {
            link.classList.add('active');
            link.classList.add('dashboard-btn'); // Ensure highlight style
            // Auto-expand submenu if on a child page
            submenuWrapper.classList.add('is-open');
            toggle.setAttribute("aria-expanded", "true");
            submenu.setAttribute("aria-hidden", "false");
        }
    }
    
        // 儀表板按鈕自動高光：根據點擊和當前URL
        function highlightActiveDashboardBtn() {
            // Remove active from all dashboard-btn
            document.querySelectorAll('.dashboard-btn').forEach(btn => btn.classList.remove('active'));
            // Try to match current path and query string
            const fullPath = window.location.pathname + window.location.search;
            document.querySelectorAll('.dashboard-btn').forEach(btn => {
                if (btn.tagName === 'A') {
                    // Match href with path and query
                    if (btn.getAttribute('href') === fullPath || btn.getAttribute('href') === window.location.pathname) {
                        btn.classList.add('active');
                        // If it's a submenu link, auto-expand submenu
                        if (btn.closest('.nav-submenu')) {
                            const parentSubmenu = btn.closest('.nav-item-with-submenu');
                            if (parentSubmenu) {
                                parentSubmenu.classList.add('is-open');
                                const toggleBtn = parentSubmenu.querySelector('.nav-submenu-toggle');
                                const submenuEl = parentSubmenu.querySelector('.nav-submenu');
                                if (toggleBtn && submenuEl) {
                                    toggleBtn.setAttribute('aria-expanded', 'true');
                                    submenuEl.setAttribute('aria-hidden', 'false');
                                }
                            }
                        }
                    }
                }
                // Special case: logout button
                if (btn.tagName === 'BUTTON' && window.location.pathname === '/logout') {
                    btn.classList.add('active');
                }
            });
        }
        highlightActiveDashboardBtn();
        // Also highlight on click
        document.querySelectorAll('.dashboard-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                document.querySelectorAll('.dashboard-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                if (this.closest('.nav-submenu')) {
                    // Always open parent submenu when clicking a submenu item
                    const parentSubmenu = this.closest('.nav-item-with-submenu');
                    if (parentSubmenu) {
                        parentSubmenu.classList.add('is-open');
                        const toggleBtn = parentSubmenu.querySelector('.nav-submenu-toggle');
                        const submenuEl = parentSubmenu.querySelector('.nav-submenu');
                        if (toggleBtn && submenuEl) {
                            toggleBtn.setAttribute('aria-expanded', 'true');
                            submenuEl.setAttribute('aria-hidden', 'false');
                        }
                    }
                } else if (!this.classList.contains('nav-submenu-toggle')) {
                    // Only collapse submenu if clicked button is NOT inside any nav-submenu
                    // and is NOT a submenu toggle itself
                    document.querySelectorAll('.nav-item-with-submenu.is-open').forEach(item => {
                        item.classList.remove('is-open');
                        const toggleBtn = item.querySelector('.nav-submenu-toggle');
                        const submenuEl = item.querySelector('.nav-submenu');
                        if (toggleBtn && submenuEl) {
                            toggleBtn.setAttribute('aria-expanded', 'false');
                            submenuEl.setAttribute('aria-hidden', 'true');
                        }
                    });
                }
            });
        });
});

// Re-run sidebar highlight after every HTMX swap
document.addEventListener("htmx:afterSettle", function() {
    // Re-highlight active dashboard button based on new URL
    const fullPath = window.location.pathname + window.location.search;
    document.querySelectorAll('.dashboard-btn').forEach(btn => btn.classList.remove('active'));
    // Highlight submenu link based on current category param (for coefficient submenu)
    const params = new URLSearchParams(window.location.search);
    const category = params.get('category');
    let submenuLinkHighlighted = false;
    if (category) {
        const link = document.getElementById(`submenu-link-${category}`);
        if (link) {
            link.classList.add('active');
            submenuLinkHighlighted = true;
        }
    }
    // If no submenu link is matched, fallback to path-based highlight for other buttons
    if (!submenuLinkHighlighted) {
        document.querySelectorAll('.dashboard-btn').forEach(btn => {
            if (btn.tagName === 'A') {
                if (btn.getAttribute('href') === fullPath || btn.getAttribute('href') === window.location.pathname) {
                    btn.classList.add('active');
                }
            }
        });
    }
});
