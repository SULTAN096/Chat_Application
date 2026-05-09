import socket
import threading
import json
import struct
import tkinter as tk
from tkinter import scrolledtext

# --- CONFIGURATION ---
# Listen on all available network interfaces
HOST = '0.0.0.0'
# Port number to listen on
PORT = 5555

# --- STYLING ---
# Colors and fonts for the server console window
THEME = {
    "bg": "#0c0c0c",      
    "fg": "#0080ff",       
    "font": ("Consolas", 10)
}

class ChatServer:
    def __init__(self, root):
        self.root = root
        self.root.title("SERVER CONSOLE")
        self.root.geometry("500x400")
        self.root.configure(bg=THEME["bg"])
        
        # Header Label
        lbl = tk.Label(root, text=">> SERVER STATUS: RUNNING", bg=THEME["bg"], fg="white", font=("Consolas", 12, "bold"))
        lbl.pack(pady=10)

        # Scrollable text area to display server logs
        self.log_area = scrolledtext.ScrolledText(root, state='disabled', bg="black", fg=THEME["fg"], 
                                                  insertbackground="white", font=THEME["font"], borderwidth=0)
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Dictionary to keep track of connected clients (Username -> Socket)
        self.clients = {} 
        
        # Create the server socket (TCP)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((HOST, PORT))
        self.server_socket.listen()
        
        self.log(f"[INIT] Server bound to {HOST}:{PORT}")
        
        # Start a background thread to accept new connections so the GUI doesn't freeze
        threading.Thread(target=self.accept_loop, daemon=True).start()

    def log(self, msg):
        """Updates the GUI log area with a new message."""
        self.log_area.config(state='normal') # Enable writing
        self.log_area.insert(tk.END, f"> {msg}\n")
        self.log_area.see(tk.END)            # Auto-scroll to bottom
        self.log_area.config(state='disabled') # Disable writing (read-only)

    def send_packet(self, sock, data_dict):
        """Helper function to send JSON data with a size header."""
        try:
            # Convert dictionary to JSON bytes
            payload = json.dumps(data_dict).encode('utf-8')
            # Create a 4-byte header containing the size of the data
            header = struct.pack('>I', len(payload))
            # Send header followed by the actual data
            sock.sendall(header + payload)
        except: pass

    def accept_loop(self):
        """Continuously waits for and accepts new client connections."""
        while True:
            client, addr = self.server_socket.accept()
            # Start a separate thread to handle this specific client
            threading.Thread(target=self.handle_client, args=(client, addr), daemon=True).start()

    def handle_client(self, sock, addr):
        """Manages the connection for a single client."""
        username = ""
        try:
            # --- HANDSHAKE / LOGIN STEP ---
            # Receive the header (first 4 bytes) to know data size
            header = sock.recv(4)
            length = struct.unpack('>I', header)[0]
            # Receive the actual login data
            login_data = json.loads(sock.recv(length).decode('utf-8'))
            username = login_data['username']
            
            # Prevent duplicate usernames
            if username in self.clients:
                sock.close(); return

            # Save client info
            self.clients[username] = sock
            self.log(f"[CONN] {username} connected from {addr}")
            
            # Update user lists for everyone and announce arrival
            self.broadcast_user_list()
            self.route_message(username, {'type': 'INFO', 'target': 'General', 'msg': f'{username} joined.'})

            # --- MAIN MESSAGE LOOP ---
            while True:
                header = sock.recv(4)
                if not header: break # Client disconnected
                length = struct.unpack('>I', header)[0]
                
                # Read the full message based on length
                data = b""
                while len(data) < length:
                    packet = sock.recv(length - len(data))
                    if not packet: break
                    data += packet
                
                # Process the message
                msg = json.loads(data.decode('utf-8'))
                self.route_message(username, msg)
        except: pass
        finally:
            # --- CLEANUP ON DISCONNECT ---
            if username in self.clients:
                del self.clients[username]
                self.broadcast_user_list()
                self.route_message(username, {'type': 'INFO', 'target': 'General', 'msg': f'{username} left.'})
            sock.close()

    def route_message(self, sender, msg):
        """Decides where to send the message (General vs Private)."""
        target = msg.get('target')
        msg['src'] = sender # Attach sender name to the message
        
        if target == 'General':
            # Send to everyone except the sender
            for user, sock in self.clients.items():
                if user != sender: self.send_packet(sock, msg)
        elif target in self.clients:
            # Send to a specific user (Private message)
            self.send_packet(self.clients[target], msg)

    def broadcast_user_list(self):
        """Sends the list of currently connected users to all clients."""
        users = list(self.clients.keys())
        for sock in self.clients.values():
            self.send_packet(sock, {'type': 'USER_LIST', 'data': users})

if __name__ == "__main__":
    root = tk.Tk()
    ChatServer(root)
    root.mainloop()