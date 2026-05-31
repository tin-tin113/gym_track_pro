/* GymTrack Pro - Unified Premium JavaScript Engine */

let confirmModalInstance = null;

document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Theme Switcher Controller
    const themeToggleBtn = document.getElementById('theme-toggle-btn');
    const themeToggleIcon = document.getElementById('theme-toggle-icon');

    if (themeToggleBtn && themeToggleIcon) {
        const updateToggleUI = (theme) => {
            if (theme === 'light') {
                themeToggleIcon.className = 'fas fa-moon';
                themeToggleBtn.title = 'Switch to Dark Mode';
            } else {
                themeToggleIcon.className = 'fas fa-sun';
                themeToggleBtn.title = 'Switch to Light Mode';
            }
        };

        // Initialize UI icon based on active theme
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
        updateToggleUI(currentTheme);

        themeToggleBtn.addEventListener('click', function() {
            const activeTheme = document.documentElement.getAttribute('data-theme') || 'dark';
            const nextTheme = activeTheme === 'dark' ? 'light' : 'dark';

            document.documentElement.setAttribute('data-theme', nextTheme);
            localStorage.setItem('gym-theme', nextTheme);
            updateToggleUI(nextTheme);

            showToast(`Theme switched to ${nextTheme === 'light' ? 'Athletic Light' : 'Midnight Slate'}`, 'info');
        });
    }

    // Parse hidden flash messages into premium floating toasts
    const hiddenFlashContainer = document.getElementById('flash-messages');
    if (hiddenFlashContainer) {
        const flashes = hiddenFlashContainer.querySelectorAll('.flash-message');
        flashes.forEach(flash => {
            const category = flash.getAttribute('data-category') || 'info';
            const message = flash.textContent || '';
            showToast(message, category);
        });
        hiddenFlashContainer.remove(); // Clean up from DOM
    }

    // Auto-dismiss temporary alerts after 5 seconds (explicitly marked with .auto-dismiss)
    const alerts = document.querySelectorAll('.alert.auto-dismiss');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
});

/**
 * Renders a premium, non-blocking glassmorphic toast notification
 * @param {string} message 
 * @param {string} category (success, danger/error, warning, info)
 */
function showToast(message, category = 'info') {
    const container = document.getElementById('global-toast-container');
    if (!container) return;

    // Standardize category name
    if (category === 'error') category = 'danger';

    // Map categories to standard icons
    let iconClass = 'fa-info-circle';
    if (category === 'success') iconClass = 'fa-circle-check';
    else if (category === 'danger') iconClass = 'fa-circle-exclamation';
    else if (category === 'warning') iconClass = 'fa-triangle-exclamation';

    const toast = document.createElement('div');
    toast.className = `premium-toast premium-toast-${category}`;
    toast.innerHTML = `
        <span class="premium-toast-icon"><i class="fas ${iconClass}"></i></span>
        <span class="premium-toast-message" style="flex: 1;">${message}</span>
        <button type="button" class="premium-toast-close" aria-label="Close">
            <i class="fas fa-times"></i>
        </button>
    `;

    container.appendChild(toast);

    // Trigger layout reflow for animation entry
    toast.offsetHeight;
    toast.classList.add('show');

    const closeBtn = toast.querySelector('.premium-toast-close');
    const dismiss = () => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 400);
    };

    closeBtn.addEventListener('click', dismiss);

    // Auto-dismiss after 4 seconds
    setTimeout(dismiss, 4000);
}

/**
 * Triggers a premium, theme-integrated Bootstrap confirmation modal
 * @param {string} title 
 * @param {string} message 
 * @param {function} onConfirm callback
 * @param {string} category (info, danger, success, warning)
 */
function showConfirmModal(title, message, onConfirm, category = 'info') {
    const modalEl = document.getElementById('gymConfirmModal');
    if (!modalEl) {
        // Fallback to native if DOM elements aren't initialized yet
        if (confirm(message)) onConfirm();
        return;
    }

    document.getElementById('gymConfirmTitle').textContent = title;
    document.getElementById('gymConfirmMessage').innerHTML = message;

    const submitBtn = document.getElementById('gymConfirmSubmit');
    
    // Reset and apply theme classes to action button
    submitBtn.className = 'btn';
    if (category === 'danger') submitBtn.classList.add('btn-danger');
    else if (category === 'success') submitBtn.classList.add('btn-success');
    else if (category === 'warning') submitBtn.classList.add('btn-warning');
    else submitBtn.classList.add('btn-primary');

    // Clone button to strip all previous click listeners cleanly
    const newSubmitBtn = submitBtn.cloneNode(true);
    submitBtn.parentNode.replaceChild(newSubmitBtn, submitBtn);

    if (!confirmModalInstance) {
        confirmModalInstance = new bootstrap.Modal(modalEl);
    }

    newSubmitBtn.addEventListener('click', function() {
        confirmModalInstance.hide();
        if (typeof onConfirm === 'function') {
            onConfirm();
        }
    });

    confirmModalInstance.show();
}

/**
 * Global Capture-Phase Interceptor to transparently replace inline native confirm() popups
 */
(function() {
    // 1. Intercept Link Clicks and Button Actions
    document.addEventListener('click', function(event) {
        let target = event.target;
        while (target && target !== document) {
            if (target.hasAttribute('onclick')) {
                const onclickAttr = target.getAttribute('onclick');
                if (onclickAttr && onclickAttr.includes('confirm(')) {
                    // Prevent original browser prompt and cancel inline bubble execution
                    event.preventDefault();
                    event.stopImmediatePropagation();

                    const match = onclickAttr.match(/confirm\(['"](.*?)['"]\)/);
                    const message = match ? match[1] : 'Are you sure you want to proceed?';
                    const category = (message.toLowerCase().includes('delete') || message.toLowerCase().includes('deactivate') || message.toLowerCase().includes('reject') || message.toLowerCase().includes('remove')) ? 'danger' : 'warning';

                    showConfirmModal('Confirm Action', message, function() {
                        // Action confirmed: bypass prompt and run action programmatically
                        target.removeAttribute('onclick');
                        target.click();
                        target.setAttribute('onclick', onclickAttr);
                    }, category);
                    return;
                }
            }
            target = target.parentElement;
        }
    }, true);

    // 2. Intercept Form Submissions
    document.addEventListener('submit', function(event) {
        const form = event.target;
        if (form.hasAttribute('onsubmit')) {
            const onsubmitAttr = form.getAttribute('onsubmit');
            if (onsubmitAttr && onsubmitAttr.includes('confirm(')) {
                // Prevent original form submission and bubble
                event.preventDefault();
                event.stopImmediatePropagation();

                const match = onsubmitAttr.match(/confirm\(['"](.*?)['"]\)/);
                const message = match ? match[1] : 'Are you sure you want to proceed?';
                const category = (message.toLowerCase().includes('delete') || message.toLowerCase().includes('deactivate') || message.toLowerCase().includes('reject') || message.toLowerCase().includes('remove')) ? 'danger' : 'warning';

                showConfirmModal('Confirm Action', message, function() {
                    // Submission confirmed: bypass handler and submit form programmatically
                    form.removeAttribute('onsubmit');
                    form.submit();
                    form.setAttribute('onsubmit', onsubmitAttr);
                }, category);
            }
        }
    }, true);
})();

function copyToClipboard(text, button) {
    navigator.clipboard.writeText(text).then(() => {
        const originalText = button.innerHTML;
        button.innerHTML = '<i class="fas fa-check"></i> Copied!';
        button.classList.add('btn-success');
        button.classList.remove('btn-outline-primary', 'btn-outline-secondary', 'btn-outline-danger');
        setTimeout(() => {
            button.innerHTML = originalText;
            button.classList.remove('btn-success');
            button.classList.add('btn-outline-primary');
        }, 2000);
    }).catch(() => {
        showToast('Failed to copy to clipboard', 'danger');
    });
}
