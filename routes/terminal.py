# routes/terminal.py

import os
import pty
import eventlet
from flask import Blueprint, render_template_string
from flask_socketio import Namespace

terminal_bp = Blueprint('terminal', __name__)

@terminal_bp.route('/terminal')
def terminal():
    # inline HTML + JS for xterm.js + Socket.IO client
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8"/>
      <title>Web Shell</title>
      <!-- xterm.js stylesheet -->
      <link rel="stylesheet" href="https://unpkg.com/xterm@4.19.0/css/xterm.css" />
      <!-- Socket.IO client (from CDN) -->
      <script src="https://cdn.socket.io/4.6.1/socket.io.min.js"></script>
      <!-- xterm.js library -->
      <script src="https://unpkg.com/xterm@4.19.0/lib/xterm.js"></script>
      <style>
        body, html { margin:0; height:100%; }
        #term { width:100%; height:100%; }
      </style>
    </head>
    <body>
      <div id="term"></div>
      <script>
        // connect to the '/terminal' namespace
        const socket = io('/terminal');
        const term   = new Terminal();
        term.open(document.getElementById('term'));

        // send keystrokes to server
        term.onData(data => socket.emit('input', { data }));

        // write server output to screen
        socket.on('output', msg => term.write(msg.data));
      </script>
    </body>
    </html>
    """)

class TerminalNamespace(Namespace):
    def on_connect(self):
        # fork a PTY and exec bash in the child
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.execv('/bin/bash', ['/bin/bash'])
        else:
            # parent: relay PTY output asynchronously
            eventlet.spawn_n(self._read_and_emit)

    def _read_and_emit(self):
        max_read = 1024
        while True:
            data = os.read(self.fd, max_read).decode(errors='ignore')
            self.emit('output', {'data': data})

    def on_input(self, message):
        os.write(self.fd, message['data'].encode())

    def on_disconnect(self):
        try:
            os.close(self.fd)
        except OSError:
            pass
