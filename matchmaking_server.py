import socket
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

        with lock:
            client_id = create_client_id(shared["player_count"])
            shared["player_count"] += 1

        send_message(client_socket, f"SESS {version} {client_id}")
        print(f"Assigned {client_id}")

        # --- queue join ---
        message = read_message(client_file)
        if not message:
            client_socket.close()
            return
        print(f"Received: {message}")

        parts = message.split()
        if not (len(parts) == 2 and parts[0] == "QJOIN"):
            send_message(client_socket, "INVL expected-qjoin")
            client_socket.close()
            return

        send_message(client_socket, "WAIT")
        print(f"{client_id} joined the queue")

        player = {
            "socket": client_socket,
            "file": client_file,
            "address": client_address,
            "client_id": client_id,
        }

        # --- matchmaking ---
        match_message = None
        with lock:
            shared["waiting_players"].append(player)

            if len(shared["waiting_players"]) >= 2:
                player1 = shared["waiting_players"].pop(0)
                player2 = shared["waiting_players"].pop(0)

                match_id = create_match_id(shared["match_count"])
                shared["match_count"] += 1

                match_message = (
                    player1,
                    player2,
                    f"MATCH {match_id} {GAME_SERVER_HOST} {GAME_SERVER_PORT}",
                    match_id,
                )

        # send MATCH outside the lock so we don't hold it during network I/O
        if match_message:
            player1, player2, msg, match_id = match_message
            send_message(player1["socket"], msg)
            send_message(player2["socket"], msg)
            print(f"Matched {player1['client_id']} and {player2['client_id']} into {match_id}")

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