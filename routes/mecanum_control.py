# ~/jetbot-dashboard/routes/mecanum_control.py

import time
import json
import os
import serial
from flask import (Blueprint, render_template, request, jsonify, current_app, url_for)
# Import SocketIO components needed at the top level (emit might be needed globally)
from flask_socketio import emit

# --- Configuration ---
CONFIG_FILE = 'mecanum_config.json'
NUM_MOTORS = 4
PWM_MAX = 255

# --- Global Variables within Blueprint Context ---
ser = None
config = {}
last_sent_command = ""
default_serial_port = '/dev/ttyACM0'
default_baud_rate = 9600

# --- Blueprint Definition ---
mecanum_control_bp = Blueprint(
    'mecanum_control',
    __name__,
    template_folder='../templates',
    static_folder='../static'
)

# --- SocketIO Instance Holder ---
# This will be set by main.py using init_socketio
socketio = None
NAMESPACE = '/mecanum' # Define namespace constant

# --- Default Configuration ---
def get_default_config():
    # ... (keep the function as it was) ...
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
    # ... (keep the function as it was) ...
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
                # Use current_app.logger only if app context is available, might not be during initial load
                # print(f"INFO: Mecanum controller: Loaded config from {CONFIG_FILE}") # Use print for early logging
        except (json.JSONDecodeError, IOError, TypeError) as e:
            # print(f"ERROR: Mecanum controller: Error loading config '{CONFIG_FILE}': {e}. Using defaults.") # Use print
            config = defaults
            save_config() # Save defaults if loading failed
    else:
        # print(f"INFO: Mecanum controller: Config file '{CONFIG_FILE}' not found. Creating default.") # Use print
        config = defaults
        save_config()

def save_config():
    # ... (keep the function as it was) ...
    global config
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        if current_app: # Check if app context exists for logger
             current_app.logger.info(f"Mecanum controller: Configuration saved to {CONFIG_FILE}")
        else:
             print(f"INFO: Mecanum controller: Configuration saved to {CONFIG_FILE}")
        return True
    except IOError as e:
        if current_app:
            current_app.logger.error(f"Mecanum controller: Error saving config file '{CONFIG_FILE}': {e}")
        else:
            print(f"ERROR: Mecanum controller: Error saving config file '{CONFIG_FILE}': {e}")
        return False

# --- Serial Communication (Independent - CAUTION: Potential Conflicts) ---
# ... (Keep get_serial_status, init_serial, close_serial, send_serial_command as they were) ...
# Ensure logger calls check for current_app or use print for early stages if needed

def get_serial_status():
    """Returns the connection status of the mecanum controller's serial port."""
    return "Connected" if ser and ser.is_open else "Disconnected"

def init_serial():
    global ser, config
    if not config: load_config() # Ensure config is loaded

    port = config.get("serial_port", default_serial_port)
    baud = config.get("baud_rate", default_baud_rate)

    logger = current_app.logger if current_app else print # Use logger if available

    if ser and ser.is_open:
        if ser.port == port and ser.baudrate == baud:
             logger(f"INFO: Mecanum controller: Already connected to {port}")
             return True
        else:
             logger(f"INFO: Mecanum controller: Closing existing connection to {ser.port} to connect to {port}")
             ser.close()

    logger(f"WARNING: Mecanum controller: Attempting to connect to {port}. Ensure Serial Monitor is not using this port!")

    try:
        ser = serial.Serial(port, baud, timeout=1)
        time.sleep(2)
        if ser.in_waiting > 0:
            initial_message = ser.readline().decode('utf-8', errors='ignore').strip()
            logger(f"INFO: Mecanum controller Arduino ({port}): {initial_message}")
        else:
             logger(f"INFO: Mecanum controller: Successfully connected to {port}, no initial message.")
        if socketio: # Check if socketio object exists
             socketio.emit('mecanum_serial_status', {'status': get_serial_status(), 'port': port}, namespace=NAMESPACE)
        return True
    except serial.SerialException as e:
        logger(f"ERROR: Mecanum controller: Failed to connect to serial port {port}: {e}")
        ser = None
        if socketio:
             socketio.emit('mecanum_serial_status', {'status': 'Error', 'port': port, 'message': str(e)}, namespace=NAMESPACE)
        return False
    except Exception as e:
        logger(f"ERROR: Mecanum controller: Unexpected error during serial init on {port}: {e}")
        ser = None
        if socketio:
            socketio.emit('mecanum_serial_status', {'status': 'Error', 'port': port, 'message': str(e)}, namespace=NAMESPACE)
        return False

def close_serial():
    global ser, last_sent_command
    logger = current_app.logger if current_app else print
    if ser and ser.is_open:
        try:
            stop_command = "0,0,0,0"
            ser.write((stop_command + '\n').encode('utf-8'))
            time.sleep(0.1)
            ser.close()
            logger(f"INFO: Mecanum controller: Closed serial port {ser.port}")
        except Exception as e:
            logger(f"ERROR: Mecanum controller: Error sending stop or closing serial port: {e}")
    ser = None
    last_sent_command = ""
    if socketio:
        socketio.emit('mecanum_serial_status', {'status': 'Disconnected'}, namespace=NAMESPACE)


def send_serial_command(command_str):
    global ser, last_sent_command
    logger = current_app.logger if current_app else print
    if not ser or not ser.is_open:
        logger("WARNING: Mecanum controller: Serial port not connected. Cannot send command.")
        return False

    if command_str == last_sent_command:
        return True

    try:
        ser.write((command_str + '\n').encode('utf-8'))
        # Use debug level for frequent messages
        if current_app: current_app.logger.debug(f"Mecanum controller: Sent command: {command_str}")
        last_sent_command = command_str
        return True
    except serial.SerialException as e:
        logger(f"ERROR: Mecanum controller: Serial communication error: {e}")
        close_serial()
        return False
    except Exception as e:
        logger(f"ERROR: Mecanum controller: Unexpected error sending command: {e}")
        last_sent_command = ""
        return False


# --- Motor Speed Calculation ---
# ... (Keep scale_speed and calculate_motor_speeds as they were) ...
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
    logger = current_app.logger if current_app else print
    if not config:
        logger("ERROR: Mecanum controller: Config not loaded.")
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
        elif physical_index is not None:
             logger(f"WARNING: Invalid physical index '{physical_index}' mapped for '{logical_name}'. Ignoring.")
    return physical_speeds


# --- Mecanum Drive Kinematics ---
# ... (Keep get_move_speeds as it was) ...
def get_move_speeds(vx, vy, omega):
    fl = vx - vy - omega
    fr = vx + vy + omega
    rl = vx + vy - omega
    rr = vx - vy + omega
    max_abs_speed = max(abs(fl), abs(fr), abs(rl), abs(rr), 1)
    if max_abs_speed > PWM_MAX:
        scale_factor = PWM_MAX / max_abs_speed
        fl *= scale_factor; fr *= scale_factor; rl *= scale_factor; rr *= scale_factor
    return {"front_left": int(fl), "front_right": int(fr), "rear_left": int(rl), "rear_right": int(rr)}


# --- Flask Routes (Keep as they are) ---
@mecanum_control_bp.route('/mecanum-control')
def controller_page():
    load_config()
    serial_status = get_serial_status()
    return render_template(
        'mecanum_control.html',
        config=config,
        serial_status=serial_status,
        num_motors=NUM_MOTORS
    )

# ... (keep /get_config, /save_config, /reset_config routes as they were) ...
@mecanum_control_bp.route('/mecanum-control/get_config', methods=['GET'])
def get_config_json():
    # load_config() # Config should be loaded on page load/init
    serial_status = get_serial_status()
    return jsonify({"config": config, "serial_status": serial_status})

@mecanum_control_bp.route('/mecanum-control/save_config', methods=['POST'])
def save_config_route():
    global config
    logger = current_app.logger if current_app else print
    try:
        new_config_data = request.get_json()
        if not new_config_data: return jsonify({"success": False, "message": "No data received."}), 400

        # Basic validation could be added here
        config = new_config_data # Update global config directly

        port_changed = not (ser and ser.is_open and ser.port == config.get("serial_port"))
        baud_changed = not (ser and ser.is_open and ser.baudrate == int(config.get("baud_rate",0))) # cast baud to int

        if save_config():
             if port_changed or baud_changed:
                 logger(f"INFO: Mecanum Serial Port/Baud changed (Port: {port_changed}, Baud: {baud_changed}). Closing connection.")
                 close_serial() # Close old connection if settings changed
             return jsonify({"success": True, "message": "Configuration saved."})
        else:
            return jsonify({"success": False, "message": "Failed to write config file."}), 500
    except Exception as e:
        logger(f"ERROR: Mecanum controller: Error saving config: {e}")
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500

@mecanum_control_bp.route('/mecanum-control/reset_config', methods=['POST'])
def reset_config_route():
    global config
    logger = current_app.logger if current_app else print
    logger("INFO: Mecanum controller: Resetting config to defaults.")
    config = get_default_config()
    if save_config():
        close_serial() # Close any existing connection
        return jsonify({"success": True, "message": "Configuration reset to defaults.", "config": config})
    else:
        return jsonify({"success": False, "message": "Failed to write default config file."}), 500


# --- SocketIO Initialization and Handlers ---
def init_socketio(sio_instance):
    """ Function to receive the SocketIO instance and define handlers """
    global socketio # Allow modification of the global variable
    socketio = sio_instance
    logger = current_app.logger if current_app else print
    logger("INFO: Mecanum Control SocketIO initialized and handlers are being defined.")

    # --- DEFINE SocketIO Event Handlers INSIDE this function ---
    @socketio.on('connect', namespace=NAMESPACE)
    def handle_mecanum_connect():
        # request needs to be imported from flask if used here
        from flask import request
        logger = current_app.logger if current_app else print
        logger(f'INFO: Client {request.sid} connected to Mecanum namespace')
        load_config() # Ensure latest config when client connects
        emit('mecanum_config', {'config': config})
        emit('mecanum_serial_status', {'status': get_serial_status(), 'port': config.get("serial_port")})

    @socketio.on('disconnect', namespace=NAMESPACE)
    def handle_mecanum_disconnect():
        from flask import request
        logger = current_app.logger if current_app else print
        logger(f'INFO: Client {request.sid} disconnected from Mecanum namespace')

    @socketio.on('mecanum_connect_serial', namespace=NAMESPACE)
    def handle_connect_serial_request():
        from flask import request
        logger = current_app.logger if current_app else print
        logger(f"INFO: Client {request.sid} requested serial connect.")
        init_serial() # Attempt connection

    @socketio.on('mecanum_disconnect_serial', namespace=NAMESPACE)
    def handle_disconnect_serial_request():
        from flask import request
        logger = current_app.logger if current_app else print
        logger(f"INFO: Client {request.sid} requested serial disconnect.")
        close_serial() # Close connection

    @socketio.on('mecanum_control_command', namespace=NAMESPACE)
    def handle_control_command(data):
        logger = current_app.logger if current_app else print
        # 'emit' is imported at top level and should be available via the socketio instance
        if not ser or not ser.is_open:
            emit('mecanum_error', {'message': 'Serial port not connected. Cannot send command.'})
            return

        action = data.get('action')
        vx = data.get('vx', 0)
        vy = data.get('vy', 0)
        omega = data.get('omega', 0)
        logical_speeds = {}

        try:
            if action == 'stop': logical_speeds = get_move_speeds(0, 0, 0)
            elif action == 'move': logical_speeds = get_move_speeds(vx, vy, omega)
            else:
                logger(f"WARNING: Mecanum controller: Invalid action received: {action}")
                return

            physical_speeds = calculate_motor_speeds(logical_speeds)
            command_str = ",".join(map(str, physical_speeds))

            if not send_serial_command(command_str):
                 emit('mecanum_error', {'message': 'Failed to send command. Serial disconnected?'})

        except Exception as e:
            logger(f"ERROR: Mecanum controller: Error processing control command: {e}")
            emit('mecanum_error', {'message': f'Error processing command: {e}'})

# --- Blueprint Loading Hook ---
# This runs when the blueprint is registered, *before* init_socketio is called
# So logger might not be fully configured here yet. Use print for safety.
@mecanum_control_bp.record_once
def on_load(state):
    print("INFO: Loading Mecanum controller configuration during blueprint registration.")
    load_config()