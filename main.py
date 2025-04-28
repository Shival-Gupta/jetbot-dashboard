# main.py
import eventlet
eventlet.monkey_patch()  # must be first

import os
import logging
from dotenv import load_dotenv
from flask import Flask, request
from flask_socketio import SocketIO, emit

# Load env
load_dotenv()
import config

# Import Blueprints
from routes.dashboard import dashboard_bp
from routes.uploader import uploader_bp
from routes.serial_monitor import (
    serial_monitor_bp,
    init_socketio as init_serial_monitor_socketio,
    handle_client_disconnect, # Keep existing handlers if still needed globally
    # ... other specific serial monitor handlers ...
)
from routes.terminal import (
    terminal_bp,
    TerminalNamespace, # Keep if using class-based namespace
    init_socketio as init_terminal_socketio
)
# Import the new Mecanum Control Blueprint
from routes.mecanum_control import (
    mecanum_control_bp,
    init_socketio as init_mecanum_socketio # Import its initializer
)

app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY

# --- Logging Setup --- (Example using basicConfig)
# Configure logging level and format if not done elsewhere
log_level = logging.DEBUG if os.getenv('FLASK_ENV') == 'development' else logging.INFO
logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
app.logger.setLevel(log_level) # Ensure Flask logger level matches

# Initialize Socket.IO
socketio = SocketIO(app, async_mode='eventlet', logger=True, engineio_logger=True, cors_allowed_origins="*") # Added CORS for safety


# Give SocketIO instance to each module that needs it
init_serial_monitor_socketio(socketio)
init_terminal_socketio(socketio)
init_mecanum_socketio(socketio)

# Register Blueprints
app.register_blueprint(dashboard_bp)
app.register_blueprint(uploader_bp)
app.register_blueprint(serial_monitor_bp)
app.register_blueprint(terminal_bp)
app.register_blueprint(mecanum_control_bp)

# Mount the terminal namespace (keep if used)
socketio.on_namespace(TerminalNamespace('/terminal'))


# --- Global SocketIO Handlers (Example - Keep yours if needed) ---
@socketio.on('connect')
def sio_connect():
    # This is a global connect handler, maybe remove if namespaces handle connects
    app.logger.info(f"Global connect: Client connected: {request.sid}")
    # emit('serial_status', {'status': 'connected_server', 'message': 'Connected to server'}) # Be careful not to conflict

@socketio.on('disconnect')
def sio_disconnect():
    app.logger.info(f"Global disconnect: Client disconnected: {request.sid}")
    # Call disconnect handlers for different parts if needed
    handle_client_disconnect(request.sid) # Assuming this handles serial monitor cleanup


# --- REMOVE OLD Serial Handlers if they conflict or move to namespaces ---
# Check if these are needed globally or are specific to serial_monitor
# @socketio.on('serial_connect')
# def sio_serial_connect(json_data):
#     handle_serial_connect_request(request.sid, json_data)

# @socketio.on('serial_disconnect')
# def sio_serial_disconnect():
#     handle_serial_disconnect_request(request.sid)

# @socketio.on('serial_send')
# def sio_serial_send(json_data):
#     handle_serial_send_request(request.sid, json_data)

@socketio.on('connect')
def sio_connect():
    app.logger.info(f"Client connected: {request.sid}")
    emit('serial_status', {'status': 'connected_server', 'message': 'Connected to server'})

@socketio.on('disconnect')
def sio_disconnect():
    app.logger.info(f"Client disconnected: {request.sid}")
    handle_client_disconnect(request.sid)

@socketio.on('serial_connect')
def sio_serial_connect(json_data):
    handle_serial_connect_request(request.sid, json_data)

@socketio.on('serial_disconnect')
def sio_serial_disconnect():
    handle_serial_disconnect_request(request.sid)

@socketio.on('serial_send')
def sio_serial_send(json_data):
    handle_serial_send_request(request.sid, json_data)

if __name__ == '__main__':
    app.logger.info(f"Starting Jetbot Dashboard on http://{config.APP_HOST}:{config.APP_PORT}")
    if app.config['SECRET_KEY'] == 'temporary_insecure_development_key':
        app.logger.critical("INSECURE SECRET_KEY—aborting start")
        exit(1)

    # Use socketio.run for development with SocketIO
    socketio.run(
        app,
        host=config.APP_HOST,
        port=config.APP_PORT,
        debug=(os.getenv('FLASK_ENV') == 'development'),
        use_reloader=False # Important with eventlet/gevent
    )
    app.logger.info("Server shutdown")
