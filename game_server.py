import socket

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


def main():
    host = '0.0.0.0'
    port = 4243

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((host, port))
    server_socket.listen(2)

    print(f"Game Server is listening on port {port}")

    players = []

    while len(players) < 2:
        client_socket, client_address = server_socket.accept()
        print(f"connected to {client_address}")
        try:
            client_file = client_socket.makefile("rb")
            message = read_message(client_file)
            print(f"received: {message}")

            parts = message.split() if message else []

            if len(parts) == 3 and parts[0] == "GCON":
                match_id = parts[1]
                client_id = parts[2]

                players.append({
                    "socket": client_socket,
                    "file": client_file,
                    "address": client_address,
                    "match_id": match_id,
                    "client_id": client_id
                })
            else:
                send_message(client_socket, "INVL bad-gcon")
                client_socket.close()
        except Exception as e:
            print(f"Error handling connection: {e}")
            client_socket.close()

    game = ConnectFour()

    player1 = players[0]
    player2 = players[1]

    start_message = f"STRT {player1['match_id']} {player1['client_id']} {player2['client_id']}"

    broadcast(players, start_message)

    try:
        while not game.is_game_over():

            current_player_idx = 0 if game.turn else 1
            active_player = players[current_player_idx]
            waiting_player = players[1 - current_player_idx]

            broadcast(players, f"BOARD {game.get_board_string()}")

            send_message(active_player["socket"], "YOUR_TURN")
            send_message(waiting_player["socket"], "WAIT_TURN")

            try:
                move_msg = read_message(active_player["file"])
                if not move_msg:
                    print(f"Player {active_player['client_id']} disconnected.")
                    broadcast(players, "ERR opponent-disconnected")
                    break

                print(f"Player {active_player['client_id']} chose column: {move_msg}")
                column = int(move_msg)

                game.make_move(column)

            except ValueError as e:
                send_message(active_player["socket"], f"INVL {str(e)}")
                continue
            except Exception as e:
                print(f"Error handling player turn: {e}")
                break

        broadcast(players, f"BOARD {game.get_board_string()}")
        winner = game.get_winner()
        
        if winner == 1:
            broadcast(players, f"OVER WIN {player1['client_id']}")
        elif winner == 2:
            broadcast(players, f"OVER WIN {player2['client_id']}")
        else:
            broadcast(players, "OVER DRAW")

    finally:
        print("Closing player sockets and shutting down server.")
        player1["socket"].close()
        player2["socket"].close()
        server_socket.close()

if __name__ == "__main__":
    main()