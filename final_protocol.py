import pickle
import socket
import struct

payload_size = struct.calcsize("Q")  # unsigned Long Long = 8 bytes
index_size = struct.calcsize("I")  # unsigned Int = 4 bytes


def send_frame(soc: socket, frame, index: int, my_index: int):
    data = pickle.dumps(frame)
    message = struct.pack("I", index) + struct.pack("I", my_index) + struct.pack("Q", len(data)) + data

    try:
        soc.sendall(message)
    except TypeError:
        print("connection closed")

    # Packet Structure:
    """ 

    index - 4 bytes unsigned int
    my_index - 4 bytes unsigned int
    data_length - 8 bytes unsigned long long
    data - data_length bytes data

    """


def receive_frame(soc: socket, data: bytes):
    packed_index, data = receive_parameter(soc, data, index_size)  # index
    index = struct.unpack("I", packed_index)[0]

    packed_my_index, data = receive_parameter(soc, data, index_size)  # my_index
    my_index = struct.unpack("I", packed_my_index)[0]

    packed_msg_size, data = receive_parameter(soc, data, payload_size)  # data_length
    msg_size = struct.unpack("Q", packed_msg_size)[0]

    frame_data, data = receive_parameter(soc, data, msg_size)  # data
    frame = pickle.loads(frame_data)

    return frame, data, flag, index, my_index


def send_credentials(soc: socket, signup: bool, username: str, password: str):
    sign_char = 'l'
    if signup:
        sign_char = 's'
    message = sign_char + str(len(username)).zfill(4) + username + str(len(password)).zfill(4) + password
    print(message)

    try:
        soc.sendall(message.encode())
    except TypeError:
        print("connection closed")


def recv_credentials(soc: socket):
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


def receive_parameter(soc: socket, data, size):
    while len(data) < size:
        data += soc.recv(4 * 4096)

    parameter = data[:size]
    data = data[size:]

    return parameter, data