import pickle
import socket
import struct
from Crypto.Cipher import DES

# Define the payload size and index size
payload_size = struct.calcsize("Q")  # unsigned Long Long = 8 bytes
index_size = struct.calcsize("I")  # unsigned Int = 4 bytes

# DES encryption/decryption key (must be 8 bytes long)
DES_KEY = b'8bytekey'

def des_encrypt(data):
    cipher = DES.new(DES_KEY, DES.MODE_ECB)
    padded_data = data + b' ' * (8 - len(data) % 8)
    encrypted_data = cipher.encrypt(padded_data)
    return encrypted_data

def des_decrypt(data):
    cipher = DES.new(DES_KEY, DES.MODE_ECB)
    decrypted_data = cipher.decrypt(data).rstrip(b' ')
    return decrypted_data

def send_frame(soc: socket.socket, frame, source: int, dest: int):
    data = pickle.dumps(frame)
    encrypted_data = des_encrypt(data)
    message = struct.pack("I", dest) + struct.pack("I", source) + struct.pack("Q", len(encrypted_data)) + encrypted_data

    try:
        soc.sendall(message)
    except TypeError:
        print("connection closed")

    # Packet Structure:
    """ 
    dest - 4 bytes unsigned int
    source - 4 bytes unsigned int
    data_length - 8 bytes unsigned long long
    data - data_length bytes data
    """

def receive_frame(soc: socket.socket, data: bytes):
    packed_dest, data = receive_parameter(soc, data, index_size)  # dest
    dest = struct.unpack("I", packed_dest)[0]

    packed_source, data = receive_parameter(soc, data, index_size)  # source
    source = struct.unpack("I", packed_source)[0]

    packed_msg_size, data = receive_parameter(soc, data, payload_size)  # data_length
    msg_size = struct.unpack("Q", packed_msg_size)[0]

    encrypted_frame_data, data = receive_parameter(soc, data, msg_size)  # data
    frame_data = des_decrypt(encrypted_frame_data)
    frame = pickle.loads(frame_data)

    return frame, data, dest, source

def send_credentials(soc: socket.socket, signup: bool, username: str, password: str):
    sign_char = 'l'
    if signup:
        sign_char = 's'
    message = sign_char + str(len(username)).zfill(4) + username + str(len(password)).zfill(4) + password
    encrypted_message = des_encrypt(message.encode())

    try:
        soc.sendall(encrypted_message)
    except TypeError:
        print("connection closed")

def recv_credentials(soc: socket.socket):
    encrypted_signup = soc.recv(1)
    signup = des_decrypt(encrypted_signup).decode()
    ul = int(des_decrypt(soc.recv(4)).decode())
    username = des_decrypt(soc.recv(ul)).decode()
    pl = int(des_decrypt(soc.recv(4)).decode())
    password = des_decrypt(soc.recv(pl)).decode()

    if signup == 'l':
        signup = False
    else:
        signup = True

    return signup, username, password

def receive_parameter(soc: socket.socket, data, size):
    while len(data) < size:
        data += soc.recv(4 * 4096)

    parameter = data[:size]
    data = data[size:]

    return parameter, data
