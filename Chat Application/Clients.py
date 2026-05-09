import socket
import threading
import json
import struct
import base64
import os
import time
import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox, Listbox 
import sys
import subprocess

# --- CONFIGURATION ---
PORT = 5555

# --- MEDIA IMPORTS ---
# Try to import Windows sound library.
try:
    import winsound
    import ctypes
    WIN_AUDIO = True
except ImportError:
    WIN_AUDIO = False

# Try to import OpenCV for video.
try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

# --- THEME CONSTANTS ---
COLORS = {
    "bg": "#2C2F33",        
    "sidebar": "#23272A",   
    "input_bg": "#40444B",  
    "text": "#FFFFFF",      
    "accent": "#7289DA",    
    "accent_hover": "#677BC4",
    "green": "#43B581",     
    "red": "#F04747",       
    "font_main": ("Helvetica", 10),
    "font_head": ("Verdana", 12, "bold")
}

class MediaEngine:
    """Handles audio recording, playback, and video capture."""
    def __init__(self):
        self.cap = None
        # NOTE: Camera is NOT started here to keep the light off at startup.
    
    def start_cam(self):
        """Initializes the camera hardware."""
        if HAS_OPENCV and (self.cap is None or not self.cap.isOpened()):
            self.cap = cv2.VideoCapture(0)

    def stop_cam(self):
        """Releases the camera hardware (Turns off the light)."""
        if self.cap:
            self.cap.release()
            self.cap = None

    def play_audio(self, filename):
        try:
            if WIN_AUDIO: 
                winsound.PlaySound(filename, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                opener = 'afplay' if sys.platform == 'darwin' else 'aplay'
                subprocess.Popen([opener, filename])
        except: pass

    def record_audio(self, filename, duration):
        try:
            if WIN_AUDIO:
                mci = ctypes.windll.winmm.mciSendStringW
                mci("close capture", None, 0, None)
                mci("open new type waveaudio alias capture", None, 0, None)
                mci("record capture", None, 0, None)
                time.sleep(duration)
                abs_path = os.path.abspath(filename)
                mci(f'save capture "{abs_path}"', None, 0, None)
                mci("close capture", None, 0, None)
            else:
                subprocess.call(f"arecord -d {duration} -f cd {filename}", shell=True)
        except: pass

    def generate_video_frame(self, frame_counter):
        width, height = 160, 120
        # If webcam is working, get the real image
        if HAS_OPENCV and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                try:
                    frame = cv2.resize(frame, (width, height))
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    return f"P6 {width} {height} 255 ".encode() + frame.tobytes()
                except: pass
        
        # Fallback Animation if camera is off or not found
        header = f"P6 {width} {height} 255 ".encode()
        data = bytearray(width * height * 3)
        box_x, box_y = (frame_counter * 5) % width, (frame_counter * 3) % height
        for y in range(height):
            for x in range(width):
                idx = (y * width + x) * 3
                data[idx], data[idx+1], data[idx+2] = 0, x % 255, y % 255
                if box_x < x < box_x + 20 and box_y < y < box_y + 20:
                    data[idx] = 255
                    data[idx+1] = 0
        return header + data

media = MediaEngine()

class PrivateChatWindow:
    def __init__(self, master_root, target_user, client_app):
        self.target_user = target_user
        self.client_app = client_app
        self.is_audio_calling = False
        self.is_video_calling = False
        
        self.window = tk.Toplevel(master_root)
        self.window.title(f"@{target_user}")
        self.window.geometry("600x600")
        self.window.configure(bg=COLORS["bg"])
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)

        self.video_frame = tk.Frame(self.window, bg="black", height=200)
        self.video_frame.pack(fill=tk.X, padx=10, pady=10)
        self.video_frame.pack_propagate(False)
        self.video_label = tk.Label(self.video_frame, text="Waiting for Video...", bg="black", fg="#555")
        self.video_label.pack(expand=True)

        self.chat_area = scrolledtext.ScrolledText(self.window, state='disabled', bg=COLORS["input_bg"], fg=COLORS["text"], font=COLORS["font_main"], borderwidth=0)
        self.chat_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.chat_area.tag_config('me', foreground=COLORS["accent"], font=("Helvetica", 10, "bold"))
        self.chat_area.tag_config('them', foreground="#FFA500", font=("Helvetica", 10, "bold"))
        
        self.status_lbl = tk.Label(self.window, text="", bg=COLORS["bg"], fg=COLORS["red"], font=("Arial", 9))
        self.status_lbl.pack()

        btn_frame = tk.Frame(self.window, bg=COLORS["bg"])
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.mk_btn(btn_frame, "📎 File", self.send_file, COLORS["sidebar"]).pack(side=tk.LEFT, padx=2)
        self.vn_btn = self.mk_btn(btn_frame, "🎤 Voice Note", self.record_vn, COLORS["sidebar"])
        self.vn_btn.pack(side=tk.LEFT, padx=2)
        
        self.video_btn = self.mk_btn(btn_frame, "📹 Video Call", lambda: self.toggle_call("VIDEO"), COLORS["accent"])
        self.video_btn.pack(side=tk.RIGHT, padx=2)
        self.audio_btn = self.mk_btn(btn_frame, "📞 Voice Call", lambda: self.toggle_call("AUDIO"), COLORS["green"])
        self.audio_btn.pack(side=tk.RIGHT, padx=2)

        inp_frame = tk.Frame(self.window, bg=COLORS["bg"])
        inp_frame.pack(fill=tk.X, padx=10, pady=10)
        self.entry = tk.Entry(inp_frame, bg=COLORS["input_bg"], fg="white", font=COLORS["font_main"], insertbackground="white", relief=tk.FLAT)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
        self.entry.bind("<Return>", lambda e: self.send_text())
        self.mk_btn(inp_frame, "➤", self.send_text, COLORS["accent"]).pack(side=tk.LEFT, padx=(5,0))

    def mk_btn(self, parent, text, cmd, bg_col):
        btn = tk.Button(parent, text=text, command=cmd, bg=bg_col, fg="white", activebackground="#555", 
                        relief=tk.FLAT, font=("Arial", 9, "bold"), padx=10, pady=5)
        return btn

    def add_message(self, sender, text, link_path=None):
        self.client_app.append_to_chat(self.chat_area, sender, text, link_path)

    def update_video_frame(self, img_data):
        try:
            self.current_image = tk.PhotoImage(data=img_data)
            self.video_label.config(image=self.current_image, text="")
        except: pass

    def send_text(self):
        msg = self.entry.get()
        if msg:
            self.client_app.send_packet({'type': 'MSG', 'target': self.target_user, 'payload': msg})
            self.add_message("Me", msg)
            self.entry.delete(0, tk.END)

    def send_file(self): self.client_app.send_file(self.target_user, "FILE", self)

    def record_vn(self):
        self.status_lbl.config(text="Recording (5s)...", fg=COLORS["red"])
        self.vn_btn.config(state="disabled", bg=COLORS["red"])
        threading.Thread(target=self.client_app.record_and_send_vn, args=(self.target_user, self)).start()

    def toggle_call(self, mode):
        active = self.is_video_calling if mode == "VIDEO" else self.is_audio_calling
        if not active:
            self.client_app.send_packet({'type': 'CALL_SIGNAL', 'target': self.target_user, 'signal': 'REQUEST', 'mode': mode})
            self.add_message("System", f"Calling ({mode})...")
        else:
            self.end_call_ui(mode)
            self.client_app.send_packet({'type': 'CALL_SIGNAL', 'target': self.target_user, 'signal': 'END', 'mode': mode})

    def start_call_ui(self, mode):
        """Updates UI when a call connects and starts streaming."""
        self.stop_call_event = threading.Event()
        self.status_lbl.config(text=f"● LIVE {mode}", fg=COLORS["green"])
        if mode == "AUDIO":
            self.is_audio_calling = True
            self.audio_btn.config(text="✖ End Audio", bg=COLORS["red"])
            threading.Thread(target=self.stream_audio, daemon=True).start()
        elif mode == "VIDEO":
            self.is_video_calling = True
            # *** START CAMERA ***
            media.start_cam()
            self.video_btn.config(text="✖ End Video", bg=COLORS["red"])
            threading.Thread(target=self.stream_video, daemon=True).start()

    def end_call_ui(self, mode):
        """Resets UI when a call ends."""
        if hasattr(self, 'stop_call_event'): self.stop_call_event.set()
        self.status_lbl.config(text="Call Ended", fg="gray")
        if mode == "AUDIO":
            self.is_audio_calling = False
            self.audio_btn.config(text="📞 Voice Call", bg=COLORS["green"])
        elif mode == "VIDEO":
            self.is_video_calling = False
            # *** STOP CAMERA (Turn off light) ***
            media.stop_cam()
            self.video_btn.config(text="📹 Video Call", bg=COLORS["accent"])
            self.video_label.config(image='', text="[Video Ended]")

    def stream_audio(self):
        fname = "temp_stream.wav"
        while not self.stop_call_event.is_set():
            media.record_audio(fname, 1.5) 
            if self.stop_call_event.is_set(): break
            try:
                with open(fname, "rb") as f: data = base64.b64encode(f.read()).decode('utf-8')
                self.client_app.send_packet({'type': 'STREAM_AUDIO', 'target': self.target_user, 'payload': data})
            except: break

    def stream_video(self):
        frame_count = 0
        while not self.stop_call_event.is_set():
            ppm_bytes = media.generate_video_frame(frame_count)
            frame_count += 1
            b64_img = base64.b64encode(ppm_bytes).decode('utf-8')
            self.client_app.send_packet({'type': 'STREAM_VIDEO', 'target': self.target_user, 'payload': b64_img})
            time.sleep(0.1)

    def on_close(self):
        if self.is_audio_calling: self.toggle_call("AUDIO")
        if self.is_video_calling: self.toggle_call("VIDEO")
        
        # Ensure camera is off if window is closed
        media.stop_cam()
        
        if self.target_user in self.client_app.private_windows: del self.client_app.private_windows[self.target_user]
        self.window.destroy()

class ChatClient:
    def __init__(self, root):
        self.root = root
        self.root.withdraw()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.username = ""
        self.private_windows = {} 
        self.login_window()

    def login_window(self):
        win = tk.Toplevel(self.root)
        win.title("Login")
        win.geometry("300x250")
        win.configure(bg=COLORS["bg"])
        
        tk.Label(win, text="WELCOME", bg=COLORS["bg"], fg=COLORS["text"], font=("Verdana", 14, "bold")).pack(pady=20)
        
        f1 = tk.Frame(win, bg=COLORS["bg"]); f1.pack(pady=5)
        tk.Label(f1, text="IP Addr:", bg=COLORS["bg"], fg="#ccc").pack(anchor="w")
        e_ip = tk.Entry(f1, bg=COLORS["input_bg"], fg="white", relief=tk.FLAT, width=25)
        e_ip.insert(0, "127.0.0.1")
        e_ip.pack(ipady=4)
        
        f2 = tk.Frame(win, bg=COLORS["bg"]); f2.pack(pady=5)
        tk.Label(f2, text="Username:", bg=COLORS["bg"], fg="#ccc").pack(anchor="w")
        e_user = tk.Entry(f2, bg=COLORS["input_bg"], fg="white", relief=tk.FLAT, width=25)
        e_user.pack(ipady=4)
        
        def connect():
            try:
                self.sock.connect((e_ip.get(), PORT))
                payload = json.dumps({'username': e_user.get()}).encode('utf-8')
                self.sock.sendall(struct.pack('>I', len(payload)) + payload)
                self.username = e_user.get()
                win.destroy()
                self.setup_main_ui()
                self.root.deiconify() 
                threading.Thread(target=self.receive_loop, daemon=True).start()
            except Exception as e: messagebox.showerror("Connection Error", str(e))
            
        tk.Button(win, text="CONNECT", command=connect, bg=COLORS["accent"], fg="white", relief=tk.FLAT, font=("Arial", 10, "bold"), width=20).pack(pady=20)

    def setup_main_ui(self):
        self.root.title(f"HyperChat - {self.username}")
        self.root.geometry("850x600")
        self.root.configure(bg=COLORS["bg"])
        
        left = tk.Frame(self.root, width=220, bg=COLORS["sidebar"])
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)
        
        tk.Label(left, text="ONLINE USERS", bg=COLORS["sidebar"], fg="#888", font=("Arial", 9, "bold")).pack(pady=(15,5))
        
        self.user_list = Listbox(left, bg=COLORS["sidebar"], fg="white", selectbackground=COLORS["accent"], 
                                 borderwidth=0, font=("Helvetica", 11), highlightthickness=0)
        self.user_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.user_list.bind('<Double-Button-1>', self.open_private_chat)
        
        tk.Label(left, text="Double-click to chat", bg=COLORS["sidebar"], fg="#555", font=("Arial", 8)).pack(side=tk.BOTTOM, pady=10)

        right = tk.Frame(self.root, bg=COLORS["bg"])
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        head = tk.Frame(right, bg=COLORS["bg"], height=50)
        head.pack(fill=tk.X)
        self.head_lbl = tk.Label(head, text="# GENERAL CHAT", bg=COLORS["bg"], fg="white", font=COLORS["font_head"])
        self.head_lbl.pack(side=tk.LEFT, padx=15, pady=10)
        
        self.group_chat = scrolledtext.ScrolledText(right, bg=COLORS["input_bg"], fg="white", 
                                                    font=COLORS["font_main"], borderwidth=0, state='disabled')
        self.group_chat.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        self.group_chat.tag_config('me', foreground=COLORS["accent"], font=("Helvetica", 10, "bold"))
        self.group_chat.tag_config('them', foreground="#FFA500", font=("Helvetica", 10, "bold"))

        c_frame = tk.Frame(right, bg=COLORS["bg"], height=60)
        c_frame.pack(fill=tk.X, padx=15, pady=15)
        
        tk.Button(c_frame, text="📎", command=lambda: self.send_file("General", "FILE", None), 
                  bg=COLORS["sidebar"], fg="white", relief=tk.FLAT, width=3).pack(side=tk.LEFT, padx=(0, 2), fill=tk.Y)
        
        self.grp_vn_btn = tk.Button(c_frame, text="🎤", command=self.trigger_group_vn, 
                  bg=COLORS["sidebar"], fg="white", relief=tk.FLAT, width=4)
        self.grp_vn_btn.pack(side=tk.LEFT, padx=(0, 5), fill=tk.Y)

        self.grp_entry = tk.Entry(c_frame, bg=COLORS["input_bg"], fg="white", insertbackground="white", 
                                  relief=tk.FLAT, font=COLORS["font_main"])
        self.grp_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.grp_entry.bind("<Return>", lambda e: self.send_group_msg())
        
        tk.Button(c_frame, text="SEND", command=self.send_group_msg, 
                  bg=COLORS["accent"], fg="white", relief=tk.FLAT, padx=15).pack(side=tk.LEFT, padx=(5,0), fill=tk.Y)

    def open_private_chat(self, event):
        sel = self.user_list.curselection()
        if sel:
            user = self.user_list.get(sel[0])
            if user != self.username: self.get_window(user)

    def get_window(self, user):
        if user not in self.private_windows:
            self.private_windows[user] = PrivateChatWindow(self.root, user, self)
        self.private_windows[user].window.deiconify()
        return self.private_windows[user]

    def send_packet(self, data):
        try:
            payload = json.dumps(data).encode('utf-8')
            self.sock.sendall(struct.pack('>I', len(payload)) + payload)
        except: pass

    def append_to_chat(self, widget, sender, text, link=None):
        widget.config(state='normal')
        tag = 'me' if sender == "Me" else 'them'
        widget.insert(tk.END, f"{sender}: ", tag)
        if link:
            lnk_tag = f"lnk_{widget.index('end')}"
            widget.insert(tk.END, text + "\n", lnk_tag)
            widget.tag_config(lnk_tag, foreground="#4da6ff", underline=1)
            cmd = (lambda e: media.play_audio(link)) if "VOICE" in text else (lambda e: os.startfile(link) if os.name=='nt' else None)
            widget.tag_bind(lnk_tag, "<Button-1>", cmd)
        else:
            widget.insert(tk.END, text + "\n")
        widget.see(tk.END)
        widget.config(state='disabled')

    def send_group_msg(self):
        msg = self.grp_entry.get()
        if msg:
            self.send_packet({'type': 'MSG', 'target': 'General', 'payload': msg})
            self.append_to_chat(self.group_chat, "Me", msg)
            self.grp_entry.delete(0, tk.END)

    def send_file(self, target, ftype, win):
        fpath = filedialog.askopenfilename()
        if fpath:
            fname = os.path.basename(fpath)
            with open(fpath, "rb") as f: b64 = base64.b64encode(f.read()).decode('utf-8')
            self.send_packet({'type': 'MSG', 'target': target, 'payload': b64, 'is_file': True, 'filename': fname, 'filetype': ftype})
            msg = f"Sent {ftype}: {fname}"
            if target == "General": self.append_to_chat(self.group_chat, "Me", msg, fpath)
            elif win: win.add_message("Me", msg, fpath)

    def trigger_group_vn(self):
        self.head_lbl.config(text="# GENERAL CHAT (Recording 5s...)", fg=COLORS["red"])
        self.grp_vn_btn.config(state="disabled", bg=COLORS["red"])
        threading.Thread(target=self.record_and_send_vn, args=("General", None)).start()

    def record_and_send_vn(self, target, win):
        fname = f"vn_{int(time.time())}.wav"
        media.record_audio(fname, 5.0) 
        
        if win:
            win.status_lbl.config(text="", fg=COLORS["red"])
            win.vn_btn.config(state="normal", bg=COLORS["sidebar"])
        else:
            self.head_lbl.config(text="# GENERAL CHAT", fg="white")
            self.grp_vn_btn.config(state="normal", bg=COLORS["sidebar"])
            
        try:
            with open(fname, "rb") as f: b64 = base64.b64encode(f.read()).decode('utf-8')
            self.send_packet({'type': 'MSG', 'target': target, 'payload': b64, 'is_file': True, 'filename': fname, 'filetype': 'VOICE'})
            
            if target == "General":
                self.append_to_chat(self.group_chat, "Me", "[VOICE] Sent Note", fname)
            elif win:
                win.add_message("Me", "[VOICE] Sent Note", fname)
        except: pass

    def receive_loop(self):
        while True:
            try:
                header = self.sock.recv(4)
                if not header: break
                length = struct.unpack('>I', header)[0]
                data = b""
                while len(data) < length:
                    packet = self.sock.recv(length - len(data))
                    if not packet: break
                    data += packet
                msg = json.loads(data.decode('utf-8'))
                self.handle_msg(msg)
            except: break
        self.root.quit()

    def handle_msg(self, msg):
        mtype = msg.get('type')
        sender = msg.get('src')
        
        if mtype == 'USER_LIST':
            self.user_list.delete(0, tk.END)
            for u in msg['data']:
                if u != self.username: self.user_list.insert(tk.END, u)
        
        elif mtype == 'MSG':
            target = msg.get('target')
            widget = self.group_chat if target == 'General' else self.get_window(sender).chat_area
            if msg.get('is_file'):
                data = base64.b64decode(msg['payload'])
                fname = f"recv_{int(time.time())}_{msg['filename']}"
                with open(fname, "wb") as f: f.write(data)
                txt = "[VOICE] Note" if msg.get('filetype')=='VOICE' else f"[FILE] {msg['filename']}"
                self.append_to_chat(widget, sender, txt, os.path.abspath(fname))
            else:
                self.append_to_chat(widget, sender, msg['payload'])
        
        elif mtype == 'CALL_SIGNAL':
            mode, signal = msg.get('mode', 'AUDIO'), msg['signal']
            win = self.get_window(sender)
            if signal == 'REQUEST':
                if messagebox.askyesno("Incoming Call", f"{sender} is requesting a {mode} call."):
                    self.send_packet({'type': 'CALL_SIGNAL', 'target': sender, 'signal': 'ACCEPT', 'mode': mode})
                    win.start_call_ui(mode)
                else: self.send_packet({'type': 'CALL_SIGNAL', 'target': sender, 'signal': 'REJECT', 'mode': mode})
            elif signal == 'ACCEPT': win.start_call_ui(mode)
            elif signal == 'END': win.end_call_ui(mode)
        
        elif mtype == 'STREAM_AUDIO':
            try:
                with open(f"s_{sender}.wav", "wb") as f: f.write(base64.b64decode(msg['payload']))
                media.play_audio(f"s_{sender}.wav")
            except: pass
        elif mtype == 'STREAM_VIDEO':
            if sender in self.private_windows:
                self.private_windows[sender].update_video_frame(base64.b64decode(msg['payload']))

if __name__ == "__main__":
    root = tk.Tk()
    client = ChatClient(root)
    root.mainloop()