# routes/dashboard.py
from flask import Blueprint, render_template_string, jsonify
import socket # Standard library
import helpers # Local helper module
import subprocess # Standard library

# Create Blueprint
dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/api/system/reboot', methods=['POST'])
def system_reboot():
    """API endpoint to reboot the system."""
    try:
        subprocess.run(['sudo','systemctl','reboot'], check=True)
        return jsonify({'status': 'success', 'message': 'System is rebooting...'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@dashboard_bp.route('/api/system/poweroff', methods=['POST'])
def system_poweroff():
    """API endpoint to power off the system."""
    try:
        subprocess.run(['sudo','systemctl','poweroff'], check=True)
        return jsonify({'status': 'success', 'message': 'System is shutting down...'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@dashboard_bp.route('/')
def index():
    """Serves the main dashboard page with system analytics."""
    hostname = socket.gethostname()
    uptime = helpers.get_system_uptime()

    # Fetch analytics data
    analytics = {
        'cpu': helpers.get_cpu_data(),
        'memory': helpers.get_memory_data(),
        'disk': helpers.get_disk_data(),
        'network': helpers.get_network_data(),
        'processes': helpers.get_process_data(),
        'sensors': helpers.get_sensor_data()
    }

    # --- Dashboard HTML Template String ---
    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{{ hostname }} - Dashboard</title>
        <script src="https://cdn.tailwindcss.com/3.4.3"></script>
         <style>
            /* Simple progress bar styling */
            .progress-bar-bg { background-color: #e5e7eb; border-radius: 0.375rem; overflow: hidden; }
            .progress-bar { background-color: #3b82f6; height: 1rem; border-radius: 0.375rem; text-align: center; color: white; font-size: 0.75rem; line-height: 1rem; transition: width 0.3s ease-in-out; }
            .progress-bar-warn { background-color: #f59e0b; }
            .progress-bar-error { background-color: #ef4444; }
         </style>
    </head>
    <body class="bg-gray-100 p-6">
        <div class="container mx-auto max-w-6xl bg-white p-6 rounded-lg shadow-xl">
            <h1 class="text-3xl font-bold mb-4 text-center text-gray-800">System Dashboard</h1>
            <div class="text-center mb-6 text-gray-600 text-sm">
                Hostname: <span class="font-semibold">{{ hostname }}</span> |
                Uptime: <span class="font-semibold">{{ uptime }}</span>
            </div>

            <div class="flex justify-center space-x-4 mb-8">
                 <a href="/arduino-upload" class="py-2 px-4 bg-blue-500 text-white rounded hover:bg-blue-600 transition">Arduino Uploader</a>
                 <a href="/arduino-serial" class="py-2 px-4 bg-green-500 text-white rounded hover:bg-green-600 transition">Serial Monitor</a>
                 <button onclick="if(confirm('Are you sure you want to reboot the system?')) fetch('/api/system/reboot', {method: 'POST'})" 
                         class="py-2 px-4 bg-yellow-500 text-white rounded hover:bg-yellow-600 transition">Reboot</button>
                 <button onclick="if(confirm('Are you sure you want to power off the system?')) fetch('/api/system/poweroff', {method: 'POST'})"
                         class="py-2 px-4 bg-red-500 text-white rounded hover:bg-red-600 transition">Power Off</button>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

                <div class="bg-white p-4 rounded-lg shadow border border-gray-200">
                    <h2 class="text-xl font-semibold mb-3 text-gray-700">CPU</h2>
                    <p class="text-sm text-gray-600 mb-1">Overall Usage:</p>
                    <div class="progress-bar-bg mb-3">
                        <div class="progress-bar {% if analytics.cpu.usage_percent > 90 %}progress-bar-error{% elif analytics.cpu.usage_percent > 75 %}progress-bar-warn{% endif %}"
                             style="width: {{ analytics.cpu.usage_percent }}%;">
                             {{ '%.1f' % analytics.cpu.usage_percent }}%
                        </div>
                    </div>
                    {% if analytics.cpu.core_usage %}
                    <p class="text-sm text-gray-600 mb-1">Usage per Core ({{ analytics.cpu.core_count }} cores):</p>
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
                    <p class="text-sm text-gray-500">Load Avg (1/5/15m): {{ '%.2f' % analytics.cpu.load_avg[0] }} / {{ '%.2f' % analytics.cpu.load_avg[1] }} / {{ '%.2f' % analytics.cpu.load_avg[2] }}</p>
                </div>

                <div class="bg-white p-4 rounded-lg shadow border border-gray-200">
                     <h2 class="text-xl font-semibold mb-3 text-gray-700">Memory</h2>
                     <p class="text-sm text-gray-600 mb-1">RAM Usage ({{ analytics.memory.virtual.total_gb }} GB Total):</p>
                     <div class="progress-bar-bg mb-3">
                         <div class="progress-bar {% if analytics.memory.virtual.percent > 90 %}progress-bar-error{% elif analytics.memory.virtual.percent > 75 %}progress-bar-warn{% endif %}"
                              style="width: {{ analytics.memory.virtual.percent }}%;">
                              {{ analytics.memory.virtual.used_gb }} GB Used ({{ '%.1f' % analytics.memory.virtual.percent }}%)
                         </div>
                     </div>
                      <p class="text-sm text-gray-600 mb-1">Swap Usage ({{ analytics.memory.swap.total_gb }} GB Total):</p>
                     <div class="progress-bar-bg mb-3">
                         <div class="progress-bar {% if analytics.memory.swap.percent > 70 %}progress-bar-error{% elif analytics.memory.swap.percent > 40 %}progress-bar-warn{% endif %}"
                              style="width: {{ analytics.memory.swap.percent }}%;">
                              {% if analytics.memory.swap.percent > 0 %} {{ analytics.memory.swap.used_gb }} GB Used ({% endif %}{{ '%.1f' % analytics.memory.swap.percent }}%{% if analytics.memory.swap.percent > 0 %}){% endif %}
                         </div>
                     </div>
                </div>

                <div class="bg-white p-4 rounded-lg shadow border border-gray-200">
                    <h2 class="text-xl font-semibold mb-3 text-gray-700">Disk Usage & I/O</h2>
                    {% if analytics.disk.partitions %}
                        {% for part in analytics.disk.partitions %}
                        <div class="mb-2">
                             <p class="text-sm text-gray-600 mb-1 truncate" title="{{ part.device }} mounted at {{ part.mountpoint }} ({{ part.fstype }})">
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
                        <p class="text-sm text-gray-500 italic">No suitable disk partitions found or error reading disks.</p>
                     {% endif %}
                      <p class="text-sm text-gray-500 mt-3">Total I/O: Read {{ analytics.disk.io.read_mb }} MB / Write {{ analytics.disk.io.write_mb }} MB</p>
                </div>

                <div class="bg-white p-4 rounded-lg shadow border border-gray-200">
                    <h2 class="text-xl font-semibold mb-3 text-gray-700">Network I/O</h2>
                    <div class="text-sm text-gray-600 space-y-1">
                        <p>Data Sent: <span class="font-medium">{{ analytics.network.sent_mb }} MB</span> ({{ analytics.network.packets_sent }} packets)</p>
                        <p>Data Received: <span class="font-medium">{{ analytics.network.recv_mb }} MB</span> ({{ analytics.network.packets_recv }} packets)</p>
                        <p>Errors In/Out: <span class="font-medium">{{ analytics.network.errin }} / {{ analytics.network.errout }}</span></p>
                        <p>Drops In/Out: <span class="font-medium">{{ analytics.network.dropin }} / {{ analytics.network.dropout }}</span></p>
                    </div>
                </div>

                 <div class="bg-white p-4 rounded-lg shadow border border-gray-200">
                    <h2 class="text-xl font-semibold mb-3 text-gray-700">Top Processes</h2>
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                             <h3 class="text-sm font-medium text-gray-600 mb-1">By CPU %</h3>
                             <ul class="text-xs text-gray-500 space-y-1">
                             {% for proc in analytics.processes.top_cpu %}
                                <li>{{ proc.name }} ({{ '%.1f' % proc.cpu_percent }}%)</li>
                             {% else %}
                                <li>N/A</li>
                             {% endfor %}
                             </ul>
                        </div>
                         <div>
                             <h3 class="text-sm font-medium text-gray-600 mb-1">By Memory %</h3>
                             <ul class="text-xs text-gray-500 space-y-1">
                             {% for proc in analytics.processes.top_mem %}
                                <li>{{ proc.name }} ({{ '%.1f' % proc.memory_percent }}%)</li>
                             {% else %}
                                <li>N/A</li>
                             {% endfor %}
                             </ul>
                        </div>
                    </div>
                </div>

                 <div class="bg-white p-4 rounded-lg shadow border border-gray-200">
                    <h2 class="text-xl font-semibold mb-3 text-gray-700">Sensors</h2>
                     <div class="text-sm text-gray-600 space-y-1">
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

            </div> </div>
    </body>
    </html>
    """
    return render_template_string(template, hostname=hostname, uptime=uptime, analytics=analytics)