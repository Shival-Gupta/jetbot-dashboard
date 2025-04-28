#!/bin/bash

# Script: setup.sh
# Purpose: One-time setup for JetBot Dashboard automation on a fresh system
# Run: sudo bash setup/setup.sh from /home/jetson/jetbot-dashboard

# Exit on error
set -e

# Set variables
REPO_DIR="/home/jetson/jetbot-dashboard"
REPO_BRANCH="master"  # Adjust if needed
SETUP_DIR="$REPO_DIR/setup"
VENV_DIR="$REPO_DIR/.venv"
REQUIREMENTS_FILE="$REPO_DIR/requirements.txt"
START_SCRIPT="$SETUP_DIR/start-jetbot-dashboard.sh"
SERVICE_FILE_SRC="$SETUP_DIR/jetbot-dashboard.service"
SERVICE_FILE_DEST="/etc/systemd/system/jetbot-dashboard.service"
SUDOERS_FILE_SRC="$SETUP_DIR/jetbot-dashboard-sudoer"
SUDOERS_FILE_DEST="/etc/sudoers.d/jetbot-dashboard-sudoer"
ENV_FILE="$REPO_DIR/.env"
LOG_FILE="$REPO_DIR/setup.log"
NETWORK_TIMEOUT=300  # 5 minutes timeout for network check

# Redirect output to log file
exec > >(tee -a "$LOG_FILE") 2>&1
echo "[$(date)] Starting JetBot Dashboard setup"

# Function to wait for internet connectivity
wait_for_network() {
    echo "Checking for internet connectivity..."
    local timeout=$1
    local start_time=$(date +%s)
    until ping -c 1 google.com > /dev/null 2>&1; do
        current_time=$(date +%s)
        elapsed=$((current_time - start_time))
        if [ $elapsed -ge $timeout ]; then
            echo "Error: No internet connectivity after $timeout seconds"
            exit 1
        fi
        echo "Waiting for network... ($elapsed/$timeout seconds)"
        sleep 5
    done
    echo "Internet connectivity confirmed."
}

# Step 1: Wait for network and install system dependencies
wait_for_network $NETWORK_TIMEOUT
echo "Installing system dependencies..."
apt update
apt install -y git python3 python3-venv python3-pip || { echo "Failed to install system dependencies"; exit 1; }
echo "System dependencies installed."

# Step 2: Ensure repository directory exists
if [ ! -d "$REPO_DIR" ]; then
    echo "Repository directory $REPO_DIR not found. Please clone the repository first."
    exit 1
fi
cd "$REPO_DIR" || { echo "Failed to navigate to $REPO_DIR"; exit 1; }

# Step 3: Generate SECRET_KEY and create .env file
if [ ! -f "$ENV_FILE" ]; then
    echo "Generating SECRET_KEY and creating .env file..."
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "SECRET_KEY=$SECRET_KEY" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    chown jetson:jetson "$ENV_FILE"
    echo ".env file created with secure SECRET_KEY."
else
    echo ".env file already exists."
fi

# Step 4: Fix requirements.txt (remove apturl if present)
if grep -q "apturl==0.5.2" "$REQUIREMENTS_FILE"; then
    echo "Removing apturl==0.5.2 from requirements.txt..."
    sed -i '/apturl==0.5.2/d' "$REQUIREMENTS_FILE"
    echo "requirements.txt updated."
fi

# Step 5: Create virtual environment and install dependencies
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "Virtual environment created."
else
    echo "Virtual environment already exists."
fi
source "$VENV_DIR/bin/activate" || { echo "Failed to activate virtual environment"; exit 1; }
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r "$REQUIREMENTS_FILE" || { echo "Failed to install dependencies"; exit 1; }
echo "Python dependencies installed."
deactivate

# Step 6: Create start-jetbot-dashboard.sh script
echo "Creating automation script at $START_SCRIPT..."
cat > "$START_SCRIPT" << EOF
#!/bin/bash

# Script: start-jetbot-dashboard.sh
# Purpose: Automate JetBot Dashboard setup and startup on reboot

# Set variables
REPO_DIR="/home/jetson/jetbot-dashboard"
REPO_BRANCH="$REPO_BRANCH"  # Adjust if needed
VENV_DIR="\$REPO_DIR/.venv"
REQUIREMENTS_FILE="\$REPO_DIR/requirements.txt"
SERVICE_FILE_SRC="\$REPO_DIR/setup/jetbot-dashboard.service"
SERVICE_FILE_DEST="/etc/systemd/system/jetbot-dashboard.service"
SUDOERS_FILE_SRC="\$REPO_DIR/setup/jetbot-dashboard-sudoer"
SUDOERS_FILE_DEST="/etc/sudoers.d/jetbot-dashboard-sudoer"
MAIN_PY="\$REPO_DIR/main.py"
LOG_FILE="\$REPO_DIR/startup.log"
NETWORK_TIMEOUT=300  # 5 minutes timeout for network check

# Redirect output to log file
exec > >(tee -a "\$LOG_FILE") 2>&1
echo "[\$(date)] Starting JetBot Dashboard automation script"

# Function to wait for internet connectivity
wait_for_network() {
    echo "Checking for internet connectivity..."
    local timeout=\$1
    local start_time=\$(date +%s)
    until ping -c 1 google.com > /dev/null 2>&1; do
        current_time=\$(date +%s)
        elapsed=\$((\current_time - start_time))
        if [ \$elapsed -ge \$timeout ]; then
            echo "Error: No internet connectivity after \$timeout seconds"
            exit 1
        fi
        echo "Waiting for network... (\$elapsed/\$timeout seconds)"
        sleep 5
    done
    echo "Internet connectivity confirmed."
}

# Navigate to repository directory jitter
cd "\$REPO_DIR" || { echo "Failed to navigate to \$REPO_DIR"; exit 1; }

# Step 1: Wait for network and fetch/pull latest code
wait_for_network \$NETWORK_TIMEOUT
echo "Fetching and pulling latest code..."
git fetch origin
git reset --hard origin/\$REPO_BRANCH
git pull --force
echo "Code updated."

# Step 2: Set up virtual environment
if [ ! -d "\$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "\$VENV_DIR"
    echo "Virtual environment created."
else
    echo "Virtual environment already exists."
fi

# Activate virtual environment
source "\$VENV_DIR/bin/activate" || { echo "Failed to activate virtual environment"; exit 1; }

# Step 3: Install dependencies
echo "Installing dependencies from \$REQUIREMENTS_FILE..."
pip install --upgrade pip
pip install -r "\$REQUIREMENTS_FILE" || { echo "Failed to install dependencies"; exit 1; }
echo "Dependencies installed."

# Step 4: Update sudoers file if changed
if [ -f "\$SUDOERS_FILE_SRC" ]; then
    if ! cmp -s "\$SUDOERS_FILE_SRC" "\$SUDOERS_FILE_DEST"; then
        echo "Updating sudoers file..."
        sudo cp "\$SUDOERS_FILE_SRC" "\$SUDOERS_FILE_DEST" || { echo "Failed to update sudoers file"; exit 1; }
        sudo chmod 440 "\$SUDOERS_FILE_DEST" || { echo "Failed to set sudoers permissions"; exit 1; }
        sudo visudo -c || { echo "Sudoers file syntax check failed"; exit 1; }
        echo "Sudoers file updated."
    else
        echo "Sudoers file is up to date."
    fi
else
    echo "Warning: Sudoers source file not found at \$SUDOERS_FILE_SRC"
fi

# Step 5: Update systemd service file if changed
if [ -f "\$SERVICE_FILE_SRC" ]; then
    if ! cmp -s "\$SERVICE_FILE_SRC" "\$SERVICE_FILE_DEST"; then
        echo "Updating systemd service file..."
        sudo cp "\$SERVICE_FILE_SRC" "\$SUDOERS_FILE_DEST" || { echo "Failed to update service file"; exit 1; }
        sudo chmod 644 "\$SUDOERS_FILE_DEST" || { echo "Failed to set service file permissions"; exit 1; }
        sudo systemctl daemon-reload || { echo "Failed to reload systemd daemon"; exit 1; }
        sudo systemctl enable jetbot-dashboard.service || { echo "Failed to enable service"; exit 1; }
        echo "Systemd service file updated."
    else
        echo "Systemd service file is up to date."
    fi
else
    echo "Warning: Service source file not found at \$SERVICE_FILE_SRC"
fi

# Step 6: Run the main application
echo "Starting JetBot Dashboard..."
"\$VENV_DIR/bin/python3" "\$MAIN_PY" || { echo "Failed to start main.py"; exit 1; }

echo "[\$(date)] JetBot Dashboard startup completed."
EOF
chmod +x "$START_SCRIPT"
chown jetson:jetson "$START_SCRIPT"
echo "Automation script created."

# Step 7: Install sudoers file
if [ -f "$SUDOERS_FILE_SRC" ]; then
    echo "Installing sudoers file..."
    # Remove existing sudoers file to avoid duplicate aliases
    if [ -f "$SUDOERS_FILE_DEST" ]; then
        echo "Existing sudoers file found, backing up and removing..."
        cp "$SUDOERS_FILE_DEST" "${SUDOERS_FILE_DEST}.bak-$(date +%F_%H-%M-%S)"
        rm "$SUDOERS_FILE_DEST" || { echo "Failed to remove existing sudoers file"; exit 1; }
    fi
    cp "$SUDOERS_FILE_SRC" "$SUDOERS_FILE_DEST" || { echo "Failed to install sudoers file"; exit 1; }
    chmod 440 "$SUDOERS_FILE_DEST" || { echo "Failed to set sudoers permissions"; exit 1; }
    visudo -c || { echo "Sudoers file syntax check failed"; exit 1; }
    echo "Sudoers file installed."
else
    echo "Error: Sudoers source file not found at $SUDOERS_FILE_SRC"
    exit 1
fi

# Step 8: Install and configure systemd service
if [ -f "$SERVICE_FILE_SRC" ]; then
    echo "Installing systemd service..."
    cp "$SERVICE_FILE_SRC" "$SERVICE_FILE_DEST" || { echo "Failed to install service file"; exit 1; }
    chmod 644 "$SERVICE_FILE_DEST" || { echo "Failed to set service file permissions"; exit 1; }
    systemctl daemon-reload || { echo "Failed to reload systemd daemon"; exit 1; }
    systemctl enable jetbot-dashboard.service || { echo "Failed to enable service"; exit 1; }
    echo "Systemd service installed and enabled."
else
    echo "Error: Service source file not found at $SERVICE_FILE_SRC"
    exit 1
fi

# Step 9: Start the service
echo "Starting JetBot Dashboard service..."
systemctl start jetbot-dashboard.service || { echo "Failed to start service"; exit 1; }
echo "JetBot Dashboard service started."

echo "[$(date)] JetBot Dashboard setup completed successfully."
echo "Check logs at $LOG_FILE and $REPO_DIR/startup.log"
echo "Service status: systemctl status jetbot-dashboard.service"

# Step 10: Run verification
if [ -f "$SETUP_DIR/verify.sh" ]; then
    echo "Running verification script..."
    bash "$SETUP_DIR/verify.sh" || { echo "Verification failed; check $LOG_FILE"; }
else
    echo "Warning: verify.sh not found at $SETUP_DIR/verify.sh"
fi