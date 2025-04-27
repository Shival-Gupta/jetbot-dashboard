#!/usr/bin/env python3
import os
import glob
import subprocess
import tempfile
import shutil
import logging
import time
import socket # For hostname
import threading # For managing serial read threads
import psutil # For uptime

from flask import Flask, request, render_template_string, jsonify, session
from flask_socketio import SocketIO, emit, disconnect
from werkzeug.utils import secure_filename
import serial # For pyserial

# --- Configuration ---
APP_HOST = '0.0.0.0'
APP_PORT = 6001 # Keep port from previous working version
ALLOWED_EXTENSIONS = {'.ino'}
ARDUINO_CLI_TIMEOUT = 180
ARDUINO_CLI_PATH = 'arduino-cli'
SECRET_KEY = os.urandom(24) # Needed for Flask sessions used by SocketIO

# Common FQBNs (Value: User-Friendly Name) - For Uploader
COMMON_FQBNS = {
    "arduino:avr:uno": "Arduino Uno",
    "arduino:avr:nano": "Arduino Nano (ATmega328P)",
    "arduino:avr:mega": "Arduino Mega or Mega 2560",
    "arduino:samd:mkr1000": "Arduino MKR 1000",
    "esp32:esp32:esp32": "ESP32 Dev Module",
    "esp32:esp32:nodemcu-32s": "NodeMCU-32S",
    "esp8266:esp8266:nodemcuv2": "NodeMCU 1.0 (ESP-12E)",
    "esp8266:esp8266:d1_mini": "WEMOS D1 Mini",
    "other": "Other..."
}

# Common Baud Rates - For Serial Monitor
COMMON_BAUD_RATES = [300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 74880, 115200, 230400, 250000, 500000, 1000000]

# --- Flask App & SocketIO Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
# Use eventlet for async mode, required for background tasks with SocketIO
socketio = SocketIO(app, async_mode='eventlet')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Global State for Serial Monitor (Needs careful management) ---
# Store serial connections per client session ID (sid)
# Structure: {sid: {'serial': serial_instance, 'thread': read_thread, 'stop_event': stop_event}}
serial_connections = {}

# --- Helper Functions ---
def allowed_file(filename):
    return '.' in filename and os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS

def find_serial_ports():
    ports = glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')
    ports.sort()
    return ports

def get_system_uptime():
    try:
        boot_time_timestamp = psutil.boot_time()
        elapsed_seconds = time.time() - boot_time_timestamp
        # Format nicely
        days, rem = divmod(elapsed_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        if days > 0:
            return f"{int(days)}d {int(hours)}h {int(minutes)}m"
        elif hours > 0:
            return f"{int(hours)}h {int(minutes)}m"
        else:
            return f"{int(minutes)}m {int(seconds)}s"

    except Exception as e:
        app.logger.error(f"Could not get uptime: {e}")
        return "N/A"

# ==================================================================
# === Homepage / Dashboard Route ===
# ==================================================================
@app.route('/')
def index():
    """Serves the main dashboard page."""
    hostname = socket.gethostname()
    uptime = get_system_uptime()
    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Jetson Dashboard</title>
        <script src="https://cdn.tailwindcss.com/3.4.3"></script>
    </head>
    <body class="bg-gray-200 p-10">
        <div class="container mx-auto max-w-4xl bg-white p-8 rounded-lg shadow-xl">
            <h1 class="text-3xl font-bold mb-6 text-center text-gray-800">Jetson Control Panel</h1>
            <div class="text-center mb-8 text-gray-600">
                <p>Hostname: <span class="font-semibold">{{ hostname }}</span></p>
                <p>System Uptime: <span class="font-semibold">{{ uptime }}</span></p>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <a href="/arduino-upload" class="block p-6 bg-blue-500 text-white rounded-lg shadow hover:bg-blue-600 transition text-center">
                    <h2 class="text-xl font-semibold mb-2">Arduino Uploader</h2>
                    <p>Compile and upload .ino sketches to connected Arduino boards.</p>
                </a>
                <a href="/arduino-serial" class="block p-6 bg-green-500 text-white rounded-lg shadow hover:bg-green-600 transition text-center">
                    <h2 class="text-xl font-semibold mb-2">Serial Monitor</h2>
                    <p>Connect to and monitor serial port communication in real-time.</p>
                </a>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(template, hostname=hostname, uptime=uptime)

# ==================================================================
# === Arduino Upload Functionality ===
# ==================================================================
@app.route('/arduino-upload')
def arduino_upload_page():
    """Serves the Arduino Uploader page."""
    # This HTML is basically the template from your previous working script
    # (with minor adjustments if needed, ensure IDs/names match JS)
    upload_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Arduino Web Uploader</title>
        <script src="https://cdn.tailwindcss.com/3.4.3"></script>
        <style>
            body { font-family: sans-serif; }
            #output { min-height: 100px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; word-wrap: break-word; }
            .upload-spinner { border: 4px solid rgba(0, 0, 0, 0.1); width: 24px; height: 24px; border-radius: 50%; border-left-color: #09f; animation: spin 1s ease infinite; display: inline-block; vertical-align: middle; margin-left: 10px; }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        </style>
    </head>
    <body class="bg-gray-100 p-8">
        <div class="container mx-auto max-w-2xl bg-white p-6 rounded-lg shadow-md">
            <div class="flex justify-between items-center mb-4">
                 <h1 class="text-2xl font-bold text-center text-gray-700 flex-grow">Upload Arduino Sketch</h1>
                 <a href="/" class="text-sm text-blue-600 hover:underline">&larr; Back to Dashboard</a>
            </div>

            <form id="uploadForm" class="space-y-4"> {# Removed method/enctype, handled by JS #}
                <div>
                    <label for="port" class="block text-sm font-medium text-gray-700 mb-1">Serial Port:</label>
                    <div class="flex items-center">
                        <select id="port" name="port"
                                class="mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
                            <option value="" selected>Detecting ports...</option> {# Default message #}
                        </select>
                        <button type="button" id="refreshPorts" title="Refresh Ports"
                                class="ml-2 p-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 110 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd" /></svg>
                        </button>
                    </div>
                     <p id="port-error" class="text-red-500 text-xs italic mt-1 hidden">Could not fetch ports.</p>
                     <p id="no-ports-found" class="text-yellow-600 text-xs italic mt-1 hidden">No serial ports detected. ('None' selected)</p>
                     <p id="port-required-error" class="text-red-500 text-xs italic mt-1 hidden">A valid serial port is required for uploading.</p>
                </div>

                <div>
                    <label for="fqbnSelect" class="block text-sm font-medium text-gray-700 mb-1">Board:</label>
                    <select id="fqbnSelect" name="fqbnSelected" required
                           class="mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
                        {% for value, name in common_fqbns.items() %}
                            <option value="{{ value }}" {% if value == 'arduino:avr:uno' %}selected{% endif %}>{{ name }}</option>
                        {% endfor %}
                    </select>
                    <input type="text" id="fqbnCustom" name="fqbnCustom" placeholder="Enter custom FQBN (e.g., arduino:avr:uno)"
                           class="mt-2 hidden w-full py-2 px-3 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
                     <p id="fqbn-error" class="text-red-500 text-xs italic mt-1 hidden">Please select or enter a Board FQBN.</p>
                </div>

                <div>
                    <label for="sketchFile" class="block text-sm font-medium text-gray-700 mb-1">Sketch .ino file:</label>
                    <input type="file" id="sketchFile" name="sketchFile" accept=".ino" required
                           class="mt-1 block w-full text-sm text-gray-500
                                  file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0
                                  file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100">
                     <p id="file-error" class="text-red-500 text-xs italic mt-1 hidden">Please select a .ino file.</p>
                </div>

                <div class="flex items-center justify-center space-x-4 pt-4">
                     <button type="button" id="compileButton"
                            class="inline-flex justify-center py-2 px-6 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50">
                        Compile / Verify
                    </button>
                     <button type="button" id="uploadButton"
                            class="inline-flex justify-center py-2 px-6 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 disabled:opacity-50">
                        Compile and Upload
                    </button>
                    <div id="spinner" class="upload-spinner hidden"></div>
                </div>
            </form>

            <div class="mt-8">
                <h2 class="text-lg font-semibold text-gray-800 mb-2">Output:</h2>
                <pre id="output" class="bg-gray-900 text-white p-4 rounded-md border border-gray-700 text-sm leading-relaxed"></pre>
            </div>
        </div>

        <script>
            // --- PASTE UPLOAD PAGE JAVASCRIPT HERE ---
            // (The entire <script> block from arduino_web_uploader_v2.py)
            // --- DOM Elements ---
            const portSelect = document.getElementById('port');
            const refreshButton = document.getElementById('refreshPorts');
            const uploadForm = document.getElementById('uploadForm');
            const outputArea = document.getElementById('output');
            const compileButton = document.getElementById('compileButton');
            const uploadButton = document.getElementById('uploadButton');
            const spinner = document.getElementById('spinner');
            const sketchFileInput = document.getElementById('sketchFile');
            const portErrorMsg = document.getElementById('port-error');
            const noPortsFoundMsg = document.getElementById('no-ports-found');
            const portRequiredErrorMsg = document.getElementById('port-required-error');
            const fileErrorMsg = document.getElementById('file-error');
            const fqbnSelect = document.getElementById('fqbnSelect');
            const fqbnCustom = document.getElementById('fqbnCustom');
            const fqbnErrorMsg = document.getElementById('fqbn-error');

            // --- Port Handling ---
            async function fetchPorts() {
                portSelect.disabled = true;
                portErrorMsg.classList.add('hidden');
                noPortsFoundMsg.classList.add('hidden');
                portRequiredErrorMsg.classList.add('hidden');
                portSelect.innerHTML = '<option value="" disabled selected>Refreshing ports...</option>';

                try {
                    // Use the correct API endpoint relative to the current page or root
                    const response = await fetch('/api/ports'); // Keep API at root
                    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                    const ports = await response.json();

                    portSelect.innerHTML = ''; // Clear existing options
                    const noneOption = document.createElement('option'); // Add "None" option
                    noneOption.value = ""; // Use empty string for "None"
                    noneOption.textContent = "None";
                    portSelect.appendChild(noneOption);

                    if (ports.length > 0) {
                        ports.forEach((port, index) => {
                            const option = document.createElement('option');
                            option.value = port;
                            option.textContent = port;
                            portSelect.appendChild(option);
                            // Auto-select the first *actual* port found
                            if (index === 0) {
                                option.selected = true;
                            }
                        });
                        portSelect.disabled = false;
                    } else {
                        noneOption.selected = true; // Select "None" if no ports found
                        noPortsFoundMsg.classList.remove('hidden');
                        portSelect.disabled = true; // Keep disabled if only "None"
                    }

                } catch (error) {
                    console.error('Error fetching ports:', error);
                    portSelect.innerHTML = '<option value="" disabled selected>Error loading</option>';
                    portErrorMsg.classList.remove('hidden');
                    portSelect.disabled = true;
                }
            }

            // --- FQBN Handling ---
            fqbnSelect.addEventListener('change', () => {
                fqbnCustom.classList.toggle('hidden', fqbnSelect.value !== 'other');
                if (fqbnSelect.value !== 'other') {
                    fqbnCustom.value = ''; // Clear custom input if dropdown changed away from other
                    fqbnErrorMsg.classList.add('hidden'); // Hide potential error
                    fqbnCustom.required = false;
                } else {
                     fqbnCustom.required = true; // Make custom required if selected
                }
            });

             // Trigger change on load in case 'Other...' is pre-selected (though unlikely with default)
            document.addEventListener('DOMContentLoaded', () => {
                fqbnSelect.dispatchEvent(new Event('change'));
            });


            // --- Action Handling (Compile or Upload) ---
            async function handleAction(actionType) {
                // --- Validation ---
                let isValid = true;
                fileErrorMsg.classList.add('hidden');
                portRequiredErrorMsg.classList.add('hidden');
                fqbnErrorMsg.classList.add('hidden');

                // 1. Check File
                if (!sketchFileInput.files || sketchFileInput.files.length === 0 || !sketchFileInput.files[0].name.toLowerCase().endsWith('.ino')) {
                    fileErrorMsg.classList.remove('hidden');
                    isValid = false;
                }

                // 2. Check Port (only required for Upload)
                if (actionType === 'compile_upload' && !portSelect.value) { // Check if port is "" (None)
                    portRequiredErrorMsg.classList.remove('hidden');
                    isValid = false;
                }

                 // 3. Check FQBN
                 let finalFqbn = '';
                 if (fqbnSelect.value === 'other') {
                     if (!fqbnCustom.value.trim()) {
                         fqbnErrorMsg.classList.remove('hidden');
                         isValid = false;
                     } else {
                         finalFqbn = fqbnCustom.value.trim();
                     }
                 } else if (!fqbnSelect.value) { // Should not happen with required, but check anyway
                      fqbnErrorMsg.classList.remove('hidden');
                      isValid = false;
                 }
                 else {
                      finalFqbn = fqbnSelect.value;
                 }


                if (!isValid) {
                    outputArea.textContent = 'Please fix the errors above before proceeding.';
                    outputArea.className = 'bg-red-100 text-red-700 p-4 rounded-md border border-red-300 text-sm leading-relaxed';
                    return;
                }

                // --- Proceed with Fetch ---
                compileButton.disabled = true;
                uploadButton.disabled = true;
                spinner.classList.remove('hidden');
                const actionText = actionType === 'compile_upload' ? 'Uploading' : 'Compiling';
                outputArea.textContent = `Processing request...\n${actionText} - this may take a minute...`;
                outputArea.className = 'bg-blue-100 text-blue-800 p-4 rounded-md border border-blue-300 text-sm leading-relaxed';

                const formData = new FormData(); // Don't use the form directly now
                formData.append('sketchFile', sketchFileInput.files[0]);
                formData.append('port', portSelect.value); // Send empty string if "None"
                formData.append('fqbn', finalFqbn); // Send the determined FQBN
                formData.append('action_type', actionType); // 'compile' or 'compile_upload'


                try {
                    const response = await fetch('/action', { // API endpoint stays at root
                        method: 'POST',
                        body: formData
                    });
                    const data = await response.json();
                    outputArea.textContent = data.output || 'No output received.';
                    outputArea.className = (response.ok && data.success)
                        ? 'bg-green-100 text-green-800 p-4 rounded-md border border-green-300 text-sm leading-relaxed'
                        : 'bg-red-100 text-red-700 p-4 rounded-md border border-red-300 text-sm leading-relaxed';
                } catch (error) {
                    console.error('Error during fetch:', error);
                    outputArea.textContent = `Client-side error during request: ${error}`;
                    outputArea.className = 'bg-red-100 text-red-700 p-4 rounded-md border border-red-300 text-sm leading-relaxed';
                } finally {
                    compileButton.disabled = false;
                    uploadButton.disabled = false;
                    spinner.classList.add('hidden');
                }
            }

            // --- Event Listeners ---
            refreshButton.addEventListener('click', fetchPorts);
            compileButton.addEventListener('click', () => handleAction('compile'));
            uploadButton.addEventListener('click', () => handleAction('compile_upload'));

            // Initial population of ports
            document.addEventListener('DOMContentLoaded', fetchPorts);
        </script>

    </body>
    </html>
    """
    return render_template_string(upload_template, common_fqbns=COMMON_FQBNS)

# API route for upload/compile actions (no change needed here)
@app.route('/action', methods=['POST'])
def perform_action():
    # --- PASTE ENTIRE '/action' ROUTE LOGIC HERE ---
    # (From arduino_web_uploader_v2.py)
    """Handles compile or compile+upload actions."""
    port = request.form.get('port') # Will be "" if "None" selected
    fqbn = request.form.get('fqbn') # The final FQBN is sent from JS
    action_type = request.form.get('action_type') # 'compile' or 'compile_upload'
    sketch_file = request.files.get('sketchFile')

    # --- Input Validation (Backend) ---
    if not action_type or action_type not in ['compile', 'compile_upload']:
         return jsonify({'success': False, 'output': 'Error: Invalid action specified.'}), 400
    if action_type == 'compile_upload' and not port:
        return jsonify({'success': False, 'output': 'Error: A serial port is required for uploading.'}), 400
    if not fqbn:
        return jsonify({'success': False, 'output': 'Error: Board FQBN not provided.'}), 400
    if not sketch_file or sketch_file.filename == '':
        return jsonify({'success': False, 'output': 'Error: No sketch file provided.'}), 400
    if not allowed_file(sketch_file.filename):
         return jsonify({'success': False, 'output': f'Error: Invalid file type.'}), 400

    # --- Secure File Handling ---
    outer_temp_dir = None
    try:
        outer_temp_dir = tempfile.mkdtemp(prefix='arduino_web_')
        app.logger.info(f"Created temp dir: {outer_temp_dir}")

        safe_filename = secure_filename(sketch_file.filename)
        sketch_name = os.path.splitext(safe_filename)[0]
        sketch_dir_path = os.path.join(outer_temp_dir, sketch_name)
        os.makedirs(sketch_dir_path)
        sketch_file_path = os.path.join(sketch_dir_path, safe_filename)
        sketch_file.save(sketch_file_path)
        app.logger.info(f"Saved sketch to: {sketch_file_path}")

        # --- Execute arduino-cli ---
        cmd = [ARDUINO_CLI_PATH, 'compile'] # Start with compile command

        if action_type == 'compile_upload':
            cmd.append('--upload') # Add upload flag if requested
            cmd.extend(['-p', port]) # Add port only if uploading

        cmd.extend(['--fqbn', fqbn])
        cmd.extend(['--log-level', 'info'])
        cmd.append(sketch_dir_path) # Target is the directory

        app.logger.info(f"Executing command: {' '.join(cmd)}")
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=ARDUINO_CLI_TIMEOUT)

        # --- Process Output ---
        cli_output = f"--- arduino-cli execution ({action_type}) ---\n"
        cli_output += f"Command: {' '.join(cmd)}\n"
        cli_output += f"FQBN: {fqbn}\n"
        if action_type == 'compile_upload':
             cli_output += f"Port: {port}\n"
        cli_output += f"Return Code: {process.returncode}\n\n"
        if process.stdout: cli_output += f"--- STDOUT ---\n{process.stdout.strip()}\n\n"
        if process.stderr: cli_output += f"--- STDERR ---\n{process.stderr.strip()}\n"

        app.logger.info(f"arduino-cli completed with code {process.returncode}")
        if process.returncode != 0: app.logger.warning(f"STDERR:\n{process.stderr}")

        success = process.returncode == 0
        http_status = 200 if success else 500
        return jsonify({'success': success, 'output': cli_output}), http_status

    # --- Error Handling ---
    except subprocess.TimeoutExpired:
        error_msg = f"Error: Command timed out after {ARDUINO_CLI_TIMEOUT}s."
        app.logger.error(error_msg)
        return jsonify({'success': False, 'output': error_msg}), 500
    except FileNotFoundError:
         error_msg = f"Error: '{ARDUINO_CLI_PATH}' not found. Check installation and PATH."
         app.logger.error(error_msg)
         return jsonify({'success': False, 'output': error_msg}), 500
    except Exception as e:
        error_msg = f"An unexpected server error occurred: {e}"
        app.logger.error(error_msg, exc_info=True)
        return jsonify({'success': False, 'output': error_msg}), 500
    # --- Cleanup ---
    finally:
        if outer_temp_dir and os.path.exists(outer_temp_dir):
            try:
                shutil.rmtree(outer_temp_dir)
                app.logger.info(f"Cleaned up temp dir: {outer_temp_dir}")
            except Exception as e:
                app.logger.error(f"Error cleaning temp dir {outer_temp_dir}: {e}")


# ==================================================================
# === Serial Monitor Functionality ===
# ==================================================================

# --- Serial Read Background Task ---
def read_serial_data(sid, ser_instance, stop_event):
    """Background thread function to read serial data and emit via WebSocket."""
    app.logger.info(f"Starting serial read thread for {sid} on {ser_instance.port}")
    while not stop_event.is_set():
        try:
            if ser_instance.in_waiting > 0:
                # Read available bytes, decode cautiously
                try:
                    line = ser_instance.readline()
                    decoded_line = line.decode('utf-8', errors='replace').strip()
                    if decoded_line: # Only emit if there's content
                         socketio.emit('serial_data', {'data': decoded_line}, to=sid)
                         # Short sleep needed even if data received, to yield
                         socketio.sleep(0.01)

                except serial.SerialException as e:
                    app.logger.error(f"Serial error for {sid} on {ser_instance.port}: {e}")
                    socketio.emit('serial_error', {'error': f'Serial Error: {e}'}, to=sid)
                    # Attempt graceful exit if port closed/error
                    stop_event.set()
                    break # Exit loop on serial error
                except UnicodeDecodeError as ue:
                     # Handle cases where we receive non-UTF8 data
                     # Maybe emit raw bytes as hex? For now, just note the error
                     app.logger.warning(f"Unicode decode error for {sid}: {ue}. Data: {line!r}")
                     socketio.emit('serial_data', {'data': f'[Decode Error: {line!r}]'}, to=sid)
                     socketio.sleep(0.01)

            else:
                # Sleep briefly when no data to prevent high CPU usage
                socketio.sleep(0.05) # Longer sleep if nothing waiting

        except Exception as e:
            # Catch unexpected errors in the read loop
            app.logger.error(f"Unexpected error in serial read loop for {sid}: {e}", exc_info=True)
            socketio.emit('serial_error', {'error': f'Unexpected read loop error: {e}'}, to=sid)
            stop_event.set() # Ensure thread stops
            break # Exit loop

    # Cleanup after loop finishes (either by stop_event or error)
    if ser_instance.is_open:
        try:
            ser_instance.close()
            app.logger.info(f"Closed serial port {ser_instance.port} for {sid} from read thread.")
        except Exception as e:
             app.logger.error(f"Error closing serial port for {sid} in read thread: {e}")

    app.logger.info(f"Serial read thread stopped for {sid} on port {ser_instance.port}")


@app.route('/arduino-serial')
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
            /* Style for autoscroll checkbox */
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

             <div id="statusMessage" class="mb-4 p-3 rounded-md text-sm hidden"></div>

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
                 statusMessage.classList.toggle('hidden', false);
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
                // Sanitize potentially harmful HTML? For now, just append text
                 const textNode = document.createTextNode(text + '\\n'); // Add newline
                 outputArea.appendChild(textNode);
                 // Handle autoscroll
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
                    const response = await fetch('/api/ports'); // Use shared API endpoint
                    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                    const ports = await response.json();

                    portSelect.innerHTML = ''; // Clear existing options
                    if (ports.length > 0) {
                        ports.forEach((port, index) => {
                            const option = document.createElement('option');
                            option.value = port;
                            option.textContent = port;
                            portSelect.appendChild(option);
                            if (index === 0) option.selected = true; // Select first found
                        });
                         portSelect.disabled = false;
                    } else {
                        portSelect.innerHTML = '<option value="" disabled selected>No ports found</option>';
                        noPortsFoundMsg.classList.remove('hidden');
                    }
                } catch (error) {
                    console.error('Error fetching serial ports:', error);
                    portSelect.innerHTML = '<option value="" disabled selected>Error loading</option>';
                    portErrorMsg.classList.remove('hidden');
                } finally {
                    portSelect.disabled = portSelect.options.length === 0 || isConnected;
                }
            }

            // --- Socket.IO Event Handlers ---
            socket.on('connect', () => {
                console.log('Socket.IO connected');
                appendOutput('[System: Connected to server]');
                // Fetch ports on initial connect
                fetchSerialPorts();
            });

            socket.on('disconnect', (reason) => {
                console.log('Socket.IO disconnected:', reason);
                appendOutput(`[System: Disconnected from server - ${reason}]`);
                setUIConnected(false); // Ensure UI reflects disconnected state
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
                } else if (msg.status === 'connected') {
                     setUIConnected(true);
                }
            });

             socket.on('serial_error', (msg) => { // Specific error channel
                console.error('Serial Error:', msg);
                const error_message = msg.error || JSON.stringify(msg);
                appendOutput(`[Serial ERROR: ${error_message}]`);
                showStatus(`Serial Error: ${error_message}`, true);
                setUIConnected(false); // Force disconnect UI on serial error
            });

            socket.on('serial_data', (msg) => {
                appendOutput(msg.data);
            });

            // --- Button/Input Event Listeners ---
            refreshButton.addEventListener('click', fetchSerialPorts);

            connectButton.addEventListener('click', () => {
                if (isConnected) {
                    // --- Disconnect ---
                    socket.emit('serial_disconnect');
                    appendOutput('[System: Disconnecting...]');
                } else {
                    // --- Connect ---
                    const port = portSelect.value;
                    const baud = baudRateSelect.value;
                    if (!port) {
                        showStatus('Please select a valid serial port.', true);
                        return;
                    }
                    connectButton.disabled = true; // Disable button during connection attempt
                    appendOutput(`[System: Connecting to ${port} at ${baud} baud...]`);
                    socket.emit('serial_connect', { port: port, baud_rate: parseInt(baud) });
                     // Re-enable button after a short delay in case connect fails quickly
                     setTimeout(() => { if (!isConnected) connectButton.disabled = false; } , 2000);
                }
            });

            sendButton.addEventListener('click', () => {
                const dataToSend = inputField.value;
                if (dataToSend && isConnected) {
                    socket.emit('serial_send', { data: dataToSend });
                    // Optionally clear input field after sending
                    // inputField.value = '';
                }
            });

            inputField.addEventListener('keypress', (event) => {
                // Allow sending on Enter key press
                if (event.key === 'Enter' && !sendButton.disabled) {
                    sendButton.click();
                }
            });

            clearOutputButton.addEventListener('click', () => {
                 outputArea.innerHTML = ''; // Clear the output area
            });

            // Initial setup
            document.addEventListener('DOMContentLoaded', () => {
                 // Fetch ports initially, but Socket connection will trigger it again
                 // fetchSerialPorts();
                 setUIConnected(false); // Start in disconnected state
            });

        </script>
    </body>
    </html>
    """
    return render_template_string(serial_template, common_baud_rates=COMMON_BAUD_RATES)

# ==================================================================
# === Shared API Routes ===
# ==================================================================
@app.route('/api/ports')
def api_get_ports():
    """Shared API endpoint to get serial ports for both pages."""
    # Check if called from a WebSocket context (optional, could add auth later)
    # is_websocket = request.sid is not None if using Flask-SocketIO sessions

    try:
        ports = find_serial_ports()
        return jsonify(ports)
    except Exception as e:
        app.logger.error(f"Error finding serial ports: {e}", exc_info=True)
        return jsonify({"error": "Failed to retrieve ports"}), 500


# ==================================================================
# === Socket.IO Event Handlers for Serial Monitor ===
# ==================================================================

@socketio.on('connect')
def handle_connect():
    """Client connected via WebSocket."""
    app.logger.info(f"Client connected: {request.sid}")
    emit('serial_status', {'status': 'connected_server', 'message': 'Connected to server'})

@socketio.on('disconnect')
def handle_disconnect():
    """Client disconnected."""
    app.logger.info(f"Client disconnected: {request.sid}")
    # Clean up any serial connection associated with this client
    cleanup_serial_connection(request.sid)

@socketio.on('serial_connect')
def handle_serial_connect(json_data):
    """Handle client request to connect to a serial port."""
    sid = request.sid
    port = json_data.get('port')
    baud_rate = json_data.get('baud_rate')
    app.logger.info(f"Connect request from {sid} for {port} @ {baud_rate} baud")

    if not port or not baud_rate:
        emit('serial_status', {'status': 'error', 'message': 'Port and baud rate required.'}, to=sid)
        return

    # Prevent multiple connections from the same client? Or handle reconnect?
    if sid in serial_connections:
        app.logger.warning(f"{sid} requested connect but already has a connection.")
        emit('serial_status', {'status': 'error', 'message': 'Already connected or previous connection unclean.'}, to=sid)
        # Maybe try cleanup first?
        cleanup_serial_connection(sid)
        # return # Optionally prevent reconnect attempt immediately

    try:
        # Attempt to open serial port
        ser = serial.Serial(port, baud_rate, timeout=1) # 1-second read timeout
        if not ser.is_open:
             # This shouldn't happen if constructor succeeds, but check anyway
             raise serial.SerialException(f"Failed to open {port} (is_open is false)")

        app.logger.info(f"Successfully opened {port} for {sid}")

        # Start background thread for reading
        stop_event = threading.Event()
        read_thread = socketio.start_background_task( # Use socketio's background task manager
            read_serial_data, sid, ser, stop_event
        )

        # Store connection details
        serial_connections[sid] = {'serial': ser, 'thread': read_thread, 'stop_event': stop_event}

        emit('serial_status', {'status': 'connected', 'message': f'Connected to {port}'}, to=sid)

    except serial.SerialException as e:
        app.logger.error(f"Failed to open serial port {port} for {sid}: {e}")
        emit('serial_status', {'status': 'error', 'message': f'Error opening {port}: {e}'}, to=sid)
    except Exception as e:
        app.logger.error(f"Unexpected error during serial connect for {sid}: {e}", exc_info=True)
        emit('serial_status', {'status': 'error', 'message': f'Unexpected server error: {e}'}, to=sid)


@socketio.on('serial_disconnect')
def handle_serial_disconnect():
    """Handle client request to disconnect from serial port."""
    sid = request.sid
    app.logger.info(f"Disconnect request from {sid}")
    if cleanup_serial_connection(sid):
         emit('serial_status', {'status': 'disconnected', 'message': 'Disconnected.'}, to=sid)
    else:
         # Already disconnected or no connection found
         emit('serial_status', {'status': 'disconnected', 'message': 'Not connected.'}, to=sid)


@socketio.on('serial_send')
def handle_serial_send(json_data):
    """Handle data sent from client to be written to serial port."""
    sid = request.sid
    data_to_send = json_data.get('data')

    if sid in serial_connections and data_to_send is not None:
        conn = serial_connections[sid]
        ser = conn['serial']
        try:
            if ser and ser.is_open:
                 # Add newline? Often expected by Arduino sketches reading Serial.println()
                 data_with_newline = data_to_send + '\n'
                 ser.write(data_with_newline.encode('utf-8', errors='replace'))
                 #app.logger.debug(f"Sent to {ser.port} from {sid}: {data_with_newline!r}")
            else:
                 app.logger.warning(f"Send attempt from {sid} but serial not open/available.")
                 emit('serial_error', {'error': 'Cannot send, serial port not open.'}, to=sid)

        except serial.SerialException as e:
            app.logger.error(f"Error writing to serial port for {sid}: {e}")
            emit('serial_error', {'error': f'Serial Write Error: {e}'}, to=sid)
            cleanup_serial_connection(sid) # Disconnect on write error
        except Exception as e:
            app.logger.error(f"Unexpected error sending serial data for {sid}: {e}")
            emit('serial_error', {'error': f'Unexpected Send Error: {e}'}, to=sid)


def cleanup_serial_connection(sid):
    """Safely close serial port and stop read thread for a given SID."""
    if sid in serial_connections:
        conn = serial_connections.pop(sid) # Remove from dict immediately
        ser = conn.get('serial')
        stop_event = conn.get('stop_event')
        thread = conn.get('thread') # Not strictly needed for stopping, but good practice

        app.logger.info(f"Cleaning up serial connection for {sid}...")

        # Signal the thread to stop
        if stop_event:
            stop_event.set()

        # Close the serial port (thread should also try this on exit)
        if ser and ser.is_open:
            try:
                ser.close()
                app.logger.info(f"Closed serial port {ser.port} during cleanup for {sid}")
            except Exception as e:
                app.logger.error(f"Error closing serial port {ser.port} for {sid}: {e}")

        # Optional: Wait briefly for thread to join (can block if thread hangs)
        # if thread:
        #    thread.join(timeout=1.0) # Wait max 1 second
        #    if thread.is_alive():
        #        app.logger.warning(f"Serial read thread for {sid} did not exit cleanly.")

        return True # Indicate cleanup was attempted
    return False # Indicate no connection found for SID


# ==================================================================
# === Main Execution ===
# ==================================================================
if __name__ == '__main__':
    app.logger.info(f"Starting Arduino Dashboard on http://{APP_HOST}:{APP_PORT}")
    # Use socketio.run() and specify eventlet for async operations
    socketio.run(app, host=APP_HOST, port=APP_PORT, debug=False, use_reloader=False)
    # use_reloader=False is important with eventlet/gevent background tasks