import socket
import uuid

HOST = "0.0.0.0"
MATCHMAKING_PORT = 4242

# for testing/playing locally
GAME_SERVER_HOST = "127.0.0.1"

# for playing with multiple users (ipconfig getifaddr en0)
# GAME_SERVER_HOST = "10.18.33.24"
GAME_SERVER_PORT = 4243


def read_message(client_socket):
    data = client_socket.recv(1024).decode("utf-8")
    return data.strip()


def send_message(client_socket, message):
    client_socket.sendall((message + "\r\n").encode("utf-8"))


def create_client_id(player_num):
    return f"CID{player_num}"


def create_match_id(match_num):
    return f"M{match_num}"


def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, MATCHMAKING_PORT))
    server_socket.listen()

    print(f"Matchmaking Server is listening on port {MATCHMAKING_PORT}")

    waiting_players = []
    player_count = 1
    match_count = 1

    while True:
        client_socket, client_address = server_socket.accept()
        print(f"Connected to {client_address}")

        try:
            message = read_message(client_socket)
            print(f"Received: {message}")

            parts = message.split()

            if len(parts) >= 2 and parts[0] == "HELO":
                version = parts[1]

                client_id = create_client_id(player_count)
                player_count += 1

                session_id = str(uuid.uuid4())

                send_message(client_socket, f"SESS {version} {session_id} {client_id}")
                print(f"Assigned {client_id}")

                qjoin_message = read_message(client_socket)
                print(f"Received: {qjoin_message}")

                qjoin_parts = qjoin_message.split()

                if len(qjoin_parts) == 2 and qjoin_parts[0] == "QJOIN":
                    waiting_players.append({
                        "socket": client_socket,
                        "address": client_address,
                        "client_id": client_id,
                        "session_id": session_id
                    })

                    send_message(client_socket, "WAIT Waiting for opponent...")

                    if len(waiting_players) >= 2:
                        player1 = waiting_players.pop(0)
                        player2 = waiting_players.pop(0)

                        match_id = create_match_id(match_count)
                        match_count += 1

                        match_message = f"MATCH {match_id} {GAME_SERVER_HOST} {GAME_SERVER_PORT}"

                        send_message(player1["socket"], match_message)
                        send_message(player2["socket"], match_message)

                        print(
                            f"Matched {player1['client_id']} and "
                            f"{player2['client_id']} into {match_id}"
                        )

                else:
                    send_message(client_socket, "INVL expected-qjoin")
                    client_socket.close()

            else:
                send_message(client_socket, "INVL expected-helo")
                client_socket.close()

        except Exception as e:
            print(f"Error handling client: {e}")
            client_socket.close()


if __name__ == "__main__":
    main()