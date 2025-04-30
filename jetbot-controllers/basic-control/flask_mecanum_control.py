import time
import serial
import serial.tools.list_ports
from flask import Flask, render_template_string, request, jsonify
from flask_cors import CORS
import math

# --- Configuration ---
# Try to auto-detect Arduino port, otherwise set manually
SERIAL_PORT = None
# SERIAL_PORT = '/dev/ttyACM0'  # Example for Linux
# SERIAL_PORT = '/dev/tty.usbmodem14201' # Example for Mac
# SERIAL_PORT = 'COM3'         # Example for Windows

BAUD_RATE = 9600
SERIAL_TIMEOUT = 0.1 # seconds
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 6002

# Movement parameters (tune these based on your robot's performance)
DEFAULT_SPEED = 150       # Default PWM value for movement (0-255)
TURN_SPEED = 100          # Default PWM value for turning
TEST_MOTOR_SPEED = 80     # Speed for individual motor tests
TEST_MOTOR_DURATION = 500 # ms for individual motor tests

# --- Global Variables ---
ser = None # Serial connection object

# --- Flask App Setup ---
app = Flask(__name__)
# Allow all origins for simplicity in this example
CORS(app, resources={r"/*": {"origins": "*"}})

# --- Serial Communication Functions ---

def find_arduino_port():
    """Attempts to find a USB serial port likely connected to an Arduino."""
    ports = serial.tools.list_ports.comports()
    arduino_ports = [p.device for p in ports if 'arduino' in p.description.lower() or \
                     'usb serial' in p.description.lower() or \
                     'ch340' in p.description.lower() or \
                     'cp210x' in p.description.lower()] # Add more keywords if needed
    if arduino_ports:
        print(f"Found potential Arduino ports: {arduino_ports}")
        return arduino_ports[0] # Return the first one found
    print("Warning: Could not auto-detect Arduino port.")
    return None

def connect_serial():
    """Establishes the serial connection."""
    global ser, SERIAL_PORT
    if ser and ser.is_open:
        print("Serial connection already open.")
        return True

    if SERIAL_PORT is None:
        SERIAL_PORT = find_arduino_port()
        if SERIAL_PORT is None:
            print("Error: Serial port not specified and auto-detection failed.")
            print("Please set SERIAL_PORT manually in the script.")
            return False

    try:
        print(f"Attempting to connect to {SERIAL_PORT} at {BAUD_RATE} baud...")
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=SERIAL_TIMEOUT)
        time.sleep(2) # Wait for Arduino to reset after connection
        # Read any startup messages from Arduino
        startup_lines = ser.readlines()
        for line in startup_lines:
             try:
                 print(f"Arduino startup: {line.decode('utf-8').strip()}")
             except UnicodeDecodeError:
                 print(f"Arduino startup (raw): {line}")
        print("Serial connection established.")
        return True
    except serial.SerialException as e:
        print(f"Error opening serial port {SERIAL_PORT}: {e}")
        ser = None
        return False
    except Exception as e:
        print(f"An unexpected error occurred during serial connection: {e}")
        ser = None
        return False


def send_command(command):
    """Sends a command string to the Arduino over serial."""
    global ser
    if ser is None or not ser.is_open:
        print("Serial port not connected. Attempting to reconnect...")
        if not connect_serial():
            print("Error: Cannot send command, serial connection failed.")
            return False

    try:
        command_bytes = (command + '\n').encode('utf-8')
        ser.write(command_bytes)
        print(f"Sent: {command}")

        # Optional: Read response (useful for debugging Arduino)
        # response = ser.readline().decode('utf-8').strip()
        # if response:
        #    print(f"Received: {response}")
        return True

    except serial.SerialException as e:
        print(f"Serial error during send: {e}")
        # Attempt to close and signal for reconnect on next command
        try:
            ser.close()
        except:
            pass
        ser = None
        return False
    except Exception as e:
        print(f"Error sending command '{command}': {e}")
        return False

def calculate_mecanum_speeds(vx, vy, omega):
    """
    Calculates individual wheel speeds for Mecanum drive.
    Assumes standard configuration:
      / \
     1   2  (Front)
      | |
     3   4  (Rear)
      \ /
    vx: forward/backward speed (+ forward)
    vy: strafing speed (+ left)
    omega: rotational speed (+ counter-clockwise)
    Returns: [fl_speed, fr_speed, rl_speed, rr_speed] clamped to -255 to 255
    """
    # Basic kinematic model (adjust signs based on your motor directions/wiring)
    # These signs assume positive PWM = forward wheel rotation, and standard wheel orientation
    fl = vx - vy - omega
    fr = vx + vy + omega
    rl = vx + vy - omega
    rr = vx - vy + omega

    # Find the maximum absolute speed magnitude
    max_mag = max(abs(fl), abs(fr), abs(rl), abs(rr))

    # Scale speeds if any exceed PWM_MAX, preserving ratios
    scale_factor = 1.0
    if max_mag > 255:
        scale_factor = 255.0 / max_mag

    fl = int(fl * scale_factor)
    fr = int(fr * scale_factor)
    rl = int(rl * scale_factor)
    rr = int(rr * scale_factor)

    # Clamp to ensure they are within [-255, 255] after potential rounding
    fl = max(-255, min(255, fl))
    fr = max(-255, min(255, fr))
    rl = max(-255, min(255, rl))
    rr = max(-255, min(255, rr))

    # IMPORTANT: The order returned here MUST match the Arduino's motor index order
    # (FL=0, FR=1, RL=2, RR=3 in the Arduino code)
    return [fl, fr, rl, rr]

# --- Movement Logic ---

def move_forward(speed=DEFAULT_SPEED, duration=1.0):
    speeds = calculate_mecanum_speeds(speed, 0, 0)
    cmd = f"{speeds[0]},{speeds[1]},{speeds[2]},{speeds[3]}"
    if send_command(cmd):
        time.sleep(duration)
        stop_motors()

def move_backward(speed=DEFAULT_SPEED, duration=1.0):
    speeds = calculate_mecanum_speeds(-speed, 0, 0)
    cmd = f"{speeds[0]},{speeds[1]},{speeds[2]},{speeds[3]}"
    if send_command(cmd):
        time.sleep(duration)
        stop_motors()

def strafe_left(speed=DEFAULT_SPEED, duration=1.0):
    speeds = calculate_mecanum_speeds(0, speed, 0)
    cmd = f"{speeds[0]},{speeds[1]},{speeds[2]},{speeds[3]}"
    if send_command(cmd):
        time.sleep(duration)
        stop_motors()

def strafe_right(speed=DEFAULT_SPEED, duration=1.0):
    speeds = calculate_mecanum_speeds(0, -speed, 0)
    cmd = f"{speeds[0]},{speeds[1]},{speeds[2]},{speeds[3]}"
    if send_command(cmd):
        time.sleep(duration)
        stop_motors()

def rotate_cw(speed=TURN_SPEED, duration=1.0):
    speeds = calculate_mecanum_speeds(0, 0, -speed) # Negative omega for CW
    cmd = f"{speeds[0]},{speeds[1]},{speeds[2]},{speeds[3]}"
    if send_command(cmd):
        time.sleep(duration)
        stop_motors()

def rotate_ccw(speed=TURN_SPEED, duration=1.0):
    speeds = calculate_mecanum_speeds(0, 0, speed) # Positive omega for CCW
    cmd = f"{speeds[0]},{speeds[1]},{speeds[2]},{speeds[3]}"
    if send_command(cmd):
        time.sleep(duration)
        stop_motors()

def stop_motors():
    send_command("0,0,0,0")
    print("Stopped motors.")

def run_square(side_length_units, speed=DEFAULT_SPEED):
    """
    Moves the robot in a square.
    'side_length_units' is abstract; map it to time based on speed.
    This is an approximation without odometry.
    """
    # Very rough estimate: time = units / (speed_factor * speed)
    # You MUST tune 'time_per_unit' based on your robot's physical speed.
    time_per_unit = 0.02 # Example: 20ms per unit at DEFAULT_SPEED
    duration = max(0.1, side_length_units * time_per_unit * (DEFAULT_SPEED / speed)) # Ensure minimum duration
    print(f"Executing square: {side_length_units} units -> {duration:.2f}s per side at speed {speed}")

    # 1. Move Forward
    print("Moving forward...")
    speeds = calculate_mecanum_speeds(speed, 0, 0)
    cmd = f"{speeds[0]},{speeds[1]},{speeds[2]},{speeds[3]}"
    if not send_command(cmd): return False
    time.sleep(duration)

    # 2. Strafe Right
    print("Strafing right...")
    speeds = calculate_mecanum_speeds(0, -speed, 0) # Strafe right is negative vy
    cmd = f"{speeds[0]},{speeds[1]},{speeds[2]},{speeds[3]}"
    if not send_command(cmd): return False
    time.sleep(duration)

    # 3. Move Backward
    print("Moving backward...")
    speeds = calculate_mecanum_speeds(-speed, 0, 0)
    cmd = f"{speeds[0]},{speeds[1]},{speeds[2]},{speeds[3]}"
    if not send_command(cmd): return False
    time.sleep(duration)

    # 4. Strafe Left
    print("Strafing left...")
    speeds = calculate_mecanum_speeds(0, speed, 0) # Strafe left is positive vy
    cmd = f"{speeds[0]},{speeds[1]},{speeds[2]},{speeds[3]}"
    if not send_command(cmd): return False
    time.sleep(duration)

    stop_motors()
    print("Square finished.")
    return True

def run_circle(radius_units, speed=DEFAULT_SPEED, turn_bias=0.8):
    """
    Attempts to move the robot in a circle using combined forward and rotation.
    'radius_units' and 'speed' determine duration. Highly approximate.
    'turn_bias' adjusts rotation speed relative to forward speed. Tune this!
    """
    # Approximation: Circumference = 2 * pi * r
    # Time = Circumference / (speed_factor * speed)
    # Rotation speed needs to be constant to complete 360 degrees in that time.
    time_per_unit_circumference = 0.01 # Tune this! Time per unit of circumference length.
    circumference = 2 * math.pi * radius_units
    duration = max(0.5, circumference * time_per_unit_circumference * (DEFAULT_SPEED / speed))

    # Constant forward speed and constant angular velocity (omega)
    # Omega needed = 2*pi / duration
    # Relationship: omega_pwm = scaling_factor * omega_rad_s
    # Let's simplify: Set a forward speed and derive a turn speed.
    # Higher turn_bias means sharper turn (smaller circle for given fwd speed).
    fwd_speed = speed
    # Turn speed should be proportional to fwd_speed / radius (roughly)
    # Let's use turn_bias as a direct scaler for simplicity here.
    rot_speed = int(turn_bias * TURN_SPEED * (DEFAULT_SPEED / speed))
    # Ensure rotation speed isn't excessive
    rot_speed = max(30, min(255, rot_speed))

    print(f"Executing circle: radius {radius_units} units -> approx {duration:.2f}s duration")
    print(f"Using Fwd Speed: {fwd_speed}, Rot Speed: {rot_speed} (CCW)")

    speeds = calculate_mecanum_speeds(fwd_speed, 0, rot_speed) # Combine forward and CCW rotation
    cmd = f"{speeds[0]},{speeds[1]},{speeds[2]},{speeds[3]}"
    if not send_command(cmd): return False

    time.sleep(duration)
    stop_motors()
    print("Circle finished.")
    return True


def test_motor(motor_index, speed=TEST_MOTOR_SPEED, duration=TEST_MOTOR_DURATION):
    """Sends a test command to the Arduino for a specific motor."""
    # Motor index mapping assumed here matches the Flask UI and Arduino Enum
    # 0: FL, 1: FR, 2: RL, 3: RR
    if not (0 <= motor_index <= 3):
        print(f"Error: Invalid motor index {motor_index}")
        return False

    cmd = f"TEST,{motor_index},{speed},{duration}"
    return send_command(cmd)

# --- Flask Routes ---

# Simple HTML Frontend
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Mecanum Robot Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: sans-serif; padding: 20px; }
        .control-section { margin-bottom: 25px; padding: 15px; border: 1px solid #ccc; border-radius: 5px; }
        .control-section h2 { margin-top: 0; }
        button { padding: 10px 15px; margin: 5px; font-size: 1em; cursor: pointer; }
        input[type=number] { padding: 8px; margin: 5px; width: 80px; }
        .motor-test button { min-width: 100px; }
        #status { margin-top: 15px; font-weight: bold; color: #333; }
        .error { color: red; }
        .success { color: green; }
    </style>
</head>
<body>
    <h1>Mecanum Robot Control</h1>

    <div id="status">Connecting to backend...</div>

    <div class="control-section">
        <h2>Motor Mapping Test</h2>
        <p>Click to run each motor briefly (check rotation direction too!). Map the physical motor to the label.</p>
        <p>Assumed mapping (Index): FL(0), FR(1), RL(2), RR(3)</p>
        <div class="motor-test">
            <button onclick="sendCommand('test', { index: 0 })">Test FL (0)</button>
            <button onclick="sendCommand('test', { index: 1 })">Test FR (1)</button> <br>
            <button onclick="sendCommand('test', { index: 2 })">Test RL (2)</button>
            <button onclick="sendCommand('test', { index: 3 })">Test RR (3)</button> <br>
             <button onclick="sendCommand('test', { index: 0, speed: -{{ default_test_speed }} })">Test FL (Rev)</button>
             <button onclick="sendCommand('test', { index: 1, speed: -{{ default_test_speed }} })">Test FR (Rev)</button> <br>
             <button onclick="sendCommand('test', { index: 2, speed: -{{ default_test_speed }} })">Test RL (Rev)</button>
             <button onclick="sendCommand('test', { index: 3, speed: -{{ default_test_speed }} })">Test RR (Rev)</button>
        </div>
         <p><small>Default Test Speed: {{ default_test_speed }}, Duration: {{ default_test_duration }}ms</small></p>
    </div>

    <div class="control-section">
        <h2>Movement Commands</h2>
        <div>
             <button onclick="sendCommand('stop')">STOP MOTORS</button>
        </div>
        <hr>
        <div>
            <label for="square-size">Square Side (units):</label>
            <input type="number" id="square-size" value="10" min="1">
            <button onclick="sendCommand('square', { size: document.getElementById('square-size').value })">Run Square</button>
        </div>
        <hr>
        <div>
            <label for="circle-radius">Circle Radius (units):</label>
            <input type="number" id="circle-radius" value="5" min="1">
             <button onclick="sendCommand('circle', { radius: document.getElementById('circle-radius').value })">Run Circle (CCW)</button>
        </div>
         <hr>
         <div>
             <label for="move-speed">Move Speed (0-255):</label>
             <input type="number" id="move-speed" value="{{ default_speed }}" min="0" max="255">
              <button onclick="sendCommand('move', { dir: 'fwd', speed: document.getElementById('move-speed').value })">Move Fwd (1s)</button>
               <button onclick="sendCommand('move', { dir: 'bwd', speed: document.getElementById('move-speed').value })">Move Bwd (1s)</button>
               <button onclick="sendCommand('move', { dir: 'left', speed: document.getElementById('move-speed').value })">Strafe Left (1s)</button>
               <button onclick="sendCommand('move', { dir: 'right', speed: document.getElementById('move-speed').value })">Strafe Right (1s)</button>
               <br>
               <button onclick="sendCommand('move', { dir: 'rot_ccw', speed: document.getElementById('move-speed').value })">Rotate CCW (1s)</button>
               <button onclick="sendCommand('move', { dir: 'rot_cw', speed: document.getElementById('move-speed').value })">Rotate CW (1s)</button>


         </div>
    </div>


    <script>
        const statusDiv = document.getElementById('status');

        async function sendCommand(type, params = {}) {
            statusDiv.textContent = 'Sending command...';
            statusDiv.className = ''; // Reset color

            // Include default test parameters if not provided
            if (type === 'test') {
                params.speed = params.speed === undefined ? {{ default_test_speed }} : params.speed;
                params.duration = params.duration === undefined ? {{ default_test_duration }} : params.duration;
            }

            console.log('Sending:', type, params);

            try {
                const response = await fetch('/control', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ command: type, params: params }),
                });

                const result = await response.json();

                if (response.ok && result.success) {
                    statusDiv.textContent = `Success: ${result.message}`;
                    statusDiv.className = 'success';
                    console.log('Server response:', result);
                } else {
                    statusDiv.textContent = `Error: ${result.message || 'Unknown error'}`;
                    statusDiv.className = 'error';
                     console.error('Server error:', result);
                }
            } catch (error) {
                statusDiv.textContent = `Network Error: Could not reach backend. Is it running? ${error}`;
                statusDiv.className = 'error';
                console.error('Fetch error:', error);
            }
        }

        // Initial check to see if backend is running
        document.addEventListener('DOMContentLoaded', () => {
             fetch('/control', { method: 'GET' }) // Simple GET request to check connectivity
                .then(response => {
                    if (response.ok) {
                        statusDiv.textContent = 'Connected to backend. Ready.';
                        statusDiv.className = 'success';
                    } else {
                       throw new Error(`HTTP error! status: ${response.status}`);
                    }
                 })
                .catch(error => {
                    statusDiv.textContent = `Error: Cannot connect to backend. ${error}`;
                    statusDiv.className = 'error';
                });
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Serves the main HTML control page."""
    return render_template_string(HTML_TEMPLATE,
                                 default_test_speed=TEST_MOTOR_SPEED,
                                 default_test_duration=TEST_MOTOR_DURATION,
                                 default_speed=DEFAULT_SPEED)

@app.route('/control', methods=['GET', 'POST'])
def control_robot():
    """Handles commands from the web interface."""
    if request.method == 'GET':
        # Simple check for frontend connectivity test
        return jsonify(success=True, message="Backend reachable")

    if request.method == 'POST':
        data = request.get_json()
        if not data:
            return jsonify(success=False, message="Error: Invalid request data"), 400

        command_type = data.get('command')
        params = data.get('params', {})
        print(f"Received control request: {command_type}, Params: {params}")

        success = False
        message = "Command not recognized."

        try:
            if command_type == 'test':
                idx = int(params.get('index', -1))
                spd = int(params.get('speed', TEST_MOTOR_SPEED))
                dur = int(params.get('duration', TEST_MOTOR_DURATION))
                if 0 <= idx <= 3:
                    success = test_motor(idx, speed=spd, duration=dur)
                    message = f"Test command {'sent' if success else 'failed'} for motor {idx}."
                else:
                    message = "Invalid motor index specified."

            elif command_type == 'square':
                size = int(params.get('size', 10))
                if size > 0:
                    success = run_square(size)
                    message = f"Square command {'initiated' if success else 'failed'}."
                else:
                    message = "Invalid square size."

            elif command_type == 'circle':
                radius = int(params.get('radius', 5))
                if radius > 0:
                    success = run_circle(radius)
                    message = f"Circle command {'initiated' if success else 'failed'}."
                else:
                    message = "Invalid circle radius."

            elif command_type == 'stop':
                success = stop_motors()
                message = f"Stop command {'sent' if success else 'failed'}."

            elif command_type == 'move': # Basic directional moves for 1 sec
                 direction = params.get('dir', 'stop')
                 speed = int(params.get('speed', DEFAULT_SPEED))
                 speed = max(0, min(255, speed)) # Clamp speed
                 duration = 1.0 # Fixed duration for simple moves

                 if direction == 'fwd':
                     success = move_forward(speed, duration)
                 elif direction == 'bwd':
                     success = move_backward(speed, duration)
                 elif direction == 'left':
                     success = strafe_left(speed, duration)
                 elif direction == 'right':
                      success = strafe_right(speed, duration)
                 elif direction == 'rot_cw':
                      success = rotate_cw(speed, duration)
                 elif direction == 'rot_ccw':
                      success = rotate_ccw(speed, duration)
                 else:
                      success = stop_motors()

                 message = f"Move '{direction}' command {'sent' if success else 'failed'}."


            else:
                 message = f"Unknown command type: {command_type}"


        except ValueError as e:
             success = False
             message = f"Error: Invalid parameter value. {e}"
        except Exception as e:
             success = False
             message = f"An unexpected error occurred: {e}"
             print(f"Error handling command {command_type}: {e}") # Log detailed error server-side


        return jsonify(success=success, message=message)


# --- Main Execution ---
if __name__ == '__main__':
    print("--- Mecanum Robot Flask Controller ---")
    if connect_serial():
        print(f"Flask server starting on http://{FLASK_HOST}:{FLASK_PORT}")
        # Use threaded=True if your movement functions block for too long,
        # but be aware of potential serial access conflicts if not handled carefully.
        # For simple timed movements like this, threaded=False is often safer.
        app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, threaded=False)
    else:
        print("\nExiting due to serial connection failure.")
        print("Please check:")
        print("1. Arduino is connected via USB.")
        print("2. The correct SERIAL_PORT is set in the script (or auto-detection works).")
        print("3. You have the necessary permissions to access the serial port.")
        print("4. The Arduino code is uploaded and running (check Serial Monitor in Arduino IDE).")

    # Cleanup serial connection on exit
    if ser and ser.is_open:
        try:
            stop_motors() # Try to stop motors before closing
            ser.close()
            print("Serial port closed.")
        except Exception as e:
            print(f"Error closing serial port: {e}")
