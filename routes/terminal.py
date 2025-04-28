import os
import pty
import eventlet
from flask import Blueprint, render_template_string, request
from flask_socketio import Namespace

# Will be set by main.py
socketio_instance = None

def init_socketio(sio):
    global socketio_instance
    socketio_instance = sio

terminal_bp = Blueprint('terminal', __name__)

@terminal_bp.route('/terminal')
def terminal():
    # Inline HTML + JS (Tailwind theme, xterm.js, reconnect, exit handling)
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Web Shell</title>

  <!-- Tailwind CSS (class-based dark mode) -->
  <script>
    tailwind.config = { darkMode: 'class' };
  </script>
  <script src="https://cdn.tailwindcss.com"></script>

  <!-- xterm.js CSS & JS -->
  <link rel="stylesheet" href="https://unpkg.com/xterm@4.19.0/css/xterm.css" />
  <script src="https://unpkg.com/xterm@4.19.0/lib/xterm.js"></script>

  <!-- Socket.IO client -->
  <script src="https://cdn.socket.io/4.6.1/socket.io.min.js"></script>

  <style>
    /* Full‐screen terminal area */
    #term { width:100%; height:100%; }
  </style>
</head>
<body class="bg-white dark:bg-gray-900 flex flex-col h-screen">
  <!-- Header -->
  <div class="flex-shrink-0 p-4 bg-gray-100 dark:bg-gray-800 flex justify-between items-center">
    <h1 class="text-lg font-semibold text-gray-900 dark:text-gray-100">Web Shell</h1>
    <div class="space-x-2">
      <button id="reconnectBtn" class="hidden px-3 py-1 bg-blue-600 text-white rounded text-sm">Reconnect</button>
      <button id="themeToggle" class="px-3 py-1 bg-gray-300 dark:bg-gray-600 rounded text-sm">
        <span id="themeIcon">🌙</span>
      </button>
    </div>
  </div>

  <!-- Terminal viewport -->
  <div id="term" class="flex-grow"></div>

  <script>
    // ===== Theme Toggle =====
    const themeToggle = document.getElementById('themeToggle');
    const themeIcon = document.getElementById('themeIcon');
    function updateIcon() {
      themeIcon.textContent = document.documentElement.classList.contains('dark') ? '☀️' : '🌙';
    }
    themeToggle.addEventListener('click', () => {
      document.documentElement.classList.toggle('dark');
      updateIcon();
    });
    updateIcon();

    // ===== Terminal & Socket.IO Setup =====
    const socket = io('/terminal');
    const term = new Terminal({ cursorBlink: true });
    term.open(document.getElementById('term'));
    term.focus();

    term.onData(data => socket.emit('input', { data }));
    socket.on('output', msg => term.write(msg.data));

    // ===== Exit & Disconnect Handling =====
    const reconnectBtn = document.getElementById('reconnectBtn');

    socket.on('exit', () => {
      term.write('\\r\\n\\x1b[31m*** Shell exited ***\\x1b[0m\\r\\n');
      reconnectBtn.classList.remove('hidden');
    });

    socket.on('disconnect', reason => {
      term.write(`\\r\\n\\x1b[33m*** Disconnected: ${reason} ***\\x1b[0m\\r\\n`);
      reconnectBtn.classList.remove('hidden');
    });

    reconnectBtn.addEventListener('click', () => window.location.reload());
  </script>
</body>
</html>
    """)

class TerminalNamespace(Namespace):
    def on_connect(self):
      # Fork a PTY; child will exec bash, parent gets (pid, fd)
      pid, fd = pty.fork()
      # Save the fd so on_input() can write into it
      self.fd = fd

      if pid == 0:
          # In the child process: tell programs what terminal type to use
          os.environ['TERM'] = 'xterm-256color'
          # Launch bash as a login shell (loads ~/.bashrc, etc.)
          os.execv('/bin/bash', ['/bin/bash', '--login'])
      else:
          # In the parent process: start reading PTY output for this client
          eventlet.spawn_n(self._reader, fd, request.sid)

    def _reader(self, fd, sid):
        """Read from PTY and emit to the right client."""
        while True:
            try:
                data = os.read(fd, 1024)
            except OSError:
                break
            if not data:
                # EOF => shell closed
                socketio_instance.emit('exit', namespace='/terminal', room=sid)
                break
            socketio_instance.emit('output',
                                   {'data': data.decode(errors='ignore')},
                                   namespace='/terminal',
                                   room=sid)

    def on_input(self, message):
        # Write incoming keystrokes to the PTY
        os.write(self.fd, message['data'].encode())

    def on_disconnect(self):
        # Nothing special needed beyond letting the PTY thread notice EOF
        pass
