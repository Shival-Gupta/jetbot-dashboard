# helpers.py
import os
import glob
import time
import psutil
import config # Import config for ALLOWED_EXTENSIONS etc.

def allowed_file(filename):
    """Checks if the uploaded file has an allowed extension."""
    return '.' in filename and \
           os.path.splitext(filename)[1].lower() in config.ALLOWED_EXTENSIONS

def find_serial_ports():
    """Detects potential Arduino serial ports."""
    ports = glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')
    ports.sort() # Consistent order
    return ports

def get_system_uptime():
    """Gets system uptime using psutil and formats it."""
    try:
        boot_time_timestamp = psutil.boot_time()
        elapsed_seconds = time.time() - boot_time_timestamp
        days, rem = divmod(elapsed_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)

        parts = []
        if days > 0: parts.append(f"{int(days)}d")
        if hours > 0: parts.append(f"{int(hours)}h")
        if minutes > 0: parts.append(f"{int(minutes)}m")
        if not parts: # Only show seconds if uptime < 1 minute
             parts.append(f"{int(seconds)}s")

        return " ".join(parts) if parts else "0s"

    except Exception:
        # Log the error in a real app
        return "N/A"

# --- Analytics Helper Functions ---

def get_cpu_data():
    """Gets CPU usage, load average, and core count."""
    data = {}
    try: data['usage_percent'] = psutil.cpu_percent(interval=0.5) # Short interval for responsiveness
    except Exception: data['usage_percent'] = 'N/A'
    try: data['core_usage'] = psutil.cpu_percent(interval=None, percpu=True) # Get latest per-core without wait
    except Exception: data['core_usage'] = []
    try: data['load_avg'] = psutil.getloadavg() # Tuple (1min, 5min, 15min) - Linux/macOS
    except Exception: data['load_avg'] = ('N/A', 'N/A', 'N/A')
    try: data['core_count'] = psutil.cpu_count(logical=True)
    except Exception: data['core_count'] = 'N/A'
    return data

def get_memory_data():
    """Gets virtual memory and swap usage."""
    data = {}
    try:
        mem = psutil.virtual_memory()
        data['virtual'] = {
            'total_gb': round(mem.total / (1024**3), 2),
            'available_gb': round(mem.available / (1024**3), 2),
            'used_gb': round(mem.used / (1024**3), 2),
            'percent': mem.percent
        }
    except Exception: data['virtual'] = {'percent': 'N/A'}
    try:
        swap = psutil.swap_memory()
        data['swap'] = {
            'total_gb': round(swap.total / (1024**3), 2),
            'used_gb': round(swap.used / (1024**3), 2),
            'percent': swap.percent
        }
    except Exception: data['swap'] = {'percent': 'N/A'}
    return data

def get_disk_data():
    """Gets disk usage for relevant partitions and overall I/O."""
    data = {'partitions': [], 'io': {}}
    try:
        partitions = psutil.disk_partitions()
        for p in partitions:
            # Filter for physical devices and relevant types
            if p.device.startswith('/dev/loop') or p.fstype not in config.DISK_FILTER_TYPES:
                 continue
            try:
                usage = psutil.disk_usage(p.mountpoint)
                data['partitions'].append({
                    'device': p.device,
                    'mountpoint': p.mountpoint,
                    'fstype': p.fstype,
                    'total_gb': round(usage.total / (1024**3), 2),
                    'used_gb': round(usage.used / (1024**3), 2),
                    'percent': usage.percent
                })
            except Exception:
                # Ignore mountpoints we can't access
                continue
    except Exception: data['partitions'] = [] # Failed to get partitions list
    try:
        io = psutil.disk_io_counters()
        data['io'] = {
            'read_mb': round(io.read_bytes / (1024**2), 2),
            'write_mb': round(io.write_bytes / (1024**2), 2),
            'read_count': io.read_count,
            'write_count': io.write_count
        }
    except Exception: data['io'] = {}
    return data

def get_network_data():
    """Gets network I/O counters."""
    data = {}
    try:
        net_io = psutil.net_io_counters()
        data = {
            'sent_mb': round(net_io.bytes_sent / (1024**2), 2),
            'recv_mb': round(net_io.bytes_recv / (1024**2), 2),
            'packets_sent': net_io.packets_sent,
            'packets_recv': net_io.packets_recv,
            'errin': net_io.errin,
            'errout': net_io.errout,
            'dropin': net_io.dropin,
            'dropout': net_io.dropout
        }
    except Exception: data = {}
    return data

def get_process_data():
    """Gets top N processes by CPU and Memory."""
    processes = []
    try:
        # Iterate over processes and get required info efficiently
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent', 'create_time']):
            try:
                 # Get CPU percent over a short period if possible (can be expensive)
                 # p.cpu_percent(interval=0.1) # Uncomment if needed, but impacts performance
                 procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        # Sort by CPU and Memory and take top N
        top_cpu = sorted(procs, key=lambda p: p['cpu_percent'], reverse=True)[:config.TOP_PROCESS_COUNT]
        top_mem = sorted(procs, key=lambda p: p['memory_percent'], reverse=True)[:config.TOP_PROCESS_COUNT]

        return {'top_cpu': top_cpu, 'top_mem': top_mem}

    except Exception:
        return {'top_cpu': [], 'top_mem': []}

def get_sensor_data():
    """Gets temperature and fan speeds (if available)."""
    data = {'temperatures': {}, 'fans': {}}
    # Temperatures
    try:
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if temps:
                # Simplify structure: take first temp reading per label if multiple exist
                for name, entries in temps.items():
                    if entries:
                        data['temperatures'][name] = entries[0].current # take first sensor reading
    except Exception: data['temperatures'] = {'error': 'N/A'} # Handle errors/unavailability

    # Fans (Less common, often needs specific drivers)
    try:
        if hasattr(psutil, "sensors_fans"):
            fans = psutil.sensors_fans()
            if fans:
                 for name, entries in fans.items():
                    if entries:
                        data['fans'][name] = entries[0].current
    except Exception: data['fans'] = {'error': 'N/A'}

    return data