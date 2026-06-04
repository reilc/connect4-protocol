import json
import os
import socket
import threading
from datetime import datetime, timezone

HOST = "0.0.0.0"
STATS_PORT = 4244
STATS_FILE = "stats.json"
STATS_ARCHIVE_DIR = "stats_archive"


# ---------------------------------------------------------------------------
# networking
# ---------------------------------------------------------------------------

def read_message(client_file):
    line = client_file.readline()
    if not line:
        return None
    return line.decode("utf-8").strip()


def send_message(client_socket, message):
    client_socket.sendall((message + "\r\n").encode("utf-8"))


# ---------------------------------------------------------------------------
# JSON file helpers
# ---------------------------------------------------------------------------

def load_stats(lock):
    """Read the stats file. Returns an empty dict if the file doesn't exist yet."""
    with lock:
        if not os.path.exists(STATS_FILE):
            return {}
        with open(STATS_FILE, "r") as f:
            return json.load(f)


def save_stats(data, lock):
    """Write stats atomically — temp file then rename so a crash can't corrupt the file."""
    tmp = STATS_FILE + ".tmp"
    with lock:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, STATS_FILE)


def get_or_create_player(data, client_id):
    """Return the player entry, creating it if this is their first game."""
    if client_id not in data:
        data[client_id] = {
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "matches": []
        }
    return data[client_id]


# ---------------------------------------------------------------------------
# message handlers
# ---------------------------------------------------------------------------

def handle_result(parts, file_lock):
    """
    RESULT <match_id> <p1_id> <p2_id> <winner_id|DRAW> <outcome>
           <p1_moves> <p2_moves> <duration>
    """
    if len(parts) != 9:
        print(f"Malformed RESULT message: {' '.join(parts)}")
        return False

    _, match_id, p1_id, p2_id, winner_id, outcome, p1_moves, p2_moves, duration = parts

    try:
        p1_moves = int(p1_moves)
        p2_moves = int(p2_moves)
        duration = int(duration)
    except ValueError:
        print(f"Non-numeric fields in RESULT message: {' '.join(parts)}")
        return False

    timestamp = datetime.now(timezone.utc).isoformat()

    data = load_stats(file_lock)

    for player_id, opponent_id, my_moves, opp_moves in [
        (p1_id, p2_id, p1_moves, p2_moves),
        (p2_id, p1_id, p2_moves, p1_moves),
    ]:
        player = get_or_create_player(data, player_id)

        if outcome == "DRAW":
            player["draws"] += 1
            player_outcome = "DRAW"
        elif winner_id == player_id:
            player["wins"] += 1
            player_outcome = outcome  # WIN or FORFEIT
        else:
            player["losses"] += 1
            player_outcome = "LOSS" if outcome == "WIN" else "LOSS_FORFEIT"

        player["matches"].append({
            "match_id": match_id,
            "opponent": opponent_id,
            "outcome": player_outcome,
            "moves": my_moves,
            "opponent_moves": opp_moves,
            "duration": duration,
            "timestamp": timestamp,
        })

    save_stats(data, file_lock)
    print(f"Saved result for match {match_id}: {p1_id} vs {p2_id} — {outcome}")
    return True


def handle_stats(client_socket, parts, file_lock):
    """
    STATS <client_id>
    Responds with STATS_OK <json> or STATS_NONE if the player has no history.
    """
    if len(parts) != 2:
        send_message(client_socket, "INVL expected-stats-client-id")
        return

    client_id = parts[1]
    data = load_stats(file_lock)

    if client_id not in data:
        send_message(client_socket, "STATS_NONE")
        return

    payload = json.dumps(data[client_id])
    send_message(client_socket, f"STATS_OK {payload}")
    print(f"Sent stats for {client_id}")


# ---------------------------------------------------------------------------
# connection handler
# ---------------------------------------------------------------------------

def handle_connection(client_socket, client_address, file_lock):
    client_file = client_socket.makefile("rb")
    try:
        message = read_message(client_file)
        if not message:
            return
        print(f"Received from {client_address}: {message}")

        parts = message.split()
        if not parts:
            return

        if parts[0] == "RESULT":
            success = handle_result(parts, file_lock)
            if success:
                send_message(client_socket, "RESULT_OK")
            else:
                send_message(client_socket, "INVL malformed-result")

        elif parts[0] == "STATS":
            handle_stats(client_socket, parts, file_lock)

        else:
            send_message(client_socket, "INVL unknown-verb")

    except Exception as e:
        print(f"Error handling {client_address}: {e}")
    finally:
        client_file.close()
        client_socket.close()


# ---------------------------------------------------------------------------
# startup
# ---------------------------------------------------------------------------

def archive_stats():
    """If a stats file exists from a previous session, move it to the archive folder."""
    if not os.path.exists(STATS_FILE):
        return

    os.makedirs(STATS_ARCHIVE_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archive_path = os.path.join(STATS_ARCHIVE_DIR, f"stats_{timestamp}.json")
    os.rename(STATS_FILE, archive_path)
    print(f"Archived previous stats to: {archive_path}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    archive_stats()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, STATS_PORT))
    server_socket.listen()

    print(f"Stats Server is listening on port {STATS_PORT}")
    print(f"Storing stats in: {os.path.abspath(STATS_FILE)}")

    file_lock = threading.Lock()

    try:
        while True:
            client_socket, client_address = server_socket.accept()
            print(f"Connected: {client_address}")
            thread = threading.Thread(
                target=handle_connection,
                args=(client_socket, client_address, file_lock),
                daemon=True,
            )
            thread.start()

    finally:
        print("Shutting down stats server.")
        server_socket.close()


if __name__ == "__main__":
    main()