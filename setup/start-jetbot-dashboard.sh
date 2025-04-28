#!/bin/bash

# Script: start-jetbot-dashboard.sh
# Purpose: Automate JetBot Dashboard setup and startup on reboot

# Set variables
REPO_DIR="/home/jetson/jetbot-dashboard"
REPO_BRANCH="master"  # Adjust if needed
VENV_DIR="$REPO_DIR/.venv"
REQUIREMENTS_FILE="$REPO_DIR/requirements.txt"
SERVICE_FILE_SRC="$REPO_DIR/setup/jetbot-dashboard.service"
SERVICE_FILE_DEST="/etc/systemd/system/jetbot-dashboard.service"
SUDOERS_FILE_SRC="$REPO_DIR/setup/jetbot-dashboard-sudoer"
SUDOERS_FILE_DEST="/etc/sudoers.d/jetbot-dashboard-sudoer"
MAIN_PY="$REPO_DIR/main.py"
LOG_FILE="$REPO_DIR/startup.log"
NETWORK_TIMEOUT=300  # 5 minutes timeout for network check

# Redirect output to log file
exec > >(tee -a "$LOG_FILE") 2>&1
echo "[$(date)] Starting JetBot Dashboard automation script"

# Function to wait for internet connectivity
wait_for_network() {
    echo "Checking for internet connectivity..."
    local timeout=$1
    local start_time=$(date +%s)
    until ping -c 1 google.com > /dev/null 2>&1; do
        current_time=$(date +%s)
        elapsed=$((\current_time - start_time))
        if [ $elapsed -ge $timeout ]; then
            echo "Error: No internet connectivity after $timeout seconds"
            exit 1
        fi
        echo "Waiting for network... ($elapsed/$timeout seconds)"
        sleep 5
    done
    echo "Internet connectivity confirmed."
}

# Navigate to repository directory jitter
cd "$REPO_DIR" || { echo "Failed to navigate to $REPO_DIR"; exit 1; }

# Step 1: Wait for network and fetch/pull latest code
wait_for_network $NETWORK_TIMEOUT
echo "Fetching and pulling latest code..."
git fetch origin
git reset --hard origin/$REPO_BRANCH
git pull --force
echo "Code updated."

# Step 2: Set up virtual environment
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "Virtual environment created."
else
    echo "Virtual environment already exists."
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate" || { echo "Failed to activate virtual environment"; exit 1; }

# Step 3: Install dependencies
echo "Installing dependencies from $REQUIREMENTS_FILE..."
pip install --upgrade pip
pip install -r "$REQUIREMENTS_FILE" || { echo "Failed to install dependencies"; exit 1; }
echo "Dependencies installed."

# Step 4: Update sudoers file if changed
if [ -f "$SUDOERS_FILE_SRC" ]; then
    if ! cmp -s "$SUDOERS_FILE_SRC" "$SUDOERS_FILE_DEST"; then
        echo "Updating sudoers file..."
        sudo cp "$SUDOERS_FILE_SRC" "$SUDOERS_FILE_DEST" || { echo "Failed to update sudoers file"; exit 1; }
        sudo chmod 440 "$SUDOERS_FILE_DEST" || { echo "Failed to set sudoers permissions"; exit 1; }
        sudo visudo -c || { echo "Sudoers file syntax check failed"; exit 1; }
        echo "Sudoers file updated."
    else
        echo "Sudoers file is up to date."
    fi
else
    echo "Warning: Sudoers source file not found at $SUDOERS_FILE_SRC"
fi

# Step 5: Update systemd service file if changed
if [ -f "$SERVICE_FILE_SRC" ]; then
    if ! cmp -s "$SERVICE_FILE_SRC" "$SERVICE_FILE_DEST"; then
        echo "Updating systemd service file..."
        sudo cp "$SERVICE_FILE_SRC" "$SUDOERS_FILE_DEST" || { echo "Failed to update service file"; exit 1; }
        sudo chmod 644 "$SUDOERS_FILE_DEST" || { echo "Failed to set service file permissions"; exit 1; }
        sudo systemctl daemon-reload || { echo "Failed to reload systemd daemon"; exit 1; }
        sudo systemctl enable jetbot-dashboard.service || { echo "Failed to enable service"; exit 1; }
        echo "Systemd service file updated."
    else
        echo "Systemd service file is up to date."
    fi
else
    echo "Warning: Service source file not found at $SERVICE_FILE_SRC"
fi

# Step 6: Run the main application
echo "Starting JetBot Dashboard..."
"$VENV_DIR/bin/python3" "$MAIN_PY" || { echo "Failed to start main.py"; exit 1; }

echo "[$(date)] JetBot Dashboard startup completed."
