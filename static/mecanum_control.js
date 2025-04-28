// ~/jetbot-dashboard/static/mecanum_control.js

document.addEventListener('DOMContentLoaded', () => {
    const PWM_MAX = 255; // Should match backend/Arduino
    const GAMEPAD_AXIS_THRESHOLD = 0.15; // Deadzone for gamepad sticks
    const GAMEPAD_POLL_INTERVAL = 100; // Milliseconds

    // --- DOM Elements ---
    const messageArea = document.getElementById('message-area');
    const serialStatusText = document.getElementById('serial-status-text');
    const serialPortDisplay = document.getElementById('serial-port-display');
    const btnConnectSerial = document.getElementById('btn-connect-serial');
    const btnDisconnectSerial = document.getElementById('btn-disconnect-serial');
    const btnSaveConfig = document.getElementById('btn-save-config');
    const btnResetConfig = document.getElementById('btn-reset-config');
    const controlButtons = document.querySelectorAll('.control-button');
    const mappingSelects = document.querySelectorAll('#mecanum-config-form fieldset:nth-of-type(1) select'); // Specific selector
    const calibrationInputs = document.querySelectorAll('#mecanum-config-form fieldset:nth-of-type(2) input');
    const scalingInputs = document.querySelectorAll('#mecanum-config-form fieldset:nth-of-type(3) input');
    const advancedInputs = document.querySelectorAll('#mecanum-config-form fieldset:nth-of-type(4) input');
    const gamepadStatus = document.getElementById('gamepad-status');
    const warningMessage = document.getElementById('serial-warning'); // Add an ID to the warning <p> tag if you want to hide/show it

    // --- State Variables ---
    let keysPressed = {};
    let gamepad = null;
    let gamepadPollIntervalId = null;
    let lastGamepadCommandKey = null; // Track last sent command via gamepad
    let lastKeyboardCommandKey = null; // Track last sent command via keyboard
    let isSerialConnected = false; // Track connection state locally
    let currentConfig = {}; // Store config locally

    // --- Utility Functions ---
    function showMessage(msg, isError = false, duration = 5000) {
        if (!messageArea) return;
        messageArea.textContent = msg;
        messageArea.style.color = isError ? '#f44336' : '#4CAF50'; // Red or Green
        if (duration > 0) {
            setTimeout(() => {
                if (messageArea.textContent === msg) { // Clear only if the message hasn't changed
                     messageArea.textContent = '';
                }
             }, duration);
        }
    }

    // --- SocketIO Setup ---
    const socket = io('/mecanum', {
        reconnectionAttempts: 3, // Try to reconnect a few times
        timeout: 10000 // Connection timeout
    });

    // --- API Fetch Helper (Still needed for config GET/POST) ---
    async function fetchApi(url, options = {}) {
        try {
            // Add cache-busting parameter for GET requests if needed
            const getUrl = options.method === 'GET' ? `${url}?t=${Date.now()}` : url;

            const response = await fetch(getUrl, options);
            if (!response.ok) {
                let errorData;
                try {
                    errorData = await response.json();
                } catch (e) {
                    errorData = { message: `HTTP error! Status: ${response.status} ${response.statusText}` };
                }
                throw new Error(errorData.message || `HTTP error! status: ${response.status}`);
            }
             // Handle cases where the response might be empty (e.g., 204 No Content)
            const contentType = response.headers.get("content-type");
             if (contentType && contentType.indexOf("application/json") !== -1) {
                return await response.json();
             } else {
                 return await response.text(); // Or handle as needed
             }
        } catch (error) {
            console.error('API Fetch Error:', error);
            showMessage(`API Error: ${error.message}`, true);
            throw error; // Re-throw for calling function
        }
    }

     // --- SocketIO Event Handlers ---
    socket.on('connect', () => {
        console.log('Socket.IO: Connected to /mecanum namespace');
        showMessage('Socket.IO Connected', false, 2000);
        // Backend will send initial config/status on connect
    });

    socket.on('disconnect', (reason) => {
        console.log('Socket.IO: Disconnected from /mecanum namespace:', reason);
        showMessage(`Socket.IO Disconnected: ${reason}`, true, 0); // Keep disconnect message visible
        updateSerialStatusUI('Disconnected', config?.serial_port || 'N/A'); // Update UI
        isSerialConnected = false;
        enableDisableControls(false); // Disable controls on disconnect
    });

    socket.on('connect_error', (err) => {
        console.error('Socket.IO: Connection error:', err);
        showMessage(`Socket.IO Connection Error: ${err.message}`, true, 0); // Keep error visible
        updateSerialStatusUI('Error', config?.serial_port || 'N/A', `Socket.IO Error: ${err.message}`);
        isSerialConnected = false;
        enableDisableControls(false);
    });

    socket.on('mecanum_serial_status', (data) => {
        console.log('Socket.IO: Received mecanum_serial_status:', data);
        updateSerialStatusUI(data.status, data.port, data.message);
        isSerialConnected = (data.status === 'Connected');
        enableDisableControls(isSerialConnected);
        if (data.status === 'Connected' && data.message) {
             showMessage(`Serial: ${data.message}`, false, 10000);
        } else if (data.status === 'Error' && data.message) {
             showMessage(`Serial Error: ${data.message}`, true, 0);
        } else if (data.message) {
             showMessage(`Serial Info: ${data.message}`, false);
        }
    });

    socket.on('mecanum_config', (data) => {
         console.log('Socket.IO: Received mecanum_config:', data.config);
         if(data.config) {
             currentConfig = data.config; // Store locally
             updateUIFromConfig(data.config);
         }
     });

     socket.on('mecanum_error', (data) => {
          console.error('Socket.IO: Received mecanum_error:', data.message);
          showMessage(`Backend Error: ${data.message}`, true);
      });

    // --- UI Update Functions ---
    function updateSerialStatusUI(status, port, message = '') {
         if (serialStatusText) serialStatusText.textContent = status;
         if (serialPortDisplay && port) serialPortDisplay.textContent = port;
         if (btnConnectSerial) btnConnectSerial.disabled = (status === 'Connected');
         if (btnDisconnectSerial) btnDisconnectSerial.disabled = (status !== 'Connected');

         // Update warning visibility based on status? (Optional)
         // if (warningMessage) warningMessage.style.display = (status === 'Connected') ? 'none' : 'block';
    }

    function enableDisableControls(isEnabled) {
         controlButtons.forEach(btn => {
            if (btn.dataset.action === 'stop') {
                btn.disabled = false; // Always enable STOP button
            } else {
                btn.disabled = !isEnabled;
            }
         });
         // You could also disable config saving while disconnected if desired
         // if (btnSaveConfig) btnSaveConfig.disabled = !isEnabled;
    }

    function readConfigFromUI() {
        const config = {
            mapping: {},
            calibration: {},
            scaling: {},
            // Read values from the Advanced Settings inputs
            serial_port: document.getElementById('setting-serial-port')?.value || default_serial_port,
            baud_rate: parseInt(document.getElementById('setting-baud-rate')?.value) || default_baud_rate
        };

        mappingSelects.forEach(select => {
            const logicalName = select.dataset.logical;
            if (logicalName) {
                const selectedValue = select.value;
                config.mapping[logicalName] = (selectedValue === 'none') ? null : selectedValue; // Store as string '0', '1' etc. or null
            }
        });

        calibrationInputs.forEach(input => {
             const logicalName = input.dataset.logical;
            if (logicalName) {
                config.calibration[logicalName] = parseFloat(input.value) || 1.0;
            }
        });

        config.scaling.deadzone_min = parseInt(document.getElementById('scale-deadzone-min')?.value) || 0;
        config.scaling.deadzone_max = parseInt(document.getElementById('scale-deadzone-max')?.value) || PWM_MAX;

        // Clamp values to reasonable ranges if necessary
        config.scaling.deadzone_min = Math.max(0, Math.min(config.scaling.deadzone_min, PWM_MAX -1));
        config.scaling.deadzone_max = Math.max(config.scaling.deadzone_min + 1, Math.min(config.scaling.deadzone_max, PWM_MAX));
        config.baud_rate = Math.max(300, config.baud_rate); // Basic sanity check

        return config;
    }

    function updateUIFromConfig(config) {
        currentConfig = config; // Update local store

        // Advanced Settings
        const serialPortInput = document.getElementById('setting-serial-port');
        const baudRateInput = document.getElementById('setting-baud-rate');
        if(serialPortInput) serialPortInput.value = config.serial_port || '';
        if(baudRateInput) baudRateInput.value = config.baud_rate || '';

        // Mapping
        mappingSelects.forEach(select => {
            const logicalName = select.dataset.logical;
            if (logicalName) {
                const physicalIndexStr = config.mapping[logicalName]; // Might be null, '0', '1', etc.
                select.value = (physicalIndexStr === null || physicalIndexStr === undefined) ? 'none' : String(physicalIndexStr);
            }
        });

        // Calibration
        calibrationInputs.forEach(input => {
            const logicalName = input.dataset.logical;
            if (logicalName) {
                 input.value = config.calibration[logicalName] || 1.0;
            }
        });

        // Scaling
        const scaleMinInput = document.getElementById('scale-deadzone-min');
        const scaleMaxInput = document.getElementById('scale-deadzone-max');
        if(scaleMinInput) scaleMinInput.value = config.scaling.deadzone_min ?? 0;
        if(scaleMaxInput) scaleMaxInput.value = config.scaling.deadzone_max ?? PWM_MAX;

        updateMappingDropdownStates(); // Update dropdown enable/disable states
    }

    // --- Motor Mapping Logic ---
    function updateMappingDropdownStates() {
        const selectedValues = new Set();
        // First pass: record selected physical motor indices (excluding 'none')
        mappingSelects.forEach(select => {
            if (select.value !== 'none') {
                selectedValues.add(select.value); // Values are '0', '1', '2', '3' as strings
            }
        });

        // Second pass: enable/disable options in other selects
        mappingSelects.forEach(currentSelect => {
            const currentSelectedValue = currentSelect.value;
            const options = currentSelect.querySelectorAll('option');
            options.forEach(option => {
                // Skip the 'none' option
                if (option.value !== 'none') {
                     // Disable if selected in *another* dropdown, enable otherwise
                    option.disabled = selectedValues.has(option.value) && option.value !== currentSelectedValue;
                }
            });
        });
    }

    // --- Configuration Actions ---
    async function saveConfig() {
        const configData = readConfigFromUI();
        console.log("Saving config:", configData);
        try {
            // Use the specific route for this blueprint
            const data = await fetchApi('/mecanum-control/save_config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(configData)
            });
            showMessage(data.message || 'Configuration saved successfully.', !data.success);
            if (data.success) {
                 // Optionally reload config from server ONLY IF NEEDED, rely on socket emit mostly
                 // loadConfig();
            }
        } catch (error) { /* Handled by fetchApi */ }
    }

    async function resetConfig() {
        if (!confirm("Are you sure you want to reset all Mecanum controller settings to default?")) {
            return;
        }
        try {
             // Use the specific route for this blueprint
            const data = await fetchApi('/mecanum-control/reset_config', { method: 'POST' });
            showMessage(data.message || 'Configuration reset.', !data.success);
            if (data.success && data.config) {
                // Update UI immediately with the returned default config
                updateUIFromConfig(data.config);
            }
        } catch (error) { /* Handled by fetchApi */ }
    }

    async function initialLoadConfig() {
         try {
             // Use the specific route for this blueprint
             const data = await fetchApi('/mecanum-control/get_config', { method: 'GET' });
             if (data.config) {
                 currentConfig = data.config; // Store initially
                 updateUIFromConfig(data.config);
                 updateSerialStatusUI(data.serial_status || 'Unknown', data.config.serial_port);
                 console.log("Initial config loaded via fetch:", data.config);
                 // Enable/disable controls based on initial status
                 isSerialConnected = (data.serial_status === 'Connected');
                 enableDisableControls(isSerialConnected);
             }
         } catch (error) {
             console.error("Initial config fetch failed:", error);
             showMessage("Failed to load initial configuration.", true);
             enableDisableControls(false); // Disable controls if config fails
         }
    }


    // --- Control Logic ---
    function sendControlCommand(payload) {
        if (!isSerialConnected && payload.action !== 'stop') {
            // Don't send movement commands if not connected
            // console.log("Blocked command send - Serial not connected:", payload);
            return;
        }
        if (!socket.connected && payload.action !== 'stop') {
             // Don't send if socket itself is down
             console.log("Blocked command send - Socket not connected:", payload);
             return;
        }

        // Throttle sending identical commands (especially useful for gamepad/keyboard)
        const commandKey = JSON.stringify(payload);
        if (payload.action === 'move') {
             // For continuous move commands
            if (gamepad && commandKey === lastGamepadCommandKey) return; // Skip if identical gamepad command
            if (!gamepad && commandKey === lastKeyboardCommandKey) return; // Skip if identical keyboard command

            lastGamepadCommandKey = gamepad ? commandKey : null;
            lastKeyboardCommandKey = !gamepad ? commandKey : null;
        } else if (payload.action === 'stop') {
             // Allow sending stop, but maybe not hundreds? Check last overall command.
             if (lastGamepadCommandKey === commandKey || lastKeyboardCommandKey === commandKey) return;
             // Reset tracking when stop is sent
             lastGamepadCommandKey = commandKey; // Treat stop as the last command
             lastKeyboardCommandKey = commandKey;
        } else {
             // For button presses (non-move actions) - allow sending press, maybe throttle release?
             // Reset continuous tracking for discrete button actions
             lastGamepadCommandKey = null;
             lastKeyboardCommandKey = null;
        }


        // console.debug("Sending command via SocketIO:", payload); // Reduce console noise
        socket.emit('mecanum_control_command', payload);
    }

    function stopMovement() {
        sendControlCommand({ action: 'stop', vx: 0, vy: 0, omega: 0 }); // Send explicit stop
        keysPressed = {}; // Clear keys when stopping explicitly
        // Reset last command tracking on explicit stop
        lastGamepadCommandKey = JSON.stringify({ action: 'stop', vx: 0, vy: 0, omega: 0 });
        lastKeyboardCommandKey = JSON.stringify({ action: 'stop', vx: 0, vy: 0, omega: 0 });
    }


    // --- Event Listeners ---

    // Configuration Buttons
    if (btnSaveConfig) btnSaveConfig.addEventListener('click', saveConfig);
    if (btnResetConfig) btnResetConfig.addEventListener('click', resetConfig);

    // Serial Connect/Disconnect Buttons
    if (btnConnectSerial) {
        btnConnectSerial.addEventListener('click', () => {
             console.log("Requesting serial connect via SocketIO...");
             showMessage('Attempting to connect...', false, 0); // Show connecting message
             socket.emit('mecanum_connect_serial');
         });
    }
     if (btnDisconnectSerial) {
         btnDisconnectSerial.addEventListener('click', () => {
              console.log("Requesting serial disconnect via SocketIO...");
              socket.emit('mecanum_disconnect_serial');
         });
     }


    // Mapping Dropdown Changes
    mappingSelects.forEach(select => {
        select.addEventListener('change', updateMappingDropdownStates);
    });

    // Control Buttons (Touch and Mouse) - Add checks for isSerialConnected
    controlButtons.forEach(button => {
        const action = button.dataset.action;
        let pressTimer = null; // For potential long-press features (unused currently)

        const handlePress = (e) => {
             e.preventDefault(); // Prevent default actions like text selection/scrolling
             if (!isSerialConnected && action !== 'stop') return; // Don't process if not connected (except stop)
             if (action === 'stop') {
                 stopMovement(); // Stop is immediate
             } else {
                 sendControlCommand({ action: action }); // Send discrete action name
             }
        };

        const handleRelease = (e) => {
            e.preventDefault();
            // Always send stop on release if it wasn't the stop button itself
            if (action !== 'stop') {
                 // No need to check isSerialConnected here, stop should always work if possible
                 stopMovement();
             }
        };

        // Mouse events
        button.addEventListener('mousedown', handlePress);
        button.addEventListener('mouseup', handleRelease);
        button.addEventListener('mouseleave', (e) => {
             // If mouse button is still down when leaving, treat as release
             if (e.buttons === 1 && action !== 'stop') {
                handleRelease(e);
            }
        });

        // Touch events
        button.addEventListener('touchstart', handlePress, { passive: false });
        button.addEventListener('touchend', handleRelease, { passive: false });
        button.addEventListener('touchcancel', handleRelease, { passive: false });
    });


    // Keyboard Controls
    function handleKeyboardControl() {
        // Do nothing if serial is not connected
        if (!isSerialConnected) return;

        let vx = 0, vy = 0, omega = 0;
        const speed = PWM_MAX; // Use max speed for simple key presses

        if (keysPressed['w']) vx += speed;
        if (keysPressed['s']) vx -= speed;
        if (keysPressed['a']) vy += speed; // Strafe left -> Positive Vy
        if (keysPressed['d']) vy -= speed; // Strafe right -> Negative Vy
        if (keysPressed['q']) omega += speed; // Rotate left -> Positive Omega
        if (keysPressed['e']) omega -= speed; // Rotate right -> Negative Omega

        // Send combined movement command
        if (vx !== 0 || vy !== 0 || omega !== 0) {
            sendControlCommand({ action: 'move', vx: vx, vy: vy, omega: omega });
        } else {
            // Keys released, send stop
            stopMovement();
        }
    }

    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return; // Ignore typing in inputs
        if (['w', 'a', 's', 'd', 'q', 'e', ' '].includes(e.key.toLowerCase())) e.preventDefault(); // Prevent browser scroll/actions

        const key = e.key.toLowerCase();
        if (key === ' '){ // Spacebar for immediate stop
             stopMovement();
             return;
        }

        // Only handle movement keys here
        if (['w', 'a', 's', 'd', 'q', 'e'].includes(key)) {
            if (!keysPressed[key]) { // Process only on first press, ignore repeats
                keysPressed[key] = true;
                 // Don't trigger if gamepad is active (let gamepad take priority)
                if (!gamepad && isSerialConnected) { // Check connection status
                     handleKeyboardControl();
                }
            }
        }
    });

    document.addEventListener('keyup', (e) => {
         if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;

         const key = e.key.toLowerCase();
         // Handle movement keys release
         if (['w', 'a', 's', 'd', 'q', 'e'].includes(key)) {
             if (keysPressed[key]) {
                delete keysPressed[key];
                // Don't trigger if gamepad is active
                if (!gamepad && isSerialConnected) { // Check connection status
                     handleKeyboardControl(); // Recalculate movement (will send stop if no keys are pressed)
                }
            }
        }
    });


    // --- Gamepad Controls ---
    function handleGamepadInput() {
        // Do nothing if serial is not connected or gamepad not present
        if (!isSerialConnected || !gamepad) return;

        const axes = gamepad.axes;
        let vx = 0, vy = 0, omega = 0;

        // --- Adjust Axis Indices and Signs based on your specific gamepad ---
        // Common layout:
        // Axis 0: Left Stick X (Left/Right) -> maps to vy (Strafe)
        // Axis 1: Left Stick Y (Up/Down)   -> maps to vx (Forward/Backward) - Often needs inversion (-)
        // Axis 2: Right Stick X (Left/Right) -> maps to omega (Rotation)
        // Axis 3: Right Stick Y (Up/Down)   -> unused here

        const leftStickX = axes[0] || 0;
        const leftStickY = axes[1] || 0;
        const rightStickX = axes[2] || 0; // Or potentially axes[3] on some gamepads

        // Apply deadzone and scale to PWM range
        if (Math.abs(leftStickY) > GAMEPAD_AXIS_THRESHOLD) {
            vx = -leftStickY * PWM_MAX; // Invert Y axis typically
        }
        if (Math.abs(leftStickX) > GAMEPAD_AXIS_THRESHOLD) {
            vy = leftStickX * PWM_MAX; // Positive X maps to positive vy (strafe left)
        }
        if (Math.abs(rightStickX) > GAMEPAD_AXIS_THRESHOLD) {
            omega = rightStickX * PWM_MAX; // Positive X maps to positive omega (rotate left)
        }

        // Send combined 'move' command (includes zeros if sticks are centered)
        sendControlCommand({
             action: 'move',
             vx: Math.round(vx),
             vy: Math.round(vy),
             omega: Math.round(omega)
        });
    }


    function startGamepadPolling() {
        if (gamepadPollIntervalId) clearInterval(gamepadPollIntervalId); // Clear existing interval just in case

        gamepadPollIntervalId = setInterval(() => {
            // Need to re-get the gamepad object each time
             const freshGamepads = navigator.getGamepads();
             if (!freshGamepads[gamepad.index]) { // Check if gamepad still exists at index
                 stopGamepadPolling(); // Stop polling if it disappeared
                 return;
             }
             gamepad = freshGamepads[gamepad.index]; // Update reference

            if (gamepad && gamepad.connected) {
                handleGamepadInput();
            } else {
                // Gamepad disconnected unexpectedly or polling detected disconnect
                stopGamepadPolling();
            }
        }, GAMEPAD_POLL_INTERVAL);

        if (gamepadStatus) gamepadStatus.textContent = `Gamepad: Connected (${gamepad.id})`;
        // Stop keyboard control explicitly when gamepad connects if serial is active
        keysPressed = {};
        if (isSerialConnected) stopMovement(); // Send stop when gamepad connects initially if robot might be moving
    }

    function stopGamepadPolling() {
        if (gamepadPollIntervalId) {
            clearInterval(gamepadPollIntervalId);
            gamepadPollIntervalId = null;
            console.log("Gamepad polling stopped.");
        }
        if (gamepadStatus) gamepadStatus.textContent = 'Gamepad: Disconnected';
        // Send a final stop command if serial was connected when gamepad polling stops
        if (isSerialConnected) {
            stopMovement();
        }
        gamepad = null;
        // Optional: Re-enable keyboard if needed? The keyup/keydown handlers will take over if keys are pressed.
    }

    window.addEventListener('gamepadconnected', (e) => {
        console.log('Gamepad connected:', e.gamepad);
        // Use the first connected gamepad
        if (!gamepad) {
             gamepad = e.gamepad;
             startGamepadPolling();
        } else {
            console.log("Another gamepad already active.");
        }
    });

    window.addEventListener('gamepaddisconnected', (e) => {
        console.log('Gamepad disconnected:', e.gamepad);
        if (gamepad && gamepad.index === e.gamepad.index) {
            stopGamepadPolling(); // This will also send stop command if needed
        }
    });

    // --- Initial Load ---
    initialLoadConfig(); // Fetch initial config via HTTP GET

    // Check for existing gamepads on load
     try {
        const initialGamepads = navigator.getGamepads();
         for (const gp of initialGamepads) {
             if (gp) {
                 console.log("Found existing gamepad on load:", gp);
                 gamepad = gp;
                 startGamepadPolling();
                 break; // Use the first one found
             }
         }
     } catch(err) {
         console.error("Error getting initial gamepads:", err);
     }
     if (!gamepad && gamepadStatus) {
        gamepadStatus.textContent = 'Gamepad: Not detected (Press button)';
     }
     // Initial control state based on connection status (done in initialLoadConfig)


}); // End DOMContentLoaded