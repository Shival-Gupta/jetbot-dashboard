# --- Imports ---
import time
import serial
import serial.tools.list_ports
from flask import Flask, render_template_string, request, jsonify
from flask_cors import CORS  # Enable cross-origin requests
import math
import threading
import ssl  # For HTTPS support

# --- Configuration ---
# Set your serial port (adjust as needed)
SERIAL_PORT = '/dev/ttyACM0'  # Example: '/dev/ttyUSB0' or 'COM3' on Windows
BAUD_RATE = 9600
SERIAL_TIMEOUT = 0.1  # Seconds
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 6002
USE_HTTPS = True  # Toggle to False for HTTP instead of HTTPS

# Movement Parameters (Tune these!)
MOVE_SPEED = 150       # Base speed (0-255)
MAX_SPEED = 255
RAMP_STEPS = 4         # Steps for ramp-up/down
RAMP_DELAY = 0.05      # Seconds between ramp steps
TIME_PER_UNIT = 0.03   # Full speed time per unit
STOP_REPEATS = 3       # Number of stop commands to send for reliability

# --- Global Variables ---
ser = None  # Serial connection
serial_lock = threading.Lock()  # Thread-safe serial access
square_thread = None  # Movement thread
stop_event = threading.Event()  # Signal to stop

# --- Flask App Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'simple_square_secret!'
CORS(app, resources={r"/*": {"origins": "*"}})  # Allow all origins
print("CORS enabled for all origins.")

# --- Serial Communication Functions ---
def find_arduino_port():
    """Auto-detect Arduino USB port."""
    ports = serial.tools.list_ports.comports()
    keywords = ['arduino', 'usb serial ch340', 'usb serial cp210x', 'ttyacm', 'ttyusb']
    arduino_ports = []
    print("Available ports:")
    for p in ports:
        print(f"- {p.device}: {p.description}")
        if any(keyword in p.description.lower() for keyword in keywords):
            arduino_ports.append(p.device)
    if arduino_ports:
        print(f"Found Arduino ports: {arduino_ports}")
        return arduino_ports[0]
    print("Warning: No Arduino port detected.")
    return None

def connect_serial():
    """Connect to the serial port."""
    global ser, SERIAL_PORT
    if ser and ser.is_open:
        return True
    port = SERIAL_PORT if SERIAL_PORT else find_arduino_port()
    if not port:
        print("Error: No serial port specified or detected.")
        return False
    try:
        print(f"Connecting to {port} at {BAUD_RATE} baud...")
        ser = serial.Serial(port, BAUD_RATE, timeout=SERIAL_TIMEOUT)
        print("Waiting for Arduino to initialize...")
        time.sleep(2)  # Allow Arduino to reset
        startup = ser.read_all().decode('utf-8', errors='ignore').strip()
        if startup:
            print("--- Arduino Startup ---")
            print(startup)
            print("---------------------")
        ser.flushInput()
        print(f"Connected to {port}.")
        return True
    except Exception as e:
        print(f"Serial connection failed: {e}")
        ser = None
        return False

def send_command(command):
    """Send command to Arduino with thread safety."""
    global ser, serial_lock
    if not ser or not ser.is_open:
        print("Serial not connected.")
        return False
    with serial_lock:
        try:
            ser.write((command + '\n').encode('utf-8'))
            return True
        except Exception as e:
            print(f"Serial send error: {e}")
            try:
                ser.close()
            except:
                pass
            ser = None
            return False

def calculate_mecanum_speeds(vx, vy, omega):
    """Compute wheel speeds for Mecanum drive."""
    fl = vx - vy - omega
    fr = vx + vy + omega
    rl = vx + vy - omega
    rr = vx - vy + omega
    max_abs = max(abs(fl), abs(fr), abs(rl), abs(rr), 1)
    scale = MAX_SPEED / max_abs if max_abs > MAX_SPEED else 1.0
    return [
        max(-MAX_SPEED, min(MAX_SPEED, int(fl * scale))),
        max(-MAX_SPEED, min(MAX_SPEED, int(fr * scale))),
        max(-MAX_SPEED, min(MAX_SPEED, int(rl * scale))),
        max(-MAX_SPEED, min(MAX_SPEED, int(rr * scale)))
    ]

def _send_motor_speeds(fl, fr, rl, rr):
    """Format and send motor speeds."""
    cmd = f"{int(fl)},{int(fr)},{int(rl)},{int(rr)}"
    print(f"Sending: {cmd}")  # Debug output
    return send_command(cmd)

def _safe_sleep(duration, event):
    """Sleep with frequent stop checks."""
    start = time.monotonic()
    while time.monotonic() - start < duration:
        if event.is_set():
            return True
        time.sleep(min(0.01, duration - (time.monotonic() - start)))  # Faster response
    return event.is_set()

# --- Square Movement Logic ---
def run_square_background(units, stop_event_ref):
    """Execute square movement in a thread."""
    global square_thread
    print(f"Starting square: {units} units")
    full_speed_time = max(0.1, units * TIME_PER_UNIT)
    total_ramp_time = 2 * RAMP_STEPS * RAMP_DELAY
    print(f"Segment duration: {full_speed_time + total_ramp_time:.2f}s")

    segments = [[1, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0]]  # Fwd, Right, Bwd, Left
    names = ["Forward", "Strafe Left", "Backward", "Strafe Right"]

    try:
        for i, (vx_f, vy_f, omega_f) in enumerate(segments):
            print(f"-- Segment {i+1}: {names[i]} --")

            # Ramp Up
            print("   Ramping up...")
            for step in range(1, RAMP_STEPS + 1):
                if stop_event_ref.is_set():
                    raise InterruptedError("Stopped during ramp up")
                speed = MOVE_SPEED * (step / RAMP_STEPS)
                speeds = calculate_mecanum_speeds(speed * vx_f, speed * vy_f, 0)
                if not _send_motor_speeds(*speeds):
                    raise ConnectionError("Serial send failed")
                time.sleep(RAMP_DELAY)

            # Full Speed
            print(f"   Moving full speed ({full_speed_time:.2f}s)...")
            speeds = calculate_mecanum_speeds(MOVE_SPEED * vx_f, MOVE_SPEED * vy_f, 0)
            if not _send_motor_speeds(*speeds):
                raise ConnectionError("Serial send failed")
            if _safe_sleep(full_speed_time, stop_event_ref):
                raise InterruptedError("Stopped during full speed")

            # Ramp Down
            print("   Ramping down...")
            for step in range(RAMP_STEPS - 1, -1, -1):
                if stop_event_ref.is_set():
                    raise InterruptedError("Stopped during ramp down")
                speed = MOVE_SPEED * (step / RAMP_STEPS)
                speeds = calculate_mecanum_speeds(speed * vx_f, speed * vy_f, 0)
                _send_motor_speeds(*speeds)
                time.sleep(RAMP_DELAY)

            print("   Segment end.")
            _send_motor_speeds(0, 0, 0, 0)
            time.sleep(0.1)

        print("Square completed.")
    except InterruptedError as e:
        print(f"Interrupted: {e}")
    except Exception as e:
        print(f"Error in square thread: {e}")
    finally:
        print("Stopping motors...")
        for _ in range(STOP_REPEATS):
            _send_motor_speeds(0, 0, 0, 0)
            time.sleep(0.01)
        square_thread = None
        stop_event_ref.clear()
        print("Thread finished.")

# --- Flask Routes ---
@app.route('/')
def index():
    """Serve the control page with dark mode."""
    return render_template_string(HTML_TEMPLATE)

@app.route('/start_square', methods=['POST'])
def start_square_route():
    """Start square movement."""
    global square_thread, stop_event
    if not ser or not ser.is_open:
        return jsonify(success=False, message="Serial not connected"), 503
    if square_thread and square_thread.is_alive():
        return jsonify(success=False, message="Movement in progress"), 409
    try:
        units = int(request.get_json().get('units', 10))
        if units <= 0:
            return jsonify(success=False, message="Units must be positive"), 400
    except (ValueError, TypeError):
        return jsonify(success=False, message="Invalid units"), 400

    stop_event.clear()
    square_thread = threading.Thread(target=run_square_background, args=(units, stop_event), daemon=True)
    square_thread.start()
    return jsonify(success=True, message=f"Square started ({units} units)")

@app.route('/stop', methods=['POST'])
def stop_route():
    """Stop movement immediately."""
    global square_thread, stop_event
    print(">>> Stop Requested <<<")
    stop_event.set()
    print("Sending stop commands...")
    success = True
    for _ in range(STOP_REPEATS):
        if not _send_motor_speeds(0, 0, 0, 0):
            success = False
        time.sleep(0.01)
    if square_thread:
        print("Thread signaled to stop.")
    return jsonify(success=success, message="Stop command sent" if success else "Stop sent, serial may have failed")

# --- HTML Template with Dark Mode ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Mecanum Square Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: sans-serif;
            padding: 20px;
            max-width: 500px;
            margin: auto;
            background-color: #1e1e1e;
            color: #ffffff;
        }
        .control-group {
            margin-bottom: 15px;
            padding: 15px;
            border: 1px solid #444;
            border-radius: 5px;
            background-color: #2a2a2a;
        }
        label { margin-right: 10px; color: #ddd; }
        input[type=number] {
            width: 80px;
            padding: 8px;
            background-color: #333;
            color: #fff;
            border: 1px solid #555;
        }
        button {
            padding: 10px 15px;
            margin: 5px 10px 5px 0;
            font-size: 1em;
            cursor: pointer;
            border: none;
            border-radius: 4px;
        }
        #start-button { background-color: #4CAF50; color: white; }
        #stop-button { background-color: #f44336; color: white; }
        #status {
            margin-top: 20px;
            padding: 10px;
            border: 1px solid transparent;
            border-radius: 4px;
        }
        .status-success { border-color: #4CAF50; background-color: #2d4b2d; color: #b7e1b7; }
        .status-error { border-color: #f44336; background-color: #4b2d2d; color: #e1b7b7; }
        .status-info { border-color: #31708f; background-color: #2d3b4b; color: #b7d3e1; }
    </style>
</head>
<body>
    <h1>Mecanum Square Controller</h1>
    <div class="control-group">
        <label for="units">Square Size (units):</label>
        <input type="number" id="units" name="units" value="10" min="1">
    </div>
    <div class="control-group">
        <button id="start-button" onclick="startSquare()">Start Square</button>
        <button id="stop-button" onclick="stopMovement()">Stop Immediately</button>
    </div>
    <div id="status" class="status-info">Enter units and click Start.</div>

    <script>
        const unitsInput = document.getElementById('units');
        const startButton = document.getElementById('start-button');
        const stopButton = document.getElementById('stop-button');
        const statusDiv = document.getElementById('status');

        function setStatus(message, type = 'info') {
            statusDiv.textContent = message;
            statusDiv.className = `status-${type}`;
        }

        async function startSquare() {
            const units = parseInt(unitsInput.value, 10);
            if (isNaN(units) || units <= 0) {
                setStatus('Enter a valid positive number.', 'error');
                return;
            }
            setStatus('Starting...', 'info');
            startButton.disabled = true;
            stopButton.disabled = false;
            try {
                const response = await fetch('/start_square', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ units })
                });
                const result = await response.json();
                if (response.ok && result.success) {
                    setStatus(`Square started (${units} units).`, 'success');
                } else {
                    setStatus(`Start error: ${result.message || 'Unknown'}`, 'error');
                    startButton.disabled = false;
                }
            } catch (e) {
                setStatus(`Network error: ${e}`, 'error');
                startButton.disabled = false;
            }
        }

        async function stopMovement() {
            setStatus('Stopping...', 'info');
            stopButton.disabled = true;
            try {
                const response = await fetch('/stop', { method: 'POST' });
                const result = await response.json();
                if (response.ok && result.success) {
                    setStatus('Stopped.', 'success');
                } else {
                    setStatus(`Stop issue: ${result.message || 'Unknown'}`, 'error');
                }
            } catch (e) {
                setStatus(`Network error: ${e}`, 'error');
            } finally {
                startButton.disabled = false;
                stopButton.disabled = false;
            }
        }
    </script>
</body>
</html>
"""

# --- Main Execution ---
if __name__ == '__main__':
    print("--- Mecanum Square Controller ---")
    if connect_serial():
        protocol = 'https' if USE_HTTPS else 'http'
        print(f"Starting server on {protocol}://{FLASK_HOST}:{FLASK_PORT}")
        if USE_HTTPS:
            print("Using ad-hoc HTTPS. Browser may show a security warning.")
        try:
            app.run(
                host=FLASK_HOST,
                port=FLASK_PORT,
                debug=False,
                threaded=True,
                ssl_context='adhoc' if USE_HTTPS else None
            )
        except Exception as e:
            print(f"Server error: {e}")
        finally:
            if ser and ser.is_open:
                print("Shutting down, stopping motors...")
                stop_event.set()
                for _ in range(STOP_REPEATS):
                    _send_motor_speeds(0, 0, 0, 0)
                    time.sleep(0.01)
                ser.close()
                print("Serial closed.")
            print("Server stopped.")
    else:
        print("Exiting due to serial failure.")
