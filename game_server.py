import socket
import threading
import time

TURN_TIMEOUT = 45  # seconds a player has to submit a move

STATS_SERVER_HOST = "127.0.0.1"
STATS_SERVER_PORT = 4244

class ConnectFour:
    def __init__(self):
        self.board = [
            ['*', '*', '*', '*', '*', '*', '*'],
            ['*', '*', '*', '*', '*', '*', '*'],
            ['*', '*', '*', '*', '*', '*', '*'],
            ['*', '*', '*', '*', '*', '*', '*'],
            ['*', '*', '*', '*', '*', '*', '*'],
            ['*', '*', '*', '*', '*', '*', '*']
        ]
        self.turn = True

    def make_move(self, column):
        if column < 1 or column > 7:
            raise ValueError("past column limits")

        column = column - 1

        if self.board[0][column] != '*':
            raise ValueError("column is full")

        row = len(self.board) - 1
        while self.board[row][column] != '*':
            row -= 1

        if self.turn:
            self.board[row][column] = 'R'
        else:
            self.board[row][column] = 'Y'

        self.turn = not self.turn

    def is_game_over(self):
        if self.get_winner() != -1:
            return True

        return self.is_draw()

    def is_draw(self):
        for row in self.board:
            for spot in row:
                if spot == '*':
                    return False

        return True

    def get_winner(self):
        for i in range(len(self.board)):
            for j in range(len(self.board[i])):
                position = self.board[i][j]

                if position != '*' and j + 3 < len(self.board[i]):
                    if position == self.board[i][j + 1] and position == self.board[i][j + 2] and position == self.board[i][j + 3]:
                        return 2 if self.turn else 1

                if position != '*' and i + 3 < len(self.board):
                    if position == self.board[i + 1][j] and position == self.board[i + 2][j] and position == self.board[i + 3][j]:
                        return 2 if self.turn else 1

                if position != '*' and i >= 3 and j >= 3:
                    if position == self.board[i - 3][j - 3] and position == self.board[i - 2][j - 2] and position == self.board[i - 1][j - 1]:
                        return 2 if self.turn else 1

                if position != '*' and i >= 3 and j < len(self.board[i]) - 3:
                    if position == self.board[i - 3][j + 3] and position == self.board[i - 2][j + 2] and position == self.board[i - 1][j + 1]:
                        return 2 if self.turn else 1

        return -1

    def get_next_player(self):
        if self.is_game_over():
            return -1

        return 1 if self.turn else 2

    def get_board_string(self):
        result = ""
        for row in self.board:
            for spot in row:
                result += spot

        return result


def read_message(client_file):
    line = client_file.readline()
    if not line:
        return None
    return line.decode('utf-8').strip()


def send_message(client_socket, message):
    client_socket.sendall((message + "\r\n").encode('utf-8'))

def broadcast(players, message):
    for player in players:
        try:
            send_message(player["socket"], message)
        except Exception as e:
            print(f"Error broadcasting to {player['client_id']}: {e}")


def report_result(match_id, p1_id, p2_id, winner_id, outcome, p1_moves, p2_moves, duration):
    """Send the completed game result to the stats server. Failures are logged but not fatal."""
    try:
        stats_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        stats_socket.connect((STATS_SERVER_HOST, STATS_SERVER_PORT))
        stats_file = stats_socket.makefile("rb")

        msg = (
            f"RESULT {match_id} {p1_id} {p2_id} {winner_id} "
            f"{outcome} {p1_moves} {p2_moves} {duration}"
        )
        send_message(stats_socket, msg)

        response = stats_file.readline().decode("utf-8").strip()
        if response != "RESULT_OK":
            print(f"[{match_id}] Stats server returned unexpected response: {response}")

    except Exception as e:
        print(f"[{match_id}] Could not report result to stats server: {e}")
    finally:
        try:
            stats_file.close()
            stats_socket.close()
        except Exception:
            pass


def run_game(players):
    assert players[0]["match_id"] == players[1]["match_id"], "Match ID mismatch — players should not have been paired"

    game = ConnectFour()

    player1 = players[0]
    player2 = players[1]

    match_id = player1["match_id"]
    print(f"[{match_id}] Starting game between {player1['client_id']} and {player2['client_id']}")

    broadcast(players, f"STRT {match_id} {player1['client_id']} {player2['client_id']}")

    start_time = time.time()
    move_counts = {player1["client_id"]: 0, player2["client_id"]: 0}

    # result state — updated at each exit point, read in finally
    winner_id = "DRAW"
    outcome = "DRAW"

    try:
        while not game.is_game_over():

            current_player_idx = 0 if game.turn else 1
            active_player = players[current_player_idx]
            waiting_player = players[1 - current_player_idx]

            broadcast(players, f"BOARD {game.get_board_string()}")

            send_message(active_player["socket"], f"YOUR_TURN {TURN_TIMEOUT}")
            send_message(waiting_player["socket"], "WAIT_TURN")

            try:
                active_player["socket"].settimeout(TURN_TIMEOUT)
                move_msg = read_message(active_player["file"])
                active_player["socket"].settimeout(None)

                if not move_msg:
                    print(f"[{match_id}] {active_player['client_id']} disconnected.")
                    broadcast(players, "ERR opponent-disconnected")
                    winner_id = None
                    outcome = None
                    break

                print(f"[{match_id}] {active_player['client_id']} sent: {move_msg}")

                parts = move_msg.split()
                if len(parts) != 4 or parts[0] != "MOVE":
                    send_message(active_player["socket"], "INVL bad-move-format")
                    continue

                move_match_id = parts[1]
                move_client_id = parts[2]
                move_column = parts[3]

                if move_match_id != match_id:
                    send_message(active_player["socket"], "INVL wrong-match-id")
                    continue

                if move_client_id != active_player["client_id"]:
                    send_message(active_player["socket"], "INVL wrong-client-id")
                    continue

                column = int(move_column)
                game.make_move(column)
                move_counts[active_player["client_id"]] += 1

            except socket.timeout:
                active_player["socket"].settimeout(None)
                print(f"[{match_id}] {active_player['client_id']} timed out.")
                send_message(active_player["socket"], "OVER FORFEIT timeout")
                send_message(waiting_player["socket"], f"OVER WIN {waiting_player['client_id']} forfeit")
                winner_id = waiting_player["client_id"]
                outcome = "FORFEIT"
                return
            except ValueError as e:
                send_message(active_player["socket"], f"INVL {str(e)}")
                continue
            except Exception as e:
                print(f"[{match_id}] Error handling player turn: {e}")
                winner_id = None
                outcome = None
                break

        broadcast(players, f"BOARD {game.get_board_string()}")
        game_winner = game.get_winner()

        if game_winner == 1:
            winner_id = player1["client_id"]
            outcome = "WIN"
            broadcast(players, f"OVER WIN {player1['client_id']}")
        elif game_winner == 2:
            winner_id = player2["client_id"]
            outcome = "WIN"
            broadcast(players, f"OVER WIN {player2['client_id']}")
        else:
            winner_id = "DRAW"
            outcome = "DRAW"
            broadcast(players, "OVER DRAW")

    finally:
        duration = int(time.time() - start_time)
        print(f"[{match_id}] Game over. Closing player sockets.")

        if outcome is not None:
            report_result(
                match_id,
                player1["client_id"],
                player2["client_id"],
                winner_id,
                outcome,
                move_counts[player1["client_id"]],
                move_counts[player2["client_id"]],
                duration,
            )

        for player in players:
            player["file"].close()
            player["socket"].close()


def main():
    host = '0.0.0.0'
    port = 4243

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((host, port))
    server_socket.listen()

    print(f"Game Server is listening on port {port}")

    # match_id -> list of connected players waiting for their opponent
    matches = {}
    lock = threading.Lock()

    try:
        while True:
            client_socket, client_address = server_socket.accept()
            print(f"Connected: {client_address}")
            try:
                client_file = client_socket.makefile("rb")
                message = read_message(client_file)
                print(f"Received: {message}")

                parts = message.split() if message else []

                if len(parts) == 3 and parts[0] == "GCON":
                    match_id = parts[1]
                    client_id = parts[2]

                    player = {
                        "socket": client_socket,
                        "file": client_file,
                        "address": client_address,
                        "match_id": match_id,
                        "client_id": client_id
                    }

                    with lock:
                        if match_id not in matches:
                            matches[match_id] = []
                        matches[match_id].append(player)

                        if len(matches[match_id]) == 2:
                            paired_players = matches.pop(match_id)
                            thread = threading.Thread(
                                target=run_game,
                                args=(paired_players,),
                                daemon=True
                            )
                            thread.start()
                            print(f"[{match_id}] Both players connected. Game thread started.")
                        else:
                            print(f"[{match_id}] Waiting for second player...")
                else:
                    send_message(client_socket, "INVL bad-gcon")
                    client_socket.close()
            except Exception as e:
                print(f"Error handling connection: {e}")
                client_socket.close()

    finally:
        print("Shutting down game server.")
        server_socket.close()


if __name__ == "__main__":
    main()