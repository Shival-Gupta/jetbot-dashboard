# config.py
import os

# --- Server Configuration ---
APP_HOST = '0.0.0.0'
APP_PORT = 6001
SECRET_KEY = os.urandom(24) # For Flask session/SocketIO security

# --- Arduino Uploader Configuration ---
ALLOWED_EXTENSIONS = {'.ino'}
ARDUINO_CLI_TIMEOUT = 180 # Timeout in seconds
ARDUINO_CLI_PATH = 'arduino-cli' # Assumes it's in the system PATH

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

# --- Serial Monitor Configuration ---
COMMON_BAUD_RATES = [300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 74880, 115200, 230400, 250000, 500000, 1000000]

# --- Dashboard Configuration ---
TOP_PROCESS_COUNT = 5 # Number of top processes to show
DISK_FILTER_TYPES = ['ext4', 'vfat', 'ntfs', 'ext3'] # Filesystem types to show usage for (adjust as needed)