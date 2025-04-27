# routes/serial_monitor.py
from flask import Blueprint, render_template_string, current_app # Keep current_app for logger use *within context* later
import serial
import threading
# import logging # No longer needed at top level if only using current_app.logger

# Import necessary items from shared modules
import config
import helpers

# Create Blueprint
serial_monitor_bp = Blueprint('serial_monitor', __name__)

# --- Global State & SocketIO Instance Holder ---
serial_connections = {}
socketio_instance = None

def init_socketio(socketio):
    """Allows main.py to pass the initialized SocketIO instance."""
    global socketio_instance
    socketio_instance = socketio
    # REMOVED: current_app.logger.info("SocketIO instance received by serial_monitor module.")
    # Cannot use current_app.logger here as it's outside app context during init.
    # Logging inside request/event handlers below is okay.
    print("INFO: SocketIO instance received by serial_monitor module.") # Use basic print during init if needed

# --- Route for the Serial Monitor Page ---
@serial_monitor_bp.route('/arduino-serial')
def arduino_serial_page():
    """Serves the Serial Monitor page."""
    serial_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Web Serial Monitor</title>
        <script src="https://cdn.tailwindcss.com/3.4.3"></script>
        {# Socket.IO Client Library #}
        <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
        <style>
            body { font-family: sans-serif; }
            #serialOutput { height: 400px; background-color: #1a202c; color: #c6f6d5; font-family: monospace; font-size: 0.875rem; overflow-y: scroll; padding: 1rem; border: 1px solid #4a5568; border-radius: 0.375rem; white-space: pre-wrap; word-wrap: break-word; }
            .form-checkbox:checked { background-color: #48bb78; border-color: #48bb78; }
        </style>
    </head>
    <body class="bg-gray-100 p-8">
        <div class="container mx-auto max-w-3xl bg-white p-6 rounded-lg shadow-md">
             <div class="flex justify-between items-center mb-4">
                 <h1 class="text-2xl font-bold text-center text-gray-700 flex-grow">Web Serial Monitor</h1>
                 <a href="/" class="text-sm text-blue-600 hover:underline">&larr; Back to Dashboard</a>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4 items-end">
                <div>
                    <label for="serialPort" class="block text-sm font-medium text-gray-700 mb-1">Port:</label>
                    <div class="flex items-center">
                        <select id="serialPort" class="mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
                           <option value="" selected>Detecting...</option>
                        </select>
                        <button type="button" id="refreshSerialPorts" title="Refresh Ports" class="ml-2 p-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500">
                             <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 110 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd" /></svg>
                        </button>
                    </div>
                     <p id="serialPortError" class="text-red-500 text-xs italic mt-1 hidden">Could not fetch ports.</p>
                     <p id="noSerialPortsFound" class="text-yellow-600 text-xs italic mt-1 hidden">No serial ports detected.</p>
                </div>
                <div>
                    <label for="baudRate" class="block text-sm font-medium text-gray-700 mb-1">Baud Rate:</label>
                    <select id="baudRate" class="mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
                         {% for rate in common_baud_rates %}
                            <option value="{{ rate }}" {% if rate == 115200 %}selected{% endif %}>{{ rate }}</option>
                         {% endfor %}
                    </select>
                </div>
                 <div>
                    <button type="button" id="connectButton" class="w-full py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 disabled:opacity-50">
                        Connect
                    </button>
                </div>
            </div>

             <div id="statusMessage" class="mb-4 p-3 rounded-md text-sm hidden border"></div>

            <div class="mb-4">
                 <div class="flex justify-between items-center mb-1">
                     <label class="block text-sm font-medium text-gray-700">Serial Output:</label>
                     <div>
                         <label for="autoscroll" class="mr-2 text-sm text-gray-600">Autoscroll</label>
                         <input type="checkbox" id="autoscroll" class="form-checkbox h-4 w-4 text-green-600 border-gray-300 rounded focus:ring-green-500" checked>
                          <button type="button" id="clearOutput" class="ml-4 text-sm text-blue-600 hover:underline">Clear</button>
                     </div>
                 </div>
                <div id="serialOutput" class="bg-gray-800"></div> {# Use a darker background for contrast #}
            </div>

            <div class="flex items-center space-x-2">
                 <input type="text" id="serialInput" placeholder="Send data to serial port..." disabled
                       class="flex-grow block w-full py-2 px-3 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm disabled:bg-gray-100">
                 <button type="button" id="sendButton" disabled
                        class="py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed">
                    Send
                </button>
            </div>
        </div>

        <script>
           // --- PASTE SERIAL MONITOR JAVASCRIPT HERE ---
            // (The <script> block from the previous version's /arduino-serial route)
            const socket = io(); // Connect to Socket.IO server

            // --- DOM Elements ---
            const portSelect = document.getElementById('serialPort');
            const refreshButton = document.getElementById('refreshSerialPorts');
            const baudRateSelect = document.getElementById('baudRate');
            const connectButton = document.getElementById('connectButton');
            const statusMessage = document.getElementById('statusMessage');
            const outputArea = document.getElementById('serialOutput');
            const inputField = document.getElementById('serialInput');
            const sendButton = document.getElementById('sendButton');
            const autoscrollCheckbox = document.getElementById('autoscroll');
            const clearOutputButton = document.getElementById('clearOutput');
            const portErrorMsg = document.getElementById('serialPortError');
            const noPortsFoundMsg = document.getElementById('noSerialPortsFound');

            let isConnected = false;

            // --- UI Update Functions ---
            function setUIConnected(connected) {
                isConnected = connected;
                connectButton.textContent = connected ? 'Disconnect' : 'Connect';
                connectButton.classList.toggle('bg-green-600', !connected);
                connectButton.classList.toggle('hover:bg-green-700', !connected);
                connectButton.classList.toggle('focus:ring-green-500', !connected);
                connectButton.classList.toggle('bg-red-600', connected);
                connectButton.classList.toggle('hover:bg-red-700', connected);
                connectButton.classList.toggle('focus:ring-red-500', connected);

                portSelect.disabled = connected;
                baudRateSelect.disabled = connected;
                refreshButton.disabled = connected;
                inputField.disabled = !connected;
                sendButton.disabled = !connected;
            }

            function showStatus(message, isError = false) {
                 statusMessage.textContent = message;
                 statusMessage.classList.remove('hidden'); // Make visible
                 statusMessage.classList.toggle('bg-green-100', !isError);
                 statusMessage.classList.toggle('text-green-800', !isError);
                 statusMessage.classList.toggle('border-green-300', !isError);
                 statusMessage.classList.toggle('bg-red-100', isError);
                 statusMessage.classList.toggle('text-red-800', isError);
                 statusMessage.classList.toggle('border-red-300', isError);
                 // Hide after a delay
                 setTimeout(() => { statusMessage.classList.add('hidden'); }, 5000);
            }


            function appendOutput(text) {
                const textNode = document.createTextNode(`${text}\n`); // Template literal with newline
                outputArea.appendChild(textNode);
                if (autoscrollCheckbox.checked) {
                    outputArea.scrollTop = outputArea.scrollHeight;
                }
            }

            // --- Port Fetching ---
            async function fetchSerialPorts() {
                portSelect.disabled = true;
                portErrorMsg.classList.add('hidden');
                noPortsFoundMsg.classList.add('hidden');
                portSelect.innerHTML = '<option value="" disabled selected>Refreshing...</option>';

                try {
                    const response = await fetch('/api/ports');
                    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                    const ports = await response.json();

                    portSelect.innerHTML = ''; // Clear existing options
                    if (ports.length > 0) {
                        ports.forEach((port, index) => {
                            const option = document.createElement('option');
                            option.value = port;
                            option.textContent = port;
                            portSelect.appendChild(option);
                            if (index === 0) option.selected = true;
                        });
                        portSelect.disabled = isConnected; // Only disable if connected
                    } else {
                        portSelect.innerHTML = '<option value="" disabled selected>No ports found</option>';
                        noPortsFoundMsg.classList.remove('hidden');
                        portSelect.disabled = true;
                    }
                } catch (error) {
                    console.error('Error fetching serial ports:', error);
                    portSelect.innerHTML = '<option value="" disabled selected>Error loading</option>';
                    portErrorMsg.classList.remove('hidden');
                    portSelect.disabled = true;
                }
            }

            // --- Socket.IO Event Handlers ---
            socket.on('connect', () => {
                console.log('Socket.IO connected');
                appendOutput('[System: Connected to server]');
                fetchSerialPorts(); // Fetch ports on initial connect
            });

            socket.on('disconnect', (reason) => {
                console.log('Socket.IO disconnected:', reason);
                appendOutput(`[System: Disconnected from server - ${reason}]`);
                setUIConnected(false);
                showStatus('Disconnected from server.', true);
            });

            socket.on('connect_error', (error) => {
                console.error('Socket.IO connection error:', error);
                appendOutput(`[System: Connection Error - ${error}]`);
                showStatus(`Connection error: ${error}`, true);
            });

            socket.on('serial_status', (msg) => {
                console.log('Serial Status:', msg);
                const message = msg.message || JSON.stringify(msg);
                const isError = msg.status === 'error';
                showStatus(message, isError);
                if (isError || msg.status === 'disconnected') {
                     setUIConnected(false);
                     // Re-enable connect button if disconnect/error occurs
                     connectButton.disabled = false;
                } else if (msg.status === 'connected') {
                     setUIConnected(true);
                     connectButton.disabled = false; // Ensure enabled after successful connect
                }
            });

             socket.on('serial_error', (msg) => {
                console.error('Serial Error:', msg);
                const error_message = msg.error || JSON.stringify(msg);
                appendOutput(`[Serial ERROR: ${error_message}]`);
                showStatus(`Serial Error: ${error_message}`, true);
                setUIConnected(false);
                connectButton.disabled = false; // Re-enable connect button on error
            });

            socket.on('serial_data', (msg) => {
                appendOutput(msg.data);
            });

            // --- Button/Input Event Listeners ---
            refreshButton.addEventListener('click', fetchSerialPorts);

            connectButton.addEventListener('click', () => {
                if (isConnected) {
                    socket.emit('serial_disconnect');
                    appendOutput('[System: Disconnecting...]');
                } else {
                    const port = portSelect.value;
                    const baud = baudRateSelect.value;
                    if (!port) {
                        showStatus('Please select a valid serial port.', true);
                        return;
                    }
                    connectButton.disabled = true;
                    appendOutput(`[System: Connecting to ${port} @ ${baud} baud...]`);
                    socket.emit('serial_connect', { port: port, baud_rate: parseInt(baud) });
                     // Let server response re-enable the button
                }
            });

            sendButton.addEventListener('click', () => {
                const dataToSend = inputField.value;
                if (dataToSend && isConnected) {
                    socket.emit('serial_send', { data: dataToSend });
                    // inputField.value = ''; // Optional: clear after send
                }
            });

            inputField.addEventListener('keypress', (event) => {
                if (event.key === 'Enter' && !sendButton.disabled) {
                    sendButton.click();
                }
            });

            clearOutputButton.addEventListener('click', () => {
                 outputArea.innerHTML = '';
            });

            // Initial setup
            document.addEventListener('DOMContentLoaded', () => {
                 setUIConnected(false);
                 // Fetch ports happens on socket connect
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(serial_template, common_baud_rates=config.COMMON_BAUD_RATES)

# --- Serial Port Logic Helpers (called by SocketIO handlers in main.py) ---

def read_serial_data_task(sid, ser_instance, stop_event):
    """Background task function to read serial data."""
    # Use current_app.logger here because this task is started within an app context
    logger = current_app.logger
    logger.info(f"Starting serial read thread for {sid} on {ser_instance.port}")
    if not socketio_instance:
        logger.error("SocketIO instance not initialized in serial_monitor module!")
        return

    while not stop_event.is_set():
        try:
            if ser_instance.is_open and ser_instance.in_waiting > 0:
                line = ser_instance.readline()
                try:
                    decoded_line = line.decode('utf-8', errors='replace').strip()
                    if decoded_line:
                        socketio_instance.emit('serial_data', {'data': decoded_line}, to=sid)
                        socketio_instance.sleep(0.01)
                except UnicodeDecodeError as ue:
                    logger.warning(f"Unicode decode error for {sid}: {ue}. Data: {line!r}")
                    socketio_instance.emit('serial_data', {'data': f'[Decode Error: {line!r}]'}, to=sid)
                    socketio_instance.sleep(0.01)
            else:
                if not ser_instance.is_open or stop_event.is_set():
                    break
                socketio_instance.sleep(0.05)

        except serial.SerialException as e:
            logger.error(f"Serial error for {sid} on {ser_instance.port}: {e}")
            # Emit error back to the specific client
            socketio_instance.emit('serial_error', {'error': f'Serial Error: {e}'}, to=sid)
            stop_event.set()
            break # Exit loop on serial error
        except Exception as e:
            logger.error(f"Unexpected error in read loop for {sid}: {e}", exc_info=True)
            socketio_instance.emit('serial_error', {'error': f'Unexpected read loop error: {e}'}, to=sid)
            stop_event.set()
            break

    if ser_instance and ser_instance.is_open:
        try:
            ser_instance.close()
        except Exception as e:
             logger.error(f"Error closing serial port for {sid} in read thread exit: {e}")
    logger.info(f"Serial read thread stopped for {sid} on port {ser_instance.port}")


def handle_client_disconnect(sid):
    """Called by main.py when a client disconnects."""
    cleanup_serial_connection(sid)

def handle_serial_connect_request(sid, json_data):
    """Called by main.py to handle connection request."""
    logger = current_app.logger # Okay to use logger here
    port = json_data.get('port')
    baud_rate = json_data.get('baud_rate')
    logger.info(f"Connect request from {sid} for {port} @ {baud_rate} baud")

    if not port or not baud_rate:
        socketio_instance.emit('serial_status', {'status': 'error', 'message': 'Port and baud rate required.'}, to=sid)
        return

    if sid in serial_connections:
        logger.warning(f"{sid} requested connect but already handled? Cleaning up first.")
        cleanup_serial_connection(sid)

    try:
        ser = serial.Serial(port, baud_rate, timeout=1)
        if not ser.is_open:
             raise serial.SerialException(f"Failed to open {port}")
        logger.info(f"Successfully opened {port} for {sid}")

        stop_event = threading.Event()
        read_thread = socketio_instance.start_background_task(
            read_serial_data_task, sid, ser, stop_event
        )
        if read_thread is None:
             ser.close() # Close port if task failed to start
             raise Exception("Failed to start background task.")

        serial_connections[sid] = {'serial': ser, 'thread': read_thread, 'stop_event': stop_event}
        socketio_instance.emit('serial_status', {'status': 'connected', 'message': f'Connected to {port}'}, to=sid)

    except serial.SerialException as e:
        logger.error(f"Failed to open serial port {port} for {sid}: {e}")
        socketio_instance.emit('serial_status', {'status': 'error', 'message': f'Error opening {port}: {e}'}, to=sid)
    except Exception as e:
        logger.error(f"Unexpected error during serial connect for {sid}: {e}", exc_info=True)
        socketio_instance.emit('serial_status', {'status': 'error', 'message': f'Unexpected server error: {e}'}, to=sid)

def handle_serial_disconnect_request(sid):
    """Called by main.py to handle disconnect request."""
    logger = current_app.logger # Okay here
    logger.info(f"Disconnect request from {sid}")
    if cleanup_serial_connection(sid):
         socketio_instance.emit('serial_status', {'status': 'disconnected', 'message': 'Disconnected.'}, to=sid)
    else:
         socketio_instance.emit('serial_status', {'status': 'disconnected', 'message': 'Not connected.'}, to=sid)

def handle_serial_send_request(sid, json_data):
    """Called by main.py to handle data sending."""
    logger = current_app.logger # Okay here
    data_to_send = json_data.get('data')

    if sid in serial_connections and data_to_send is not None:
        conn = serial_connections[sid]
        ser = conn['serial']
        try:
            if ser and ser.is_open:
                 data_with_newline = data_to_send + '\n'
                 ser.write(data_with_newline.encode('utf-8', errors='replace'))
            else:
                 logger.warning(f"Send attempt from {sid} but serial not open.")
                 socketio_instance.emit('serial_error', {'error': 'Cannot send, serial port not open.'}, to=sid)
        except serial.SerialException as e:
            logger.error(f"Error writing to serial port for {sid}: {e}")
            socketio_instance.emit('serial_error', {'error': f'Serial Write Error: {e}'}, to=sid)
            cleanup_serial_connection(sid)
        except Exception as e:
            logger.error(f"Unexpected error sending data for {sid}: {e}")
            socketio_instance.emit('serial_error', {'error': f'Unexpected Send Error: {e}'}, to=sid)

def cleanup_serial_connection(sid):
    """Safely close serial port and stop read thread for a given SID."""
    logger = current_app.logger # Okay here (usually called from disconnect event)
    if sid in serial_connections:
        conn = serial_connections.pop(sid)
        ser = conn.get('serial')
        stop_event = conn.get('stop_event')
        logger.info(f"Cleaning up serial connection for {sid}...")
        if stop_event: stop_event.set()
        if ser and ser.is_open:
            try:
                ser.close()
                logger.info(f"Closed serial port {ser.port} for {sid}")
            except Exception as e:
                logger.error(f"Error closing port {ser.port} for {sid}: {e}")
        return True
    return False