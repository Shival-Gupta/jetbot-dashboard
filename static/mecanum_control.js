document.addEventListener('DOMContentLoaded', () => {
    const socket = io('/mecanum', {
        reconnectionAttempts: 5, // Optional: Limit reconnection attempts
        timeout: 10000 // Optional: Connection timeout
    });
    const PWM_MAX = 255; // Should match backend/Arduino
    const GAMEPAD_AXIS_THRESHOLD = 0.15; // Deadzone for gamepad sticks
    const GAMEPAD_POLL_INTERVAL = 100; // Milliseconds

    // --- DOM Elements ---
    const messageArea = document.getElementById('message-area');
    const serialStatusText = document.getElementById('serial-status-text');
    const btnConnectSerial = document.getElementById('btn-connect-serial');
    const btnSaveConfig = document.getElementById('btn-save-config');
    const btnResetConfig = document.getElementById('btn-reset-config');
    const controlButtons = document.querySelectorAll('.control-button');
    const mappingSelects = document.querySelectorAll('fieldset:nth-of-type(1) select'); // More specific selector
    const calibrationInputs = document.querySelectorAll('fieldset:nth-of-type(2) input');
    const scalingInputs = document.querySelectorAll('fieldset:nth-of-type(3) input');
    const advancedInputs = document.querySelectorAll('fieldset:nth-of-type(4) input');
    const gamepadStatus = document.getElementById('gamepad-status');

    // --- State Variables ---
    let keysPressed = {};
    let gamepad = null;
    let gamepadPollIntervalId = null;
    let lastGamepadCommand = null; // To avoid sending redundant commands
    let lastKeyboardCommand = null;
    let currentConfig = {}; // Store config locally

    // --- Utility Functions ---
    function showMessage(msg, isError = false) {
        messageArea.textContent = msg;
        messageArea.style.color = isError ? 'red' : 'green';
        // Clear message after a delay
        setTimeout(() => { messageArea.textContent = ''; }, 5000);
    }

    async function fetchApi(url, options = {}) {
        try {
            const response = await fetch(url, options);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ message: `HTTP error! status: ${response.status}` }));
                throw new Error(errorData.message || `HTTP error! status: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error('API Fetch Error:', error);
            showMessage(`Error: ${error.message}`, true);
            // If serial disconnects during operation, update status
            if (error.message && error.message.toLowerCase().includes("serial")) {
                 updateSerialStatus("Disconnected");
            }
            throw error; // Re-throw for calling function to handle if needed
        }
    }

     // --- Serial Communication ---
    async function connectSerial() {
        try {
            const data = await fetchApi('/connect_serial', { method: 'POST'});
            showMessage(data.message, !data.success);
            if (data.success) {
                updateSerialStatus("Connected");
            }
        } catch (error) {/* Handled by fetchApi */}
    }

    function updateSerialStatus(status) {
        serialStatusText.textContent = status;
        btnConnectSerial.disabled = (status === "Connected");
    }

    // --- Configuration Handling ---
    async function saveConfig() {
        const configData = readConfigFromUI();
        try {
            const data = await fetchApi('/save_config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(configData)
            });
            showMessage(data.message, !data.success);
            if (data.success) {
                 // Optionally reload config from server to ensure consistency
                //  loadConfig();
            }
        } catch (error) { /* Handled by fetchApi */ }
    }

    async function resetConfig() {
        if (!confirm("Are you sure you want to reset all settings to default?")) {
            return;
        }
        try {
            const data = await fetchApi('/reset_config', { method: 'POST' });
            showMessage(data.message, !data.success);
            if (data.success && data.config) {
                updateUIFromConfig(data.config);
                updateMappingDropdownStates(); // Update dropdowns based on new config
            }
        } catch (error) { /* Handled by fetchApi */ }
    }

     async function loadConfig() {
        try {
            const data = await fetchApi('/get_config');
            if (data.config) {
                currentConfig = data.config; // Store locally
                updateUIFromConfig(data.config);
                updateMappingDropdownStates();
                updateSerialStatus(data.serial_status || "Unknown");
                console.log("Config loaded:", currentConfig);
            }
        } catch (error) { /* Handled by fetchApi */ }
    }


    function readConfigFromUI() {
        const config = {
            mapping: {},
            calibration: {},
            scaling: {},
            serial_port: document.getElementById('setting-serial-port').value,
            baud_rate: parseInt(document.getElementById('setting-baud-rate').value) || 9600
        };

        mappingSelects.forEach(select => {
            const logicalName = select.dataset.logical;
            const selectedValue = select.value;
            // Store 'None' as null, otherwise parse as integer
            config.mapping[logicalName] = (selectedValue === 'none') ? null : parseInt(selectedValue);
        });

        calibrationInputs.forEach(input => {
            config.calibration[input.dataset.logical] = parseFloat(input.value) || 1.0;
        });

        config.scaling.deadzone_min = parseInt(document.getElementById('scale-deadzone-min').value) || 0;
        config.scaling.deadzone_max = parseInt(document.getElementById('scale-deadzone-max').value) || PWM_MAX;


        return config;
    }

    function updateUIFromConfig(config) {
        currentConfig = config; // Update local store

        // Serial/Advanced
        document.getElementById('setting-serial-port').value = config.serial_port || '';
        document.getElementById('setting-baud-rate').value = config.baud_rate || '';

        // Mapping
        mappingSelects.forEach(select => {
            const logicalName = select.dataset.logical;
            const physicalIndex = config.mapping[logicalName];
            select.value = (physicalIndex === null || physicalIndex === undefined) ? 'none' : physicalIndex;
        });

        // Calibration
        calibrationInputs.forEach(input => {
            const logicalName = input.dataset.logical;
            input.value = config.calibration[logicalName] || 1.0;
        });

        // Scaling
        document.getElementById('scale-deadzone-min').value = config.scaling.deadzone_min || 0;
        document.getElementById('scale-deadzone-max').value = config.scaling.deadzone_max || PWM_MAX;

        // Update mapping dropdown enable/disable states
        updateMappingDropdownStates();
    }

    // --- Motor Mapping Logic ---
    function updateMappingDropdownStates() {
        const selectedValues = new Set();
        // First pass: record selected values (excluding 'none')
        mappingSelects.forEach(select => {
            if (select.value !== 'none') {
                selectedValues.add(select.value);
            }
        });

        // Second pass: enable/disable options in other selects
        mappingSelects.forEach(currentSelect => {
            const currentSelectedValue = currentSelect.value;
            const options = currentSelect.querySelectorAll('option');
            options.forEach(option => {
                if (option.value !== 'none') {
                     // Disable if selected in *another* dropdown, enable otherwise
                    option.disabled = selectedValues.has(option.value) && option.value !== currentSelectedValue;
                }
            });
        });
    }


    // --- Control Logic ---
    
    socket.on('connect', () => {
        console.log('Connected to Mecanum Socket.IO namespace');
        showMessage('Socket.IO Connected', false);
        // Server should send initial status/config now
    });

    socket.on('disconnect', (reason) => {
        console.log('Disconnected from Mecanum Socket.IO namespace:', reason);
        showMessage('Socket.IO Disconnected', true);
        updateSerialStatusUI('Disconnected', ''); // Update UI on socket disconnect too
    });

    socket.on('connect_error', (err) => {
        console.error('Mecanum Socket.IO connection error:', err);
        showMessage(`Socket.IO Connection Error: ${err.message}`, true);
        updateSerialStatusUI('Error', '');
    });

    // Listen for status updates from backend
    socket.on('mecanum_serial_status', (data) => {
        console.log('Serial status update:', data);
        updateSerialStatusUI(data.status, data.port, data.message);
    });

    // Listen for config updates from backend (e.g., on connect)
    socket.on('mecanum_config', (data) => {
        console.log('Received config from server:', data.config);
        if(data.config) {
            updateUIFromConfig(data.config); // Reuse your existing UI update function
        }
    });

    // Listen for general errors from backend
    socket.on('mecanum_error', (data) => {
        console.error('Mecanum backend error:', data.message);
        showMessage(data.message, true);
    });

    // Function to update serial UI elements
    function updateSerialStatusUI(status, port, message = '') {
        serialStatusText.textContent = status;
        if (port) {
            serialPortDisplay.textContent = port;
        }
        btnConnectSerial.disabled = (status === 'Connected');
        btnDisconnectSerial.disabled = (status !== 'Connected');
        if (message) {
            showMessage(`Serial Info: ${message}`, status === 'Error');
        }
        // You might want to disable control buttons if not connected
        const controlButtons = document.querySelectorAll('.control-button');
        controlButtons.forEach(btn => {
            // btn.disabled = (status !== 'Connected'); // Be careful with STOP button
            if (btn.dataset.action === 'stop') {
                btn.disabled = false; // Always enable STOP
            } else {
                btn.disabled = (status !== 'Connected');
            }
        });
    }

    async function sendControlCommand(payload) {
        try {
            // Add a check to avoid sending identical commands rapidly, especially for gamepad/keyboard
            const commandKey = JSON.stringify(payload);
            if (payload.action === 'move') {
                 if (gamepad && commandKey === lastGamepadCommand) return;
                 if (!gamepad && commandKey === lastKeyboardCommand) return; // Check keyboard only if no gamepad
                 lastGamepadCommand = gamepad ? commandKey : null;
                 lastKeyboardCommand = !gamepad ? commandKey : null;
            } else if (payload.action === 'stop') {
                 // Allow stop commands more frequently if needed, but prevent spamming
                 if (lastGamepadCommand === commandKey || lastKeyboardCommand === commandKey) return;
                 lastGamepadCommand = commandKey;
                 lastKeyboardCommand = commandKey;
            } else {
                 // For button presses, always send start, but maybe limit stop
                 if (payload.action === 'stop' && (lastGamepadCommand === commandKey || lastKeyboardCommand === commandKey)) return;
                 lastGamepadCommand = null; // Reset continuous command tracking
                 lastKeyboardCommand = null;
            }

            console.debug("Sending command via SocketIO:", payload); // Debug output
            socket.emit('mecanum_control_command', payload);
        
            // await fetchApi('/control', {
            //     method: 'POST',
            //     headers: { 'Content-Type': 'application/json' },
            //     body: JSON.stringify(payload)
            // });

            // Optional: Show confirmation for non-continuous commands
            // if (payload.action !== 'move') {
            //     console.log("Sent:", payload);
            // }
        } catch (error) {
            lastGamepadCommand = null; // Reset last command on error
            lastKeyboardCommand = null;
            // Error already shown by fetchApi
        }
    }

    // Add listeners for the new Connect/Disconnect buttons
    btnConnectSerial.addEventListener('click', () => {
        console.log("Requesting serial connect...");
        socket.emit('mecanum_connect_serial');
    });

    btnDisconnectSerial.addEventListener('click', () => {
        console.log("Requesting serial disconnect...");
        socket.emit('mecanum_disconnect_serial');
    });

    function stopMovement() {
        sendControlCommand({ action: 'stop' });
        keysPressed = {}; // Clear keys when stopping explicitly
        lastGamepadCommand = null; // Clear last command state
        lastKeyboardCommand = null;
    }

    // --- Event Listeners ---

    // Configuration Buttons
    btnSaveConfig.addEventListener('click', saveConfig);
    btnResetConfig.addEventListener('click', resetConfig);
    btnConnectSerial.addEventListener('click', connectSerial);

    // Mapping Dropdown Changes
    mappingSelects.forEach(select => {
        select.addEventListener('change', updateMappingDropdownStates);
    });

    // Control Buttons (Touch and Mouse)
    controlButtons.forEach(button => {
        const action = button.dataset.action;
        let pressTimer = null;

        // Mouse events
        button.addEventListener('mousedown', (e) => {
             e.preventDefault(); // Prevent text selection, etc.
             if (action === 'stop') {
                 stopMovement(); // Stop is immediate
             } else {
                 sendControlCommand({ action: action });
             }
        });
        button.addEventListener('mouseup', (e) => {
            e.preventDefault();
            if (action !== 'stop') {
                 stopMovement();
             }
        });
        button.addEventListener('mouseleave', (e) => {
             // If mouse button is still down when leaving, treat as mouseup
             if (e.buttons === 1 && action !== 'stop') { // Check if left mouse button is pressed
                stopMovement();
            }
        });

        // Touch events
        button.addEventListener('touchstart', (e) => {
            e.preventDefault(); // Crucial for stopping double taps, scroll, etc.
             if (action === 'stop') {
                 stopMovement();
             } else {
                 sendControlCommand({ action: action });
             }
        }, { passive: false }); // Need passive: false to call preventDefault

        button.addEventListener('touchend', (e) => {
            e.preventDefault();
             if (action !== 'stop') {
                 stopMovement();
             }
        });
        button.addEventListener('touchcancel', (e) => {
             e.preventDefault();
             if (action !== 'stop') {
                stopMovement();
            }
        });
    });


    // Keyboard Controls
    function handleKeyboardControl() {
        let vx = 0, vy = 0, omega = 0;
        const speed = PWM_MAX;

        if (keysPressed['w']) vx += speed;
        if (keysPressed['s']) vx -= speed;
        if (keysPressed['a']) vy += speed; // Strafe left
        if (keysPressed['d']) vy -= speed; // Strafe right
        if (keysPressed['q']) omega += speed; // Rotate left
        if (keysPressed['e']) omega -= speed; // Rotate right

        // Normalize if necessary (though mecanum function handles this)
        // Basic clamping here might be useful if not using get_move_speeds directly
        // vx = Math.max(-speed, Math.min(speed, vx));
        // vy = Math.max(-speed, Math.min(speed, vy));
        // omega = Math.max(-speed, Math.min(speed, omega));

        if (vx !== 0 || vy !== 0 || omega !== 0) {
            sendControlCommand({ action: 'move', vx: vx, vy: vy, omega: omega });
        } else {
            // Only send stop if the last command wasn't already stop
            const stopCommand = JSON.stringify({ action: 'stop' });
             if (lastKeyboardCommand !== stopCommand && lastGamepadCommand !== stopCommand) {
                stopMovement();
            }
        }
    }

    document.addEventListener('keydown', (e) => {
        // Ignore if typing in input fields
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') {
            return;
        }
        // Prevent default browser actions for control keys (scrolling, etc.)
        if (['w', 'a', 's', 'd', 'q', 'e', ' '].includes(e.key.toLowerCase())) {
             e.preventDefault();
        }

        const key = e.key.toLowerCase();
        if (!keysPressed[key]) { // Prevent continuous trigger from key repeat
            keysPressed[key] = true;
             // Don't trigger movement if gamepad is active (prevents conflicts)
            if (!gamepad) {
                 handleKeyboardControl();
            }
        }
         // Allow spacebar for immediate stop anytime
         if (key === ' ') {
             stopMovement();
         }

    });

    document.addEventListener('keyup', (e) => {
         // Ignore if typing in input fields
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') {
            return;
        }
         const key = e.key.toLowerCase();
         if (keysPressed[key]) {
            delete keysPressed[key];
            // Don't trigger movement if gamepad is active
            if (!gamepad) {
                 handleKeyboardControl(); // Recalculate movement based on remaining keys
            }
        }
    });


    // --- Gamepad Controls ---
    function handleGamepadInput() {
        if (!gamepad) return;

        const axes = gamepad.axes;
        let vx = 0, vy = 0, omega = 0;

        // Left stick for movement (Axis 0: L/R, Axis 1: U/D) - Often inverted Y
        const leftStickX = axes[0];
        const leftStickY = -axes[1]; // Invert Y axis for typical forward motion

        if (Math.abs(leftStickY) > GAMEPAD_AXIS_THRESHOLD) {
            vx = leftStickY * PWM_MAX;
        }
        if (Math.abs(leftStickX) > GAMEPAD_AXIS_THRESHOLD) {
            vy = leftStickX * PWM_MAX; // Positive X usually means right, map to negative vy for strafe right
            //vy = -leftStickX * PWM_MAX; // map to negative vy for strafe right
        }

        // Right stick for rotation (Axis 2: L/R or Axis 3, depends on controller)
        // Common layouts: Axis 2 (X), Axis 3 (Y) OR Axis 3 (X), Axis 4 (Y)
        let rightStickX = axes[2] ?? axes[3] ?? 0; // Try axis 2 first, then axis 3

        if (Math.abs(rightStickX) > GAMEPAD_AXIS_THRESHOLD) {
            omega = rightStickX * PWM_MAX; // Positive X for rotate right (clockwise, often maps to negative omega)
            //omega = -rightStickX * PWM_MAX;
        }

        // Send move command (includes zero speeds if sticks are centered)
        sendControlCommand({ action: 'move', vx: Math.round(vx), vy: Math.round(vy), omega: Math.round(omega) });
    }


    function startGamepadPolling() {
        if (gamepadPollIntervalId) clearInterval(gamepadPollIntervalId); // Clear existing interval

        gamepadPollIntervalId = setInterval(() => {
            // Need to re-get the gamepad object each time as the browser might update it
             const freshGamepads = navigator.getGamepads();
             gamepad = freshGamepads[gamepad.index]; // Update reference

            if (gamepad && gamepad.connected) {
                handleGamepadInput();
            } else {
                // Gamepad disconnected unexpectedly
                stopGamepadPolling();
                gamepadStatus.textContent = 'Gamepad: Disconnected';
                gamepad = null;
                // If keyboard was also pressed, it might need a stop command now
                if (Object.keys(keysPressed).length === 0) {
                    stopMovement();
                } else {
                    handleKeyboardControl(); // Let keyboard take over if keys are pressed
                }
            }
        }, GAMEPAD_POLL_INTERVAL);
         gamepadStatus.textContent = `Gamepad: Connected (${gamepad.id})`;
         // Stop keyboard control explicitly when gamepad connects
         keysPressed = {};
         stopMovement(); // Send stop when gamepad connects initially
    }

    function stopGamepadPolling() {
        if (gamepadPollIntervalId) {
            clearInterval(gamepadPollIntervalId);
            gamepadPollIntervalId = null;
        }
    }

    window.addEventListener('gamepadconnected', (e) => {
        console.log('Gamepad connected:', e.gamepad);
        // Only take the first connected gamepad for simplicity
        if (!gamepad) {
             gamepad = e.gamepad;
             startGamepadPolling();
             // Ensure keyboard stops interfering
             keysPressed = {};
             stopMovement();
        }
    });

    window.addEventListener('gamepaddisconnected', (e) => {
        console.log('Gamepad disconnected:', e.gamepad);
        if (gamepad && gamepad.index === e.gamepad.index) {
            stopGamepadPolling();
            gamepadStatus.textContent = 'Gamepad: Disconnected';
            gamepad = null;
             // Send a final stop command when gamepad disconnects
             stopMovement();
        }
    });

    // --- Initial Load ---
    // Initial fetch for config might still be useful for first page load before socket connects fully
    async function initialLoad() {
        try {
            const data = await fetchApi('/mecanum-control/get_config'); // Use fetch for initial load
            if (data.config) {
                updateUIFromConfig(data.config);
                updateSerialStatusUI(data.serial_status || 'Unknown', data.config.serial_port);
                console.log("Initial config loaded via fetch:", data.config);
            }
        } catch (error) {
            console.error("Initial config fetch failed:", error);
            showMessage("Failed to load initial configuration.", true);
        }
    }
    initialLoad();
    // loadConfig(); // Load config from server on page load
    updateMappingDropdownStates(); // Initial setup for dropdowns

    // Check for existing gamepads on load
     const initialGamepads = navigator.getGamepads();
     for (const gp of initialGamepads) {
         if (gp) {
             gamepad = gp;
             startGamepadPolling();
             break; // Use the first one found
         }
     }
     if (!gamepad) {
        gamepadStatus.textContent = 'Gamepad: Not detected (Press button)';
     }


}); // End DOMContentLoaded