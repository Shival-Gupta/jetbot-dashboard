#!/bin/bash

# Script: verify.sh
# Purpose: Verify the JetBot Dashboard setup on Jetson Nano
# Run: sudo bash setup/verify.sh from /home/jetson/jetbot-dashboard

# Set variables
REPO_DIR="/home/jetson/jetbot-dashboard"
SETUP_DIR="$REPO_DIR/setup"
VENV_DIR="$REPO_DIR/.venv"
REQUIREMENTS_FILE="$REPO_DIR/requirements.txt"
SERVICE_NAME="jetbot-dashboard.service"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"
SUDOERS_FILE="/etc/sudoers.d/jetbot-dashboard-sudoer"
LOG_FILE="$REPO_DIR/verify.log"
STARTUP_LOG="$REPO_DIR/startup.log"
SETUP_LOG="$REPO_DIR/setup.log"
DASHBOARD_URL="http://localhost:6001"
REPO_BRANCH="master"
NETWORK_TIMEOUT=10  # 10 seconds for network check

# Redirect output to log file and console
exec > >(tee -a "$LOG_FILE") 2>&1
echo "[$(date)] Starting JetBot Dashboard verification"

# Function to print status
print_status() {
    local check=$1
    local status=$2
    local message=$3
    printf "%-40s: %-8s %s\n" "$check" "$status" "$message"
}

# Function to check internet connectivity
check_network() {
    echo "Checking internet connectivity..."
    local timeout=$1
    local start_time=$(date +%s)
    until ping -c 1 google.com > /dev/null 2>&1; do
        current_time=$(date +%s)
        elapsed=$((current_time - start_time))
        if [ $elapsed -ge $timeout ]; then
            print_status "Internet Connectivity" "FAILED" "No internet after $timeout seconds"
            return 1
        fi
        sleep 1
    done
    print_status "Internet Connectivity" "OK" "Internet access confirmed"
    return 0
}

# Step 1: Check network
check_network $NETWORK_TIMEOUT || echo "Warning: Network issues may affect some checks"

# Step 2: Check repository directory
if [ -d "$REPO_DIR" ]; then
    print_status "Repository Directory" "OK" "$REPO_DIR exists"
    cd "$REPO_DIR" || { print_status "Repository Navigation" "FAILED" "Cannot cd to $REPO_DIR"; exit 1; }
else
    print_status "Repository Directory" "FAILED" "$REPO_DIR does not exist"
    exit 1
fi

# Step 3: Check Git branch and status
if git rev-parse --verify $REPO_BRANCH > /dev/null 2>&1; then
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    if [ "$current_branch" = "$REPO_BRANCH" ]; then
        print_status "Git Branch" "OK" "On branch $REPO_BRANCH"
    else
        print_status "Git Branch" "FAILED" "On $current_branch, expected $REPO_BRANCH"
    fi
    git fetch origin > /dev/null 2>&1
    if git diff origin/$REPO_BRANCH --quiet; then
        print_status "Git Repository Status" "OK" "Up-to-date with origin/$REPO_BRANCH"
    else
        print_status "Git Repository Status" "WARNING" "Local changes or behind origin/$REPO_BRANCH"
    fi
else
    print_status "Git Branch" "FAILED" "Branch $REPO_BRANCH not found"
fi

# Step 4: Check virtual environment
if [ -d "$VENV_DIR" ]; then
    print_status "Virtual Environment" "OK" "$VENV_DIR exists"
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate" || { print_status "Virtual Environment Activation" "FAILED" "Cannot activate $VENV_DIR"; exit 1; }
        if pip check > /dev/null 2>&1; then
            print_status "Dependencies" "OK" "All dependencies satisfied"
        else
            print_status "Dependencies" "FAILED" "Dependency issues detected; run 'pip check' for details"
        fi
        deactivate
    else
        print_status "Virtual Environment Activation" "FAILED" "No activate script in $VENV_DIR"
    fi
else
    print_status "Virtual Environment" "FAILED" "$VENV_DIR does not exist"
fi

# Step 5: Check systemd service
if systemctl is-active $SERVICE_NAME > /dev/null; then
    print_status "Service Status" "OK" "$SERVICE_NAME is active"
else
    print_status "Service Status" "FAILED" "$SERVICE_NAME is not running; try 'sudo systemctl start $SERVICE_NAME'"
fi
if systemctl is-enabled $SERVICE_NAME > /dev/null; then
    print_status "Service Enabled" "OK" "$SERVICE_NAME is enabled"
else
    print_status "Service Enabled" "FAILED" "$SERVICE_NAME is not enabled; try 'sudo systemctl enable $SERVICE_NAME'"
fi
if [ -f "$SERVICE_FILE" ]; then
    print_status "Service File" "OK" "$SERVICE_FILE exists"
    if cmp -s "$SERVICE_FILE" "$SETUP_DIR/jetbot-dashboard.service"; then
        print_status "Service File Consistency" "OK" "Matches repository version"
    else
        print_status "Service File Consistency" "WARNING" "Differs from repository version"
    fi
else
    print_status "Service File" "FAILED" "$SERVICE_FILE does not exist"
fi

# Step 6: Check sudoers file
if [ -f "$SUDOERS_FILE" ]; then
    print_status "Sudoers File" "OK" "$SUDOERS_FILE exists"
    if visudo -c > /dev/null 2>&1; then
        print_status "Sudoers Syntax" "OK" "Sudoers configuration is valid"
    else
        print_status "Sudoers Syntax" "FAILED" "Invalid sudoers configuration; check $SUDOERS_FILE"
    fi
else
    print_status "Sudoers File" "FAILED" "$SUDOERS_FILE does not exist"
fi

# Step 7: Check dashboard accessibility
if curl --connect-timeout 5 --head "$DASHBOARD_URL" > /dev/null 2>&1; then
    print_status "Dashboard Accessibility" "OK" "$DASHBOARD_URL is accessible"
else
    print_status "Dashboard Accessibility" "FAILED" "$DASHBOARD_URL is not accessible; check service and port 6001"
fi

# Step 8: Check logs for errors
if [ -f "$SETUP_LOG" ]; then
    if grep -i -E '\b(error|failed)\b' "$SETUP_LOG" > /dev/null; then
        print_status "Setup Log" "WARNING" "Errors or failures found in $SETUP_LOG"
        echo "Setup Log Errors:"
        grep -i "error\|failed" "$SETUP_LOG" | head -n 5
    else
        print_status "Setup Log" "OK" "No errors in $SETUP_LOG"
    fi
else
    print_status "Setup Log" "FAILED" "$SETUP_LOG does not exist"
fi
if [ -f "$STARTUP_LOG" ]; then
    if grep -i "error\|failed" "$STARTUP_LOG" > /dev/null; then
        print_status "Startup Log" "WARNING" "Errors or failures found in $STARTUP_LOG"
        echo "Startup Log Errors:"
        grep -i "error\|failed" "$STARTUP_LOG" | head -n 5
    else
        print_status "Startup Log" "OK" "No errors in $STARTUP_LOG"
    fi
else
    print_status "Startup Log" "FAILED" "$STARTUP_LOG does not exist"
fi

# Step 9: Summary
echo "[$(date)] Verification complete. Summary:"
if grep -E "FAILED|WARNING" "$LOG_FILE" | grep -v "Verification complete" | uniq; then
    echo "Issues detected. Review details above."
else
    echo "All checks passed!"
fi

echo "Logs saved to $LOG_FILE"
echo "To fix issues, review messages above and consider re-running setup.sh or checking logs."