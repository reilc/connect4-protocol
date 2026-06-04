import socket

MATCHMAKING_HOST = "127.0.0.1"
# MATCHMAKING_HOST = "10.18.33.24"
MATCHMAKING_PORT = 4242
PROTOCOL_VERSION = "1"


def read_message(server_file):
    line = server_file.readline()
    if not line:
        return None
    return line.decode("utf-8").strip()


def send_message(server_socket, message):
    server_socket.sendall((message + "\r\n").encode("utf-8"))


def connect_to_matchmaking():
    matchmaking_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    matchmaking_socket.connect((MATCHMAKING_HOST, MATCHMAKING_PORT))
    matchmaking_file = matchmaking_socket.makefile("rb")

    send_message(matchmaking_socket, f"HELO {PROTOCOL_VERSION}")

    session_msg = read_message(matchmaking_file)
    if session_msg is None:
        raise ConnectionError("Matchmaking server closed before sending SESS")

    print(session_msg)
    parts = session_msg.split()

    if len(parts) < 4 or parts[0] != "SESS":
        raise ValueError("Expected SESS message from matchmaking server")

    client_id = parts[3]
    print(f"You are {client_id}")

    send_message(matchmaking_socket, f"QJOIN {client_id}")
    print("Searching for opponent...")

    match_id = None
    game_server_host = None
    game_server_port = None

    while True:
        msg = read_message(matchmaking_file)
        if msg is None:
            raise ConnectionError("Matchmaking server closed before MATCH")

        print(msg)
        parts = msg.split()

        if len(parts) == 4 and parts[0] == "MATCH":
            match_id = parts[1]
            game_server_host = parts[2]
            game_server_port = int(parts[3])
            break

    matchmaking_file.close()
    matchmaking_socket.close()

    return client_id, match_id, game_server_host, game_server_port


def play_game(client_id, match_id, game_server_host, game_server_port):
    game_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    game_socket.connect((game_server_host, game_server_port))
    game_file = game_socket.makefile("rb")

    send_message(game_socket, f"GCON {match_id} {client_id}")
    print(f"Connected to game server as {client_id}")

    try:
        while True:
            msg = read_message(game_file)
            if msg is None:
                print("Disconnected from game server.")
                break

            print(msg)

            if msg.startswith("YOUR_TURN"):
                move = input("Choose a column (1-7): ").strip()
                send_message(game_socket, move)

            if msg.startswith("OVER"):
                break

    finally:
        game_file.close()
        game_socket.close()


def main():
    try:
        client_id, match_id, game_server_host, game_server_port = connect_to_matchmaking()
        play_game(client_id, match_id, game_server_host, game_server_port)
    except ConnectionRefusedError:
        print("Could not connect. Make sure the servers are running first.")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()