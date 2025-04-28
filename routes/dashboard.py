from flask import Blueprint, render_template_string, jsonify, request, redirect, url_for
import subprocess

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

@dashboard_bp.route('/update', methods=['POST'])
def update():
    """Perform git pull to update the repository."""
    try:
        output = subprocess.check_output(['git', 'pull'], text=True)
        print(output)  # Optional: log output
        return redirect(url_for('dashboard.index'))
    except Exception as e:
        return f"Update failed: {str(e)}", 500

def get_git_versions():
    """Fetch current and latest git commit hashes."""
    try:
        current_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
        # Fetch latest info from origin (optional if already fetched)
        subprocess.run(['git', 'fetch'], check=True)
        latest_commit = subprocess.check_output(['git', 'rev-parse', 'origin/master'], text=True).strip()
    except Exception as e:
        current_commit = latest_commit = f"Error: {str(e)}"
    return current_commit, latest_commit

# endregion

# region Main Dashboard Route
@dashboard_bp.route('/')
def index():
    """Renders the main dashboard page with system analytics."""
    # Get system hostname and uptime
    hostname = socket.gethostname()
    uptime = helpers.get_system_uptime()
    current_version, latest_version = get_git_versions()

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

    # HTML template with Tailwind CSS and external CSS/JS references
    template = """
    <!DOCTYPE html>
    <html lang="en" class="dark">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="refresh" content="7">
        <title>{{ hostname }} - Jetbot Dashboard</title>
        <script src="https://cdn.tailwindcss.com/3.4.3"></script>
        <link rel="stylesheet" href="/static/globals.css">
    </head>
    <body class="p-6 min-h-screen">
        <div class="container mx-auto max-w-6xl p-6 rounded-lg shadow-xl">
            <!-- region Header -->
            <header class="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
            <div class="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-y-4 md:gap-y-0 items-center">
                
                <!-- region Left -->
                <div class="flex flex-col space-y-2">
                <div class="flex items-center space-x-3">
                    <h1 class="text-3xl font-bold text-gray-900 dark:text-gray-100">🚀 Jetbot Dashboard</h1>
                    <span 
                    id="status-dot" 
                    class="w-3 h-3 rounded-full bg-gray-300 dark:bg-gray-600" 
                    aria-label="Service status">
                    </span>
                    <span id="status-text" class="text-sm text-gray-700 dark:text-gray-300">Loading…</span>
                </div>
                <button 
                    onclick="controlService('restart')" 
                    class="inline-flex items-center gap-1 text-sm font-medium py-1.5 px-3 bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 rounded transition"
                    aria-label="Restart Jetbot service">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v6h6M20 20v-6h-6" />
                    </svg>
                    Restart Service
                </button>
                </div>
                <!-- endregion Left -->

                <!-- region Center -->
                <div class="flex flex-col space-y-3 text-sm text-gray-700 dark:text-gray-300 text-center">
                <div>
                    <strong>Host:</strong> {{ hostname }} &nbsp;|&nbsp; <strong>Uptime:</strong> {{ uptime }}
                </div>
                <div>
                    <strong>Current:</strong> {{ current_version[:7] }} &nbsp;|&nbsp; <strong>Latest:</strong> {{ latest_version[:7] }}
                </div>

                {% if current_version != latest_version %}
                <div class="inline-block bg-yellow-50 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200 px-4 py-2 rounded-lg shadow">
                    <div class="flex items-center justify-between">
                    <span class="font-semibold">Update Available!</span>
                    <form method="POST" action="{{ url_for('dashboard.update') }}">
                        <button 
                        type="submit" 
                        class="inline-flex items-center gap-1 text-sm font-bold py-1.5 px-3 bg-yellow-500 hover:bg-yellow-600 text-white rounded transition"
                        aria-label="Update Jetbot to latest version">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v6h6M20 20v-6h-6" />
                        </svg>
                        Update Now
                        </button>
                    </form>
                    </div>
                </div>
                {% endif %}
                </div>
                <!-- endregion Center -->

                <!-- region Right -->
                <div class="flex flex-col md:flex-row md:justify-end items-center space-y-3 md:space-y-0 md:space-x-4">
                
                <!-- region Theme Toggle -->
                <button 
                    id="theme-toggle" 
                    class="p-2 bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 rounded transition" 
                    aria-label="Toggle light / dark theme">
                    <span id="theme-icon" class="text-lg">🌙</span>
                </button>
                <!-- endregion Theme Toggle -->

                <!-- region System Controls -->
                <div class="flex gap-3">
                    <button 
                    onclick="confirmAction('reboot', '/api/system/reboot', 'System is rebooting...')" 
                    class="flex-1 text-sm font-medium py-2 px-4 bg-purple-500 hover:bg-purple-600 text-white rounded transition"
                    aria-label="Reboot system">
                    Reboot
                    </button>
                    <button 
                    onclick="confirmAction('power off', '/api/system/poweroff', 'System is shutting down...')" 
                    class="flex-1 text-sm font-medium py-2 px-4 bg-red-500 hover:bg-red-600 text-white rounded transition"
                    aria-label="Power off system">
                    Power Off
                    </button>
                </div>
                <!-- endregion System Controls -->

                </div>
                <!-- endregion Right -->

            </div>
            </header>
            <!-- endregion Header -->


            <!-- region Tools -->
            <div class="p-4 rounded-lg shadow border mb-6">
                <h2 class="text-xl font-semibold mb-4">Tools</h2>
                <div class="flex flex-wrap justify-center gap-3">
                    <a href="/arduino-upload" 
                       class="py-2 px-4 bg-blue-500 text-white rounded hover:bg-blue-600 transition text-sm font-medium">
                        Arduino Upload
                    </a>
                    <a href="/arduino-serial" 
                       class="py-2 px-4 bg-green-500 text-white rounded hover:bg-green-600 transition text-sm font-medium">
                        Serial Monitor
                    </a>
                    <!-- Add Web Shell -->
                    <a href="/terminal"
                    class="py-2 px-4 bg-gray-700 text-white rounded hover:bg-gray-800 transition text-sm font-medium">
                        Web Shell
                    </a>
                </div>
            </div>
            <!-- endregion -->

            <!-- region System Information -->
            <div class="p-4 rounded-lg shadow border mb-6">
                <h2 class="text-xl font-semibold mb-3">System Information</h2>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
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
                <div class="p-4 rounded-lg shadow border">
                    <h2 class="text-xl font-semibold mb-3">CPU</h2>
                    <p class="text-sm">{{ analytics.cpu.model }} @ {{ analytics.cpu.frequency }}</p>
                    <p class="text-sm mb-1">Overall Usage:</p>
                    <div class="progress-bar-bg mb-3">
                        <div class="progress-bar {% if analytics.cpu.usage_percent > 90 %}progress-bar-error{% elif analytics.cpu.usage_percent > 75 %}progress-bar-warn{% endif %}"
                             style="width: {{ analytics.cpu.usage_percent }}%;">
                            {{ '%.1f' % analytics.cpu.usage_percent }}%
                        </div>
                    </div>
                    {% if analytics.cpu.core_usage %}
                    <p class="text-sm mb-1">Usage per Core ({{ analytics.cpu.core_count }} cores):</p>
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
                    <p class="text-sm">
                        Load Avg (1/5/15m): {{ '%.2f' % analytics.cpu.load_avg[0] }} / {{ '%.2f' % analytics.cpu.load_avg[1] }} / {{ '%.2f' % analytics.cpu.load_avg[2] }}
                    </p>
                </div>

                <!-- Memory -->
                <div class="p-4 rounded-lg shadow border">
                    <h2 class="text-xl font-semibold mb-3">Memory</h2>
                    <p class="text-sm mb-1">
                        RAM Usage: {{ analytics.memory.virtual.used_gb }} GB / {{ analytics.memory.virtual.total_gb }} GB ({{ '%.1f' % analytics.memory.virtual.percent }}%)
                    </p>
                    <div class="progress-bar-bg mb-3">
                        <div class="progress-bar {% if analytics.memory.virtual.percent > 90 %}progress-bar-error{% elif analytics.memory.virtual.percent > 75 %}progress-bar-warn{% endif %}"
                             style="width: {{ analytics.memory.virtual.percent }}%;">
                        </div>
                    </div>
                    <p class="text-sm mb-1">
                        Swap Usage: {{ analytics.memory.swap.used_gb }} GB / {{ analytics.memory.swap.total_gb }} GB ({{ '%.1f' % analytics.memory.swap.percent }}%)
                    </p>
                    <div class="progress-bar-bg mb-3">
                        <div class="progress-bar {% if analytics.memory.swap.percent > 70 %}progress-bar-error{% elif analytics.memory.swap.percent > 40 %}progress-bar-warn{% endif %}"
                             style="width: {{ analytics.memory.swap.percent }}%;">
                        </div>
                    </div>
                </div>

                <!-- Disk -->
                <div class="p-4 rounded-lg shadow border">
                    <h2 class="text-xl font-semibold mb-3">Disk Usage & I/O</h2>
                    {% if analytics.disk.partitions %}
                    {% for part in analytics.disk.partitions %}
                    <div class="mb-2">
                        <p class="text-sm mb-1 truncate" 
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
                    <p class="text-sm italic">No suitable disk partitions found or error reading disks.</p>
                    {% endif %}
                    <p class="text-sm mt-3">
                        Total I/O: Read {{ analytics.disk.io.read_mb }} MB / Write {{ analytics.disk.io.write_mb }} MB
                    </p>
                </div>

                <!-- Network -->
                <div class="p-4 rounded-lg shadow border">
                    <h2 class="text-xl font-semibold mb-3">Network</h2>
                    <div class="text-sm space-y-1">
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
                <div class="p-4 rounded-lg shadow border">
                    <h2 class="text-xl font-semibold mb-3">Top Processes</h2>
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <h3 class="text-sm font-medium mb-1">By CPU %</h3>
                            <ul class="text-xs space-y-1">
                            {% for proc in analytics.processes.top_cpu %}
                            <li>{{ proc.name }} ({{ '%.1f' % proc.cpu_percent }}%)</li>
                            {% else %}
                            <li>N/A</li>
                            {% endfor %}
                            </ul>
                        </div>
                        <div>
                            <h3 class="text-sm font-medium mb-1">By Memory %</h3>
                            <ul class="text-xs space-y-1">
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
                <div class="p-4 rounded-lg shadow border">
                    <h2 class="text-xl font-semibold mb-3">Sensors</h2>
                    <div class="text-sm space-y-1">
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
        </div>
        <script src="/static/main.js"></script>
    </body>
    </html>
    """
    return render_template_string(template,
                                hostname=hostname,
                                uptime=uptime,
                                analytics=analytics,
                                current_version=current_version,
                                latest_version=latest_version)
# endregion