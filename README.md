# **RFC INFO314 — Connect 4 Network Protocol**

## **Abstract**

This RFC details a network protocol for two players to play a game of Connect 4 over a computer network using a strict client-server architecture. The protocol defines communication between a Game Lobby (player client), a Matchmaking Server, a Game Server, and a Statistics Server.

## **Status of This Memo**

This document is not an Internet Standards Track specification; it is published for informational purposes, primarily for the purpose of students taking INFO314 at the University of Washington, Seattle to implement a distributed game protocol and gain hands-on experience with networked systems design.

This document is not a product of the Internet Engineering Task Force (IETF) and does not in any way represent the consensus of the IETF community. It has not been approved for publication by the Internet Engineering Steering Group (IESG) and should not be used for production purposes.

---

## **Table of Contents**

1. History  
2. Rules of Connect 4  
   * Determination of which player begins  
   * Restrictions around token placement  
   * Game termination  
3. System Architecture Overview  
4. Component Specifications  
   * Game Lobby / Player Client  
   * Matchmaking Server  
   * Game Server  
   * Statistics Server  
5. Detailed Description  
   * Description of Terms  
   * TCP-Based Service  
   * Session  
   * Matchmaking  
   * Getting into a Game  
   * Making a Move  
   * Winning and Recording Results  
   * Turn Timeout  
   * Crash and Disconnection Handling  
6. Message Reference  
7. Communication Scenarios  
8. Error and Failure Handling  
9. References

---

## **History**

Connect 4 was first sold under that name by Milton Bradley in 1974\. It is a two-player strategy game in which players drop colored discs into a vertically suspended grid. The first player to form a horizontal, vertical, or diagonal line of four of their own discs wins the game. The game became widely popular due to its simple rules and the depth of strategic play it allows.

---

## **Rules of Connect 4**

Connect 4 is played on a 7-column, 6-row vertically suspended grid. Players alternate turns dropping one disc of their color into any of the seven columns. Discs fall to the lowest unoccupied row within the chosen column.

### **Determination of which player begins**

The server determines which player goes first when the match begins and notifies both clients. The first player is assigned the Red token; the second is assigned Yellow.

### **Restrictions around token placement**

A player may drop a disc into any column that is not already full (i.e., has fewer than 6 discs). A player may not place a disc in a full column. Players may not play out of turn.

### **Game termination**

The game ends as soon as one player achieves four discs in a row — horizontally, vertically, or diagonally. If all 42 squares are filled and no player has four in a row, the game is declared a draw. A game also ends if a player disconnects or forfeits.

---

## **System Architecture Overview**

    +-------------------------------------------------+
    |               Matchmaking Server                |
    +-------------------------------------------------+
            /                                  \
    Matchmaking Request                Paired match handed
          /                               to game server
         /                                       \
    +------------------+                   +------------------+     Game results
    |    Game Lobby    |                   |    Game Server   |------------------>
    | (Player Client)  |                   |                  |   +---------------+
    +------------------+                   +------------------+   | Stats Server  |
            \                                  /                   +---------------+
           Redirected                         /
          to find opp                       /
               \                         /
                +-----------------------+

The system follows a sequential lifecycle: players interact with the Game Lobby, which communicates with the Matchmaking Server to find opponents via random queue or room code. Once matched, the Matchmaking Server hands the connection off to a Game Server, which acts as the sole referee for the match. When the game concludes, the Game Server pushes results to the Statistics Server. After stats are displayed, the client is automatically returned to the lobby.

---

## **Component Specifications**

### **Game Lobby / Player Client**

**Responsibilities:**

* Allow users to join rooms via room code, enter random matchmaking, make moves, and view the board.
* Display game instructions, board state, and post-game statistics.
* Return players to the lobby automatically after each game.

**State Stored/Managed:**

* Current client ID (persisted across games within a session), current room code, current match ID, local copy of the board, connection status.

**Messages:**

* *Sends:* `HELO`, `QJOIN`, `RCREATE`, `RJOIN`, `GCON`, move column number, `STATS`.
* *Receives:* `SESS`, `WAIT`, `ROOM`, `MATCH`, `STRT`, `BOARD`, `YOUR_TURN`, `WAIT_TURN`, `INVL`, `ERR`, `OVER`, `STATS_OK`, `STATS_NONE`.

**Important Logic:**

* The client performs no game logic and does not determine move legality. It only displays state and forwards user actions to the appropriate server.
* Client IDs are assigned once per session on first connection and reused on subsequent lobby visits.

---

### **Matchmaking Server**

**Responsibilities:**

* Pair players together through room code or random queue, then hand them off to a Game Server.
* Handle multiple concurrent players without blocking.

**State Stored/Managed:**

* Waiting players (random queue), active room codes and their host player sockets, player connection status, created match IDs, player count, match count.

**Messages:**

* *Sends:* `SESS`, `WAIT`, `ROOM`, `MATCH`, `INVL`.
* *Receives:* `HELO`, `QJOIN`, `RCREATE`, `RJOIN`.

**Important Logic:**

* Handles each incoming connection in its own thread. Shared state (queue, rooms, counters) is protected by a single threading lock.
* On random queue pairing, checks both sockets for liveness before sending `MATCH`. Dead sockets are removed; surviving players are re-queued.
* On room join, checks the host socket for liveness before pairing. If the host has disconnected, the room is removed and the joiner receives `INVL room-host-disconnected`.
* If a client reconnects with an existing client ID in `HELO`, that ID is reused rather than a new one being assigned.

---

### **Game Server**

**Responsibilities:**

* Run and manage the actual Connect 4 match; serve as the official source of truth for the board.
* Handle multiple simultaneous games concurrently.

**State Stored/Managed:**

* Board state, player turn, player IDs, match ID, move counts per player, game status, start time.

**Messages:**

* *Sends:* `STRT`, `BOARD`, `YOUR_TURN`, `WAIT_TURN`, `INVL`, `ERR`, `OVER`; `RESULT` to the Statistics Server.
* *Receives:* `GCON` from clients; `RESULT_OK` from the Statistics Server.

**Important Logic:**

* Each game runs in its own thread. Incoming connections are grouped by match ID; a thread is spawned once both players for a given match ID have connected.
* Validates that both players carry the same match ID before starting.
* Enforces a server-side 45-second turn timer. Timed-out players forfeit; the waiting player wins.
* Tracks move counts per player and game duration, reported to the Statistics Server on game end.
* Disconnects mid-game are detected and the game is abandoned without recording a result.

---

### **Statistics Server**

**Responsibilities:**

* Store and organize information about completed games.
* Serve per-player stats to clients on request.

**State Stored/Managed:**

* Per-player win/loss/draw counts, match history including outcome, move counts, opponent, and duration. Stored locally as a JSON file (`stats.json`).

**Messages:**

* *Sends:* `STATS_OK`, `STATS_NONE`, `RESULT_OK`, `INVL`.
* *Receives:* `RESULT` from the Game Server; `STATS` from clients.

**Important Logic:**

* On startup, any existing `stats.json` from a previous session is archived to a timestamped file in the `stats_archive/` directory before a fresh file is created.
* Writes are atomic — results are written to a temporary file and then renamed over the live file, preventing corruption on crash.
* A threading lock protects the read-modify-write cycle, preventing concurrent game results from overwriting each other.
* Stats are recorded from each player's individual perspective — their outcome, their move count, and their opponent.

---

## **Detailed Description**

### **Description of Terms**

**Server:** A process acting as the arbiter of game state. This protocol uses multiple servers (Matchmaking, Game, Statistics); each is referred to by its role where context requires disambiguation.

**Client:** A process representing a player in the game (the Game Lobby).

**Client Identifier (CID):** A unique string assigned by the Matchmaking Server to identify a player. Assigned on first connection and reused for the duration of the session.

**Match Identifier:** A unique string identifying a specific game instance, assigned by the Matchmaking Server.

**Room Code:** A 6-character uppercase alphabetic code used to allow two specific players to join a private game.

---

### **TCP-Based Service**

The Connect 4 protocol is a connection-based application running over TCP. Default ports are:

| Server | Port |
|---|---|
| Matchmaking Server | 4242 |
| Game Server | 4243 |
| Statistics Server | 4244 |

Messages are plain text, terminated by CRLF (`\r\n`). Fields within a message are separated by single spaces. All messages are read using line-based I/O (`readline`) to respect message boundaries.

---

### **Session**

A client establishes a session with the Matchmaking Server by sending `HELO` with the protocol version. On first connection, the server assigns a new client ID and responds with `SESS`. On reconnection (after returning to the lobby), the client includes its existing CID in `HELO`; the server echoes it back unchanged rather than assigning a new one.

---

### **Matchmaking**

Once in a session, a client may either:

* **Create a private room** using `RCREATE`, receiving a `ROOM` message with a 6-letter code to share with another player.
* **Join a private room** using `RJOIN <room-code>`.
* **Enter the random queue** using `QJOIN`, which pairs the client with the next available player on a first-come, first-served basis.

When two players are paired, the Matchmaking Server sends both a `MATCH` message containing the Game Server address and match ID. Clients then connect directly to the Game Server using `GCON`.

---

### **Getting into a Game**

1. Client sends `HELO` to Matchmaking Server → Server responds with `SESS`.
2. Client sends `QJOIN`, `RCREATE`, or `RJOIN <code>` → Server pairs players.
3. Server sends `MATCH` (with Game Server address and match ID) to both clients.
4. Both clients send `GCON` to the Game Server to begin the match.
5. Game Server validates that both `GCON` messages carry the same match ID, then sends `STRT` to both clients.

---

### **Making a Move**

1. The Game Server sends `BOARD <board-string>` to both clients, then `YOUR_TURN <timeout>` to the active player and `WAIT_TURN` to the other.
2. The active player's client sends the column number (1–7) to the Game Server.
3. The Game Server validates the move.
4. If valid: the board is updated, move count is incremented, and the loop continues from step 1.
5. If invalid: the server sends `INVL <reason>` to the active player; the board state is unchanged and the player is prompted again.

---

### **Winning and Recording Results**

1. After each valid move, the Game Server checks for a win or draw condition.
2. If the game is over, the server sends a final `BOARD` update followed by `OVER WIN <client-id>` or `OVER DRAW` to both clients.
3. The Game Server sends a `RESULT` message to the Statistics Server with the match ID, player IDs, winner, outcome, move counts, and duration.
4. The Statistics Server responds with `RESULT_OK` and saves the result.
5. The client displays post-game stats retrieved from the Statistics Server, then automatically returns to the lobby.

---

### **Turn Timeout**

The Game Server runs a **45-second server-side turn timer** beginning the moment a player's turn starts. The timeout value is included in the `YOUR_TURN` message so the client can display a countdown. If the timer expires before a move is received:

1. The idle player receives `OVER FORFEIT timeout`.
2. The waiting player receives `OVER WIN <client-id> forfeit`.
3. The result is recorded with the Statistics Server with outcome `FORFEIT`.

---

### **Crash and Disconnection Handling**

If a client disconnects unexpectedly mid-game (detected via an empty read on the socket), the Game Server:

1. Broadcasts `ERR opponent-disconnected` to the remaining client.
2. Ends the game without recording a result — disconnects are treated as abandoned games.

---

## **Message Reference**

Messages consist of a command verb followed by optional parameters, terminated by CRLF (`\r\n`). Fields are delimited by single spaces. All command verbs are uppercase.

---

### **HELO**

*Client → Matchmaking Server*

Initiates or resumes a session. On first connect, includes only the protocol version. On reconnect, includes the client's existing CID so the server can reuse it.

`HELO <version>` — first connection  
`HELO <version> <client-id>` — reconnection

---

### **SESS**

*Matchmaking Server → Client*

Confirms session creation or resumption. Returns the protocol version and the assigned or reused client ID.

`SESS <version> <client-id>`

Example: `SESS 1 CID1`

---

### **RCREATE**

*Client → Matchmaking Server*

Creates a new private room. The server responds with a `ROOM` message containing the generated room code.

`RCREATE`

---

### **ROOM**

*Matchmaking Server → Client*

Confirms room creation and provides the 6-letter room code to share with an opponent.

`ROOM <room-code>`

Example: `ROOM XKQZBT`

---

### **RJOIN**

*Client → Matchmaking Server*

Joins a private room by room code.

`RJOIN <room-code>`

---

### **QJOIN**

*Client → Matchmaking Server*

Enters the random matchmaking queue. The client will be paired with the next available player.

`QJOIN`

---

### **WAIT**

*Matchmaking Server → Client*

Acknowledges queue or room entry. The client should wait for a `MATCH` message.

`WAIT`

---

### **MATCH**

*Matchmaking Server → Client*

Notifies both matched players of the Game Server address and the match identifier.

`MATCH <match-id> <game-server-ip> <game-server-port>`

Example: `MATCH M1 127.0.0.1 4243`

---

### **GCON**

*Client → Game Server*

Announces the client's presence on the Game Server to begin a matched game.

`GCON <match-id> <client-id>`

---

### **STRT**

*Game Server → Client*

Signals the start of the match. Identifies which player is Red (moves first) and which is Yellow.

`STRT <match-id> <red-client-id> <yellow-client-id>`

---

### **BOARD**

*Game Server → All Clients*

Broadcasts the current board state. The board is a 42-character string read left-to-right, top-to-bottom: `R` = Red, `Y` = Yellow, `*` = empty.

`BOARD <board-string>`

Example: `BOARD **************R*****************************`

---

### **YOUR_TURN**

*Game Server → Active Client*

Notifies the active player it is their turn and provides the turn time limit in seconds.

`YOUR_TURN <timeout-seconds>`

Example: `YOUR_TURN 45`

---

### **WAIT_TURN**

*Game Server → Waiting Client*

Notifies the waiting player that their opponent is making a move.

`WAIT_TURN`

---

### **INVL**

*Game Server or Matchmaking Server → Client*

Notifies the client that their last action was invalid. Includes a machine-readable reason code.

`INVL <reason>`

Reason codes:

| Reason | Source | Meaning |
|---|---|---|
| `past-column-limits` | Game Server | Column number out of range |
| `column-is-full` | Game Server | Chosen column has no empty slots |
| `bad-gcon` | Game Server | Malformed GCON message |
| `wrong-match-id` | Game Server | Match ID does not match expected |
| `unknown-room-code` | Matchmaking Server | Room code does not exist |
| `room-host-disconnected` | Matchmaking Server | Room host left before match started |
| `expected-helo` | Matchmaking Server | Expected HELO as first message |
| `expected-qjoin-rcreate-rjoin` | Matchmaking Server | Unrecognised routing message |

---

### **OVER**

*Game Server → All Clients*

Signals game over. Format varies by outcome.

`OVER WIN <winner-client-id>` — normal win  
`OVER WIN <winner-client-id> forfeit` — win by opponent timeout  
`OVER DRAW` — board full with no winner  
`OVER FORFEIT timeout` — sent to the player who timed out

---

### **ERR**

*Game Server → All Clients*

Signals an unrecoverable game error. The game is ended.

`ERR <reason>`

Example: `ERR opponent-disconnected`

---

### **RESULT**

*Game Server → Statistics Server*

Sends a completed match result for storage.

`RESULT <match-id> <p1-client-id> <p2-client-id> <winner-client-id|DRAW> <outcome> <p1-moves> <p2-moves> <duration-seconds>`

Example: `RESULT M1 CID1 CID2 CID1 WIN 12 9 47`

---

### **RESULT_OK**

*Statistics Server → Game Server*

Confirms a result was successfully stored.

`RESULT_OK`

---

### **STATS**

*Client → Statistics Server*

Requests statistics for a specific player.

`STATS <client-id>`

---

### **STATS_OK**

*Statistics Server → Client*

Returns the player's statistics as a JSON payload on a single line.

`STATS_OK <json>`

---

### **STATS_NONE**

*Statistics Server → Client*

Indicates the requested player has no recorded history yet.

`STATS_NONE`

---

### **Client-Sent Messages**

| Message | Destination |
|---|---|
| `HELO` | Matchmaking Server |
| `RCREATE` | Matchmaking Server |
| `RJOIN` | Matchmaking Server |
| `QJOIN` | Matchmaking Server |
| `GCON` | Game Server |
| `<column-number>` | Game Server |
| `STATS` | Statistics Server |

### **Server-Sent Messages**

| Message | Sender |
|---|---|
| `SESS` | Matchmaking Server |
| `WAIT` | Matchmaking Server |
| `ROOM` | Matchmaking Server |
| `MATCH` | Matchmaking Server |
| `STRT` | Game Server |
| `BOARD` | Game Server |
| `YOUR_TURN` | Game Server |
| `WAIT_TURN` | Game Server |
| `INVL` | Game Server / Matchmaking Server |
| `ERR` | Game Server |
| `OVER` | Game Server |
| `RESULT` | Game Server |
| `RESULT_OK` | Statistics Server |
| `STATS_OK` | Statistics Server |
| `STATS_NONE` | Statistics Server |

---

## **Communication Scenarios**

### **Scenario 1: Getting into a Game (Random Queue)**

    Client (Lobby)        Matchmaking Server         Game Server
      |                         |                        |
      |-- HELO 1 -------------->|                        |
      |<-- SESS 1 CID1 ---------|                        |
      |                         |                        |
      |-- QJOIN --------------->|                        |
      |<-- WAIT ----------------|                        |
      |                         | (waits for opponent)   |
      |<-- MATCH M1 127.0.0.1 4243 ---|                  |
      |                         |                        |
      |-- GCON M1 CID1 --------------------------------->|
      |<-- STRT M1 CID1 CID2 ----------------------------|

### **Scenario 2: Getting into a Game (Private Room)**

    Client A (Lobby)      Matchmaking Server       Client B (Lobby)
      |                         |                        |
      |-- HELO 1 -------------->|                        |
      |<-- SESS 1 CID1 ---------|                        |
      |-- RCREATE ------------->|                        |
      |<-- ROOM XKQZBT ---------|                        |
      |                         |<------- HELO 1 --------|
      |                         |--- SESS 1 CID2 ------->|
      |                         |<------- RJOIN XKQZBT --|
      |<-- MATCH M1 ... --------|--- MATCH M1 ... ------>|

### **Scenario 3: Making a Move**

    Player 1 (Client)         Game Server         Player 2 (Client)
        |                         |                      |
        |<-- BOARD ************.. |-- BOARD ************.|
        |<-- YOUR_TURN 45 --------|-- WAIT_TURN -------->|
        |                         |                      |
        |-- 3 ------------------->|                      |
        |                         | [Server validates]   |
        |<-- BOARD *****R******.. |-- BOARD *****R***..->|

### **Scenario 4: Winning and Recording Results**

    Client              Game Server          Statistics Server
     |                      |                       |
     |<-- BOARD ... --------|                       |
     |<-- OVER WIN CID1 ----|-- OVER WIN CID1 ----->|
     |                      |                       |
     |                      |-- RESULT M1 CID1 ... >|
     |                      |<-- RESULT_OK ----------|

### **Scenario 5: Turn Timeout**

    Active Player         Game Server         Waiting Player
        |                     |                     |
        |<-- YOUR_TURN 45 ----|-- WAIT_TURN ------->|
        |                     |                     |
        |    [45s elapsed]    |                     |
        |                     |                     |
        |<-- OVER FORFEIT ... |-- OVER WIN CID2 ... >|

### **Scenario 6: Reconnecting to Lobby**

    Client (Lobby)        Matchmaking Server
      |                         |
      | [game just ended]       |
      |                         |
      |-- HELO 1 CID1 --------->|   (sends existing CID)
      |<-- SESS 1 CID1 ---------|   (server reuses it)
      |-- QJOIN --------------->|

---

## **Error and Failure Handling**

### **Matchmaking Server Crash**

If players are already in a game, they will not notice any disruption. New players will be unable to start new games until the server recovers. A standby backup matchmaker should be maintained for high availability.

### **Game Server Crash**

The active game is lost. Clients are disconnected and returned to the lobby on their next action. The result is not recorded.

### **Statistics Server Crash or Unavailability**

The Game Server attempts to report the result once after the game ends. If the Statistics Server is unreachable, the failure is logged and the game ends normally for the players. Stats for that game will not be recorded.

### **Slow or Missing Messages**

The Game Server enforces a **45-second turn timer**. If no move is received before the timer expires, the idle player forfeits, the waiting player is awarded the win, and the result is sent to the Statistics Server.

### **Player Disconnects Mid-Game**

Detected via an empty read on the socket. The game is ended and `ERR opponent-disconnected` is sent to the remaining player. The result is not recorded since the game was not completed legitimately.

### **Dead Socket in Matchmaking Queue or Room**

Detected at the point of pairing using a non-blocking socket check. Dead players are silently removed from the queue or room. Surviving queue players are re-queued; surviving room joiners receive `INVL room-host-disconnected`.

---

## **References**

* Milton Bradley, *Connect Four* (1974). Hasbro.  
* [Wikipedia: Connect Four](https://en.wikipedia.org/wiki/Connect_Four)  
* INFO314 Tic-Tac-Toe RFC Reference Implementation: [https://github.com/info314-26sp/tic-tac-toe](https://github.com/info314-26sp/tic-tac-toe)