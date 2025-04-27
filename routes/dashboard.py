# routes/dashboard.py
from flask import Blueprint, render_template_string, jsonify
import socket
import helpers
import subprocess

# region Blueprint Setup
# Create Flask Blueprint for dashboard routes
dashboard_bp = Blueprint('dashboard', __name__)
# endregion

# region System API Endpoints
@dashboard_bp.route('/api/system/reboot', methods=['POST'])
def system_reboot():
    """Initiates a system reboot via systemctl."""
    try:
        subprocess.run(['sudo', 'systemctl', 'reboot'], check=True)
        return jsonify({'status': 'success', 'message': 'System is rebooting...'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@dashboard_bp.route('/api/system/poweroff', methods=['POST'])
def system_poweroff():
    """Powers off the system via systemctl."""
    try:
        subprocess.run(['sudo', 'systemctl', 'poweroff'], check=True)
        return jsonify({'status': 'success', 'message': 'System is shutting down...'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
# endregion

# region Service API Endpoints
@dashboard_bp.route('/api/service/start', methods=['POST'])
def start_service():
    """Starts the jetbot-dashboard service."""
    try:
        subprocess.run(['sudo', 'systemctl', 'start', 'jetbot-dashboard.service'], check=True)
        return jsonify({'status': 'success', 'message': 'Service started.'})
    except subprocess.CalledProcessError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@dashboard_bp.route('/api/service/stop', methods=['POST'])
def stop_service():
    """Stops the jetbot-dashboard service."""
    try:
        subprocess.run(['sudo', 'systemctl', 'stop', 'jetbot-dashboard.service'], check=True)
        return jsonify({'status': 'success', 'message': 'Service stopped.'})
    except subprocess.CalledProcessError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@dashboard_bp.route('/api/service/restart', methods=['POST'])
def restart_service():
    """Restarts the jetbot-dashboard service."""
    try:
        subprocess.run(['sudo', 'systemctl', 'restart', 'jetbot-dashboard.service'], check=True)
        return jsonify({'status': 'success', 'message': 'Service restarted.'})
    except subprocess.CalledProcessError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@dashboard_bp.route('/api/service/status', methods=['GET'])
def get_service_status():
    """Checks the status of the jetbot-dashboard service."""
    try:
        result = subprocess.run(['sudo', 'systemctl', 'is-active', 'jetbot-dashboard.service'], 
                              capture_output=True, text=True)
        status = result.stdout.strip()
        return jsonify({'status': 'success', 'service_status': status})
    except subprocess.CalledProcessError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
# endregion

# region Main Dashboard Route
@dashboard_bp.route('/')
def index():
    """Renders the main dashboard page with system analytics."""
    # Get system hostname and uptime
    hostname = socket.gethostname()
    uptime = helpers.get_system_uptime()

    # Collect analytics data from helpers module
    analytics = {
        'system': helpers.get_system_info(),
        'cpu': helpers.get_cpu_data(),
        'memory': helpers.get_memory_data(),
        'disk': helpers.get_disk_data(),
        'network': helpers.get_network_data(),
        'processes': helpers.get_process_data(),
        'sensors': helpers.get_sensor_data()
    }

    # HTML template with Tailwind CSS and JavaScript
    template = """
    <!DOCTYPE html>
    <html lang="en" class="dark">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="refresh" content="7">
        <title>{{ hostname }} - Jetbot Dashboard</title>
        <script src="https://cdn.tailwindcss.com/3.4.3"></script>
        <!-- region CSS Styles -->
        <style>
            /* Background for progress bars */
            .progress-bar-bg {
                background-color: #e5e7eb;
                border-radius: 0.375rem;
                overflow: hidden;
            }
            /* Progress bar fill */
            .progress-bar {
                background-color: #3b82f6;
                height: 1rem;
                border-radius: 0.375rem;
                text-align: center;
                color: white;
                font-size: 0.75rem;
                line-height: 1rem;
                transition: width 0.3s ease-in-out;
            }
            /* Warning state for progress bars */
            .progress-bar-warn {
                background-color: #f59e0b;
            }
            /* Error state for progress bars */
            .progress-bar-error {
                background-color: #ef4444;
            }
            /* Dark mode adjustment for progress bar background */
            .dark .progress-bar-bg {
                background-color: #4b5563;
            }
        </style>
        <!-- endregion -->
    </head>
    <body class="bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100 p-6 min-h-screen">
        <div class="container mx-auto max-w-6xl bg-white dark:bg-gray-800 p-6 rounded-lg shadow-xl">
            <!-- region Header -->
            <div class="flex flex-col sm:flex-row justify-between items-center mb-6">
                <div class="flex flex-col space-y-2">
                    <h1 class="text-3xl font-bold text-gray-800 dark:text-gray-200">Jetbot Dashboard</h1>
                    <div class="flex items-center space-x-2">
                        <div id="status-dot" class="w-3 h-3 rounded-full"></div>
                        <span id="status-text" class="text-sm text-gray-600 dark:text-gray-400"></span>
                        <button onclick="controlService('restart')" 
                                class="py-1 px-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400 
                                       dark:bg-gray-600 dark:text-gray-300 dark:hover:bg-gray-500 transition text-sm">
                            Restart Service
                        </button>
                        <!-- Commented-out buttons -->
                        <!--
                        <button onclick="updateServiceStatus()" 
                                class="py-1 px-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400 
                                       dark:bg-gray-600 dark:text-gray-300 dark:hover:bg-gray-500 transition text-sm">
                            Refresh
                        </button>
                        <button onclick="controlService('restart')" 
                                class="py-2 px-4 bg-purple-500 text-white rounded hover:bg-purple-600 transition text-sm font-medium">
                            Restart Service
                        </button>
                        -->
                    </div>
                </div>
                <div class="flex items-center space-x-4 mt-4 sm:mt-0">
                    <span class="text-gray-600 dark:text-gray-400 text-sm">
                        Hostname: <span class="font-semibold">{{ hostname }}</span> |
                        Uptime: <span class="font-semibold">{{ uptime }}</span>
                    </span>
                    <!-- Commented-out theme toggle button -->
                    <!--
                    <button id="theme-toggle" 
                            class="py-1 px-3 bg-gray-200 text-gray-800 rounded hover:bg-gray-300 
                                   dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600 transition">
                        <span id="theme-icon">🌙</span> Theme
                    </button>
                    -->

                    <!-- region System Controls -->
                    <div class="flex flex-wrap justify-center gap-3">
                        <button onclick="confirmAction('reboot', '/api/system/reboot', 'System is rebooting...')" 
                                class="py-2 px-4 bg-purple-500 text-white rounded hover:bg-purple-600 transition text-sm font-medium">
                            Reboot
                        </button>
                        <button onclick="confirmAction('power off', '/api/system/poweroff', 'System is shutting down...')" 
                                class="py-2 px-4 bg-red-500 text-white rounded hover:bg-red-600 transition text-sm font-medium">
                            Power Off
                        </button>
                    </div>
                    <!-- endregion -->

                </div>
            </div>
            <!-- endregion -->

            <!-- region Tools -->
            <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow border border-gray-200 dark:border-gray-700 mb-6">
                <h2 class="text-xl font-semibold mb-4 text-gray-700 dark:text-gray-300">Tools</h2>
                <div class="flex flex-wrap justify-center gap-3">
                    <a href="/arduino-upload" 
                       class="py-2 px-4 bg-blue-500 text-white rounded hover:bg-blue-600 transition text-sm font-medium">
                        Arduino Upload
                    </a>
                    <a href="/arduino-serial" 
                       class="py-2 px-4 bg-green-500 text-white rounded hover:bg-green-600 transition text-sm font-medium">
                        Serial Monitor
                    </a>
                </div>
            </div>
            <!-- endregion -->

            <!-- region System Information -->
            <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow border border-gray-200 dark:border-gray-700 mb-6">
                <h2 class="text-xl font-semibold mb-3 text-gray-700 dark:text-gray-300">System Information</h2>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm text-gray-600 dark:text-gray-400">
                    <p><strong>OS:</strong> {{ analytics.system.os }}</p>
                    <p><strong>Host:</strong> {{ analytics.system.host }}</p>
                    <p><strong>Kernel:</strong> {{ analytics.system.kernel }}</p>
                    <p><strong>Packages:</strong> {{ analytics.system.packages }}</p>
                    <p><strong>Shell:</strong> {{ analytics.system.shell }}</p>
                    <p><strong>Terminal:</strong> {{ analytics.system.terminal }}</p>
                </div>
            </div>
            <!-- endregion -->

            <!-- region System Stats -->
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                <!-- CPU -->
                <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow border border-gray-200 dark:border-gray-700">
                    <h2 class="text-xl font-semibold mb-3 text-gray-700 dark:text-gray-300">CPU</h2>
                    <p class="text-sm text-gray-500 dark:text-gray-400">{{ analytics.cpu.model }} @ {{ analytics.cpu.frequency }}</p>
                    <p class="text-sm text-gray-600 dark:text-gray-400 mb-1">Overall Usage:</p>
                    <div class="progress-bar-bg mb-3">
                        <div class="progress-bar {% if analytics.cpu.usage_percent > 90 %}progress-bar-error{% elif analytics.cpu.usage_percent > 75 %}progress-bar-warn{% endif %}"
                             style="width: {{ analytics.cpu.usage_percent }}%;">
                            {{ '%.1f' % analytics.cpu.usage_percent }}%
                        </div>
                    </div>
                    {% if analytics.cpu.core_usage %}
                    <p class="text-sm text-gray-600 dark:text-gray-400 mb-1">Usage per Core ({{ analytics.cpu.core_count }} cores):</p>
                    <div class="grid grid-cols-2 gap-1 text-xs mb-3">
                        {% for core_usage in analytics.cpu.core_usage %}
                        <div class="progress-bar-bg">
                            <div class="progress-bar {% if core_usage > 90 %}progress-bar-error{% elif core_usage > 75 %}progress-bar-warn{% endif %}"
                                 style="width: {{ core_usage }}%;">
                                {{ '%.1f' % core_usage }}%
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                    {% endif %}
                    <p class="text-sm text-gray-500 dark:text-gray-400">
                        Load Avg (1/5/15m): {{ '%.2f' % analytics.cpu.load_avg[0] }} / {{ '%.2f' % analytics.cpu.load_avg[1] }} / {{ '%.2f' % analytics.cpu.load_avg[2] }}
                    </p>
                </div>

                <!-- Memory -->
                <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow border border-gray-200 dark:border-gray-700">
                    <h2 class="text-xl font-semibold mb-3 text-gray-700 dark:text-gray-300">Memory</h2>
                    <p class="text-sm text-gray-600 dark:text-gray-400 mb-1">
                        RAM Usage: {{ analytics.memory.virtual.used_gb }} GB / {{ analytics.memory.virtual.total_gb }} GB ({{ '%.1f' % analytics.memory.virtual.percent }}%)
                    </p>
                    <div class="progress-bar-bg mb-3">
                        <div class="progress-bar {% if analytics.memory.virtual.percent > 90 %}progress-bar-error{% elif analytics.memory.virtual.percent > 75 %}progress-bar-warn{% endif %}"
                             style="width: {{ analytics.memory.virtual.percent }}%;">
                        </div>
                    </div>
                    <p class="text-sm text-gray-600 dark:text-gray-400 mb-1">
                        Swap Usage: {{ analytics.memory.swap.used_gb }} GB / {{ analytics.memory.swap.total_gb }} GB ({{ '%.1f' % analytics.memory.swap.percent }}%)
                    </p>
                    <div class="progress-bar-bg mb-3">
                        <div class="progress-bar {% if analytics.memory.swap.percent > 70 %}progress-bar-error{% elif analytics.memory.swap.percent > 40 %}progress-bar-warn{% endif %}"
                             style="width: {{ analytics.memory.swap.percent }}%;">
                        </div>
                    </div>
                </div>

                <!-- Disk -->
                <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow border border-gray-200 dark:border-gray-700">
                    <h2 class="text-xl font-semibold mb-3 text-gray-700 dark:text-gray-300">Disk Usage & I/O</h2>
                    {% if analytics.disk.partitions %}
                    {% for part in analytics.disk.partitions %}
                    <div class="mb-2">
                        <p class="text-sm text-gray-600 dark:text-gray-400 mb-1 truncate" 
                           title="{{ part.device }} mounted at {{ part.mountpoint }} ({{ part.fstype }})">
                            {{ part.mountpoint }} ({{ part.total_gb }} GB):
                        </p>
                        <div class="progress-bar-bg">
                            <div class="progress-bar {% if part.percent > 95 %}progress-bar-error{% elif part.percent > 85 %}progress-bar-warn{% endif %}"
                                 style="width: {{ part.percent }}%;">
                                {{ part.used_gb }} GB Used ({{ '%.1f' % part.percent }}%)
                            </div>
                        </div>
                    </div>
                    {% endfor %}
                    {% else %}
                    <p class="text-sm text-gray-500 dark:text-gray-400 italic">No suitable disk partitions found or error reading disks.</p>
                    {% endif %}
                    <p class="text-sm text-gray-500 dark:text-gray-400 mt-3">
                        Total I/O: Read {{ analytics.disk.io.read_mb }} MB / Write {{ analytics.disk.io.write_mb }} MB
                    </p>
                </div>

                <!-- Network -->
                <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow border border-gray-200 dark:border-gray-700">
                    <h2 class="text-xl font-semibold mb-3 text-gray-700 dark:text-gray-300">Network</h2>
                    <div class="text-sm text-gray-600 dark:text-gray-400 space-y-1">
                        <p><strong>Interfaces:</strong></p>
                        {% for iface in analytics.network.interfaces %}
                        <p>{{ iface.interface }}: {{ iface.ip }}</p>
                        {% else %}
                        <p>No active interfaces found.</p>
                        {% endfor %}
                        <p class="mt-2"><strong>I/O:</strong></p>
                        <p>Data Sent: <span class="font-medium">{{ analytics.network.io.sent_mb }} MB</span> ({{ analytics.network.io.packets_sent }} packets)</p>
                        <p>Data Received: <span class="font-medium">{{ analytics.network.io.recv_mb }} MB</span> ({{ analytics.network.io.packets_recv }} packets)</p>
                        <p>Errors In/Out: <span class="font-medium">{{ analytics.network.io.errin }} / {{ analytics.network.io.errout }}</span></p>
                        <p>Drops In/Out: <span class="font-medium">{{ analytics.network.io.dropin }} / {{ analytics.network.io.dropout }}</span></p>
                    </div>
                </div>

                <!-- Top Processes -->
                <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow border border-gray-200 dark:border-gray-700">
                    <h2 class="text-xl font-semibold mb-3 text-gray-700 dark:text-gray-300">Top Processes</h2>
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <h3 class="text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">By CPU %</h3>
                            <ul class="text-xs text-gray-500 dark:text-gray-400 space-y-1">
                            {% for proc in analytics.processes.top_cpu %}
                            <li>{{ proc.name }} ({{ '%.1f' % proc.cpu_percent }}%)</li>
                            {% else %}
                            <li>N/A</li>
                            {% endfor %}
                            </ul>
                        </div>
                        <div>
                            <h3 class="text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">By Memory %</h3>
                            <ul class="text-xs text-gray-500 dark:text-gray-400 space-y-1">
                            {% for proc in analytics.processes.top_mem %}
                            <li>{{ proc.name }} ({{ '%.1f' % proc.memory_percent }}%)</li>
                            {% else %}
                            <li>N/A</li>
                            {% endfor %}
                            </ul>
                        </div>
                    </div>
                </div>

                <!-- Sensors -->
                <div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow border border-gray-200 dark:border-gray-700">
                    <h2 class="text-xl font-semibold mb-3 text-gray-700 dark:text-gray-300">Sensors</h2>
                    <div class="text-sm text-gray-600 dark:text-gray-400 space-y-1">
                        {% if analytics.sensors.temperatures and 'error' not in analytics.sensors.temperatures %}
                        <p class="font-medium">Temperatures:</p>
                        {% for name, temp in analytics.sensors.temperatures.items() %}
                        <p>{{ name }}: <span class="font-semibold">{{ temp }} °C</span></p>
                        {% endfor %}
                        {% else %}
                        <p>Temperatures: N/A</p>
                        {% endif %}
                        {% if analytics.sensors.fans and 'error' not in analytics.sensors.fans %}
                        <p class="font-medium mt-2">Fans:</p>
                        {% for name, speed in analytics.sensors.fans.items() %}
                        <p>{{ name }}: <span class="font-semibold">{{ speed }} RPM</span></p>
                        {% endfor %}
                        {% else %}
                        <p class="mt-2">Fans: N/A</p>
                        {% endif %}
                    </div>
                </div>
            </div>
            <!-- endregion -->

            <!-- region JavaScript -->
            <script>
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

                // region Theme Toggle (Commented Out)
                /*
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
                        themeButton.classList.add('dark:bg-gray-700', 'dark:text-gray-200');
                        themeButton.classList.remove('bg-gray-200', 'text-gray-800');
                    } else {
                        document.documentElement.classList.remove('dark');
                        themeIcon.textContent = '☀️';
                        themeButton.classList.add('bg-gray-200', 'text-gray-800');
                        themeButton.classList.remove('dark:bg-gray-700', 'dark:text-gray-200');
                    }
                    console.log('Initial theme:', theme);

                    // Theme toggle event listener
                    themeButton.addEventListener('click', () => {
                        const currentTheme = localStorage.getItem('theme') || 'dark';
                        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
                        localStorage.setItem('theme', newTheme);
                        if (newTheme === 'dark') {
                            document.documentElement.classList.add('dark');
                            themeIcon.textContent = '🌙';
                            themeButton.classList.add('dark:bg-gray-700', 'dark:text-gray-200');
                            themeButton.classList.remove('bg-gray-200', 'text-gray-800');
                        } else {
                            document.documentElement.classList.remove('dark');
                            themeIcon.textContent = '☀️';
                            themeButton.classList.add('bg-gray-200', 'text-gray-800');
                            themeButton.classList.remove('dark:bg-gray-700', 'dark:text-gray-200');
                        }
                        console.log('Toggled to theme:', newTheme);
                    });
                });
                */
                // endregion

                // region Initialization
                /** Initializes the dashboard on page load */
                document.addEventListener('DOMContentLoaded', () => {
                    updateServiceStatus();
                });
                // endregion
            </script>
            <!-- region Auto-Refresh (Commented Out) -->
            <!--
            <script>
                setTimeout(function() {
                    location.reload();
                }, 7000);
            </script>
            -->
            <!-- endregion -->
        </div>
    </body>
    </html>
    """
    return render_template_string(template, hostname=hostname, uptime=uptime, analytics=analytics)
# endregion