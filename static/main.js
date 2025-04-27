// region System Actions
/** Prompts for confirmation and sends POST request to system API endpoints */
function confirmAction(action, url, successMessage) {
    if (confirm(`Are you sure you want to ${action} the system?`)) {
        fetch(url, { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    alert(successMessage);
                } else {
                    alert('Error: ' + data.message);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error: Failed to perform action.');
            });
    }
}
// endregion

// region Service Controls
/** Prompts for confirmation and sends POST request to service API endpoints */
function controlService(action) {
    if (confirm(`Are you sure you want to ${action} the service?`)) {
        fetch(`/api/service/${action}`, { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    alert(data.message);
                    updateServiceStatus();
                } else {
                    alert('Error: ' + data.message);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error: Failed to perform service action.');
            });
    }
}

/** Fetches and updates the service status indicator */
function updateServiceStatus() {
    fetch('/api/service/status')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                const status = data.service_status;
                const dot = document.getElementById('status-dot');
                const text = document.getElementById('status-text');
                if (status === 'active') {
                    dot.className = 'w-3 h-3 rounded-full bg-green-500';
                    text.textContent = 'Active';
                } else if (status === 'inactive') {
                    dot.className = 'w-3 h-3 rounded-full bg-red-500';
                    text.textContent = 'Inactive';
                } else {
                    dot.className = 'w-3 h-3 rounded-full bg-yellow-500';
                    text.textContent = status;
                }
            } else {
                console.error('Error fetching service status:', data.message);
            }
        })
        .catch(error => {
            console.error('Error:', error);
        });
}
// endregion

// region Theme Toggle
/** Initializes and toggles theme between light and dark */
document.addEventListener('DOMContentLoaded', () => {
    // Initialize service status
    updateServiceStatus();

    // Initialize theme
    const theme = localStorage.getItem('theme') || 'dark';
    const themeButton = document.getElementById('theme-toggle');
    const themeIcon = document.getElementById('theme-icon');
    if (theme === 'dark') {
        document.documentElement.classList.add('dark');
        themeIcon.textContent = '🌙';
    } else {
        document.documentElement.classList.remove('dark');
        themeIcon.textContent = '☀️';
    }

    // Theme toggle event listener
    themeButton.addEventListener('click', () => {
        const currentTheme = localStorage.getItem('theme') || 'dark';
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        localStorage.setItem('theme', newTheme);
        if (newTheme === 'dark') {
            document.documentElement.classList.add('dark');
            themeIcon.textContent = '🌙';
        } else {
            document.documentElement.classList.remove('dark');
            themeIcon.textContent = '☀️';
        }
    });
});
// endregion