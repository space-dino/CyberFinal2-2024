import socket
from threading import Thread
import protocolGPT2 as protocol4  # Corrected import
import sqlite3
import bcrypt

# Create the sockets
vid_server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
aud_server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
login_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Define addresses
host = '0.0.0.0'
port = 9997
vid_socket_address = (host, port)
aud_socket_address = (host, port + 1)
login_socket_address = (host, port + 2)

# Bind the sockets
vid_server_socket.bind(vid_socket_address)
aud_server_socket.bind(aud_socket_address)
login_server_socket.bind(login_socket_address)

# Listen for TCP connections
login_server_socket.listen()

print(socket.gethostname())
print("Listening video at", vid_socket_address, "audio at", aud_socket_address, "login at", login_socket_address)

# Client lists
vid_clients = {}
aud_clients = {}
login_clients = []
valid_addresses = []

# Connection class
class connection:
    def __init__(self, soc: socket.socket, index: int, addr=None):
        self.soc = soc
        self.addr = addr  # For UDP clients
        self.frame = b''
        self.data = b''
        self.index = index

# Accept TCP connections
def accept_connections_tcp(soc: socket.socket, lis):
    while True:
        client_socket, addr = soc.accept()
        cli_index = int(str(addr[0]).replace(".", ""))
        con = connection(client_socket, cli_index)
        lis.append(con)

        if lis == login_clients:
            print(f"GOT LOGIN CONNECTION FROM: ({addr[0]}:{addr[1]}) {cli_index}\n")

        Thread(target=handle_client, args=(con, lis,)).start()

# Accept UDP connections
def accept_connections_udp(soc: socket.socket, lis):
    while True:
        data, addr = soc.recvfrom(4096)
        cli_index = int(str(addr[0]).replace(".", ""))

        if addr not in lis:
            con = connection(soc, cli_index, addr)
            lis[addr] = con
            if soc == vid_server_socket:
                print(f"GOT VIDEO CONNECTION FROM: ({addr[0]}:{addr[1]}) {cli_index}\n")
            elif soc == aud_server_socket:
                print(f"GOT AUDIO CONNECTION FROM: ({addr[0]}:{addr[1]}) {cli_index}\n")
            Thread(target=handle_client, args=(con, lis,)).start()
        else:
            lis[addr].data = data

# Handle clients
def handle_client(con: connection, client_list):
    while True:
        try:
            if con in login_clients:
                signup, username, password = protocol4.recv_credentials(con.soc)
                print(signup, username, password)
                if signup:
                    if handle_signup(username, password):
                        con.soc.send("signup_success".encode())
                    else:
                        con.soc.send("signup_fail".encode())
                else:
                    res = handle_login(username, password)
                    if res == "True":
                        valid_addresses.append(con.index)
                        con.soc.send("login_success".encode())
                        con.soc.close()
                    elif res == "Wrong Username":
                        con.soc.send("login_failU".encode())
                    elif res == "Wrong Password":
                        con.soc.send("login_failP".encode())
            else:
                if con.index in valid_addresses:
                    if con.addr:  # This is a UDP connection
                        con.frame, con.data, *_ = protocol4.receive_frame(con.soc, con.data)
                        print(con.frame)
                        if con in aud_clients.values():
                            broadcast(con, aud_clients)
                        else:
                            broadcast(con, vid_clients)
        except (ConnectionResetError, socket.error) as e:
            print(f"Connection error: {e}")
            remove_client(con, client_list)
            break
        except ValueError as e:
            print(f"Login removed")
            remove_client(con, client_list)
            break

# Handle signups and logins
def handle_signup(username, password):
    # Connect to the database
    sq = sqlite3.connect("video_chat.db")
    cur = sq.cursor()

    try:
        # Check if the username already exists in the users table
        cur.execute("SELECT 1 FROM users WHERE username = ?", (username,))
        if cur.fetchone() is not None:
            return False

        # Insert the new user into the users table
        cur.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hash_password(password)))
        sq.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False
    finally:
        # Ensure the cursor and connection are closed properly
        cur.close()
        sq.close()

    return True

def handle_login(username, password):
    sq = sqlite3.connect("video_chat.db")
    cur = sq.cursor()

    # Check if the username exists in the users table
    cur.execute("SELECT 1 FROM users WHERE username = ?", (username,))
    if cur.fetchone() is None:
        return "Wrong Username"

    cur.execute("SELECT password FROM users WHERE username=?", (username,))
    stored_password = cur.fetchone()
    cur.close()
    sq.close()
    if stored_password:
        if check_password(stored_password[0], password):
            return "True"
    return "Wrong Password"

def hash_password(password):
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def check_password(stored_password, plain_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), stored_password.encode('utf-8'))

def broadcast(con, client_list):
    for client in client_list.values():
        if client != con:
            ipos = get_index_pos(client)
            cpos = get_index_pos(con)
            try:
                protocol4.send_frame(client.soc, con.frame, 0, cpos, ipos)
            except (BrokenPipeError, ConnectionResetError, socket.error) as e:
                print(f"Error broadcasting frame: {e}")
                remove_client(client, client_list)

def get_index_pos(con):
    sorted_numbers = sorted([conn.index for conn in vid_clients.values()])
    if con.index in sorted_numbers:
        pos = sorted_numbers.index(con.index)
    else:
        pos = -1  # Handle the case when the index is not found
    return pos

def remove_client(con: connection, lis):
    if isinstance(lis, dict) and con.addr in lis:
        print(f"Removing Connection {con.index}")
        del lis[con.addr]
    else:
        for i in lis:
            if i.index == con.index:
                print(f"Removing Connection {i.index}")
                lis.remove(i)
                break

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

Thread(target=accept_connections_udp, args=(vid_server_socket, vid_clients,)).start()
Thread(target=accept_connections_udp, args=(aud_server_socket, aud_clients,)).start()
Thread(target=accept_connections_tcp, args=(login_server_socket, login_clients,)).start()
