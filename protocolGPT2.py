import pickle
import struct
import socket

payload_size = struct.calcsize("Q")  # unsigned Long Long = 8 bytes
index_size = struct.calcsize("I")  # unsigned Int = 4 bytes


def send_frame(soc: socket.socket, frame, dest: int, source: int):
    data = pickle.dumps(frame)
    data_len = len(data)

    # Ensure that the values are within the allowable range
    if not (0 <= dest <= 0xFFFFFFFF):
        raise ValueError(f"Destination index out of range: {dest}")
    if not (0 <= source <= 0xFFFFFFFF):
        raise ValueError(f"Source index out of range: {source}")
    if not (0 <= data_len <= 0xFFFFFFFFFFFFFFFF):
        raise ValueError(f"Data length out of range: {data_len}")

    message = struct.pack("I", dest) + struct.pack("I", source) + struct.pack("Q", data_len) + data

    try:
        soc.sendto(message, (soc.getpeername() if soc.getpeername() else ('<broadcast>', soc.getsockname()[1])))
    except TypeError:
        print("connection closed")

def receive_frame(soc: socket.socket, data: bytes):
    packed_dest, data = receive_parameter(soc, data, index_size)  # index
    dest = struct.unpack("I", packed_dest)[0]

    packed_source, data = receive_parameter(soc, data, index_size)  # my_index
    source = struct.unpack("I", packed_source)[0]

    packed_msg_size, data = receive_parameter(soc, data, payload_size)  # data_length
    msg_size = struct.unpack("Q", packed_msg_size)[0]

    frame_data, data = receive_parameter(soc, data, msg_size)  # data
    frame = pickle.loads(frame_data)

    return frame, data, dest, source

def receive_parameter(soc: socket.socket, data, size):
    while len(data) < size:
        data += soc.recv(4096)

    parameter = data[:size]
    data = data[size:]

    return parameter, data

def send_credentials(soc: socket.socket, signup: bool, username: str, password: str):
    sign_char = 'l'
    if signup:
        sign_char = 's'
    message = sign_char + str(len(username)).zfill(4) + username + str(len(password)).zfill(4) + password
    print(message)

    try:
        soc.send(message.encode())
    except TypeError:
        print("connection closed")


def recv_credentials(soc: socket.socket):
    signup = soc.recv(1)
    print(signup.decode())
    ul = int(soc.recv(4))
    username = soc.recv(ul)
    pl = int(soc.recv(4))
    password = soc.recv(pl)

    print("ul:", ul, "username:", username)

    if signup.decode() == 'l':
        signup = False
    else:
        signup = True

    return signup, username.decode(), password.decode()