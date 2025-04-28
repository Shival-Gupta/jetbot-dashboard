# ~/jetbot-dashboard/routes/mecanum_control.py

import time
import json
import os
import serial
from flask import (Blueprint, render_template, request, jsonify, current_app, url_for)
# Import SocketIO components needed at the top level
from flask_socketio import emit
import logging

# --- Configuration ---
CONFIG_FILE = 'mecanum_config.json' # Expect this in the project root
NUM_MOTORS = 4
PWM_MAX = 255

# --- Global Variables within Blueprint Context ---
ser = None # Holds the serial connection object
config = {} # Holds the loaded configuration
last_sent_command = "" # Track last command sent to Arduino
default_serial_port = '/dev/ttyACM0' # Default if not in config
default_baud_rate = 9600         # Default if not in config

# --- Blueprint Definition ---
mecanum_control_bp = Blueprint(
    'mecanum_control',
    __name__,
    template_folder='../templates', # Point to project's templates folder
    static_folder='../static'       # Point to project's static folder
)

# --- SocketIO Instance Holder ---
socketio = None # Will be set by main.py using init_socketio
NAMESPACE = '/mecanum' # Define a specific namespace for this controller

# --- Logging Helper ---
# Safely get logger or fallback to print if app context not available
def get_logger():
    try:
        # Try to get logger from current_app context
        return current_app.logger
    except RuntimeError:
        # Fallback to print if outside app context (e.g., during initial load)
        return print

# --- Default Configuration ---
def get_default_config():
    logger = get_logger()
    try:
        import config as main_config
        robot_port = getattr(main_config, 'ROBOT_SERIAL_PORT', default_serial_port)
        robot_baud = getattr(main_config, 'ROBOT_BAUD_RATE', default_baud_rate)
        logger(f"INFO: Mecanum defaults using main_config: Port={robot_port}, Baud={robot_baud}")
    except ImportError:
        robot_port = default_serial_port
        robot_baud = default_baud_rate
        logger(f"INFO: Mecanum defaults using hardcoded: Port={robot_port}, Baud={robot_baud}")

    return {
        "serial_port": robot_port,
        "baud_rate": int(robot_baud), # Ensure baud is integer
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

# --- Configuration Handling ---
def load_config():
    global config
    logger = get_logger()
    defaults = get_default_config()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_config = json.load(f)
                # Merge loaded config with defaults, ensuring sub-dictionaries are merged
                config = {**defaults, **loaded_config}
                for key in defaults:
                    if isinstance(defaults[key], dict):
                        config[key] = {**defaults[key], **config.get(key, {})}
                # Ensure baud rate is integer after loading
                config["baud_rate"] = int(config.get("baud_rate", defaults["baud_rate"]))
                logger(f"INFO: Mecanum controller: Loaded config from {CONFIG_FILE}")
        except (json.JSONDecodeError, IOError, TypeError, ValueError) as e:
            logger(f"ERROR: Mecanum controller: Error loading config '{CONFIG_FILE}': {e}. Using defaults.")
            config = defaults
            save_config() # Save defaults if loading failed
    else:
        logger(f"INFO: Mecanum controller: Config file '{CONFIG_FILE}' not found. Creating default.")
        config = defaults
        save_config()

def save_config():
    global config
    logger = get_logger()
    try:
        # Ensure baud rate is int before saving
        config["baud_rate"] = int(config.get("baud_rate", get_default_config()["baud_rate"]))
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        logger(f"INFO: Mecanum controller: Configuration saved to {CONFIG_FILE}")
        return True
    except (IOError, TypeError, ValueError) as e:
        logger(f"ERROR: Mecanum controller: Error saving config file '{CONFIG_FILE}': {e}")
        return False

# --- Serial Communication ---
def get_serial_status():
    return "Connected" if ser and ser.is_open else "Disconnected"

def init_serial():
    global ser, config
    logger = get_logger()
    if not config: load_config() # Ensure config is loaded before accessing

    port = config.get("serial_port", default_serial_port)
    baud = config.get("baud_rate", default_baud_rate)

    if not isinstance(baud, int): # Ensure baud is integer
        logger(f"WARNING: Mecanum controller: Baud rate '{baud}' was not an integer. Using default {default_baud_rate}.")
        baud = default_baud_rate
        config["baud_rate"] = baud # Fix it in current config

    status_payload = {'port': port} # Payload for emitting status

    if ser and ser.is_open:
        if ser.port == port and ser.baudrate == baud:
             logger(f"INFO: Mecanum controller: Already connected to {port} at {baud} baud.")
             status_payload['status'] = 'Connected'
             status_payload['message'] = f'Already connected to {port}'
             if socketio: socketio.emit('mecanum_serial_status', status_payload, namespace=NAMESPACE)
             return True # Already connected correctly
        else:
             logger(f"INFO: Mecanum controller: Closing existing connection to {ser.port}@{ser.baudrate} to connect to {port}@{baud}")
             close_serial(emit_status=False) # Close old connection without emitting disconnected status yet

    logger(f"WARNING: Mecanum controller: Attempting connection to {port} at {baud} baud. Ensure Serial Monitor tool is not using this port and permissions are correct (dialout group).")

    try:
        ser = serial.Serial(port, baud, timeout=1)
        logger(f"INFO: Mecanum controller: Serial object created for {port}. Waiting for Arduino...")
        time.sleep(2.5) # Increase wait time slightly

        # Try reading initial message
        initial_message = "No initial message received."
        try:
            if ser.in_waiting > 0:
                line = ser.readline()
                initial_message = line.decode('utf-8', errors='ignore').strip()
                logger(f"INFO: Mecanum controller: Arduino ({port}) says: '{initial_message}'")
            else:
                logger(f"INFO: Mecanum controller: Successfully connected to {port}, no initial message within timeout.")
        except Exception as read_err:
             logger(f"WARNING: Mecanum controller: Error reading initial message from {port}: {read_err}")
             initial_message = f"Connected, but error reading initial message: {read_err}"


        status_payload['status'] = 'Connected'
        status_payload['message'] = initial_message
        if socketio: socketio.emit('mecanum_serial_status', status_payload, namespace=NAMESPACE)
        return True

    except serial.SerialException as e:
        logger(f"ERROR: Mecanum controller: SerialException connecting to {port}: {e}")
        ser = None
        status_payload['status'] = 'Error'
        status_payload['message'] = f"SerialException: {e}. Check port, permissions, and ensure Arduino is connected/powered."
        if socketio: socketio.emit('mecanum_serial_status', status_payload, namespace=NAMESPACE)
        return False
    except Exception as e:
        logger(f"ERROR: Mecanum controller: Unexpected error during serial init on {port}: {e}")
        ser = None
        status_payload['status'] = 'Error'
        status_payload['message'] = f"Unexpected error: {e}"
        if socketio: socketio.emit('mecanum_serial_status', status_payload, namespace=NAMESPACE)
        return False

def close_serial(emit_status=True):
    """ Closes the serial port if open, optionally emitting status """
    global ser, last_sent_command
    logger = get_logger()
    port = ser.port if ser else config.get("serial_port", "N/A") # Get port name before closing

    if ser and ser.is_open:
        logger(f"INFO: Mecanum controller: Closing serial port {port}")
        try:
            # Optional: Send a final stop command before closing
            # stop_command = "0,0,0,0"
            # ser.write((stop_command + '\n').encode('utf-8'))
            # time.sleep(0.05)
            ser.close()
        except Exception as e:
            logger(f"ERROR: Mecanum controller: Error closing serial port {port}: {e}")
    else:
        logger(f"DEBUG: Mecanum controller: Close serial called but port {port} was not open.")

    ser = None
    last_sent_command = "" # Reset last command tracking

    if emit_status and socketio:
        status_payload = {'status': 'Disconnected', 'port': port, 'message': f'Disconnected from {port}'}
        socketio.emit('mecanum_serial_status', status_payload, namespace=NAMESPACE)

def send_serial_command(command_str):
    global ser, last_sent_command
    logger = get_logger()
    if not ser or not ser.is_open:
        logger("WARNING: Mecanum controller: Serial port not connected. Cannot send command.")
        # Don't try to auto-reconnect here, let user handle it
        if socketio: # Inform client
             socketio.emit('mecanum_error', {'message': 'Serial disconnected. Cannot send command.'}, namespace=NAMESPACE)
             # Also update overall status
             close_serial() # Ensure status is updated to disconnected
        return False

    # Avoid spamming identical stop commands, allow others
    if command_str == "0,0,0,0" and last_sent_command == "0,0,0,0":
        return True
    if command_str == last_sent_command:
        # Could potentially rate limit identical non-stop commands too if needed
        pass # Allow sending for now

    try:
        ser.write((command_str + '\n').encode('utf-8'))
        # Use debug level for potentially frequent messages
        if current_app: current_app.logger.debug(f"Mecanum controller: Sent command: {command_str}")
        last_sent_command = command_str
        return True
    except serial.SerialException as e:
        logger(f"ERROR: Mecanum controller: Serial communication error while sending '{command_str}': {e}")
        close_serial() # Close port and update status on error
        if socketio: socketio.emit('mecanum_error', {'message': f'Serial send error: {e}'}, namespace=NAMESPACE)
        return False
    except Exception as e:
        logger(f"ERROR: Mecanum controller: Unexpected error sending command '{command_str}': {e}")
        last_sent_command = "" # Reset last command tracking
        close_serial() # Assume connection is compromised
        if socketio: socketio.emit('mecanum_error', {'message': f'Unexpected send error: {e}'}, namespace=NAMESPACE)
        return False

# --- Motor Speed Calculation ---
def scale_speed(speed, deadzone_min, deadzone_max):
    if speed == 0: return 0
    sign = 1 if speed > 0 else -1
    abs_speed = abs(speed)
    if abs_speed < 1: return 0
    # Prevent division by zero if PWM_MAX == 1 (unlikely)
    if PWM_MAX <= 1: return sign * deadzone_min
    # Ensure deadzone values are logical
    deadzone_min = max(0, min(deadzone_min, PWM_MAX -1))
    deadzone_max = max(deadzone_min + 1, min(deadzone_max, PWM_MAX))

    scaled = int(deadzone_min + (abs_speed - 1) * (deadzone_max - deadzone_min) / (PWM_MAX - 1))
    # Clamp output just in case
    scaled = max(deadzone_min, min(scaled, deadzone_max))
    return sign * scaled

def calculate_motor_speeds(logical_speeds):
    global config
    physical_speeds = [0] * NUM_MOTORS
    logger = get_logger()
    if not config:
        logger("ERROR: Mecanum controller: Config not loaded during speed calculation.")
        return physical_speeds # Return zeros

    mapping = config.get('mapping', {})
    calibration = config.get('calibration', {})
    scaling_config = config.get('scaling', {})
    deadzone_min = scaling_config.get('deadzone_min', 0)
    deadzone_max = scaling_config.get('deadzone_max', PWM_MAX)

    for logical_name, input_speed in logical_speeds.items():
        physical_index_str = mapping.get(logical_name) # Value from config might be string '0', '1' etc or int or None
        physical_index = None
        if physical_index_str is not None and physical_index_str != 'none':
            try:
                physical_index = int(physical_index_str)
            except (ValueError, TypeError):
                 logger(f"WARNING: Invalid non-integer mapping '{physical_index_str}' for '{logical_name}'. Ignoring.")
                 continue # Skip this motor

        if physical_index is not None and 0 <= physical_index < NUM_MOTORS:
            try:
                 calib_factor = float(calibration.get(logical_name, 1.0))
            except (ValueError, TypeError):
                 logger(f"WARNING: Invalid calibration factor '{calibration.get(logical_name)}' for '{logical_name}'. Using 1.0.")
                 calib_factor = 1.0

            calibrated_speed = input_speed * calib_factor
            scaled_speed = scale_speed(int(round(calibrated_speed)), deadzone_min, deadzone_max)
            final_speed = max(-PWM_MAX, min(PWM_MAX, scaled_speed))
            physical_speeds[physical_index] = final_speed
        elif physical_index is not None:
             logger(f"WARNING: Invalid physical index '{physical_index}' (out of range 0-{NUM_MOTORS-1}) mapped for '{logical_name}'. Ignoring.")
        # else: Motor not mapped, speed remains 0

    logger(f"DEBUG: Logical Speeds: {logical_speeds} -> Physical Speeds: {physical_speeds}")
    return physical_speeds

# --- Mecanum Drive Kinematics ---
def get_move_speeds(vx, vy, omega):
    # Clamp inputs first to prevent excessive intermediate values
    vx = max(-PWM_MAX, min(PWM_MAX, vx))
    vy = max(-PWM_MAX, min(PWM_MAX, vy))
    omega = max(-PWM_MAX, min(PWM_MAX, omega))

    # Standard Mecanum kinematics equations
    # Adjust signs below if your robot moves incorrectly (e.g., swap vy signs)
    fl = vx - vy - omega
    fr = vx + vy + omega
    rl = vx + vy - omega
    rr = vx - vy + omega

    # Normalize speeds if any exceed PWM_MAX, preserving ratios
    max_abs_speed = max(abs(fl), abs(fr), abs(rl), abs(rr))
    if max_abs_speed > PWM_MAX:
        scale_factor = PWM_MAX / max_abs_speed
        fl *= scale_factor
        fr *= scale_factor
        rl *= scale_factor
        rr *= scale_factor

    # Return integers, rounding might be slightly better than truncating
    return {
        "front_left": int(round(fl)),
        "front_right": int(round(fr)),
        "rear_left": int(round(rl)),
        "rear_right": int(round(rr))
    }

# --- Flask Routes ---
@mecanum_control_bp.route('/mecanum-control')
def controller_page():
    logger = get_logger()
    logger.info("Accessing Mecanum Control page.")
    load_config() # Load fresh config on page load
    serial_status = get_serial_status()
    return render_template(
        'mecanum_control.html',
        config=config,
        serial_status=serial_status,
        num_motors=NUM_MOTORS
    )

@mecanum_control_bp.route('/mecanum-control/get_config', methods=['GET'])
def get_config_json():
    # Config should be up-to-date due to load_config on page load/init
    serial_status = get_serial_status()
    return jsonify({"config": config, "serial_status": serial_status})

@mecanum_control_bp.route('/mecanum-control/save_config', methods=['POST'])
def save_config_route():
    global config
    logger = get_logger()
    try:
        new_config_data = request.get_json()
        if not new_config_data: return jsonify({"success": False, "message": "No data received."}), 400

        # Basic validation could be added here - check types, ranges etc.

        # Check if serial port or baud rate is changing
        old_port = config.get("serial_port", default_serial_port)
        old_baud = config.get("baud_rate", default_baud_rate)
        new_port = new_config_data.get("serial_port", old_port)
        new_baud = int(new_config_data.get("baud_rate", old_baud)) # Ensure int

        port_changed = (new_port != old_port)
        baud_changed = (new_baud != old_baud)

        # Update global config
        config = new_config_data
        config["baud_rate"] = new_baud # Ensure baud rate is stored as int

        if save_config():
             if port_changed or baud_changed:
                 logger(f"INFO: Mecanum Serial Port/Baud changed via config save. Closing connection.")
                 close_serial() # Close old connection, user must reconnect manually
             # Emit new config to connected clients?
             if socketio:
                 socketio.emit('mecanum_config', {'config': config}, namespace=NAMESPACE)
                 # Also update status if serial was affected
                 if port_changed or baud_changed:
                     socketio.emit('mecanum_serial_status', {'status': 'Disconnected', 'port': new_port, 'message': 'Settings changed, please reconnect.'}, namespace=NAMESPACE)

             return jsonify({"success": True, "message": "Configuration saved."})
        else:
            return jsonify({"success": False, "message": "Failed to write config file."}), 500
    except (ValueError, TypeError) as e:
         logger(f"ERROR: Mecanum controller: Invalid data type in save config: {e}")
         return jsonify({"success": False, "message": f"Invalid data type in config: {e}"}), 400
    except Exception as e:
        logger(f"ERROR: Mecanum controller: Error saving config: {e}")
        return jsonify({"success": False, "message": f"Server error: {e}"}), 500

@mecanum_control_bp.route('/mecanum-control/reset_config', methods=['POST'])
def reset_config_route():
    global config
    logger = get_logger()
    logger("INFO: Mecanum controller: Resetting config to defaults.")
    config = get_default_config()
    if save_config():
        close_serial() # Close any existing connection
        # Emit new config and status to connected clients
        if socketio:
            socketio.emit('mecanum_config', {'config': config}, namespace=NAMESPACE)
            socketio.emit('mecanum_serial_status', {'status': 'Disconnected', 'port': config.get("serial_port"), 'message': 'Config reset, please connect.'}, namespace=NAMESPACE)
        return jsonify({"success": True, "message": "Configuration reset to defaults.", "config": config})
    else:
        return jsonify({"success": False, "message": "Failed to write default config file."}), 500

# --- SocketIO Initialization and Handlers ---
def init_socketio(sio_instance):
    global socketio
    socketio = sio_instance
    logger = get_logger()
    logger("INFO: Mecanum Control SocketIO initialized and handlers are being defined.")

    # --- Define SocketIO Event Handlers INSIDE this function ---
    @socketio.on('connect', namespace=NAMESPACE)
    def handle_mecanum_connect():
        from flask import request # Import request context locally
        logger = get_logger()
        logger(f'INFO: Client {request.sid} connected to Mecanum namespace')
        load_config() # Ensure latest config when client connects
        emit('mecanum_config', {'config': config})
        # Don't assume connection status, send current actual status
        emit('mecanum_serial_status', {'status': get_serial_status(), 'port': config.get("serial_port"), 'message': f'Welcome! Current status: {get_serial_status()}'})

    @socketio.on('disconnect', namespace=NAMESPACE)
    def handle_mecanum_disconnect():
        from flask import request # Import request context locally
        logger = get_logger()
        logger(f'INFO: Client {request.sid} disconnected from Mecanum namespace')
        # Optional: Add logic if needed when clients leave

    @socketio.on('mecanum_connect_serial', namespace=NAMESPACE)
    def handle_connect_serial_request():
        from flask import request # Import request context locally
        logger = get_logger()
        logger(f"INFO: Client {request.sid} requested Mecanum serial connect.")
        init_serial() # Attempt connection, status emitted inside this function

    @socketio.on('mecanum_disconnect_serial', namespace=NAMESPACE)
    def handle_disconnect_serial_request():
        from flask import request # Import request context locally
        logger = get_logger()
        logger(f"INFO: Client {request.sid} requested Mecanum serial disconnect.")
        close_serial() # Close connection, status emitted inside this function

    @socketio.on('mecanum_control_command', namespace=NAMESPACE)
    def handle_control_command(data):
        logger = get_logger()
        # Check serial connection status FIRST
        if not ser or not ser.is_open:
            # Do not try to send if not connected. Rely on user to connect.
            # emit('mecanum_error', {'message': 'Serial port not connected. Cannot send command.'}, namespace=NAMESPACE)
            logger("DEBUG: Control command received but serial not connected. Ignoring.")
            return # Silently ignore if not connected, UI should reflect this

        action = data.get('action')
        vx = data.get('vx', 0)
        vy = data.get('vy', 0)
        omega = data.get('omega', 0)
        logical_speeds = {}

        try:
            if action == 'stop': logical_speeds = get_move_speeds(0, 0, 0)
            elif action == 'move': logical_speeds = get_move_speeds(vx, vy, omega)
            # Add simple directional commands if your JS still uses them
            elif action in ['forward', 'backward', 'left', 'right', 'rotate_left', 'rotate_right', 'diag_fl', 'diag_fr', 'diag_rl', 'diag_rr']:
                 speed = PWM_MAX
                 if action == 'forward': logical_speeds = get_move_speeds(speed, 0, 0)
                 elif action == 'backward': logical_speeds = get_move_speeds(-speed, 0, 0)
                 elif action == 'left': logical_speeds = get_move_speeds(0, speed, 0)
                 elif action == 'right': logical_speeds = get_move_speeds(0, -speed, 0)
                 elif action == 'rotate_left': logical_speeds = get_move_speeds(0, 0, speed)
                 elif action == 'rotate_right': logical_speeds = get_move_speeds(0, 0, -speed)
                 elif action == 'diag_fl': logical_speeds = get_move_speeds(speed, speed, 0)
                 elif action == 'diag_fr': logical_speeds = get_move_speeds(speed, -speed, 0)
                 elif action == 'diag_rl': logical_speeds = get_move_speeds(-speed, speed, 0)
                 elif action == 'diag_rr': logical_speeds = get_move_speeds(-speed, -speed, 0)
            else:
                logger(f"WARNING: Mecanum controller: Invalid action received: {action}")
                emit('mecanum_error', {'message': f'Invalid control action: {action}'}, namespace=NAMESPACE)
                return

            physical_speeds = calculate_motor_speeds(logical_speeds)
            command_str = ",".join(map(str, physical_speeds))

            # send_serial_command handles logging, errors, and status updates on failure
            send_serial_command(command_str)

        except Exception as e:
            logger(f"ERROR: Mecanum controller: Error processing control command {data}: {e}")
            emit('mecanum_error', {'message': f'Error processing command: {e}'}, namespace=NAMESPACE)

# --- Blueprint Loading Hook ---
@mecanum_control_bp.record_once
def on_load(state):
    logger = get_logger()
    logger("INFO: Loading Mecanum controller configuration during blueprint registration.")
    load_config()