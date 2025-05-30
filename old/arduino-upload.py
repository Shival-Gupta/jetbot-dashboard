#!/usr/bin/env python3
import os
import glob
import subprocess
import tempfile
import shutil
import logging
from flask import Flask, request, render_template_string, jsonify
from werkzeug.utils import secure_filename
import json # Added for parsing board list potentially later

# --- Configuration ---
APP_HOST = '0.0.0.0'  # Listen on all network interfaces
APP_PORT = 6001       # Port for the web server - Changed as requested
ALLOWED_EXTENSIONS = {'.ino'}
ARDUINO_CLI_TIMEOUT = 180 # Timeout in seconds
ARDUINO_CLI_PATH = '/usr/local/bin/arduino-cli' # Assumes it's in the system PATH

# Common FQBNs (Value: User-Friendly Name)
COMMON_FQBNS = {
    "arduino:avr:uno": "Arduino Uno",
    "arduino:avr:nano": "Arduino Nano (ATmega328P)",
    "arduino:avr:mega": "Arduino Mega or Mega 2560",
    "arduino:samd:mkr1000": "Arduino MKR 1000",
    "esp32:esp32:esp32": "ESP32 Dev Module",
    "esp32:esp32:nodemcu-32s": "NodeMCU-32S",
    "esp8266:esp8266:nodemcuv2": "NodeMCU 1.0 (ESP-12E)",
    "esp8266:esp8266:d1_mini": "WEMOS D1 Mini",
    "other": "Other..." # Special value for custom input
}

# --- Flask App Setup ---
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Helper Functions ---
def allowed_file(filename):
    """Checks if the uploaded file has an allowed extension."""
    return '.' in filename and \
           os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS

def find_serial_ports():
    """Detects potential Arduino serial ports."""
    ports = glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')
    ports.sort() # Consistent order
    return ports

# --- HTML Template ---
# Note: COMMON_FQBNS dictionary is passed to the template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Arduino Web Uploader V2</title>
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
        <h1 class="text-2xl font-bold mb-6 text-center text-gray-700">Arduino Sketch Uploader</h1>

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
                 <p id="no-ports-found" class="text-yellow-600 text-xs italic mt-1 hidden">No serial ports detected. Check connection. ('None' selected)</p>
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
                const response = await fetch('/api/ports');
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
                const response = await fetch('/action', { // Changed endpoint
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

# --- Flask Routes ---
@app.route('/')
def index():
    """Serves the main HTML page, passing common FQBNs."""
    return render_template_string(HTML_TEMPLATE, common_fqbns=COMMON_FQBNS)

@app.route('/api/ports')
def api_get_ports():
    """Returns a JSON list of detected serial ports."""
    try:
        ports = find_serial_ports()
        return jsonify(ports)
    except Exception as e:
        app.logger.error(f"Error finding serial ports: {e}", exc_info=True)
        return jsonify({"error": "Failed to retrieve ports"}), 500

# Renamed route to handle both actions
@app.route('/action', methods=['POST'])
def perform_action():
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

# --- Main Execution ---
if __name__ == '__main__':
    app.logger.info(f"Starting Arduino Web Uploader V2 on http://{APP_HOST}:{APP_PORT}")
    app.run(host=APP_HOST, port=APP_PORT, debug=False) # Keep debug=False for stability