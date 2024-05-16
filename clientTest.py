import socket
from tkinter import *
import customtkinter as tk
from threading import Thread
import cv2
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
        self.root, self.username, self.window, self.entry, self.index_label, self.fps_label, self.username_label = self.setup_gui()
        self.video_socket, self.audio_socket, self.host, self.port = self.setup_network()
        self.labels, self.vid_data, self.aud_data, self.my_index, self.up = self.setup_data()
        self.vid = cv2.VideoCapture(0)
        self.vid.set(3, 320)  # Reduce frame width
        self.vid.set(4, 240)  # Reduce frame height
        self.mainloop()

    def setup_audio(self):
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 44100
        A_CHUNK = 1024
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

        return root, username, window, entry, index_label, fps_label, username_label

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
                    frame, self.vid_data, cpos, ipos = protocol4.receive_frame(self.video_socket, self.vid_data)
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
                    frame, self.aud_data, _, _ = protocol4.receive_frame(self.audio_socket, self.aud_data)
                    self.out_stream.write(frame)
            except (ConnectionResetError, socket.error) as e:
                print(f"Error receiving audio data: {e}")
                self.close_connection()
                break

    def start_threads(self):
        Thread(target=self.send_vid, daemon=True).start()
        Thread(target=self.receive_vid, daemon=True).start()
        Thread(target=self.send_aud, daemon=True).start()
        Thread(target=self.receive_aud, daemon=True).start()

    def mainloop(self):
        self.root.mainloop()

    def draw_GUI_frame(self, frame, cpos, fps_text):
        cv2.putText(frame, fps_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f"{self.username}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(img)
        imgtk = ImageTk.PhotoImage(image=img_pil)
        if cpos < len(self.labels):
            self.labels[cpos].configure(image=imgtk)
            self.labels[cpos].image = imgtk
        else:
            label = tk.CTkLabel(self.root)
            label.grid(row=0, column=cpos)
            self.labels.append(label)
            self.labels[cpos].configure(image=imgtk)
            self.labels[cpos].image = imgtk

if __name__ == "__main__":
    client = Client()
