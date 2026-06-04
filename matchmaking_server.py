import random
import select
import socket
import string
import threading

HOST = "0.0.0.0"
MATCHMAKING_PORT = 4242

GAME_SERVER_HOST = "127.0.0.1"
# GAME_SERVER_HOST = "10.18.33.24"
GAME_SERVER_PORT = 4243


def read_message(client_file):
    line = client_file.readline()
    if not line:
        return None
    return line.decode("utf-8").strip()


def send_message(client_socket, message):
    client_socket.sendall((message + "\r\n").encode("utf-8"))


def create_client_id(player_num):
    return f"CID{player_num}"


def create_match_id(match_num):
    return f"M{match_num}"


def create_room_code():
    return "".join(random.choices(string.ascii_uppercase, k=6))


def pair_players(player1, player2, shared):
    """Assign a match ID and return the MATCH message string. Caller must hold the lock."""
    match_id = create_match_id(shared["match_count"])
    shared["match_count"] += 1
    return match_id, f"MATCH {match_id} {GAME_SERVER_HOST} {GAME_SERVER_PORT}"


def is_socket_alive(sock):
    """Non-blocking check — safe to call inside a lock."""
    try:
        ready = select.select([sock], [], [], 0)[0]
        if ready:
            return len(sock.recv(1, socket.MSG_PEEK)) > 0
        return True
    except Exception:
        return False


def handle_qjoin(player, shared, lock):
    send_message(player["socket"], "WAIT")
    print(f"{player['client_id']} joined the random queue")

    match_message = None
    with lock:
        shared["waiting_players"].append(player)

        if len(shared["waiting_players"]) >= 2:
            player1 = shared["waiting_players"].pop(0)
            player2 = shared["waiting_players"].pop(0)

            p1_alive = is_socket_alive(player1["socket"])
            p2_alive = is_socket_alive(player2["socket"])

            if not p1_alive:
                print(f"{player1['client_id']} found disconnected in queue, removing")
                player1["socket"].close()
            if not p2_alive:
                print(f"{player2['client_id']} found disconnected in queue, removing")
                player2["socket"].close()

            if p1_alive and p2_alive:
                match_id, msg = pair_players(player1, player2, shared)
                match_message = (player1, player2, msg, match_id)
            elif p1_alive:
                shared["waiting_players"].insert(0, player1)
            elif p2_alive:
                shared["waiting_players"].insert(0, player2)

    if match_message:
        player1, player2, msg, match_id = match_message
        send_message(player1["socket"], msg)
        send_message(player2["socket"], msg)
        print(f"Matched {player1['client_id']} and {player2['client_id']} into {match_id}")


def handle_rcreate(player, shared, lock):
    with lock:
        # keep generating until we find a code not already in use
        code = create_room_code()
        while code in shared["rooms"]:
            code = create_room_code()
        shared["rooms"][code] = player

    send_message(player["socket"], f"ROOM {code}")
    print(f"{player['client_id']} created room {code}")


def handle_rjoin(player, code, shared, lock):
    match_message = None
    with lock:
        if code not in shared["rooms"]:
            send_message(player["socket"], "INVL unknown-room-code")
            return

        host_player = shared["rooms"].pop(code)

        if not is_socket_alive(host_player["socket"]):
            print(f"Room {code} host {host_player['client_id']} found disconnected, removing room")
            host_player["socket"].close()
            send_message(player["socket"], "INVL room-host-disconnected")
            return

        match_id, msg = pair_players(host_player, player, shared)
        match_message = (host_player, player, msg, match_id)

    if match_message:
        host_player, player2, msg, match_id = match_message
        send_message(host_player["socket"], msg)
        send_message(player2["socket"], msg)
        print(f"Matched {host_player['client_id']} and {player2['client_id']} into {match_id} via room {code}")


def handle_client(client_socket, client_address, shared, lock):
    client_file = client_socket.makefile("rb")
    try:
        # --- handshake ---
        message = read_message(client_file)
        if not message:
            client_socket.close()
            return
        print(f"Received: {message}")

        parts = message.split()
        if not (len(parts) >= 2 and parts[0] == "HELO"):
            send_message(client_socket, "INVL expected-helo")
            client_socket.close()
            return

        version = parts[1]

        # if the client sends an existing CID, reuse it — otherwise assign a new one
        if len(parts) >= 3:
            client_id = parts[2]
            print(f"Reconnected as {client_id}")
        else:
            with lock:
                client_id = create_client_id(shared["player_count"])
                shared["player_count"] += 1
            print(f"Assigned {client_id}")

        send_message(client_socket, f"SESS {version} {client_id}")

        # --- routing ---
        message = read_message(client_file)
        if not message:
            client_socket.close()
            return
        print(f"Received: {message}")

        parts = message.split()
        player = {
            "socket": client_socket,
            "file": client_file,
            "address": client_address,
            "client_id": client_id,
        }

        if parts[0] == "QJOIN" and len(parts) == 1:
            handle_qjoin(player, shared, lock)
        elif parts[0] == "RCREATE" and len(parts) == 1:
            handle_rcreate(player, shared, lock)
        elif parts[0] == "RJOIN" and len(parts) == 2:
            handle_rjoin(player, parts[1], shared, lock)
        else:
            send_message(client_socket, "INVL expected-qjoin-rcreate-rjoin")
            client_socket.close()

    except Exception as e:
        print(f"Error handling {client_address}: {e}")
        client_socket.close()


def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, MATCHMAKING_PORT))
    server_socket.listen()

    print(f"Matchmaking Server is listening on port {MATCHMAKING_PORT}")

    # shared state accessed across threads
    shared = {
        "waiting_players": [],
        "rooms": {},
        "player_count": 1,
        "match_count": 1,
    }
    lock = threading.Lock()

    try:
        while True:
            client_socket, client_address = server_socket.accept()
            print(f"Connected: {client_address}")
            thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address, shared, lock),
                daemon=True,
            )
            thread.start()

    finally:
        print("Shutting down matchmaking server.")
        server_socket.close()


if __name__ == "__main__":
    main()