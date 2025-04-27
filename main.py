# main.py
import eventlet
eventlet.monkey_patch() # Must be at the top

import os
import logging
from dotenv import load_dotenv # Import load_dotenv

# --- Load .env file BEFORE importing config or creating app ---
# Looks for .env in the current working directory or parent directories
load_dotenv()
print(f"Attempting to load .env file. Found SECRET_KEY: {'Yes' if os.getenv('SECRET_KEY') else 'No'}") # Debug print

from flask import Flask, request
from flask_socketio import SocketIO, emit, disconnect

# Import configurations AFTER loading .env
import config

# Import route blueprints and serial logic handlers
from routes.dashboard import dashboard_bp
from routes.uploader import uploader_bp
from routes.serial_monitor import (
    serial_monitor_bp,
    init_socketio as init_serial_monitor_socketio,
    handle_client_disconnect,
    handle_serial_connect_request,
    handle_serial_disconnect_request,
    handle_serial_send_request
)

# Initialize Flask App
app = Flask(__name__)
# Load secret key from config (which reads from environment)
app.config['SECRET_KEY'] = config.SECRET_KEY
if config.SECRET_KEY == 'temporary_insecure_development_key':
     app.logger.warning("Using default insecure SECRET_KEY. Set a real key in the .env file for production!")


# Initialize SocketIO
socketio = SocketIO(app, async_mode='eventlet', logger=True, engineio_logger=True)

# Pass the socketio instance to the serial monitor module
init_serial_monitor_socketio(socketio)

# Configure Logging (Use Flask's logger)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
if not app.debug: # Avoid duplicate logs if Flask debug is on
     app.logger.setLevel(logging.INFO)
app.logger.info("Flask App and SocketIO Initialized.")
app.logger.info(f"Running in FLASK_ENV: {os.getenv('FLASK_ENV', 'not set')}")


# --- Register Blueprints ---
app.register_blueprint(dashboard_bp)
app.register_blueprint(uploader_bp)
app.register_blueprint(serial_monitor_bp)
app.logger.info("Blueprints Registered.")


# --- SocketIO Event Handlers (Centralized Here) ---
@socketio.on('connect')
def sio_connect():
    app.logger.info(f"Client connected via SocketIO: {request.sid}")
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

# --- Main Execution ---
if __name__ == '__main__':
    app.logger.info(f"Starting Arduino Dashboard on http://{config.APP_HOST}:{config.APP_PORT}")

    # Check if secret key is still the insecure default
    if app.config['SECRET_KEY'] == 'temporary_insecure_development_key':
        app.logger.critical("!!! REFUSING TO START WITH INSECURE DEFAULT SECRET_KEY !!!")
        app.logger.critical("Please generate a strong key and set it in the .env file as SECRET_KEY.")
        exit(1) # Exit if key is insecure

    # Use socketio.run() for development server or deploy with a proper WSGI server like Gunicorn + eventlet worker
    # Example using socketio.run directly:
    socketio.run(app, host=config.APP_HOST, port=config.APP_PORT, debug=(os.getenv('FLASK_ENV') == 'development'), use_reloader=False)
    # debug=True enables Flask's debugger and reloader
    # use_reloader=False is often needed with eventlet/gevent

    # Example for production using eventlet WSGI server directly (often better):
    # if os.getenv('FLASK_ENV') == 'production':
    #      import eventlet.wsgi
    #      try:
    #          eventlet.wsgi.server(eventlet.listen((config.APP_HOST, config.APP_PORT)), app)
    #      except KeyboardInterrupt:
    #          app.logger.info("Server interrupted by user.")
    #      finally:
    #          app.logger.info("Server shutdown.")
    # else: # Development server
    #      socketio.run(app, host=config.APP_HOST, port=config.APP_PORT, debug=True, use_reloader=False)


    app.logger.info("Server shutdown initiated.")