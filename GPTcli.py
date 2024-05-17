import socket
from tkinter import *
import customtkinter as tk
from threading import Thread
import cv2
import mss
from PIL import Image, ImageTk
import pyaudio
import time
import numpy as np
import lz4.frame
import protocol4
import select

class Client:
    def __init__(self):
        self.FORMAT, self.CHANNELS, self.RATE, self.A_CHUNK, self.audio, self.in_stream, self.out_stream = self.setup_audio()
        self.root, self.username, self.window, self.entry, self.index_label, self.fps_label, self.username_label, self.screen_share_button = self.setup_gui()
        self.video_socket, self.audio_socket, self.host, self.port = self.setup_network()
        self.labels, self.vid_data, self.aud_data, self.my_index, self.up = self.setup_data()
        self.vid = cv2.VideoCapture(0)
        self.vid.set(3, 320)  # Reduce frame width
        self.vid.set(4, 240)  # Reduce frame height
        self.is_sharing_screen = False
        self.mainloop()

    def setup_audio(self):
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = int(44100/2)
        A_CHUNK = int(1024/2)
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
        window.title("Enter Your Name")
        tk.CTkLabel(window, text="Enter your name:").pack()
        entry = tk.CTkEntry(window)
        entry.pack()
        tk.CTkButton(window, text="Join Meeting", command=self.submit).pack()
        tk.CTkButton(root, text="Close", command=self.close_connection).grid(row=0, column=1)
        index_label = tk.CTkLabel(root, text="index")
        index_label.grid(row=1, column=1)
        fps_label = tk.CTkLabel(root, text="fps")
        fps_label.grid(row=2, column=1)
        username_label = tk.CTkLabel(root, text="username")
        username_label.grid(row=3, column=1)
        screen_share_button = tk.CTkButton(root, text="Share Screen", command=self.start_screen_sharing)
        screen_share_button.grid(row=4, column=1)

        return root, username, window, entry, index_label, fps_label, username_label, screen_share_button

    def setup_data(self):
        labels = []
        vid_data = b''
        aud_data = b''
        my_index = 0
        up = True

        return labels, vid_data, aud_data, my_index, up

    def setup_network(self):
        video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        audio_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        host = '127.0.0.1'
        port = 9997

        return video_socket, audio_socket, host, port

    def submit(self):
        self.username = self.entry.get()

        self.window.destroy()
        self.root.deiconify()
        self.username_label.configure(text=self.username)
        self.video_socket.connect((self.host, self.port))
        self.audio_socket.connect((self.host, self.port + 1))
        print("Connected to server")
        self.start_threads()

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

    def send_vid(self):
        counter = 0
        start_time = time.time()
        fps = 0
        while self.up:
            ret, frame = self.vid.read()
            if not ret:
                continue
            frame = cv2.flip(frame, 1)

            if self.is_sharing_screen:
                screen = self.capture_screen()
                screen_height, screen_width, _ = screen.shape
                frame_height, frame_width, _ = frame.shape

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

            _, encoded_frame = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            compressed_frame = lz4.frame.compress(encoded_frame.tobytes())
            try:
                protocol4.send_frame(self.video_socket, compressed_frame, 0, 0, self.my_index)
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
                    frame, self.vid_data, _, cpos, self.my_index = protocol4.receive_frame(self.video_socket, self.vid_data)
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
            try:
                data = self.in_stream.read(self.A_CHUNK)
                protocol4.send_frame(self.audio_socket, data, 0, 0, self.my_index)
            except (BrokenPipeError, ConnectionResetError, socket.error) as e:
                print(f"Error sending audio data: {e}")
                self.close_connection()
                break

    def receive_aud(self):
        while self.up:
            try:
                readable, _, _ = select.select([self.audio_socket], [], [], 1.0)
                if readable:
                    frame, self.aud_data, *_ = protocol4.receive_frame(self.audio_socket, self.aud_data)
                    self.out_stream.write(frame)
            except (ConnectionResetError, socket.error) as e:
                print(f"Error receiving audio data: {e}")
                self.close_connection()
                break

    """def send_screen(self):
        counter = 0
        start_time = time.time()
        fps = 0
        while self.up and self.is_sharing_screen:
            frame = self.capture_screen()
            _, encoded_frame = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            compressed_frame = lz4.frame.compress(encoded_frame.tobytes())
            protocol4.send_frame(self.video_socket, compressed_frame, 1, 0, self.my_index)

            counter += 1
            if (time.time() - start_time) >= 1:
                fps = counter
                counter = 0
                start_time = time.time()
            self.draw_GUI_frame(frame, self.my_index, f"{fps} fps")"""

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
            # Thread(target=self.send_screen, daemon=True).start()
            self.screen_share_button.configure(text="Stop Sharing")
        else:
            self.is_sharing_screen = False
            self.screen_share_button.configure(text="Share Screen")

    def start_threads(self):
        Thread(target=self.send_vid, daemon=True).start()
        Thread(target=self.receive_vid, daemon=True).start()
        Thread(target=self.send_aud, daemon=True).start()
        Thread(target=self.receive_aud, daemon=True).start()

    def mainloop(self):
        self.root.mainloop()

    def draw_GUI_frame(self, frame, index, fps=None):
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = Image.fromarray(frame)
        frame = tk.CTkImage(light_image=frame, size=(400, 300))
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
