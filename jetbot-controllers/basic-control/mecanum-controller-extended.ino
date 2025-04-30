/*
 * mecanum-controller-extended.ino
 * Version: 1.1
 *
 * Description: Controller for 4-wheel Mecanum drive using RMCS-2305 motor drivers.
 * Provides functionality for controlling a Mecanum robot via serial commands,
 * including basic movement and individual motor testing for mapping.
 *
 * Compatible with:
 * - controller-test.py
 * - controller-test-advanced.py
 * - flask_mecanum_control.py (Flask frontend)
 *
 * Original description follows:
 */
/*
 * 4-Wheel Mecanum Drive Motor Controller for RMCS-2305 Drivers
 *
 * Hardware Setup:
 * ---------------
 * - Two RMCS-2305 Dual Motor Drivers are used.
 * - Motor Driver 1 (Front):
 * • Channel 1 (Front Left): DIR pin to Arduino pin 2, PWM pin to pin 3.
 * • Channel 2 (Front Right): DIR pin to Arduino pin 4, PWM pin to pin 5.
 * - Motor Driver 2 (Rear):
 * • Channel 1 (Rear Left): DIR pin to Arduino pin 8, PWM pin to pin 9.
 * • Channel 2 (Rear Right): DIR pin to Arduino pin 10, PWM pin to pin 11.
 *
 * - The drivers' SLEEP pins should be tied HIGH to enable them.
 * - Optionally, a potentiometer can be connected to analog pin A0.
 *
 * Command Protocol:
 * -----------------
 * Commands are single lines of text terminated by newline.
 *
 * 1. Movement Command:
 * Format: "s1,s2,s3,s4" where each 's' is PWM speed (-255 to 255).
 * Order: Motor 0 (FL), Motor 1 (FR), Motor 2 (RL), Motor 3 (RR)
 * Positive = forward (DIR HIGH), Negative = reverse (DIR LOW).
 * Example: "150,150,150,150" (Move forward)
 * "0,0,0,0" (Stop)
 *
 * 2. Test Command:
 * Format: "TEST,motor_index,speed,duration_ms"
 * 'motor_index': 0 (FL), 1 (FR), 2 (RL), 3 (RR) according to code definition.
 * 'speed': PWM speed (-255 to 255).
 * 'duration_ms': How long to run the motor in milliseconds.
 * Example: "TEST,0,100,500" (Run Front Left motor forward at speed 100 for 500ms)
 */

#include <Arduino.h>

// Enable debug printing by setting DEBUG to 1; set to 0 to disable.
#define DEBUG 1

// --- Motor Configuration ---
// Structure to hold motor pin assignments.
struct Motor {
  uint8_t dirPin; // Direction control pin
  uint8_t pwmPin; // PWM (speed) control pin
};

// Using an enum for clarity on motor indices.
enum MotorIndex {
  FRONT_LEFT = 0, // Index 0
  FRONT_RIGHT,    // Index 1
  REAR_LEFT,      // Index 2
  REAR_RIGHT      // Index 3
};

// Define our four motors (order: Front Left, Front Right, Rear Left, Rear Right).
// **THIS IS THE MAPPING YOU WILL VERIFY USING THE TEST FUNCTION**
Motor motors[4] = {
  {2, 3},   // Motor 0: Assumed Front Left (Driver 1, channel 1)
  {4, 5},   // Motor 1: Assumed Front Right (Driver 1, channel 2)
  {8, 9},   // Motor 2: Assumed Rear Left (Driver 2, channel 1)
  {10, 11}  // Motor 3: Assumed Rear Right (Driver 2, channel 2)
};

const unsigned long BAUD_RATE = 9600;
const int NUM_MOTORS = 4;
const int PWM_MAX = 255;

// --- Serial Command Buffer Settings ---
#define CMD_BUFFER_SIZE 64   // Maximum command length
char cmdBuffer[CMD_BUFFER_SIZE];  // Buffer to store incoming command
int cmdIndex = 0;                 // Current position in the buffer

// --- Function Prototypes ---
void setupMotorPins();
void processSerialInput();
void handleCommand(const char* command);
bool parseSpeedCommand(const char* command, int speeds[NUM_MOTORS]);
bool parseTestCommand(const char* command, int* motorIndex, int* speed, unsigned long* duration);
void executeTest(int motorIndex, int speed, unsigned long duration);
void setMotorSpeed(int index, int speed);
void stopAllMotors();
void debugPrint(const char* msg);
void debugPrintf(const char* format, ...);


void setup() {
  // Initialize motor control pins.
  setupMotorPins();
  stopAllMotors(); // Ensure motors are stopped at boot

  // (Optional: initialize analog input for a potentiometer.)
  // pinMode(A0, INPUT);

  Serial.begin(BAUD_RATE);
  // Wait for Serial port to connect (needed for some boards like Leonardo, Micro)
  // Remove this or add a timeout if it causes issues on your board
  // while (!Serial) {
  //   delay(10); // Wait for serial connection
  // }
  Serial.println("Mecanum 4-Wheel Motor Controller Initialized (v1.1)");
  Serial.println("Ready for commands: 's1,s2,s3,s4' or 'TEST,idx,spd,dur'");
}

void loop() {
  // Process incoming serial data without blocking the main loop.
  processSerialInput();

  // Additional periodic tasks (e.g., sensor readings) can be added here.
  // Be mindful not to block for too long, especially if expecting commands frequently.
}

/*
 * setupMotorPins()
 * Initializes all motor pins as OUTPUT.
 */
void setupMotorPins() {
  for (int i = 0; i < NUM_MOTORS; i++) {
    pinMode(motors[i].dirPin, OUTPUT);
    pinMode(motors[i].pwmPin, OUTPUT);
    digitalWrite(motors[i].dirPin, LOW); // Default direction
    analogWrite(motors[i].pwmPin, 0);   // Default speed (off)
  }
}

/*
 * processSerialInput()
 * Reads serial data one character at a time into a fixed buffer.
 * When a newline (or carriage return) is encountered, the complete command
 * is processed and the buffer is reset. Handles backspace for basic editing.
 */
void processSerialInput() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    // Handle backspace/delete characters
    if (c == '\b' || c == 127) {
      if (cmdIndex > 0) {
        cmdIndex--;
        // Optional: Echo backspace to terminal if needed
        // Serial.write('\b'); Serial.write(' '); Serial.write('\b');
      }
    }
    // End of command detected.
    else if (c == '\n' || c == '\r') {
      if (cmdIndex > 0) { // Process only if buffer is not empty
        cmdBuffer[cmdIndex] = '\0';  // Null-terminate the string.
        handleCommand(cmdBuffer);
        cmdIndex = 0;  // Reset buffer for the next command.
      }
       // Ignore empty lines by simply resetting index if 0
       else {
         cmdIndex = 0;
       }
    }
    // Add character to buffer if space allows
    else if (cmdIndex < CMD_BUFFER_SIZE - 1) {
      cmdBuffer[cmdIndex++] = c;
    }
    // Buffer overflow
    else {
      debugPrint("Error: Command buffer overflow. Command ignored.");
      // Flush remaining input in the buffer for this line
      while (Serial.available() > 0 && Serial.read() != '\n');
      cmdIndex = 0; // Reset buffer
    }
  }
}


/*
 * handleCommand()
 * Processes a complete command string. Determines if it's a speed command
 * or a test command and calls the appropriate parser and executor.
 *
 * Parameters:
 * command - A null-terminated C-string containing the command.
 */
void handleCommand(const char* command) {
  #if DEBUG
  Serial.print("Received command: ");
  Serial.println(command);
  #endif

  // Check if it's a TEST command
  if (strncmp(command, "TEST,", 5) == 0) {
    int motorIndex, speed;
    unsigned long duration;
    if (parseTestCommand(command, &motorIndex, &speed, &duration)) {
      executeTest(motorIndex, speed, duration);
    } else {
      debugPrint("Error: Failed to parse TEST command.");
    }
  }
  // Otherwise, assume it's a speed command
  else {
    int speeds[NUM_MOTORS] = {0}; // Default to 0 speeds
    if (parseSpeedCommand(command, speeds)) {
      // Update each motor with the parsed speed.
      for (int i = 0; i < NUM_MOTORS; i++) {
        setMotorSpeed(i, speeds[i]);
      }
      #if DEBUG
      debugPrintf("Set speeds: %d, %d, %d, %d\n", speeds[0], speeds[1], speeds[2], speeds[3]);
      #endif
    } else {
      debugPrint("Error: Failed to parse speed command. Format: s1,s2,s3,s4");
    }
  }
}

/*
 * parseSpeedCommand()
 * Parses a command string formatted as "num,num,num,num" into an array of integers.
 *
 * Parameters:
 * command - The input command string.
 * speeds  - An array to be filled with the parsed speed values.
 *
 * Returns:
 * true if exactly 4 integers are successfully parsed, false otherwise.
 */
bool parseSpeedCommand(const char* command, int speeds[NUM_MOTORS]) {
  // Use strtok to handle potential extra spaces or variations
  char tempCmd[CMD_BUFFER_SIZE];
  strncpy(tempCmd, command, CMD_BUFFER_SIZE - 1);
  tempCmd[CMD_BUFFER_SIZE - 1] = '\0'; // Ensure null termination

  char* token = strtok(tempCmd, ",");
  int count = 0;
  while (token != NULL && count < NUM_MOTORS) {
    // Attempt to convert token to integer
    char* endptr;
    long val = strtol(token, &endptr, 10);

    // Check if conversion was successful and consumed the entire token
    if (endptr != token && *endptr == '\0') {
       speeds[count++] = (int)val;
    } else {
      // Invalid number format in token
      return false;
    }
    token = strtok(NULL, ",");
  }

  // Check if we got exactly NUM_MOTORS values
  return (count == NUM_MOTORS);
}


/*
 * parseTestCommand()
 * Parses a command string formatted as "TEST,motor_index,speed,duration_ms".
 *
 * Parameters:
 * command     - The input command string (starting with "TEST,").
 * motorIndex  - Pointer to store the parsed motor index.
 * speed       - Pointer to store the parsed speed.
 * duration    - Pointer to store the parsed duration.
 *
 * Returns:
 * true if parsing is successful and values are within valid ranges, false otherwise.
 */
bool parseTestCommand(const char* command, int* motorIndex, int* speed, unsigned long* duration) {
  // Format: TEST,index,speed,duration
  int numParsed = sscanf(command, "TEST,%d,%d,%lu", motorIndex, speed, duration);

  if (numParsed == 3) {
    // Basic validation
    if (*motorIndex < 0 || *motorIndex >= NUM_MOTORS) {
      debugPrintf("Error: Invalid motor index %d. Must be 0-%d.\n", *motorIndex, NUM_MOTORS - 1);
      return false;
    }
    // Speed validation is handled by setMotorSpeed's constrain
    // Duration validation (optional, e.g., prevent extremely long tests)
    if (*duration > 30000) { // Limit test duration to 30 seconds
        debugPrint("Warning: Test duration capped at 30000ms.");
        *duration = 30000;
    }
    return true;
  }
  return false;
}

/*
 * executeTest()
 * Runs a single specified motor for a given duration and then stops it.
 *
 * Parameters:
 * motorIndex - Index of the motor to test (0-3).
 * speed      - Speed to run the motor (-255 to 255).
 * duration   - Duration to run in milliseconds.
 */
void executeTest(int motorIndex, int speed, unsigned long duration) {
  if (motorIndex < 0 || motorIndex >= NUM_MOTORS) return;

  debugPrintf("Testing Motor %d at speed %d for %lu ms...\n", motorIndex, speed, duration);

  // Ensure other motors are stopped (optional, but safer for testing)
  // stopAllMotors(); // Uncomment if you want absolute certainty only one motor runs

  setMotorSpeed(motorIndex, speed);
  delay(duration); // Block execution for the test duration
  setMotorSpeed(motorIndex, 0); // Stop the motor after the test

  debugPrintf("Test finished for Motor %d.\n", motorIndex);
}


/*
 * setMotorSpeed()
 * Sets the speed and direction for the specified motor.
 *
 * Parameters:
 * index - The index of the motor (0 to 3).
 * speed - A signed integer (-PWM_MAX to PWM_MAX). Positive for forward, negative for reverse.
 */
void setMotorSpeed(int index, int speed) {
  if (index < 0 || index >= NUM_MOTORS) return; // Invalid index check

  // Determine direction and absolute speed
  bool reverse = (speed < 0);
  int absSpeed = abs(speed);

  // Clamp speed to the maximum PWM value
  absSpeed = constrain(absSpeed, 0, PWM_MAX);

  // Set direction pin: HIGH for "forward", LOW for "reverse"
  // Note: "Forward" wheel rotation depends on motor wiring and mounting.
  // This assumes HIGH on DIR pin corresponds to intended forward motion.
  digitalWrite(motors[index].dirPin, reverse ? LOW : HIGH);

  // Set PWM speed
  analogWrite(motors[index].pwmPin, absSpeed);

  // Debug print for individual motor setting (can be noisy)
  // #if DEBUG
  // debugPrintf("Motor %d: Dir=%s, Speed=%d\n", index, reverse ? "LOW (Rev)" : "HIGH (Fwd)", absSpeed);
  // #endif
}

/*
* stopAllMotors()
* Sets speed for all motors to 0.
*/
void stopAllMotors() {
  debugPrint("Stopping all motors.");
  for (int i = 0; i < NUM_MOTORS; i++) {
    setMotorSpeed(i, 0);
  }
}

/*
 * debugPrint()
 * Utility function for printing debug messages if debugging is enabled.
 */
void debugPrint(const char* msg) {
  #if DEBUG
  Serial.println(msg);
  #endif
}

/*
 * debugPrintf()
 * Utility function for printing formatted debug messages if debugging is enabled.
 */
void debugPrintf(const char* format, ...) {
  #if DEBUG
  char buf[128]; // Buffer for formatted string
  va_list args;
  va_start(args, format);
  vsnprintf(buf, sizeof(buf), format, args);
  va_end(args);
  Serial.print(buf); // Use print to potentially avoid extra newline
  #endif
}
