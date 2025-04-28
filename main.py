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
# Notice we also import init_socketio for terminal
from routes.terminal import (
    terminal_bp,
    TerminalNamespace,
    init_socketio as init_terminal_socketio
)

app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY

# Initialize Socket.IO
socketio = SocketIO(app, async_mode='eventlet', logger=True, engineio_logger=True)

# Give both modules the socketio instance
init_serial_monitor_socketio(socketio)
init_terminal_socketio(socketio)

# Register Blueprints
app.register_blueprint(dashboard_bp)
app.register_blueprint(uploader_bp)
app.register_blueprint(serial_monitor_bp)
app.register_blueprint(terminal_bp)

# Mount the terminal namespace
socketio.on_namespace(TerminalNamespace('/terminal'))

# Existing serial handlers
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
    app.logger.info(f"Starting on http://{config.APP_HOST}:{config.APP_PORT}")
    if app.config['SECRET_KEY'] == 'temporary_insecure_development_key':
        app.logger.critical("INSECURE SECRET_KEY—aborting start")
        exit(1)

    socketio.run(
        app,
        host=config.APP_HOST,
        port=config.APP_PORT,
        debug=(os.getenv('FLASK_ENV') == 'development'),
        use_reloader=False
    )
    app.logger.info("Server shutdown")
