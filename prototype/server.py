import http.server
import socketserver
import os
import sys
import urllib.request
import urllib.error

PORT = 8082
DIRECTORY = os.path.dirname(os.path.abspath(__file__))
BACKEND_URL = os.environ.get(
    "BACKEND_URL", 
    "https://harimau-backend-204079990661.asia-southeast1.run.app"
).rstrip('/')

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        if self.path.startswith("/api/"):
            self.proxy_request()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            self.proxy_request()
        else:
            self.send_error(405, "Method Not Allowed")

    def proxy_request(self):
        target_url = f"{BACKEND_URL}{self.path}"
        try:
            req = urllib.request.Request(target_url)
            # Forward headers
            for header, value in self.headers.items():
                if header.lower() not in ['host', 'content-length']:
                    req.add_header(header, value)
            
            # Forward body if POST
            content_length = self.headers.get('Content-Length')
            data = None
            if content_length and self.command == "POST":
                data = self.rfile.read(int(content_length))

            with urllib.request.urlopen(req, data=data, timeout=35) as resp:
                self.send_response(resp.status)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                for k, v in resp.headers.items():
                    if k.lower() not in ['access-control-allow-origin', 'transfer-encoding', 'content-length']:
                        self.send_header(k, v)
                content = resp.read()
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            err_content = e.read()
            self.wfile.write(err_content if err_content else b'{"error":"Upstream HTTP error"}')
        except Exception as err:
            self.send_response(502)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(f'{{"error":"Failed to connect to backend: {str(err)}"}}'.encode())

    def end_headers(self):
        # Enable CORS and disable aggressive caching for smooth live prototyping
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

import socket

class DualStackServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    address_family = socket.AF_INET6

    def server_bind(self):
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except (AttributeError, OSError):
            pass
        super().server_bind()

if __name__ == "__main__":
    with DualStackServer(("::", PORT), CustomHandler) as httpd:
        print(f"============================================================")
        print(f"  Project Harimau // Live Backend Connected Workbench      ")
        print(f"  Frontend: http://localhost:{PORT}")
        print(f"  Backend Proxy: {BACKEND_URL}")
        print(f"============================================================")
        sys.stdout.flush()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
