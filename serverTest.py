import socket
from threading import Thread
import protocol4
import sqlite3
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

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

logging.info(f"Server started on {socket.gethostname()} - Video: {vid_socket_address}, Audio: {aud_socket_address}")

vid_clients = []
aud_clients = []

class Connection:
    def __init__(self, soc: socket.socket, index: int):
        self.soc = soc
        self.frame = b''
        self.data = b''
        self.index = index

def accept_connections(soc: socket.socket, lis):
    while True:
        client_socket, addr = soc.accept()
        client_socket.setblocking(False)
        cli_index = int(str(addr[0]).replace(".", ""))
        con = Connection(client_socket, cli_index)
        lis.append(con)

        if lis == vid_clients:
            logging.info(f"GOT VIDEO CONNECTION FROM: ({addr[0]}:{addr[1]}) {cli_index}\n")
            update_database(cli_index, addr[0])

        if lis == aud_clients:
            logging.info(f"GOT AUDIO CONNECTION FROM: ({addr[0]}:{addr[1]}) {cli_index}\n")

        Thread(target=handle_client, args=(con, lis)).start()

def handle_client(con: Connection, client_list):
    while True:
        try:
            readable, _, _ = select.select([con.soc], [], [], 1.0)
            if readable:
                con.frame, con.data, *_ = protocol4.receive_frame(con.soc, con.data)
                if con in aud_clients:
                    broadcast(con, aud_clients)
                else:
                    broadcast(con, vid_clients)
        except (ConnectionResetError, socket.error) as e:
            logging.error(f"Connection error: {e}")
            remove_client(con, client_list)
            break

def broadcast(con, client_list):
    for client in client_list:
        if client != con:
            ipos = get_index_pos(client)
            cpos = get_index_pos(con)
            try:
                protocol4.send_frame(client.soc, con.frame, 0, cpos, ipos)
            except (BrokenPipeError, ConnectionResetError, socket.error) as e:
                logging.error(f"Error broadcasting frame: {e}")
                remove_client(client, client_list)

def get_index_pos(con):
    sorted_numbers = sorted([conn.index for conn in vid_clients])
    pos = sorted_numbers.index(con.index)
    return pos

def remove_client(con: Connection, lis):
    if con in lis:
        logging.info(f"Removing Connection {con.index}")
        lis.remove(con)
        sq = sqlite3.connect("video_chat.db")
        cur = sq.cursor()
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        sql = f'UPDATE participant SET logout_time = "{current_time}" WHERE name = {con.index}'
        cur.execute(sql)
        sq.commit()
        res = cur.execute("SELECT * FROM participant")
        logging.info("*****SQL******\n", res.fetchall())

def update_database(name, ip):
    sq = sqlite3.connect("video_chat.db")
    cur = sq.cursor()
    res = cur.execute("SELECT name FROM sqlite_master WHERE name='participant'")
    if res.fetchone() is None:
        cur.execute("CREATE TABLE participant(name, ip, login_time, logout_time)")

    res = cur.execute("SELECT name FROM participant")
    if name not in res.fetchall():
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        insert = """INSERT INTO participant(name, ip, login_time, logout_time) VALUES (?, ?, ?, ?);"""
        data_tuple = (name, ip, current_time, "")
        cur.execute(insert, data_tuple)
        sq.commit()
        res = cur.execute("SELECT * FROM participant")
        logging.info("*****SQL******\n", res.fetchall())

Thread(target=accept_connections, args=(vid_server_socket, vid_clients,)).start()
Thread(target=accept_connections, args=(aud_server_socket, aud_clients,)).start()
