from flask import Blueprint, request, jsonify, render_template_string
import subprocess
import tempfile
import shutil
import os
from werkzeug.utils import secure_filename

# Import necessary items from shared modules
import config
import helpers

# Create Blueprint
uploader_bp = Blueprint('uploader', __name__)

# Define server sketches directory
if not hasattr(config, 'SERVER_SKETCHES_DIR'):
    config.SERVER_SKETCHES_DIR = os.path.expanduser('~/jetbot-dashboard')

# --- Route for the Uploader Page ---
@uploader_bp.route('/arduino-upload')
def arduino_upload_page():
    """Serves the Arduino Uploader page with a file browser."""
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
                <a href="/" class="text-blue-600 hover:text-blue-700">
                    ← 🏠︎
                </a>
                <h1 class="text-2xl font-bold text-center text-gray-700 flex-grow">Upload Arduino Sketch</h1>
                <div class="w-6 h-6 invisible"></div>
            </div>

            <form id="uploadForm" class="space-y-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Sketch Source:</label>
                    <div class="flex items-center space-x-4">
                        <label class="inline-flex items-center">
                            <input type="radio" name="sketchSource" value="local" checked class="form-radio">
                            <span class="ml-2">Upload from local machine</span>
                        </label>
                        <label class="inline-flex items-center">
                            <input type="radio" name="sketchSource" value="server" class="form-radio">
                            <span class="ml-2">Select from server</span>
                        </label>
                    </div>
                </div>

                <div id="localSketch" class="mt-2">
                    <label for="sketchFile" class="block text-sm font-medium text-gray-700 mb-1">Sketch .ino file:</label>
                    <input type="file" id="sketchFile" name="sketchFile" accept=".ino"
                           class="mt-1 block w-full text-sm text-gray-500
                                  file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0
                                  file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100">
                </div>
                <div id="serverSketch" class="mt-2 hidden">
                    <div class="flex justify-between items-center mb-2">
                        <div id="currentPath" class="text-sm text-gray-600">Current directory: /</div>
                    </div>
                    <ul id="fileList" class="list-disc pl-5 space-y-1"></ul>
                    <p id="selectedSketch" class="text-sm text-gray-600 mt-2 hidden">Selected sketch: <span id="selectedPath"></span></p>
                </div>
                <p id="file-error" class="text-red-500 text-xs italic mt-1 hidden">Please select a .ino file.</p>

                <div>
                    <label for="port" class="block text-sm font-medium text-gray-700 mb-1">Serial Port:</label>
                    <div class="flex items-center">
                        <select id="port" name="port"
                                class="mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm">
                            <option value="" selected>Detecting ports...</option>
                        </select>
                        <button type="button" id="refreshPorts" title="Refresh Ports"
                                class="ml-2 p-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                                <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 110 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd" />
                            </svg>
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
            const sketchSourceRadios = document.querySelectorAll('input[name="sketchSource"]');
            const localSketchDiv = document.getElementById('localSketch');
            const serverSketchDiv = document.getElementById('serverSketch');
            const portErrorMsg = document.getElementById('port-error');
            const noPortsFoundMsg = document.getElementById('no-ports-found');
            const portRequiredErrorMsg = document.getElementById('port-required-error');
            const fileErrorMsg = document.getElementById('file-error');
            const fqbnSelect = document.getElementById('fqbnSelect');
            const fqbnCustom = document.getElementById('fqbnCustom');
            const fqbnErrorMsg = document.getElementById('fqbn-error');
            const selectedSketchMsg = document.getElementById('selectedSketch');
            const selectedPathSpan = document.getElementById('selectedPath');
            const currentPathDiv = document.getElementById('currentPath');
            const fileListUl = document.getElementById('fileList');

            let currentPath = '';
            let selectedInoFile = null;

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

                    portSelect.innerHTML = '';
                    const noneOption = document.createElement('option');
                    noneOption.value = "";
                    noneOption.textContent = "None";
                    portSelect.appendChild(noneOption);

                    if (ports.length > 0) {
                        ports.forEach((port, index) => {
                            const option = document.createElement('option');
                            option.value = port;
                            option.textContent = port;
                            portSelect.appendChild(option);
                            if (index === 0) option.selected = true;
                        });
                        portSelect.disabled = false;
                    } else {
                        noneOption.selected = true;
                        noPortsFoundMsg.classList.remove('hidden');
                        portSelect.disabled = true;
                    }
                } catch (error) {
                    console.error('Error fetching ports:', error);
                    portSelect.innerHTML = '<option value="" disabled selected>Error loading</option>';
                    portErrorMsg.classList.remove('hidden');
                    portSelect.disabled = true;
                }
            }

            // --- Directory Browsing ---
            async function fetchDirectory(path) {
                try {
                    const response = await fetch(`/api/browse?path=${encodeURIComponent(path)}`);
                    if (!response.ok) throw new Error('Failed to fetch directory');
                    const data = await response.json();
                    currentPath = path;
                    currentPathDiv.textContent = `Current directory: /${path}`;

                    fileListUl.innerHTML = '';
                    if (path) {
                        const parentItem = document.createElement('li');
                        parentItem.textContent = '[DIR] ..';
                        parentItem.classList.add('cursor-pointer', 'text-blue-600');
                        parentItem.addEventListener('click', () => {
                            const parentPath = path.split('/').slice(0, -1).join('/');
                            fetchDirectory(parentPath);
                        });
                        fileListUl.appendChild(parentItem);
                    }

                    data.directories.forEach(dir => {
                        const item = document.createElement('li');
                        item.textContent = `[DIR] ${dir}`;
                        item.classList.add('cursor-pointer', 'text-blue-600');
                        item.addEventListener('click', () => {
                            const newPath = path ? `${path}/${dir}` : dir;
                            fetchDirectory(newPath);
                        });
                        fileListUl.appendChild(item);
                    });

                    data.files.forEach(file => {
                        if (file.endsWith('.ino')) {
                            const item = document.createElement('li');
                            item.textContent = file;
                            item.classList.add('cursor-pointer', 'text-blue-600');
                            item.addEventListener('click', () => {
                                selectedInoFile = path ? `${path}/${file}` : file;
                                selectedPathSpan.textContent = selectedInoFile;
                                selectedSketchMsg.classList.remove('hidden');
                            });
                            fileListUl.appendChild(item);
                        } else {
                            const item = document.createElement('li');
                            item.textContent = file;
                            item.classList.add('text-gray-600');
                            fileListUl.appendChild(item);
                        }
                    });
                } catch (error) {
                    console.error('Error fetching directory:', error);
                    fileListUl.innerHTML = '<li class="text-red-500">Error loading directory</li>';
                }
            }

            // --- Sketch Source Toggle ---
            sketchSourceRadios.forEach(radio => {
                radio.addEventListener('change', () => {
                    if (radio.value === 'local') {
                        localSketchDiv.classList.remove('hidden');
                        serverSketchDiv.classList.add('hidden');
                    } else {
                        localSketchDiv.classList.add('hidden');
                        serverSketchDiv.classList.remove('hidden');
                        if (fileListUl.children.length === 0) {
                            fetchDirectory('');
                        }
                    }
                });
            });

            // --- FQBN Handling ---
            fqbnSelect.addEventListener('change', () => {
                fqbnCustom.classList.toggle('hidden', fqbnSelect.value !== 'other');
                if (fqbnSelect.value !== 'other') {
                    fqbnCustom.value = '';
                    fqbnErrorMsg.classList.add('hidden');
                    fqbnCustom.required = false;
                } else {
                    fqbnCustom.required = true;
                }
            });

            // --- Action Handling ---
            async function handleAction(actionType) {
                let isValid = true;
                fileErrorMsg.classList.add('hidden');
                portRequiredErrorMsg.classList.add('hidden');
                fqbnErrorMsg.classList.add('hidden');

                const sketchSource = document.querySelector('input[name="sketchSource"]:checked').value;
                if (sketchSource === 'local') {
                    if (!sketchFileInput.files || sketchFileInput.files.length === 0 || !sketchFileInput.files[0].name.toLowerCase().endsWith('.ino')) {
                        fileErrorMsg.textContent = "Please select a .ino file.";
                        fileErrorMsg.classList.remove('hidden');
                        isValid = false;
                    }
                } else {
                    if (!selectedInoFile) {
                        fileErrorMsg.textContent = "Please select a .ino file from the server.";
                        fileErrorMsg.classList.remove('hidden');
                        isValid = false;
                    }
                }

                if (actionType === 'compile_upload' && !portSelect.value) {
                    portRequiredErrorMsg.classList.remove('hidden');
                    isValid = false;
                }

                let finalFqbn = '';
                if (fqbnSelect.value === 'other') {
                    if (!fqbnCustom.value.trim()) {
                        fqbnErrorMsg.classList.remove('hidden');
                        isValid = false;
                    } else {
                        finalFqbn = fqbnCustom.value.trim();
                    }
                } else if (!fqbnSelect.value) {
                    fqbnErrorMsg.classList.remove('hidden');
                    isValid = false;
                } else {
                    finalFqbn = fqbnSelect.value;
                }

                if (!isValid) {
                    outputArea.textContent = 'Please fix the errors above before proceeding.';
                    outputArea.className = 'bg-red-100 text-red-700 p-4 rounded-md border border-red-300 text-sm leading-relaxed';
                    return;
                }

                compileButton.disabled = true;
                uploadButton.disabled = true;
                spinner.classList.remove('hidden');
                const actionText = actionType === 'compile_upload' ? 'Uploading' : 'Compiling';
                outputArea.textContent = `Processing request...\n${actionText} - this may take a minute...`;
                outputArea.className = 'bg-blue-100 text-blue-800 p-4 rounded-md border border-blue-300 text-sm leading-relaxed';

                const formData = new FormData();
                formData.append('sketchSource', sketchSource);
                if (sketchSource === 'local') {
                    formData.append('sketchFile', sketchFileInput.files[0]);
                } else {
                    formData.append('serverSketch', selectedInoFile);
                }
                formData.append('port', portSelect.value);
                formData.append('fqbn', finalFqbn);
                formData.append('action_type', actionType);

                try {
                    const response = await fetch('/action', {
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

            // --- Ensure "Upload from local machine" is selected on page load ---
            document.addEventListener('DOMContentLoaded', () => {
                const localRadio = document.querySelector('input[name="sketchSource"][value="local"]');
                localRadio.checked = true;
                localRadio.dispatchEvent(new Event('change')); // Trigger UI update
                fetchPorts();
                fqbnSelect.dispatchEvent(new Event('change'));
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(upload_template, common_fqbns=config.COMMON_FQBNS)

# --- API Route for Browsing Directories ---
@uploader_bp.route('/api/browse')
def api_browse():
    """API endpoint to browse directories and list .ino files within SERVER_SKETCHES_DIR."""
    base_dir = config.SERVER_SKETCHES_DIR
    relative_path = request.args.get('path', '')
    full_path = os.path.realpath(os.path.join(base_dir, relative_path))

    if not full_path.startswith(base_dir):
        return jsonify({"error": "Access denied"}), 403
    if not os.path.isdir(full_path):
        return jsonify({"error": "Directory not found"}), 404

    try:
        entries = os.listdir(full_path)
        directories = [e for e in entries if os.path.isdir(os.path.join(full_path, e))]
        files = [e for e in entries if e.endswith('.ino') and os.path.isfile(os.path.join(full_path, e))]
        return jsonify({"directories": directories, "files": files})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- API Route for Compile/Upload Actions ---
# --- API Route for Compile/Upload Actions ---
@uploader_bp.route('/action', methods=['POST'])
def perform_action():
    """Handles compile or compile+upload actions."""
    port = request.form.get('port')
    fqbn = request.form.get('fqbn')
    action_type = request.form.get('action_type')
    sketch_source = request.form.get('sketchSource')
    sketch_file = request.files.get('sketchFile') if sketch_source == 'local' else None
    server_sketch = request.form.get('serverSketch') if sketch_source == 'server' else None

    # Input Validation
    if not action_type or action_type not in ['compile', 'compile_upload']:
        return jsonify({'success': False, 'output': 'Error: Invalid action specified.'}), 400
    if action_type == 'compile_upload' and not port:
        return jsonify({'success': False, 'output': 'Error: A serial port is required for uploading.'}), 400
    if not fqbn:
        return jsonify({'success': False, 'output': 'Error: Board FQBN not provided.'}), 400
    if sketch_source not in ['local', 'server']:
        return jsonify({'success': False, 'output': 'Error: Invalid sketch source.'}), 400
    if sketch_source == 'local' and (not sketch_file or sketch_file.filename == '' or not helpers.allowed_file(sketch_file.filename)):
        return jsonify({'success': False, 'output': 'Error: Invalid or no sketch file provided.'}), 400
    if sketch_source == 'server' and not server_sketch:
        return jsonify({'success': False, 'output': 'Error: No server sketch selected.'}), 400

    # File Handling
    outer_temp_dir = None
    sketch_path = None
    try:
        if sketch_source == 'local':
            # Create a temporary directory named after the .ino file (without .ino extension)
            safe_filename = secure_filename(sketch_file.filename)
            sketch_name = os.path.splitext(safe_filename)[0]
            outer_temp_dir = tempfile.mkdtemp(prefix='arduino_web_')
            sketch_dir = os.path.join(outer_temp_dir, sketch_name)
            os.makedirs(sketch_dir, exist_ok=True)
            sketch_file_path = os.path.join(sketch_dir, safe_filename)
            sketch_file.save(sketch_file_path)
            sketch_path = sketch_dir
        elif sketch_source == 'server':
            # Validate server sketch
            server_sketch_path = os.path.join(config.SERVER_SKETCHES_DIR, server_sketch)
            if not os.path.isfile(server_sketch_path) or not server_sketch_path.lower().endswith('.ino'):
                return jsonify({'success': False, 'output': 'Error: Selected path is not a .ino file.'}), 400
            
            # Create a temporary directory named after the .ino file (without .ino extension)
            safe_filename = secure_filename(os.path.basename(server_sketch))
            sketch_name = os.path.splitext(safe_filename)[0]
            outer_temp_dir = tempfile.mkdtemp(prefix='arduino_web_')
            sketch_dir = os.path.join(outer_temp_dir, sketch_name)
            os.makedirs(sketch_dir, exist_ok=True)
            sketch_file_path = os.path.join(sketch_dir, safe_filename)
            
            # Copy the server .ino file to the temporary directory
            shutil.copy(server_sketch_path, sketch_file_path)
            sketch_path = sketch_dir

        # Execute arduino-cli
        cmd = [config.ARDUINO_CLI_PATH, 'compile']
        if action_type == 'compile_upload':
            cmd.append('--upload')
            cmd.extend(['-p', port])
        cmd.extend(['--fqbn', fqbn])
        cmd.extend(['--log-level', 'info'])
        cmd.append(sketch_path)

        process = subprocess.run(cmd, capture_output=True, text=True, timeout=config.ARDUINO_CLI_TIMEOUT)

        # Process Output
        cli_output = f"--- arduino-cli execution ({action_type}) ---\n"
        cli_output += f"Command: {' '.join(cmd)}\nFQBN: {fqbn}\n"
        if action_type == 'compile_upload': cli_output += f"Port: {port}\n"
        cli_output += f"Return Code: {process.returncode}\n\n"
        if process.stdout: cli_output += f"--- STDOUT ---\n{process.stdout.strip()}\n\n"
        if process.stderr: cli_output += f"--- STDERR ---\n{process.stderr.strip()}\n"

        success = process.returncode == 0
        http_status = 200 if success else 500
        return jsonify({'success': success, 'output': cli_output}), http_status

    except subprocess.TimeoutExpired:
        error_msg = f"Error: Command timed out after {config.ARDUINO_CLI_TIMEOUT}s."
        return jsonify({'success': False, 'output': error_msg}), 500
    except FileNotFoundError:
        error_msg = f"Error: '{config.ARDUINO_CLI_PATH}' not found."
        return jsonify({'success': False, 'output': error_msg}), 500
    except Exception as e:
        error_msg = f"An unexpected server error occurred: {e}"
        return jsonify({'success': False, 'output': error_msg}), 500
    finally:
        if outer_temp_dir and os.path.exists(outer_temp_dir):
            try:
                shutil.rmtree(outer_temp_dir)
            except Exception as e:
                pass

# --- API Route for Getting Ports ---
@uploader_bp.route('/api/ports')
def api_get_ports():
    """Shared API endpoint to get serial ports."""
    try:
        ports = helpers.find_serial_ports()
        return jsonify(ports)
    except Exception as e:
        return jsonify({"error": "Failed to retrieve ports"}), 500