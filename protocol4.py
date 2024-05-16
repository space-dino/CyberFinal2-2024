import pickle
import socket
import struct

payload_size = struct.calcsize("Q")  # unsigned Long Long = 8 bytes
index_size = struct.calcsize("I")  # unsigned Int = 4 bytes


def send_frame(soc: socket, frame, flag: int, index: int, my_index: int):
    data = pickle.dumps(frame)
    message = struct.pack("I", index) + struct.pack("I", my_index) + struct.pack("I", flag) + struct.pack("Q", len(data)) + data

    try:
        soc.sendall(message)
    except TypeError:
        print("connection closed")

    # Packet Structure:
    """ 

    index - 4 bytes unsigned int
    my_index - 4 bytes unsigned int
    flag - 4 bytes unsigned int (0: video, 1: audio, 2: chat) - Flag used for screenshare
    data_length - 8 bytes unsigned long long
    data - data_length bytes data

    """


def receive_frame(soc: socket, data: bytes):
    packed_index, data = receive_parameter(soc, data, index_size)  # index
    index = struct.unpack("I", packed_index)[0]

    packed_my_index, data = receive_parameter(soc, data, index_size)  # my_index
    my_index = struct.unpack("I", packed_my_index)[0]

    packed_flag, data = receive_parameter(soc, data, index_size)  # flag
    flag = struct.unpack("I", packed_flag)[0]

    packed_msg_size, data = receive_parameter(soc, data, payload_size)  # data_length
    msg_size = struct.unpack("Q", packed_msg_size)[0]

    frame_data, data = receive_parameter(soc, data, msg_size)  # data
    frame = pickle.loads(frame_data)

    return frame, data, flag, index, my_index


def receive_parameter(soc: socket, data, size):
    while len(data) < size:
        data += soc.recv(4 * 4096)

    parameter = data[:size]
    data = data[size:]

    return parameter, data
