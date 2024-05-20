import pickle
import socket
from threading import Thread
import protocol4
import sqlite3
import select
import hashlib
import os
import bcrypt

vid_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
aud_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

host = '0.0.0.0'
port = 9997
vid_socket_address = (host, port)
aud_socket_address = (host, port + 1)

vid_server_socket.bind(vid_socket_address)
aud_server_socket.bind(aud_socket_address)

vid_server_socket.listen()
aud_server_socket.listen()

print(socket.gethostname())
print("Listening video at", vid_socket_address, "audio at", aud_socket_address)

vid_clients = []
aud_clients = []


class connection:
    def __init__(self, soc: socket.socket, index: int):
        self.soc = soc
        self.frame = b''
        self.data = b''
        self.index = index
        self.authenticated = False


def accept_connections(soc: socket.socket, lis):
    while True:
        client_socket, addr = soc.accept()
        cli_index = int(str(addr[0]).replace(".", ""))
        con = connection(client_socket, cli_index)
        lis.append(con)

        if lis == vid_clients:
            print(f"GOT VIDEO CONNECTION FROM: ({addr[0]}:{addr[1]}) {cli_index}\n")

        if lis == aud_clients:
            print(f"GOT AUDIO CONNECTION FROM: ({addr[0]}:{addr[1]}) {cli_index}\n")

        Thread(target=handle_client, args=(con, lis,)).start()


def hash_password(password):
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed


def check_password(stored_password, provided_password):
    return bcrypt.checkpw(provided_password.encode('utf-8'), stored_password)


def handle_client(con: connection, client_list):
    while True:
        try:
            readable, _, _ = select.select([con.soc], [], [], 1.0)
            if readable:
                if not con.authenticated:
                    data = con.soc.recv(1024)
                    credentials = pickle.loads(data)
                    if credentials['type'] == 'signup':
                        if handle_signup(credentials):
                            con.soc.sendall(b'signup_success')
                        else:
                            con.soc.sendall(b'signup_fail')
                    elif credentials['type'] == 'login':
                        if handle_login(credentials):
                            con.authenticated = True
                            con.soc.sendall(b'login_success')
                        else:
                            con.soc.sendall(b'login_fail')
                else:
                    con.frame, con.data, *_ = protocol4.receive_frame(con.soc, con.data)
                    if con in aud_clients:
                        broadcast(con, aud_clients)
                    else:
                        broadcast(con, vid_clients)
        except (ConnectionResetError, socket.error) as e:
            print(f"Connection error: {e}")
            remove_client(con, client_list)
            break


def handle_signup(credentials):
    username = credentials['username']
    password = hash_password(credentials['password'])

    # Connect to the database
    sq = sqlite3.connect("video_chat.db")
    cur = sq.cursor()

    try:
        # Check if the username already exists in the users table
        cur.execute("SELECT 1 FROM users WHERE username = ?", (username,))
        if cur.fetchone() is not None:
            return False

        # Insert the new user into the users table
        cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        sq.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False
    finally:
        # Ensure the cursor and connection are closed properly
        cur.close()
        sq.close()

    return True


def handle_login(credentials):
    username = credentials['username']
    password = credentials['password']
    sq = sqlite3.connect("video_chat.db")
    cur = sq.cursor()
    cur.execute("SELECT password FROM users WHERE username=?", (username,))
    stored_password = cur.fetchone()
    cur.close()
    sq.close()
    if stored_password:
        return check_password(stored_password[0], password)
    return False


def broadcast(con, client_list):
    for client in client_list:
        if client != con:
            ipos = get_index_pos(client)
            cpos = get_index_pos(con)
            try:
                protocol4.send_frame(client.soc, con.frame, 0, cpos, ipos)
            except (BrokenPipeError, ConnectionResetError, socket.error) as e:
                print(f"Error broadcasting frame: {e}")
                remove_client(client, client_list)


def get_index_pos(i):
    sorted_numbers = sorted([conn.index for conn in vid_clients])
    pos = sorted_numbers.index(i.index)
    return pos


def remove_client(con: connection, lis):
    for i in lis:
        if i.index == con.index:
            print(f"Removing Connection {i.index}")
            lis.remove(i)

            for o in range(0, len(lis)):
                if lis[o] is None:
                    if o < len(lis) - 1:
                        lis[o].index -= 1


def create_users_table():
    sq = sqlite3.connect("video_chat.db")
    cur = sq.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL)''')
    sq.commit()
    cur.close()
    sq.close()


create_users_table()
Thread(target=accept_connections, args=(vid_server_socket, vid_clients,)).start()
Thread(target=accept_connections, args=(aud_server_socket, aud_clients,)).start()
