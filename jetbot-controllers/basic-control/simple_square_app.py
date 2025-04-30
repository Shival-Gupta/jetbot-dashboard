# --- Imports ---
import time
import serial
import serial.tools.list_ports
from flask import Flask, render_template_string, request, jsonify
import math
import threading # Use standard threading

# --- Configuration ---
# !!! SET YOUR SERIAL PORT HERE !!!
SERIAL_PORT = '/dev/ttyACM0'
# SERIAL_PORT = None # Use None to attempt auto-detection

BAUD_RATE = 9600
SERIAL_TIMEOUT = 0.1 # seconds
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 6002 # Using the requested port

# --- Movement Parameters (Tune these!) ---
MOVE_SPEED = 150       # Base speed for square sides (0-255)
MAX_SPEED = 255
RAMP_STEPS = 4         # Number of steps for ramp-up/down
RAMP_DELAY = 0.05      # Seconds between ramp steps (total ramp time = RAMP_STEPS * RAMP_DELAY)
TIME_PER_UNIT = 0.03   # Seconds of full speed movement per 'unit' - **NEEDS TUNING**

# --- Global Variables ---
ser = None # Serial connection object
serial_lock = threading.Lock() # Lock for thread-safe serial access
square_thread = None # Holds the active movement thread object
stop_event = threading.Event() # Event to signal the thread to stop

# --- Flask App Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'simple_square_secret!' # Change if needed

# --- Serial Communication & Motor Control (Reused & Adapted) ---

def find_arduino_port():
    # ... (same as before) ...
    """Attempts to find a USB serial port likely connected to an Arduino."""
    ports = serial.tools.list_ports.comports()
    keywords = ['arduino', 'usb serial ch340', 'usb serial cp210x', 'ttyacm', 'ttyusb']
    arduino_ports = []
    print("Available ports:")
    for p in ports:
        print(f"- {p.device}: {p.description}")
        if any(keyword in p.description.lower() for keyword in keywords) or \
           any(keyword in p.device.lower() for keyword in keywords):
             arduino_ports.append(p.device)
    if arduino_ports:
        print(f"Found potential Arduino ports: {arduino_ports}")
        return arduino_ports[0]
    print("Warning: Could not auto-detect Arduino port based on keywords.")
    return None

def connect_serial():
    """Establishes the serial connection."""
    global ser, SERIAL_PORT
    if ser and ser.is_open:
        return True
    port_to_try = SERIAL_PORT
    if port_to_try is None:
        print("SERIAL_PORT not set, attempting auto-detection...")
        port_to_try = find_arduino_port()
        if port_to_try is None:
            print("Error: Auto-detection failed and SERIAL_PORT not set manually.")
            return False
        else:
            print(f"Auto-detected port: {port_to_try}")
    try:
        print(f"Attempting to connect to {port_to_try} at {BAUD_RATE} baud...")
        time.sleep(0.5)
        ser = serial.Serial(port_to_try, BAUD_RATE, timeout=SERIAL_TIMEOUT)
        print("Waiting for Arduino to initialize...")
        time.sleep(2)
        try:
            startup_lines = ser.read_all().decode('utf-8', errors='ignore').strip()
            if startup_lines:
                 print("--- Arduino Startup Messages ---")
                 print(startup_lines)
                 print("------------------------------")
            ser.flushInput()
        except Exception as read_err:
            print(f"Warning: Error reading startup message: {read_err}")
        print(f"Serial connection established on {port_to_try}.")
        return True
    except serial.SerialException as e:
        print(f"Error opening serial port {port_to_try}: {e}")
        ser = None
        return False
    except Exception as e:
        print(f"An unexpected error occurred during serial connection: {e}")
        ser = None
        return False

def send_command(command):
    """Sends a command string to the Arduino over serial, using a lock."""
    global ser, serial_lock
    if ser is None or not ser.is_open:
        print("Serial port not connected. Command ignored.")
        return False

    with serial_lock: # Acquire lock
        try:
            command_bytes = (command + '\n').encode('utf-8')
            ser.write(command_bytes)
            # print(f"Sent: {command}") # Uncomment for debug
            return True
        except serial.SerialTimeoutException:
            print("Warning: Serial write timeout.")
            return False
        except serial.SerialException as e:
            print(f"Serial error during send: {e}")
            try: ser.close()
            except: pass
            ser = None
            return False
        except Exception as e:
            print(f"Error sending command '{command}': {e}")
            return False
        # Lock released automatically by 'with'

def calculate_mecanum_speeds(vx, vy, omega):
    # ... (same as before) ...
    """Calculates individual wheel speeds for Mecanum drive."""
    fl = vx - vy - omega
    fr = vx + vy + omega
    rl = vx + vy - omega
    rr = vx - vy + omega
    max_abs_speed = max(abs(fl), abs(fr), abs(rl), abs(rr), 1) # Avoid division by zero
    scale_factor = 1.0
    if max_abs_speed > MAX_SPEED:
        scale_factor = float(MAX_SPEED) / max_abs_speed
    fl = int(fl * scale_factor)
    fr = int(fr * scale_factor)
    rl = int(rl * scale_factor)
    rr = int(rr * scale_factor)
    # Clamp just in case
    fl = max(-MAX_SPEED, min(MAX_SPEED, fl))
    fr = max(-MAX_SPEED, min(MAX_SPEED, fr))
    rl = max(-MAX_SPEED, min(MAX_SPEED, rl))
    rr = max(-MAX_SPEED, min(MAX_SPEED, rr))
    return [fl, fr, rl, rr]

def _send_motor_speeds(fl, fr, rl, rr):
    """Helper to format and send motor speeds."""
    cmd = f"{int(fl)},{int(fr)},{int(rl)},{int(rr)}"
    return send_command(cmd)

def _safe_sleep(duration, event):
    """Sleep for a duration, but wake up early if event is set."""
    start_time = time.monotonic()
    while time.monotonic() - start_time < duration:
        if event.is_set():
            return True # Event was set
        # Sleep for short intervals to check event frequently
        check_interval = min(0.05, duration - (time.monotonic() - start_time))
        if check_interval > 0:
             time.sleep(check_interval)
        else: # Avoid potential negative sleep time
            break
    return event.is_set()

# --- Square Movement Logic (Background Thread) ---

def run_square_background(units, stop_event_ref):
    """Function executed in a background thread to move the robot in a square."""
    global square_thread
    print(f"Starting square movement: {units} units")

    # --- Calculations ---
    # Total time spent ramping up and down for one segment
    total_ramp_time = 2 * RAMP_STEPS * RAMP_DELAY
    # Time spent moving at full speed for one segment
    # Ensure minimum move time even if units are small
    full_speed_time = max(0.1, (units * TIME_PER_UNIT))
    segment_duration = full_speed_time + total_ramp_time # Includes ramp up/down
    print(f"Calculated segment duration: {segment_duration:.2f}s (Ramp: {total_ramp_time:.2f}s, Full: {full_speed_time:.2f}s)")


    # --- Movement Segments ---
    # Define segments: [vx_factor, vy_factor, omega_factor]
    # vx: +fwd/-bwd, vy: +left/-right, omega: +ccw/-cw
    segments = [
        [1, 0, 0],  # 1. Move Forward
        [0, -1, 0], # 2. Strafe Right
        [-1, 0, 0], # 3. Move Backward
        [0, 1, 0],  # 4. Strafe Left
    ]

    try:
        for i, factors in enumerate(segments):
            vx_f, vy_f, omega_f = factors
            segment_name = ["Forward", "Strafe Right", "Backward", "Strafe Left"][i]
            print(f"-- Segment {i+1}: {segment_name} --")

            # 1. Ramp Up
            print("   Ramping up...")
            for step in range(1, RAMP_STEPS + 1):
                if stop_event_ref.is_set(): raise InterruptedError("Stop event set during ramp up")
                speed_fraction = step / RAMP_STEPS
                current_speed = MOVE_SPEED * speed_fraction
                vx = current_speed * vx_f
                vy = current_speed * vy_f
                omega = 0 # No rotation during linear moves
                speeds = calculate_mecanum_speeds(vx, vy, omega)
                if not _send_motor_speeds(*speeds):
                    print("Error sending command during ramp up")
                    raise ConnectionError("Failed to send serial command")
                time.sleep(RAMP_DELAY) # Use standard time.sleep, thread doesn't need eventlet sleep

            # 2. Move at Full Speed
            print(f"   Moving full speed ({full_speed_time:.2f}s)...")
            vx = MOVE_SPEED * vx_f
            vy = MOVE_SPEED * vy_f
            omega = 0
            speeds = calculate_mecanum_speeds(vx, vy, omega)
            if not _send_motor_speeds(*speeds):
                 print("Error sending command during full speed move")
                 raise ConnectionError("Failed to send serial command")

            # Sleep, but check stop_event frequently
            if _safe_sleep(full_speed_time, stop_event_ref):
                 raise InterruptedError("Stop event set during full speed move")


            # 3. Ramp Down
            print("   Ramping down...")
            for step in range(RAMP_STEPS - 1, -1, -1): # Go from (steps-1) down to 0
                if stop_event_ref.is_set(): raise InterruptedError("Stop event set during ramp down")
                speed_fraction = step / RAMP_STEPS
                current_speed = MOVE_SPEED * speed_fraction
                vx = current_speed * vx_f
                vy = current_speed * vy_f
                omega = 0
                speeds = calculate_mecanum_speeds(vx, vy, omega)
                if not _send_motor_speeds(*speeds):
                    print("Error sending command during ramp down")
                    # Don't raise error here, try to finish stopping
                time.sleep(RAMP_DELAY)

            # Ensure stopped after segment before starting next
            print("   Segment end stop.")
            if not _send_motor_speeds(0, 0, 0, 0):
                print("Warning: Failed to send stop command between segments.")
            time.sleep(0.2) # Short pause between segments


        print("Square movement finished normally.")

    except InterruptedError as e:
        print(f"Square movement interrupted: {e}")
    except ConnectionError as e:
         print(f"Square movement failed due to connection error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred in square thread: {e}")
    finally:
        # Always ensure motors are stopped at the end
        print("Ensuring motors are stopped.")
        _send_motor_speeds(0, 0, 0, 0)
        time.sleep(0.05) # Give command time to send
        _send_motor_speeds(0, 0, 0, 0)
        square_thread = None # Clear the global thread variable
        stop_event_ref.clear() # Reset event for next time
        print("Square thread finished.")


# --- Flask Routes ---

@app.route('/')
def index():
    """Serves the main HTML control page."""
    return render_template_string(HTML_TEMPLATE)

@app.route('/start_square', methods=['POST'])
def start_square_route():
    """Starts the square movement in a background thread."""
    global square_thread, stop_event
    if not ser or not ser.is_open:
         return jsonify(success=False, message="Serial port not connected."), 503

    if square_thread and square_thread.is_alive():
        return jsonify(success=False, message="Square movement already in progress."), 409 # Conflict

    try:
        data = request.get_json()
        units = int(data.get('units', 10)) # Default to 10 units if not provided
        if units <= 0:
            return jsonify(success=False, message="Units must be a positive number."), 400
    except (ValueError, TypeError):
         return jsonify(success=False, message="Invalid units value."), 400

    # Prepare and start the background thread
    stop_event.clear() # Ensure stop event is reset
    square_thread = threading.Thread(target=run_square_background, args=(units, stop_event), daemon=True)
    square_thread.start()

    return jsonify(success=True, message=f"Square movement started ({units} units).")

@app.route('/stop', methods=['POST'])
def stop_route():
    """Stops any ongoing movement."""
    global square_thread, stop_event
    print(">>> Stop Requested via HTTP <<<")

    # Signal the thread to stop
    stop_event.set()

    # Send immediate stop command via serial
    success = _send_motor_speeds(0, 0, 0, 0)
    time.sleep(0.05) # Short delay
    _send_motor_speeds(0, 0, 0, 0) # Send again for reliability

    # Optional: Wait briefly for the thread to finish
    if square_thread and square_thread.is_alive():
        print("Waiting for square thread to stop...")
        square_thread.join(timeout=0.5) # Wait max 0.5 seconds
        if square_thread.is_alive():
             print("Warning: Square thread did not stop quickly.")
        else:
             print("Square thread stopped.")
        square_thread = None # Clear reference anyway

    if success:
        return jsonify(success=True, message="Stop command sent.")
    else:
        return jsonify(success=False, message="Stop command sent, but serial write may have failed."), 500


# --- HTML Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Simple Mecanum Square</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: sans-serif; padding: 20px; max-width: 500px; margin: auto; }
        .control-group { margin-bottom: 15px; padding: 15px; border: 1px solid #ccc; border-radius: 5px; }
        label { margin-right: 10px; }
        input[type=number] { width: 80px; padding: 8px; }
        button { padding: 10px 15px; margin: 5px 10px 5px 0; font-size: 1em; cursor: pointer; }
        #start-button { background-color: #4CAF50; color: white; }
        #stop-button { background-color: #f44336; color: white; }
        #status { margin-top: 20px; padding: 10px; border: 1px solid transparent; border-radius: 4px; }
        .status-success { border-color: #4CAF50; background-color: #dff0d8; color: #3c763d; }
        .status-error { border-color: #f44336; background-color: #f2dede; color: #a94442; }
        .status-info { border-color: #31708f; background-color: #d9edf7; color: #31708f; }
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
            statusDiv.className = `status-${type}`; // status-info, status-success, status-error
            // Disable/enable buttons based on state could be added here
            // e.g., disable start when running, disable stop when not running
        }

        async function startSquare() {
            const unitsValue = parseInt(unitsInput.value, 10);
            if (isNaN(unitsValue) || unitsValue <= 0) {
                setStatus('Please enter a valid positive number for units.', 'error');
                return;
            }

            setStatus('Sending start command...', 'info');
            startButton.disabled = true; // Prevent double clicks
            stopButton.disabled = false;

            try {
                const response = await fetch('/start_square', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ units: unitsValue })
                });

                const result = await response.json();

                if (response.ok && result.success) {
                    setStatus(`Square movement started (${unitsValue} units). Watch the robot!`, 'success');
                    // Keep start disabled until finished or stopped
                } else {
                    setStatus(`Error starting: ${result.message || 'Unknown error'}`, 'error');
                    startButton.disabled = false; // Re-enable on error
                }

            } catch (error) {
                setStatus(`Network Error starting square: ${error}`, 'error');
                startButton.disabled = false; // Re-enable on error
            }
        }

        async function stopMovement() {
            setStatus('Sending stop command...', 'info');
            stopButton.disabled = true; // Disable briefly

            try {
                const response = await fetch('/stop', { method: 'POST' });
                const result = await response.json();

                if (response.ok && result.success) {
                    setStatus('Stop command sent. Movement should cease.', 'success');
                } else {
                    // Even if server reports failure, UI assumes stopped
                    setStatus(`Stop command sent, but server reported an issue: ${result.message || 'Unknown error'}`, 'error');
                }

            } catch (error) {
                setStatus(`Network Error stopping movement: ${error}`, 'error');
            } finally {
                // Always re-enable buttons after stop attempt
                 startButton.disabled = false;
                 stopButton.disabled = false; // Or keep disabled until confirmed stopped? Simpler to always re-enable.
            }
        }

         // Initial state
         startButton.disabled = false;
         stopButton.disabled = false; // Stop initially enabled in case robot was moving before start

    </script>
</body>
</html>
"""


# --- Main Execution ---
if __name__ == '__main__':
    print("--- Simple Mecanum Square Controller ---")
    if connect_serial():
        print(f"Flask server starting on http://{FLASK_HOST}:{FLASK_PORT}")
        try:
            # Use Flask's default development server (Werkzeug)
            # No need for eventlet/socketio here
            app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, threaded=True)
            # threaded=True is important to allow background thread processing
        except KeyboardInterrupt:
            print("Ctrl+C detected. Stopping motors and shutting down.")
        finally:
            # Ensure motors are stopped on exit
            if ser and ser.is_open:
                 try:
                    print("Sending final stop command...")
                    stop_event.set() # Signal any running thread
                    _send_motor_speeds(0, 0, 0, 0)
                    time.sleep(0.1)
                    _send_motor_speeds(0, 0, 0, 0)
                    ser.close()
                    print("Serial port closed.")
                 except Exception as e:
                    print(f"Error during cleanup: {e}")
            print("Server shut down.")
    else:
        print("\nExiting due to serial connection failure.")
