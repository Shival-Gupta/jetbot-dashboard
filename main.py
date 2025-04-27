# main.py
import eventlet
eventlet.monkey_patch() # Must be at the top before other imports like socket

from flask import Flask, request # request needed for SID in handlers
from flask_socketio import SocketIO, emit, disconnect
import logging
import os

# Import configurations
import config

# Import route blueprints
from routes.dashboard import dashboard_bp
from routes.uploader import uploader_bp
from routes.serial_monitor import serial_monitor_bp, init_socketio as init_serial_monitor_socketio, handle_client_disconnect, handle_serial_connect_request, handle_serial_disconnect_request, handle_serial_send_request

# Initialize Flask App
app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY

# Initialize SocketIO - Must happen AFTER app is created
# Important: Use the eventlet async mode
socketio = SocketIO(app, async_mode='eventlet', logger=True, engineio_logger=True) # Enable engineio logs for debug

# Pass the socketio instance to the serial monitor module
init_serial_monitor_socketio(socketio)

# Configure Logging (Use Flask's logger)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app.logger.info("Flask App and SocketIO Initialized.")


# --- Register Blueprints ---
app.register_blueprint(dashboard_bp)
app.register_blueprint(uploader_bp)
app.register_blueprint(serial_monitor_bp)
app.logger.info("Blueprints Registered.")


# --- SocketIO Event Handlers (Centralized Here) ---
# These handlers call the logic defined in routes/serial_monitor.py

@socketio.on('connect')
def sio_connect():
    app.logger.info(f"Client connected via SocketIO: {request.sid}")
    # Emit directly or call a handler if more logic needed
    emit('serial_status', {'status': 'connected_server', 'message': 'Connected to server'})

@socketio.on('disconnect')
def sio_disconnect():
    app.logger.info(f"Client disconnected: {request.sid}")
    # Call the cleanup logic from the serial_monitor module
    handle_client_disconnect(request.sid)

@socketio.on('serial_connect')
def sio_serial_connect(json_data):
    # Pass request SID and data to the logic handler
    handle_serial_connect_request(request.sid, json_data)

@socketio.on('serial_disconnect')
def sio_serial_disconnect():
    handle_serial_disconnect_request(request.sid)

@socketio.on('serial_send')
def sio_serial_send(json_data):
    handle_serial_send_request(request.sid, json_data)

# --- Main Execution ---
if __name__ == '__main__':
    app.logger.info(f"Starting Arduino Dashboard on http://{config.APP_HOST}:{config.APP_PORT}")
    # Use socketio.run() which handles the underlying async server (eventlet)
    socketio.run(app, host=config.APP_HOST, port=config.APP_PORT, debug=False, use_reloader=False)
    # debug=False and use_reloader=False are recommended for stability with async/background tasks
    app.logger.info("Server shutdown.")