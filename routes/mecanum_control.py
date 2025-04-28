# ~/jetbot-dashboard/routes/mecanum_control.py

import time
import json
import os
import serial
from flask import (Blueprint, render_template, request, jsonify, current_app, url_for)
from flask_socketio import emit, disconnect # Import SocketIO components

# --- Configuration ---
# Store config in the project root, separate from main config
CONFIG_FILE = 'mecanum_config.json'
NUM_MOTORS = 4
PWM_MAX = 255

# --- Global Variables within Blueprint Context ---
# We manage serial connection independently for now. Be careful!
ser = None
config = {}
last_sent_command = ""
default_serial_port = '/dev/ttyACM0' # Default if not in config
default_baud_rate = 9600         # Default if not in config

# --- Blueprint Definition ---
# Point template/static folders back to the main app's locations
mecanum_control_bp = Blueprint(
    'mecanum_control',
    __name__,
    template_folder='../templates',
    static_folder='../static'
)

# --- SocketIO Instance ---
# This will be set by main.py using init_socketio
socketio = None

def init_socketio(sio_instance):
    """ Function to receive the SocketIO instance from main.py """
    global socketio
    socketio = sio_instance
    current_app.logger.info("Mecanum Control SocketIO initialized.")
    # Add specific SocketIO event handlers here if needed globally for this BP
    # Example: socketio.on('connect', namespace='/mecanum')

# --- Default Configuration ---
def get_default_config():
    # Reads defaults from main app config if available, otherwise uses hardcoded
    try:
        import config as main_config
        robot_port = getattr(main_config, 'ROBOT_SERIAL_PORT', default_serial_port)
        robot_baud = getattr(main_config, 'ROBOT_BAUD_RATE', default_baud_rate)
    except ImportError:
        robot_port = default_serial_port
        robot_baud = default_baud_rate

    return {
        "serial_port": robot_port,
        "baud_rate": robot_baud,
        "mapping": {
            "front_left": None, "front_right": None, "rear_left": None, "rear_right": None
        },
        "calibration": {
            "front_left": 1.0, "front_right": 1.0, "rear_left": 1.0, "rear_right": 1.0
        },
        "scaling": {
            "deadzone_min": 100, "deadzone_max": 255
        }
    }

# --- Configuration Handling (Adapted for Blueprint) ---
def load_config():
    global config
    defaults = get_default_config()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_config = json.load(f)
                config = {**defaults, **loaded_config}
                for key in defaults:
                    if isinstance(defaults[key], dict):
                        config[key] = {**defaults[key], **config.get(key, {})}
                current_app.logger.info(f"Mecanum controller: Loaded config from {CONFIG_FILE}")
        except (json.JSONDecodeError, IOError, TypeError) as e:
            current_app.logger.error(f"Mecanum controller: Error loading config '{CONFIG_FILE}': {e}. Using defaults.")
            config = defaults
            save_config()
    else:
        current_app.logger.info(f"Mecanum controller: Config file '{CONFIG_FILE}' not found. Creating default.")
        config = defaults
        save_config()

def save_config():
    global config
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        current_app.logger.info(f"Mecanum controller: Configuration saved to {CONFIG_FILE}")
        return True
    except IOError as e:
        current_app.logger.error(f"Mecanum controller: Error saving config file '{CONFIG_FILE}': {e}")
        return False

# --- Serial Communication (Independent - CAUTION: Potential Conflicts) ---
def get_serial_status():
    """Returns the connection status of the mecanum controller's serial port."""
    return "Connected" if ser and ser.is_open else "Disconnected"

def init_serial():
    global ser, config
    if not config: load_config() # Ensure config is loaded

    port = config.get("serial_port", default_serial_port)
    baud = config.get("baud_rate", default_baud_rate)

    if ser and ser.is_open:
        if ser.port == port and ser.baudrate == baud:
             current_app.logger.info(f"Mecanum controller: Already connected to {port}")
             return True # Already connected to the correct port
        else:
             current_app.logger.info(f"Mecanum controller: Closing existing connection to {ser.port} to connect to {port}")
             ser.close() # Close if port/baud changed

    # *** CRITICAL WARNING ***
    # Check if the port is potentially managed by serial_monitor.py - This is hard to do perfectly without shared state.
    # For now, we just try to connect, assuming the user manages conflicts.
    current_app.logger.warning(f"Mecanum controller: Attempting to connect to {port}. Ensure Serial Monitor is not using this port!")

    try:
        ser = serial.Serial(port, baud, timeout=1)
        time.sleep(2) # Wait for Arduino
        if ser.in_waiting > 0:
            initial_message = ser.readline().decode('utf-8', errors='ignore').strip()
            current_app.logger.info(f"Mecanum controller Arduino ({port}): {initial_message}")
        else:
             current_app.logger.info(f"Mecanum controller: Successfully connected to {port}, no initial message.")
        # Emit status update to clients on this page
        if socketio:
             socketio.emit('mecanum_serial_status', {'status': get_serial_status(), 'port': port}, namespace='/mecanum')
        return True
    except serial.SerialException as e:
        current_app.logger.error(f"Mecanum controller: Failed to connect to serial port {port}: {e}")
        ser = None
        if socketio:
             socketio.emit('mecanum_serial_status', {'status': 'Error', 'port': port, 'message': str(e)}, namespace='/mecanum')
        return False
    except Exception as e:
        current_app.logger.error(f"Mecanum controller: Unexpected error during serial init on {port}: {e}")
        ser = None
        if socketio:
            socketio.emit('mecanum_serial_status', {'status': 'Error', 'port': port, 'message': str(e)}, namespace='/mecanum')
        return False

def close_serial():
    """ Closes the serial port if open """
    global ser, last_sent_command
    if ser and ser.is_open:
        try:
            # Send a final stop command before closing?
            stop_command = "0,0,0,0"
            ser.write((stop_command + '\n').encode('utf-8'))
            time.sleep(0.1)
            ser.close()
            current_app.logger.info(f"Mecanum controller: Closed serial port {ser.port}")
        except Exception as e:
            current_app.logger.error(f"Mecanum controller: Error sending stop or closing serial port: {e}")
    ser = None
    last_sent_command = ""
    if socketio:
        socketio.emit('mecanum_serial_status', {'status': 'Disconnected'}, namespace='/mecanum')


def send_serial_command(command_str):
    global ser, last_sent_command
    if not ser or not ser.is_open:
        current_app.logger.warning("Mecanum controller: Serial port not connected. Cannot send command.")
        # Attempt reconnect automatically? Risky if port is busy.
        # if not init_serial(): return False # Try to reconnect
        return False

    # Avoid spamming identical commands
    if command_str == last_sent_command:
        return True

    try:
        ser.write((command_str + '\n').encode('utf-8'))
        current_app.logger.debug(f"Mecanum controller: Sent command: {command_str}")
        last_sent_command = command_str
        return True
    except serial.SerialException as e:
        current_app.logger.error(f"Mecanum controller: Serial communication error: {e}")
        close_serial() # Close on error
        return False
    except Exception as e:
        current_app.logger.error(f"Mecanum controller: Unexpected error sending command: {e}")
        last_sent_command = ""
        return False

# --- Motor Speed Calculation (Keep as is from previous answer) ---
def scale_speed(speed, deadzone_min, deadzone_max):
    if speed == 0: return 0
    sign = 1 if speed > 0 else -1
    abs_speed = abs(speed)
    if abs_speed < 1: return 0
    scaled = int(deadzone_min + (abs_speed - 1) * (deadzone_max - deadzone_min) / (PWM_MAX - 1))
    scaled = min(scaled, PWM_MAX)
    return sign * scaled

def calculate_motor_speeds(logical_speeds):
    global config
    physical_speeds = [0] * NUM_MOTORS
    if not config:
        current_app.logger.error("Mecanum controller: Config not loaded.")
        return physical_speeds

    mapping = config.get('mapping', {})
    calibration = config.get('calibration', {})
    scaling_config = config.get('scaling', {})
    deadzone_min = scaling_config.get('deadzone_min', 0)
    deadzone_max = scaling_config.get('deadzone_max', PWM_MAX)

    for logical_name, input_speed in logical_speeds.items():
        physical_index = mapping.get(logical_name)
        if physical_index is not None and 0 <= physical_index < NUM_MOTORS:
            calibrated_speed = input_speed * calibration.get(logical_name, 1.0)
            scaled_speed = scale_speed(int(calibrated_speed), deadzone_min, deadzone_max)
            final_speed = max(-PWM_MAX, min(PWM_MAX, scaled_speed))
            physical_speeds[physical_index] = final_speed
        # Add logging for unmapped or invalid indices if needed
    return physical_speeds

# --- Mecanum Drive Kinematics (Keep as is) ---
def get_move_speeds(vx, vy, omega):
    fl = vx - vy - omega
    fr = vx + vy + omega
    rl = vx + vy - omega
    rr = vx - vy + omega
    max_abs_speed = max(abs(fl), abs(fr), abs(rl), abs(rr), 1) # Avoid division by zero
    if max_abs_speed > PWM_MAX:
        scale_factor = PWM_MAX / max_abs_speed
        fl *= scale_factor; fr *= scale_factor; rl *= scale_factor; rr *= scale_factor
    return {"front_left": int(fl), "front_right": int(fr), "rear_left": int(rl), "rear_right": int(rr)}

# --- Flask Routes (Main Page & Config API) ---
@mecanum_control_bp.route('/mecanum-control')
def controller_page():
    load_config() # Load fresh config on page load
    serial_status = get_serial_status()
    # Pass necessary data to the template
    return render_template(
        'mecanum_control.html',
        config=config,
        serial_status=serial_status,
        num_motors=NUM_MOTORS
    )

@mecanum_control_bp.route('/mecanum-control/get_config', methods=['GET'])
def get_config_json():
    # load_config() # Ensure latest config
    serial_status = get_serial_status()
    return jsonify({"config": config, "serial_status": serial_status})

@mecanum_control_bp.route('/mecanum-control/save_config', methods=['POST'])
def save_config_route():
    global config # Need to modify global config
    try:
        new_config_data = request.get_json()
        if not new_config_data: return jsonify({"success": False, "message": "No data received."}), 400
        # Basic validation could be added here
        config = new_config_data # Update global config directly
        if save_config():
             # If serial port/baud changed, attempt reconnect on next command/page load
             # Or force reconnect here? Let's try lazy connection for now.
             # Check if connection needs reset
             port_changed = not (ser and ser.is_open and ser.port == config.get("serial_port"))
             baud_changed = not (ser and ser.is_open and ser.baudrate == config.get("baud_rate"))
             if port_changed or baud_changed:
                 close_serial() # Close old connection if settings changed
                 # Don't auto-connect here, let user/page load trigger it
             return jsonify({"success": True, "message": "Configuration saved."})
        else:
            return jsonify({"success": False, "message": "Failed to write config file."}), 500
    except Exception as e:
        current_app.logger.error(f"Mecanum controller: Error saving config: {e}")
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500

@mecanum_control_bp.route('/mecanum-control/reset_config', methods=['POST'])
def reset_config_route():
    global config
    current_app.logger.info("Mecanum controller: Resetting config to defaults.")
    config = get_default_config()
    if save_config():
        close_serial() # Close any existing connection
        return jsonify({"success": True, "message": "Configuration reset to defaults.", "config": config})
    else:
        return jsonify({"success": False, "message": "Failed to write default config file."}), 500

# --- SocketIO Event Handlers for Control ---
# Define a namespace for clarity
NAMESPACE = '/mecanum'

@mecanum_control_bp.record_once
def on_load(state):
    # Load config when blueprint is registered
    load_config()
    # Optionally try initial serial connection? Better to do it on page load/user action.
    # init_serial()

# Called when a client connects to this namespace
@socketio.on('connect', namespace=NAMESPACE)
def handle_mecanum_connect():
    current_app.logger.info(f'Client {request.sid} connected to Mecanum namespace')
    # Send current config and status on connect
    load_config() # Ensure latest config
    emit('mecanum_config', {'config': config})
    emit('mecanum_serial_status', {'status': get_serial_status(), 'port': config.get("serial_port")})

@socketio.on('disconnect', namespace=NAMESPACE)
def handle_mecanum_disconnect():
    current_app.logger.info(f'Client {request.sid} disconnected from Mecanum namespace')
    # Optional: If this is the *last* client, maybe stop the robot/close serial?
    # Be careful with this logic if multiple tabs/users are possible.
    # For simplicity, we won't auto-close serial on disconnect for now.

@socketio.on('mecanum_connect_serial', namespace=NAMESPACE)
def handle_connect_serial_request():
    """ Client requests to connect serial """
    current_app.logger.info(f"Client {request.sid} requested serial connect.")
    init_serial() # Attempt connection
    # Status is emitted inside init_serial

@socketio.on('mecanum_disconnect_serial', namespace=NAMESPACE)
def handle_disconnect_serial_request():
    """ Client requests to disconnect serial """
    current_app.logger.info(f"Client {request.sid} requested serial disconnect.")
    close_serial() # Close connection
    # Status is emitted inside close_serial

@socketio.on('mecanum_control_command', namespace=NAMESPACE)
def handle_control_command(data):
    """ Handles incoming drive commands from the client """
    if not ser or not ser.is_open:
        # Try to connect if not connected? Or just emit error?
        emit('mecanum_error', {'message': 'Serial port not connected. Cannot send command.'})
        # if not init_serial(): # Try to auto-connect
        #      return
        return # Fail if not connected

    action = data.get('action')
    vx = data.get('vx', 0)
    vy = data.get('vy', 0)
    omega = data.get('omega', 0)

    logical_speeds = {}

    try:
        if action == 'stop':
            logical_speeds = get_move_speeds(0, 0, 0)
        elif action == 'move':
            logical_speeds = get_move_speeds(vx, vy, omega)
        else: # Simple directional commands (optional, can be removed if only 'move' is used)
            speed = PWM_MAX
            if action == 'forward': logical_speeds = get_move_speeds(speed, 0, 0)
            elif action == 'backward': logical_speeds = get_move_speeds(-speed, 0, 0)
            # ... add other simple actions if needed ...
            else:
                current_app.logger.warning(f"Mecanum controller: Invalid action received: {action}")
                return # Ignore invalid actions

        physical_speeds = calculate_motor_speeds(logical_speeds)
        command_str = ",".join(map(str, physical_speeds))

        if not send_serial_command(command_str):
             # Error sending (likely disconnected), status updated in send_serial_command
             emit('mecanum_error', {'message': 'Failed to send command. Serial disconnected?'})
             # Maybe emit disconnect status? close_serial already does this.

    except Exception as e:
        current_app.logger.error(f"Mecanum controller: Error processing control command: {e}")
        emit('mecanum_error', {'message': f'Error processing command: {e}'})