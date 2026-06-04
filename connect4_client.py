import socket

MATCHMAKING_HOST = "127.0.0.1"
# MATCHMAKING_HOST = "10.18.33.24"
MATCHMAKING_PORT = 4242
PROTOCOL_VERSION = "1"

BOARD_ROWS = 6
BOARD_COLS = 7


# ---------------------------------------------------------------------------
# networking
# ---------------------------------------------------------------------------

def read_message(server_file):
    line = server_file.readline()
    if not line:
        return None
    return line.decode("utf-8").strip()


def send_message(server_socket, message):
    server_socket.sendall((message + "\r\n").encode("utf-8"))


# ---------------------------------------------------------------------------
# display
# ---------------------------------------------------------------------------

def print_instructions():
    print("\nHow to play:")
    print("  - You are RED (R) if you are Player 1, YELLOW (Y) if you are Player 2")
    print("  - Players take turns dropping a piece into a column (1-7)")
    print("  - First to get 4 in a row — horizontally, vertically, or diagonally — wins\n")


def render_board(board_string):
    print("\n  1 2 3 4 5 6 7")
    print(" +-+-+-+-+-+-+-+")
    for row in range(BOARD_ROWS):
        line = " |"
        for col in range(BOARD_COLS):
            spot = board_string[row * BOARD_COLS + col]
            line += spot + "|"
        print(line)
    print(" +-+-+-+-+-+-+-+\n")


# ---------------------------------------------------------------------------
# lobby
# ---------------------------------------------------------------------------

def print_lobby_menu():
    print("\n--- Connect 4 Lobby ---")
    print("  1. Random matchmaking")
    print("  2. Create a private room")
    print("  3. Join a private room")


def get_lobby_choice():
    while True:
        print_lobby_menu()
        choice = input("Choose an option (1-3): ").strip()
        if choice in ("1", "2", "3"):
            return choice
        print("Invalid choice. Please enter 1, 2, or 3.")


# ---------------------------------------------------------------------------
# matchmaking
# ---------------------------------------------------------------------------

def handshake(matchmaking_socket, matchmaking_file):
    send_message(matchmaking_socket, f"HELO {PROTOCOL_VERSION}")

    sess_msg = read_message(matchmaking_file)
    if sess_msg is None:
        raise ConnectionError("Matchmaking server closed before sending SESS")

    parts = sess_msg.split()
    if len(parts) < 3 or parts[0] != "SESS":
        raise ValueError(f"Expected SESS message, got: {sess_msg}")

    client_id = parts[2]
    print(f"Connected. You are {client_id}")
    return client_id


def wait_for_match(matchmaking_file):
    print("Waiting for opponent...")
    while True:
        msg = read_message(matchmaking_file)
        if msg is None:
            raise ConnectionError("Matchmaking server closed before MATCH")
        parts = msg.split()
        if parts[0] == "MATCH" and len(parts) == 4:
            match_id = parts[1]
            host = parts[2]
            port = int(parts[3])
            print(f"Opponent found! Match {match_id}")
            return match_id, host, port
        if parts[0] == "INVL":
            raise ValueError(f"Matchmaking error: {msg}")


def connect_random(matchmaking_socket, matchmaking_file):
    send_message(matchmaking_socket, "QJOIN")
    return wait_for_match(matchmaking_file)


def connect_create_room(matchmaking_socket, matchmaking_file):
    send_message(matchmaking_socket, "RCREATE")

    msg = read_message(matchmaking_file)
    if msg is None:
        raise ConnectionError("Matchmaking server closed before ROOM")
    parts = msg.split()
    if parts[0] != "ROOM" or len(parts) != 2:
        raise ValueError(f"Expected ROOM message, got: {msg}")

    room_code = parts[1]
    print(f"\nYour room code is: {room_code}")
    print("Share this code with your friend and wait for them to join...\n")
    return wait_for_match(matchmaking_file)


def connect_join_room(matchmaking_socket, matchmaking_file):
    while True:
        code = input("Enter room code: ").strip().upper()
        if not code:
            print("Room code cannot be empty.")
            continue

        send_message(matchmaking_socket, f"RJOIN {code}")

        msg = read_message(matchmaking_file)
        if msg is None:
            raise ConnectionError("Matchmaking server closed unexpectedly")
        parts = msg.split()

        if parts[0] == "MATCH":
            match_id = parts[1]
            host = parts[2]
            port = int(parts[3])
            print(f"Joined room! Match {match_id}")
            return match_id, host, port
        elif parts[0] == "INVL" and len(parts) >= 2:
            reason = parts[1]
            if reason == "unknown-room-code":
                print("That room code doesn't exist. Please try again.")
            elif reason == "room-host-disconnected":
                print("The room host disconnected. Please try again.")
            else:
                raise ValueError(f"Matchmaking error: {msg}")
        else:
            raise ValueError(f"Unexpected message: {msg}")


def connect_to_matchmaking():
    matchmaking_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    matchmaking_socket.connect((MATCHMAKING_HOST, MATCHMAKING_PORT))
    matchmaking_file = matchmaking_socket.makefile("rb")

    try:
        client_id = handshake(matchmaking_socket, matchmaking_file)
        choice = get_lobby_choice()

        if choice == "1":
            match_id, host, port = connect_random(matchmaking_socket, matchmaking_file)
        elif choice == "2":
            match_id, host, port = connect_create_room(matchmaking_socket, matchmaking_file)
        else:
            match_id, host, port = connect_join_room(matchmaking_socket, matchmaking_file)

    finally:
        matchmaking_file.close()
        matchmaking_socket.close()

    return client_id, match_id, host, port


# ---------------------------------------------------------------------------
# gameplay
# ---------------------------------------------------------------------------

def get_move():
    while True:
        raw = input("Choose a column (1-7): ").strip()
        if not raw.isdigit():
            print("Please enter a number.")
            continue
        col = int(raw)
        if col < 1 or col > 7:
            print("Column must be between 1 and 7.")
            continue
        return str(col)


def play_game(client_id, match_id, game_server_host, game_server_port):
    game_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    game_socket.connect((game_server_host, game_server_port))
    game_file = game_socket.makefile("rb")

    send_message(game_socket, f"GCON {match_id} {client_id}")
    print(f"\nConnected to game server as {client_id}")

    try:
        while True:
            msg = read_message(game_file)
            if msg is None:
                print("Disconnected from game server.")
                break

            parts = msg.split()
            verb = parts[0] if parts else ""

            if verb == "STRT":
                print_instructions()

            elif verb == "BOARD":
                board_string = parts[1] if len(parts) > 1 else ""
                render_board(board_string)

            elif verb == "YOUR_TURN":
                timeout = parts[1] if len(parts) > 1 else "?"
                print(f"Your turn! You have {timeout} seconds.")
                move = get_move()
                send_message(game_socket, move)

            elif verb == "WAIT_TURN":
                print("Waiting for opponent's move...")

            elif verb == "INVL":
                reason = parts[1] if len(parts) > 1 else "unknown"
                print(f"Invalid move ({reason}). Try again.")
                move = get_move()
                send_message(game_socket, move)

            elif verb == "ERR":
                reason = parts[1] if len(parts) > 1 else "unknown"
                print(f"Game error: {reason}")
                break

            elif verb == "OVER":
                outcome = parts[1] if len(parts) > 1 else ""
                if outcome == "WIN":
                    winner_id = parts[2] if len(parts) > 2 else "unknown"
                    forfeit = len(parts) > 3 and parts[3] == "forfeit"
                    if winner_id == client_id:
                        print("You win!" + (" (opponent timed out)" if forfeit else ""))
                    else:
                        print("You lose." + (" (you timed out)" if forfeit else ""))
                elif outcome == "DRAW":
                    print("It's a draw!")
                elif outcome == "FORFEIT":
                    print("You ran out of time. You lose by forfeit.")
                break

    finally:
        game_file.close()
        game_socket.close()


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def main():
    try:
        client_id, match_id, host, port = connect_to_matchmaking()
        play_game(client_id, match_id, host, port)
    except ConnectionRefusedError:
        print("Could not connect. Make sure the servers are running first.")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()