import time
import serial
import serial.tools.list_ports
from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO, emit
import math
import eventlet # Required for async SocketIO

# Required for Flask-SocketIO
eventlet.monkey_patch()

# --- Configuration ---
SERIAL_PORT = '/dev/ttyACM0' # <--- SET YOUR SERIAL PORT HERE
# SERIAL_PORT = None # Use None to attempt auto-detection

BAUD_RATE = 9600
SERIAL_TIMEOUT = 0.1 # seconds (lower timeout might feel more responsive)
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 6002

# --- Default Speeds (can be changed via UI) ---
INITIAL_DEFAULT_SPEED = 120 # Default PWM for linear movement (0-255)
INITIAL_TURN_SPEED = 90     # Default PWM for rotation (0-255)
MAX_SPEED = 255

# --- Global Variables ---
ser = None # Serial connection object
socketio = None # SocketIO instance

# --- Robot State ---
# Store current desired speeds based on key presses
current_vx = 0
current_vy = 0
current_omega = 0
# Store speed settings changeable via UI
current_default_speed = INITIAL_DEFAULT_SPEED
current_turn_speed = INITIAL_TURN_SPEED
# Track active keys to handle combinations and releases
active_keys = set()
# Emergency stop flag
emergency_stop_active = False

# --- Flask App Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key!' # Change this for production
# No need for CORS with SocketIO usually, but keep if accessing HTTP routes from different origins
# from flask_cors import CORS
# CORS(app)

socketio = SocketIO(app, async_mode='eventlet') # Use eventlet for async

# --- Serial Communication Functions ---

def find_arduino_port():
    """Attempts to find a USB serial port likely connected to an Arduino."""
    ports = serial.tools.list_ports.comports()
    # More specific keywords for common Arduino/clone types
    keywords = ['arduino', 'usb serial ch340', 'usb serial cp210x', 'ttyacm', 'ttyusb']
    arduino_ports = []
    print("Available ports:")
    for p in ports:
        print(f"- {p.device}: {p.description}")
        # Check if any keyword is present in the description or device name
        if any(keyword in p.description.lower() for keyword in keywords) or \
           any(keyword in p.device.lower() for keyword in keywords):
             arduino_ports.append(p.device)

    if arduino_ports:
        print(f"Found potential Arduino ports: {arduino_ports}")
        return arduino_ports[0] # Return the first one found
    print("Warning: Could not auto-detect Arduino port based on keywords.")
    return None

def connect_serial():
    """Establishes the serial connection."""
    global ser, SERIAL_PORT
    if ser and ser.is_open:
        # print("Serial connection already open.")
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
        # Add a short delay before opening, sometimes helps on Linux
        time.sleep(0.5)
        ser = serial.Serial(port_to_try, BAUD_RATE, timeout=SERIAL_TIMEOUT)
        print("Waiting for Arduino to initialize...")
        time.sleep(2) # Wait for Arduino reset after connection
        # Read any startup messages from Arduino
        try:
            startup_lines = ser.read_all().decode('utf-8', errors='ignore').strip()
            if startup_lines:
                 print("--- Arduino Startup Messages ---")
                 print(startup_lines)
                 print("------------------------------")
            ser.flushInput() # Clear input buffer
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
    """Sends a command string to the Arduino over serial."""
    global ser, emergency_stop_active
    if emergency_stop_active and command != "0,0,0,0":
        # print("Emergency stop active, ignoring command:", command)
        # Optionally ensure stop command keeps getting sent
        command = "0,0,0,0"
        # return False # Don't send non-stop commands

    if ser is None or not ser.is_open:
        print("Serial port not connected. Command ignored.")
        # Attempt to reconnect automatically? Be careful with loops.
        # connect_serial() # Maybe try reconnecting here?
        return False

    try:
        command_bytes = (command + '\n').encode('utf-8')
        ser.write(command_bytes)
        # print(f"Sent: {command}") # Reduce noise, uncomment for debugging
        return True

    except serial.SerialTimeoutException:
        print("Warning: Serial write timeout.")
        return False
    except serial.SerialException as e:
        print(f"Serial error during send: {e}")
        try:
            ser.close()
        except:
            pass
        ser = None # Force reconnect attempt on next call
        # Attempt immediate reconnect (optional)
        # time.sleep(1)
        # connect_serial()
        return False
    except Exception as e:
        print(f"Error sending command '{command}': {e}")
        return False

def calculate_mecanum_speeds(vx, vy, omega):
    """
    Calculates individual wheel speeds for Mecanum drive.
    vx: forward/backward speed (+ forward)
    vy: strafing speed (+ left) - Note: Positive vy = Strafe LEFT
    omega: rotational speed (+ counter-clockwise / CCW)
    Returns: [fl, fr, rl, rr] clamped to [-MAX_SPEED, MAX_SPEED]
    ORDER MUST MATCH ARDUINO: 0=FL, 1=FR, 2=RL, 3=RR
    """
    # --- Standard Mecanum Kinematics ---
    # Adjust signs based on YOUR specific motor wiring and orientation.
    # This assumes positive speed command = forward wheel rotation AND
    # wheels are mounted in the standard X configuration: / \ front, \ / rear
    #
    # Forward (vx+): All wheels forward
    # Strafe Left (vy+): FL-, FR+, RL+, RR-
    # Rotate CCW (omega+): FL-, FR+, RL-, RR+

    fl = vx - vy - omega # Front Left
    fr = vx + vy + omega # Front Right
    rl = vx + vy - omega # Rear Left
    rr = vx - vy + omega # Rear Right

    # --- Scaling ---
    # Find the maximum absolute speed calculated
    max_abs_speed = max(abs(fl), abs(fr), abs(rl), abs(rr))

    # Scale speeds down if any exceeds MAX_SPEED, preserving direction ratios
    scale_factor = 1.0
    if max_abs_speed > MAX_SPEED:
        scale_factor = float(MAX_SPEED) / max_abs_speed

    fl = int(fl * scale_factor)
    fr = int(fr * scale_factor)
    rl = int(rl * scale_factor)
    rr = int(rr * scale_factor)

    # --- Clamping (redundant if scaling is correct, but safe) ---
    fl = max(-MAX_SPEED, min(MAX_SPEED, fl))
    fr = max(-MAX_SPEED, min(MAX_SPEED, fr))
    rl = max(-MAX_SPEED, min(MAX_SPEED, rl))
    rr = max(-MAX_SPEED, min(MAX_SPEED, rr))

    return [fl, fr, rl, rr]

def update_robot_movement():
    """Calculates speeds based on active keys and sends command."""
    global current_vx, current_vy, current_omega, emergency_stop_active
    global current_default_speed, current_turn_speed

    if emergency_stop_active:
        # Ensure stop command is sent if emergency stop was just activated
        if current_vx != 0 or current_vy != 0 or current_omega != 0:
             print("Emergency Stop Activated - Sending stop command.")
             send_command("0,0,0,0")
             current_vx, current_vy, current_omega = 0, 0, 0
        # Keep sending stop? Optional, might flood serial.
        # send_command("0,0,0,0")
        return # Don't process keys if stopped

    # Reset speeds for this calculation cycle
    target_vx = 0
    target_vy = 0
    target_omega = 0

    # --- Map active keys to vx, vy, omega ---
    # Linear Movement (use default speed)
    if 'w' in active_keys: target_vx += current_default_speed
    if 'x' in active_keys: target_vx -= current_default_speed
    if 'a' in active_keys: target_vy += current_default_speed # Strafe Left
    if 'd' in active_keys: target_vy -= current_default_speed # Strafe Right

    # Diagonal Movement (Handled by combining linear components)
    if 'q' in active_keys:
        target_vx += current_default_speed
        target_vy += current_default_speed # Forward + Left
    if 'e' in active_keys:
        target_vx += current_default_speed
        target_vy -= current_default_speed # Forward + Right
    if 'z' in active_keys:
        target_vx -= current_default_speed
        target_vy += current_default_speed # Backward + Left
    if 'c' in active_keys:
        target_vx -= current_default_speed
        target_vy -= current_default_speed # Backward + Right

    # Rotation (use turn speed)
    if 'n' in active_keys: target_omega += current_turn_speed # CCW
    if 'm' in active_keys: target_omega -= current_turn_speed # CW

    # --- Apply Smoothing (Basic Velocity Smoothing) ---
    # Move current speeds towards target speeds gradually
    # Adjust smoothing_factor: 0 (no smoothing) to 1 (instant). Lower = smoother.
    smoothing_factor = 0.6 # Experiment with this value (e.g., 0.1 to 0.9)
    current_vx = int(current_vx * (1 - smoothing_factor) + target_vx * smoothing_factor)
    current_vy = int(current_vy * (1 - smoothing_factor) + target_vy * smoothing_factor)
    current_omega = int(current_omega * (1 - smoothing_factor) + target_omega * smoothing_factor)

    # Prevent tiny movements when keys are released
    dead_zone = 10 # PWM values below this are treated as zero
    if abs(current_vx) < dead_zone: current_vx = 0
    if abs(current_vy) < dead_zone: current_vy = 0
    if abs(current_omega) < dead_zone: current_omega = 0

    # --- Calculate and Send ---
    if not active_keys and current_vx == 0 and current_vy == 0 and current_omega == 0:
        # Only send stop command once when keys are released and speed is zero
        send_command("0,0,0,0")
        # print("Idling, stopped.") # Debug
    else:
        # Calculate final speeds using kinematics
        speeds = calculate_mecanum_speeds(current_vx, current_vy, current_omega)
        cmd = f"{speeds[0]},{speeds[1]},{speeds[2]},{speeds[3]}"
        send_command(cmd)
        # print(f"Active keys: {active_keys} -> vx:{current_vx} vy:{current_vy} w:{current_omega} -> Cmd: {cmd}") # Debug


# --- Flask Routes ---

@app.route('/')
def index():
    """Serves the main HTML control page."""
    # Pass initial speed values to the template
    return render_template_string(HTML_TEMPLATE,
                                 initial_default_speed=current_default_speed,
                                 initial_turn_speed=current_turn_speed,
                                 max_speed=MAX_SPEED)

# Keep the motor test route if desired (uses standard HTTP POST)
@app.route('/test_motor', methods=['POST'])
def http_test_motor():
     """Handles motor test commands from the web interface via HTTP."""
     data = request.get_json()
     if not data:
         return jsonify(success=False, message="Error: Invalid request data"), 400

     idx = data.get('index', -1)
     spd = data.get('speed', 80) # Default test speed
     dur = data.get('duration', 500) # Default test duration ms

     if not (0 <= idx <= 3):
         return jsonify(success=False, message="Invalid motor index"), 400

     cmd = f"TEST,{idx},{spd},{dur}"
     success = send_command(cmd) # Use the existing send_command

     if success:
        message = f"Test command sent for motor {idx}."
        print(message)
        return jsonify(success=True, message=message)
     else:
        message = f"Failed to send test command for motor {idx}."
        print(message)
        return jsonify(success=False, message=message), 500


# --- SocketIO Event Handlers ---

@socketio.on('connect')
def handle_connect():
    """Handles new client connections."""
    print(f"Client connected: {request.sid}")
    # Send current speed settings to the newly connected client
    emit('update_speeds', {
        'default_speed': current_default_speed,
        'turn_speed': current_turn_speed
    })
    # Ensure robot is stopped when a new client connects? Or assume previous state?
    # update_robot_movement() # Send current state (likely stopped if no keys pressed)

@socketio.on('disconnect')
def handle_disconnect():
    """Handles client disconnections."""
    print(f"Client disconnected: {request.sid}")
    # Option: Stop the robot when the *last* client disconnects?
    # This requires tracking connected clients.
    # For simplicity, we can just ensure keys are cleared.
    global active_keys, emergency_stop_active
    active_keys.clear() # Clear keys for safety
    emergency_stop_active = False # Reset stop on disconnect? Or keep it active? Let's reset.
    update_robot_movement() # Send stop command

@socketio.on('key_event')
def handle_key_event(data):
    """Handles key presses and releases from the client."""
    global active_keys, emergency_stop_active
    key = data.get('key', '').lower()
    event_type = data.get('type', '') # 'down' or 'up'

    valid_keys = {'q', 'w', 'e', 'a', 's', 'd', 'z', 'x', 'c', 'n', 'm'}

    if key not in valid_keys:
        # print(f"Ignoring invalid key: {key}")
        return

    if event_type == 'down':
        if key == 's':
            emergency_stop_active = True
            active_keys.clear() # Clear other keys on emergency stop
            print("Emergency Stop KEY PRESSED")
        elif not emergency_stop_active: # Only add keys if not stopped
            active_keys.add(key)
            # print(f"Key down: {key}, Active: {active_keys}") # Debug

    elif event_type == 'up':
        if key == 's':
            emergency_stop_active = False # Release emergency stop
            print("Emergency Stop KEY RELEASED")
        active_keys.discard(key) # Remove key regardless of stop state
        # print(f"Key up: {key}, Active: {active_keys}") # Debug

    # Update movement based on the new key state
    update_robot_movement()

@socketio.on('set_speeds')
def handle_set_speeds(data):
    """Handles updates to speed settings from the client UI."""
    global current_default_speed, current_turn_speed
    valid_update = False

    try:
        new_default = int(data.get('default_speed', current_default_speed))
        new_turn = int(data.get('turn_speed', current_turn_speed))

        # Validate and clamp speeds
        current_default_speed = max(0, min(MAX_SPEED, new_default))
        current_turn_speed = max(0, min(MAX_SPEED, new_turn))
        valid_update = True

        print(f"Speeds updated: Default={current_default_speed}, Turn={current_turn_speed}")

        # Broadcast the updated speeds to all clients so their UIs sync
        emit('update_speeds', {
            'default_speed': current_default_speed,
            'turn_speed': current_turn_speed
        }, broadcast=True)

    except (ValueError, TypeError) as e:
        print(f"Invalid speed data received: {data} - Error: {e}")
        # Optionally send error back to client
        emit('error', {'message': f'Invalid speed value received.'})

    # Optionally trigger a movement update if speeds changed while keys were held
    if valid_update and not emergency_stop_active:
         update_robot_movement()


# --- HTML Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Mecanum Keyboard Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: sans-serif; padding: 15px; display: flex; flex-direction: column; align-items: center; }
        #controls { text-align: center; margin-bottom: 20px; }
        #keyboard-info { border: 1px solid #ccc; padding: 15px; margin-bottom: 20px; max-width: 400px; }
        #keyboard-info h2, #speed-settings h2, #motor-test-section h2 { margin-top: 0; }
        #keyboard-info code { background-color: #eee; padding: 2px 5px; border-radius: 3px; }
        #speed-settings, #motor-test-section { border: 1px solid #ccc; padding: 15px; margin-bottom: 20px; width: 90%; max-width: 400px;}
        .speed-control label { display: inline-block; width: 100px; }
        .speed-control input[type=range] { width: 150px; vertical-align: middle; }
        .speed-control span { display: inline-block; min-width: 30px; text-align: right; }
        button { padding: 8px 12px; margin: 5px; font-size: 0.9em; cursor: pointer; }
        #status { margin-top: 15px; font-weight: bold; min-height: 20px; }
        .error { color: red; }
        .success { color: green; }
        .active-key { font-weight: bold; color: blue; }
    </style>
    <script src="https://cdn.socket.io/4.6.0/socket.io.min.js"></script>
</head>
<body>
    <h1>Mecanum Keyboard Control</h1>
    <div id="status">Connecting to server...</div>

    <div id="speed-settings">
        <h2>Speed Settings</h2>
        <div class="speed-control">
            <label for="default_speed">Move Speed:</label>
            <input type="range" id="default_speed" min="0" max="{{ max_speed }}" value="{{ initial_default_speed }}" oninput="updateSpeedDisplay('default_speed')">
            <span id="default_speed_val">{{ initial_default_speed }}</span>
        </div>
        <div class="speed-control">
            <label for="turn_speed">Turn Speed:</label>
            <input type="range" id="turn_speed" min="0" max="{{ max_speed }}" value="{{ initial_turn_speed }}" oninput="updateSpeedDisplay('turn_speed')">
            <span id="turn_speed_val">{{ initial_turn_speed }}</span>
        </div>
        <button onclick="sendSpeedSettings()">Apply Speeds</button>
    </div>

    <div id="keyboard-info">
        <h2>Keyboard Controls (Click here first!)</h2>
        <p>Click inside this box or the page body, then use keys:</p>
        <ul>
            <li>Movement: <code>Q</code> <code>W</code> <code>E</code> <code>A</code> <code>D</code> <code>Z</code> <code>X</code> <code>C</code></li>
            <li>Rotate CCW: <code>N</code></li>
            <li>Rotate CW: <code>M</code></li>
            <li><strong style="color:red">Emergency STOP:</strong> <code>S</code> (Hold to stop, release to enable keys again)</li>
        </ul>
        <p>Status: <span id="keyboard-status">Inactive</span></p>
        <p>Active Keys: <span id="active-keys-display">None</span></p>
    </div>

     <div id="motor-test-section">
        <h2>Motor Mapping Test</h2>
        <p><small>Assumed mapping (Index): FL(0), FR(1), RL(2), RR(3)</small></p>
        <div>
            <button onclick="testMotor(0)">Test FL (0)</button>
            <button onclick="testMotor(1)">Test FR (1)</button>
            <button onclick="testMotor(2)">Test RL (2)</button>
            <button onclick="testMotor(3)">Test RR (3)</button>
        </div>
         <div>
             <button onclick="testMotor(0, -80)">Test FL (Rev)</button>
             <button onclick="testMotor(1, -80)">Test FR (Rev)</button>
             <button onclick="testMotor(2, -80)">Test RL (Rev)</button>
             <button onclick="testMotor(3, -80)">Test RR (Rev)</button>
        </div>
         <div id="test-status" style="margin-top: 10px;"></div>
    </div>


    <script>
        // Use ws:// or wss:// depending on http/https
        const socket = io(); // Defaults to connecting to the server that served the page

        const statusDiv = document.getElementById('status');
        const keyboardStatusDiv = document.getElementById('keyboard-status');
        const activeKeysDisplay = document.getElementById('active-keys-display');
        const defaultSpeedSlider = document.getElementById('default_speed');
        const turnSpeedSlider = document.getElementById('turn_speed');
        const defaultSpeedVal = document.getElementById('default_speed_val');
        const turnSpeedVal = document.getElementById('turn_speed_val');
        const testStatusDiv = document.getElementById('test-status');


        const pressedKeys = new Set();
        const validControlKeys = ['q', 'w', 'e', 'a', 's', 'd', 'z', 'x', 'c', 'n', 'm'];

        socket.on('connect', () => {
            statusDiv.textContent = 'Connected to server.';
            statusDiv.className = 'success';
            keyboardStatusDiv.textContent = 'Ready for input.';
            // Request current speeds on connect? Server sends them anyway.
        });

        socket.on('disconnect', () => {
            statusDiv.textContent = 'Disconnected from server.';
            statusDiv.className = 'error';
            keyboardStatusDiv.textContent = 'Inactive (disconnected)';
            pressedKeys.clear();
            updateActiveKeysDisplay();
        });

        socket.on('error', (data) => {
            statusDiv.textContent = `Server Error: ${data.message}`;
            statusDiv.className = 'error';
        });

         socket.on('update_speeds', (data) => {
            console.log("Received speed update from server:", data);
            defaultSpeedSlider.value = data.default_speed;
            turnSpeedSlider.value = data.turn_speed;
            updateSpeedDisplay('default_speed');
            updateSpeedDisplay('turn_speed');
        });

        // --- Keyboard Event Handling ---
        document.addEventListener('keydown', (event) => {
            // Ignore if typing in input fields
            if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
                return;
            }

            const key = event.key.toLowerCase();
            if (validControlKeys.includes(key) && !pressedKeys.has(key)) {
                pressedKeys.add(key);
                socket.emit('key_event', { key: key, type: 'down' });
                updateActiveKeysDisplay();
                // Prevent default browser action for keys like 'space' or arrow keys if they were used
                // if (['w','a','s','d','q','e','z','x','c'].includes(key)) { // Example
                     event.preventDefault();
                // }
            }
            keyboardStatusDiv.textContent = 'Receiving input...';
        });

        document.addEventListener('keyup', (event) => {
             // Ignore if typing in input fields
             if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
                 return;
             }

            const key = event.key.toLowerCase();
            if (validControlKeys.includes(key)) {
                pressedKeys.delete(key);
                socket.emit('key_event', { key: key, type: 'up' });
                updateActiveKeysDisplay();
                 event.preventDefault();
            }
             if (pressedKeys.size === 0) {
                 keyboardStatusDiv.textContent = 'Ready for input.';
             }
        });

        // Handle window losing focus - stop the robot
        window.addEventListener('blur', () => {
             if (pressedKeys.size > 0) {
                 console.log("Window lost focus, sending stop commands for safety.");
                 // Simulate releasing all keys
                 pressedKeys.forEach(key => {
                      socket.emit('key_event', { key: key, type: 'up' });
                 });
                 pressedKeys.clear();
                 updateActiveKeysDisplay();
                 keyboardStatusDiv.textContent = 'Paused (window lost focus)';
             }
        });
         window.addEventListener('focus', () => {
             keyboardStatusDiv.textContent = 'Ready for input.';
         });


        function updateActiveKeysDisplay() {
             const keysText = pressedKeys.size > 0 ? Array.from(pressedKeys).join(', ').toUpperCase() : 'None';
             activeKeysDisplay.innerHTML = keysText.replace('S', '<strong style="color:red;">S</strong>'); // Highlight S key

        }

        // --- Speed Control UI ---
        function updateSpeedDisplay(sliderId) {
            const slider = document.getElementById(sliderId);
            const display = document.getElementById(sliderId + '_val');
            display.textContent = slider.value;
        }

        function sendSpeedSettings() {
            const speeds = {
                default_speed: parseInt(defaultSpeedSlider.value, 10),
                turn_speed: parseInt(turnSpeedSlider.value, 10)
            };
            console.log("Sending speed settings:", speeds);
            socket.emit('set_speeds', speeds);
            statusDiv.textContent = 'Speed settings sent.';
            statusDiv.className = ''; // Reset color
        }

         // --- Motor Test Function ---
         async function testMotor(index, speed = 80, duration = 500) {
             testStatusDiv.textContent = `Testing motor ${index}...`;
             testStatusDiv.className = ''; // Reset color
             console.log(`Sending test command for motor ${index}, speed ${speed}`);

             try {
                 // Using fetch for the separate HTTP endpoint
                 const response = await fetch('/test_motor', {
                     method: 'POST',
                     headers: { 'Content-Type': 'application/json' },
                     body: JSON.stringify({ index: index, speed: speed, duration: duration })
                 });

                 const result = await response.json();

                 if (response.ok && result.success) {
                     testStatusDiv.textContent = `Test Success: ${result.message}`;
                     testStatusDiv.className = 'success';
                     console.log('Motor test response:', result);
                 } else {
                     testStatusDiv.textContent = `Test Error: ${result.message || 'Unknown error'}`;
                     testStatusDiv.className = 'error';
                     console.error('Motor test error:', result);
                 }
             } catch (error) {
                 testStatusDiv.textContent = `Network Error during test: ${error}`;
                 testStatusDiv.className = 'error';
                 console.error('Fetch error during motor test:', error);
             }
         }

         // Initial display update
         document.addEventListener('DOMContentLoaded', () => {
              updateSpeedDisplay('default_speed');
              updateSpeedDisplay('turn_speed');
              // Set focus to body to ensure key events are captured immediately
              document.body.focus();
              // Add listener to the keyboard info box to focus body (helps user)
               const keyboardInfoBox = document.getElementById('keyboard-info');
               if (keyboardInfoBox) {
                    keyboardInfoBox.addEventListener('click', () => document.body.focus());
               }

         });

    </script>
</body>
</html>
"""

# --- Main Execution ---
if __name__ == '__main__':
    print("--- Mecanum Robot Keyboard Controller (SocketIO) ---")
    if connect_serial():
        print(f"Flask-SocketIO server starting on http://{FLASK_HOST}:{FLASK_PORT}")
        try:
            # Use socketio.run for Flask-SocketIO apps
            socketio.run(app, host=FLASK_HOST, port=FLASK_PORT, debug=False)
             # debug=True can be helpful but might cause issues with serial/threads
             # use_reloader=False is often recommended with hardware interaction
        except KeyboardInterrupt:
            print("Ctrl+C detected. Stopping motors and shutting down.")
        finally:
            # Ensure motors are stopped on exit
            if ser and ser.is_open:
                 try:
                    print("Sending final stop command...")
                    # Try sending stop multiple times to ensure it gets through
                    send_command("0,0,0,0")
                    time.sleep(0.1)
                    send_command("0,0,0,0")
                    ser.close()
                    print("Serial port closed.")
                 except Exception as e:
                    print(f"Error during cleanup: {e}")
            print("Server shut down.")

    else:
        print("\nExiting due to serial connection failure.")
        print("Please check:")
        print("1. Arduino is connected via USB.")
        print(f"2. The correct SERIAL_PORT is set (currently '{SERIAL_PORT}').")
        print("3. You have permissions (e.g., user in 'dialout' group on Linux).")
        print("4. Arduino code is uploaded and running (check Serial Monitor).")
