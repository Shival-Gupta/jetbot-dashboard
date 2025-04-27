# config.py
import os
from dotenv import load_dotenv # Import load_dotenv

# --- IMPORTANT: Load environment variables from .env file ---
# This should ideally happen before accessing environment variables.
# While load_dotenv() is usually called in main.py, reading here ensures
# the environment is loaded if config is imported elsewhere stand-alone.
# However, the primary loading should still be in main.py for robustness.
project_folder = os.path.join(os.path.dirname(__file__), '..') # Adjust if config is deeper
load_dotenv(os.path.join(project_folder, '.env'))
# Alternatively, if .env is always in the CWD when running:
# load_dotenv()

# --- Server Configuration ---
APP_HOST = os.getenv('APP_HOST', '0.0.0.0') # Allow override via env if needed
APP_PORT = int(os.getenv('APP_PORT', 6001)) # Allow override via env if needed

# --- Security ---
# Load Secret Key from environment (.env file) - CRITICAL for security
# Provide a fallback ONLY for local testing if .env is missing, NOT for production.
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    print("WARNING: SECRET_KEY not found in environment variables or .env file. Using a default insecure key.")
    SECRET_KEY = 'temporary_insecure_development_key' # CHANGE THIS IN PRODUCTION VIA .env

# --- Arduino Uploader Configuration ---
ALLOWED_EXTENSIONS = {'.ino'}
ARDUINO_CLI_TIMEOUT = 180
ARDUINO_CLI_PATH = 'arduino-cli'

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
    "other": "Other..."
}

# --- Serial Monitor Configuration ---
COMMON_BAUD_RATES = [300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 74880, 115200, 230400, 250000, 500000, 1000000]

# --- Dashboard Configuration ---
TOP_PROCESS_COUNT = 5
DISK_FILTER_TYPES = ['ext4', 'vfat', 'ntfs', 'ext3', 'btrfs', 'apfs'] # Added common ones