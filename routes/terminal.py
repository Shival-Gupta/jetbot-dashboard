# routes/terminal.py

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
    /* Make sure #term fills remaining space */
    #term { width: 100%; height: 100%; }
  </style>
</head>
<body class="bg-white dark:bg-gray-900 flex flex-col h-screen">
  <!-- Header -->
  <div class="flex justify-between items-center p-4 bg-gray-100 dark:bg-gray-800 mb-2">
    <!-- Left: back to dashboard -->
    <a href="/" class="text-blue-600 hover:text-blue-700">
      &larr; 🏠︎
    </a>

    <!-- Center: title -->
    <h1 class="text-2xl font-bold text-center text-gray-700 dark:text-gray-200 flex-grow">
      Web Shell
    </h1>

    <!-- Right: reconnect + theme toggle -->
    <div class="flex space-x-2 items-center">
      <button
        id="reconnectBtn"
        class="hidden px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
      >
        Reconnect
      </button>
      <button
        id="themeToggle"
        class="px-3 py-1 bg-gray-300 dark:bg-gray-600 rounded text-sm hover:bg-gray-400 dark:hover:bg-gray-500"
      >
        <span id="themeIcon">🌙</span>
      </button>
    </div>
  </div>

  <!-- Terminal viewport -->
  <div id="term" class="flex-1 min-h-0"></div>

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
    def __init__(self, namespace):
        super().__init__(namespace)
        # map each client sid → its PTY fd
        self.clients = {}

    def on_connect(self):
        sid = request.sid
        # fork a new PTY; child runs bash
        pid, fd = pty.fork()
        # save that fd for this client
        self.clients[sid] = fd

        if pid == 0:
            # in child: set TERM and start bash
            os.environ['TERM'] = 'xterm-256color'
            os.execv('/bin/bash', ['/bin/bash', '--login'])
        else:
            # in parent: read PTY output for this client
            eventlet.spawn_n(self._reader, fd, sid)

    def _reader(self, fd, sid):
        while True:
            try:
                data = os.read(fd, 1024)
            except OSError:
                break
            if not data:
                socketio_instance.emit('exit', namespace='/terminal', room=sid)
                break
            socketio_instance.emit(
                'output',
                {'data': data.decode(errors='ignore')},
                namespace='/terminal',
                room=sid
            )

    def on_input(self, message):
        fd = self.clients.get(request.sid)
        if fd is not None:
            os.write(fd, message['data'].encode())

    def on_disconnect(self):
        sid = request.sid
        fd = self.clients.pop(sid, None)
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
