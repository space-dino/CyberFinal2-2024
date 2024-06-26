import socket
from tkinter import *
import customtkinter as tk
from threading import Thread
import cv2
import mss
from PIL import Image
import pyaudio
import time
import numpy as np
import lz4.frame
import final_protocol
import select
import zlib


class Client:
    def __init__(self):
        self.FORMAT, self.CHANNELS, self.RATE, self.A_CHUNK, self.audio, self.in_stream, self.out_stream = self.setup_audio()
        self.root, self.username, self.window, self.entry, self.password_entry, self.index_label, self.fps_label, self.username_label, self.screen_share_button, self.message_box, self.vid_mute_button, self.aud_mute_button = self.setup_gui()
        self.login_socket, self.video_socket, self.audio_socket, self.host, self.port = self.setup_network()
        self.labels, self.vid_data, self.aud_data, self.my_index, self.up = self.setup_data()
        self.vid = cv2.VideoCapture(0)
        self.resolution = (320, 240)
        self.vid.set(3, self.resolution[0])
        self.vid.set(4, self.resolution[1])
        self.is_sharing_screen = False
        self.login_socket.connect((self.host, self.port + 2))
        print("Connected to server")
        self.share_window = None
        self.vid_muted = False
        self.aud_muted = False

        self.root.mainloop()

    def setup_audio(self):
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = int(44100 / 4)
        A_CHUNK = int(1024 / 4)
        audio = pyaudio.PyAudio()
        in_stream = audio.open(format=FORMAT, channels=CHANNELS,
                               rate=RATE, input=True, frames_per_buffer=A_CHUNK)
        out_stream = audio.open(format=FORMAT, channels=CHANNELS,
                                rate=RATE, output=True, frames_per_buffer=A_CHUNK)

        return FORMAT, CHANNELS, RATE, A_CHUNK, audio, in_stream, out_stream

    def setup_gui(self):
        root = tk.CTk()
        root.withdraw()
        username = ""
        window = tk.CTkToplevel(root)
        window.title("Enter Your Credentials")
        tk.CTkLabel(window, text="Enter your name:").pack()
        entry = tk.CTkEntry(window)
        entry.pack()
        tk.CTkLabel(window, text="Enter your password:").pack()
        password_entry = tk.CTkEntry(window, show="*")
        password_entry.pack()
        tk.CTkButton(window, text="Join Meeting", command=self.submit).pack()
        tk.CTkButton(window, text="Sign Up", command=self.signup).pack()
        message_box = tk.CTkLabel(window, text="")
        message_box.pack()
        tk.CTkButton(root, text="Close", command=self.close_connection).grid(row=0, column=1)
        index_label = tk.CTkLabel(root, text="index")
        index_label.grid(row=1, column=1)
        fps_label = tk.CTkLabel(root, text="fps")
        fps_label.grid(row=2, column=1)
        username_label = tk.CTkLabel(root, text="username")
        username_label.grid(row=3, column=1)

        frame = tk.CTkFrame(root, border_width=1)
        screen_share_button = tk.CTkButton(frame, text="Share Screen", command=self.start_screen_sharing)
        screen_share_button.pack()
        vid_mute_button = tk.CTkButton(frame, text="Stop Video", command=lambda: self.mute(0))
        vid_mute_button.pack()
        aud_mute_button = tk.CTkButton(frame, text="Mute Audio", command=lambda: self.mute(1))
        aud_mute_button.pack()
        frame.grid(row=3, column=1)

        return root, username, window, entry, password_entry, index_label, fps_label, username_label, screen_share_button, message_box, vid_mute_button, aud_mute_button

    def setup_data(self):
        labels = []
        vid_data = b''
        aud_data = b''
        my_index = 0
        up = True

        return labels, vid_data, aud_data, my_index, up

    def setup_network(self):
        login_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        audio_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        host = '127.0.0.1'
        port = 9997

        return login_socket, video_socket, audio_socket, host, port

    def signup(self):
        username = self.entry.get()
        password = self.password_entry.get()
        # Send username and password to the server for signup
        final_protocol.send_credentials(self.login_socket, True, username, password)
        response = self.login_socket.recv(1024).decode()
        if response == 'signup_success':
            self.username_label.configure(text=username)
            self.message_box.configure(text="Signup succeeded!\nYou can join a meeting now")
        else:
            self.message_box.configure(text="Username already taken")

    def submit(self):
        self.username = self.entry.get()
        password = self.password_entry.get()
        # Send username and password to the server for login
        final_protocol.send_credentials(self.login_socket, False, self.username, password)
        response = self.login_socket.recv(1024).decode()
        if response == 'login_success':
            self.login_socket.close()
            self.video_socket.connect((self.host, self.port))
            self.audio_socket.connect((self.host, self.port + 1))
            self.window.destroy()
            self.root.deiconify()
            self.username_label.configure(text=self.username)
            self.start_threads()
        elif response == 'login_failU':
            self.message_box.configure(text="Incorrect username")
        elif response == 'login_failP':
            self.message_box.configure(text="Incorrect password")

    def close_connection(self):
        self.in_stream.stop_stream()
        self.in_stream.close()
        self.out_stream.stop_stream()
        self.out_stream.close()
        self.audio.terminate()
        self.up = False
        print("Closing Connection")
        self.vid.release()
        self.video_socket.close()
        self.audio_socket.close()
        self.root.destroy()

    def mute(self, channel):
        if channel == 0:  # vid
            self.vid_muted = not self.vid_muted

            if self.vid_muted:
                self.vid_mute_button.configure(text="Start Video")
            else:
                self.vid_mute_button.configure(text="Stop Video")
        else:  # aud
            self.aud_muted = not self.aud_muted

            if self.aud_muted:
                self.aud_mute_button.configure(text="Unmute Audio")
            else:
                self.aud_mute_button.configure(text="Mute Audio")

    def send_vid(self):
        counter = 0
        start_time = time.time()
        fps = 0
        while self.up:
            if not self.vid_muted:
                ret, frame = self.vid.read()
                if not ret:
                    continue
                frame = cv2.flip(frame, 1)

                if self.is_sharing_screen:
                    screen = self.capture_screen()

                    screen_height, screen_width, _ = screen.shape
                    frame_height, frame_width, _ = frame.shape
                    screen = cv2.resize(screen,
                                        dsize=(int((screen_width / screen_height) * frame_width * .8), frame_height),
                                        interpolation=cv2.INTER_CUBIC)
                    screen_height, screen_width, _ = screen.shape

                    # Create a new image with dimensions to fit both images
                    new_height = max(screen_height, frame_height)
                    new_width = screen_width + frame_width
                    new_im = Image.new('RGB', (new_width, new_height))

                    # Convert cv2 images to PIL images
                    frame_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    screen_pil = Image.fromarray(cv2.cvtColor(screen, cv2.COLOR_BGR2RGB))

                    # Paste the images into the new image
                    new_im.paste(frame_pil, (0, 0))
                    new_im.paste(screen_pil, (frame_width, 0))

                    frame = np.array(new_im)
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

            else:
                if self.is_sharing_screen:
                    frame = self.capture_screen()
                else:
                    frame = np.zeros((self.resolution[1], self.resolution[0], 3), dtype=np.uint8)

            frame = cv2.putText(frame, self.username, (0, 12), cv2.FONT_ITALIC, .5, (0, 0, 0), lineType=cv2.LINE_AA,
                                thickness=4)
            frame = cv2.putText(frame, self.username, (0, 12), cv2.FONT_ITALIC, .5, (255, 255, 255),
                                lineType=cv2.LINE_AA, thickness=2)

            _, encoded_frame = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            compressed_frame = lz4.frame.compress(encoded_frame.tobytes(), compression_level=lz4.frame.COMPRESSIONLEVEL_MAX)
            try:
                final_protocol.send_frame(self.video_socket, compressed_frame, 0, self.my_index)
            except (BrokenPipeError, ConnectionResetError, socket.error) as e:
                print(f"Error sending video frame: {e}")
                self.close_connection()
                break

            counter += 1
            if (time.time() - start_time) >= 1:
                fps = counter
                counter = 0
                start_time = time.time()
            self.draw_GUI_frame(frame, self.my_index, f"{fps} fps")

    def receive_vid(self):
        while self.up:
            try:
                readable, _, _ = select.select([self.video_socket], [], [], 1.0)
                if readable:
                    frame, self.vid_data, cpos, self.my_index = final_protocol.receive_frame(self.video_socket, self.vid_data)
                    decompressed_frame = lz4.frame.decompress(frame)
                    nparr = np.frombuffer(decompressed_frame, np.uint8)
                    img_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                    self.draw_GUI_frame(img_np, cpos, "")
            except (ConnectionResetError, socket.error) as e:
                print(f"Error receiving video frame: {e}")
                self.close_connection()
                break

    def send_aud(self):
        while self.up:
            if self.aud_muted:
                time.sleep(0.1)
            else:
                try:
                    data = zlib.compress(self.in_stream.read(self.A_CHUNK))
                    final_protocol.send_frame(self.audio_socket, data, 0, self.my_index)
                except (BrokenPipeError, ConnectionResetError, socket.error) as e:
                    print(f"Error sending audio data: {e}")
                    self.close_connection()
                    break

    def receive_aud(self):
        while self.up:
            try:
                readable, _, _ = select.select([self.audio_socket], [], [], 1.0)
                if readable:
                    frame, self.aud_data, *_ = final_protocol.receive_frame(self.audio_socket, self.aud_data)
                    self.out_stream.write(zlib.decompress(frame))
            except (ConnectionResetError, socket.error) as e:
                print(f"Error receiving audio data: {e}")
                self.close_connection()
                break

    def capture_screen(self):
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Capture the primary monitor
            img = sct.grab(monitor)
            frame = np.array(img)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            return frame

    def start_screen_sharing(self):
        if not self.is_sharing_screen:
            self.is_sharing_screen = True
            self.share_window = tk.CTkToplevel(self.root)
            self.share_window.title("Enter Your Name")
            tk.CTkLabel(self.share_window, text="Sharing Screen!").pack()

            tk.CTkButton(self.share_window, text="Stop Sharing", command=self.start_screen_sharing).pack()

        else:
            self.is_sharing_screen = False
            self.screen_share_button.configure(text="Share Screen")
            self.share_window.destroy()

    def start_threads(self):
        Thread(target=self.send_vid, daemon=True).start()
        Thread(target=self.receive_vid, daemon=True).start()
        Thread(target=self.send_aud, daemon=True).start()
        Thread(target=self.receive_aud, daemon=True).start()

    def draw_GUI_frame(self, frame, index, fps=None):
        if self.is_sharing_screen:
            self.root.withdraw()
        else:
            self.root.deiconify()
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = Image.fromarray(frame)
            frame = tk.CTkImage(light_image=frame, size=frame.size)
            while index >= len(self.labels):
                label = tk.CTkLabel(self.root, text="")
                self.labels.append(label)
            self.labels[index].grid(row=index, column=0)
            self.labels[index].configure(image=frame)
            self.labels[index].image = frame
            self.index_label.configure(text="client " + str(self.my_index) + " " + str(index))
            if fps:
                self.fps_label.configure(text=fps)
            self.root.update()


if __name__ == "__main__":
    client = Client()