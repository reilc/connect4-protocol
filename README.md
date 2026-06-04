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
            /                                  \\
    Matchmaking Request                Paired match handed
          /                               to game server
         /                                       \\
    +------------------+                   +------------------+     Game results
    |    Game Lobby    |                   |    Game Server   |------------------>
    | Statistics Server|                   |                  |
    |  (Player Client) |                   |                  |
    +------------------+                   +------------------+
            \\                                  /
           Redirected                         /
          to find opp                       /
               \\                         /
                +-----------------------+

The system follows a sequential lifecycle: players interact with the Game Lobby, which communicates with the Matchmaking Server to find opponents via random queue or room code. Once matched, the Matchmaking Server hands the connection off to a Game Server, which acts as the sole referee for the match. When the game concludes, the Game Server pushes results to the Statistics Server.

---

## **Component Specifications**

### **Game Lobby / Player Client**

**Responsibilities:**

* Allow users to join rooms via room code, enter random matchmaking, make moves, and view the board.

**State Stored/Managed:**

* Current username / user ID, current room code, current match ID, local copy of the board, connection status.

**Messages:**

* *Sends:* Matchmaking requests, move requests.  
* *Receives:* Match-found messages, board updates, invalid move responses, game-over messages.

**Important Logic:**

* The client performs no game logic and does not determine move legality. It only displays state and forwards user actions to the appropriate server.

---

### **Matchmaking Server**

**Responsibilities:**

* Pair players together through room code or random queue, then hand them off to a Game Server.

**State Stored/Managed:**

* Waiting players, active room codes, player connection status, created match IDs.

**Messages:**

* *Sends:* Game start information to the Game Server; room/match details to clients.  
* *Receives:* Requests to join or create a room; random queue requests.

**Important Logic:**

* Checks for existing rooms, detects when a second player joins, and determines when a match should be created and handed off.

---

### **Game Server**

**Responsibilities:**

* Run and manage the actual Connect 4 match; serve as the official source of truth for the board.

**State Stored/Managed:**

* Board state, player turn, player IDs, match ID, move history, game status.

**Messages:**

* *Sends:* Board updates, turn updates, invalid move notices, game-over messages; final results to the Statistics Server.  
* *Receives:* Player moves from clients.

**Important Logic:**

* Validates moves, detects wins and draws, prevents out-of-turn play, manages a server-side turn timer, and handles disconnections.

---

### **Statistics Server**

**Responsibilities:**

* Store and organize information about completed games.

**State Stored/Managed:**

* Player win/loss records, match history, game duration, winner, loser, or draw result.

**Messages:**

* *Sends:* Player statistics to the lobby/client when requested.  
* *Receives:* Completed game results from the Game Server.

**Important Logic:**

* Updates player stats after each game. Operates independently from the live game servers. The Game Server queues results for delivery; if the Statistics Server is temporarily unavailable, results are held in the queue and sent once it recovers.

---

## **Detailed Description**

### **Description of Terms**

**Server:** A process acting as the arbiter of game state. This protocol uses multiple servers (Matchmaking, Game, Statistics); each is referred to by its role where context requires disambiguation.

**Client:** A process representing a player in the game (the Game Lobby).

**Session Identifier:** A unique string of non-whitespace ASCII characters (max 80 characters) assigned by the server to identify a client's connection.

**Match Identifier:** A unique string of non-whitespace ASCII characters (max 80 characters) identifying a specific game instance.

**Room Code:** A short, human-readable code used to allow two specific players to join a private game.

---

### **TCP-Based Service**

The Connect 4 protocol is a connection-based application running over TCP. The Matchmaking Server listens on **TCP port 4242**. The Game Server listens on a dynamically assigned port communicated to clients by the Matchmaking Server at match start.

Once a connection is established, a session is considered active until either the client or server closes it. Either party may initiate message sending in a fully-duplexed fashion.

A Connect 4 URL is denoted using the scheme `c4tcp:` followed by host and optional port. For example: `c4tcp://localhost` references the Matchmaking Server on the local machine on the default port. `c4tcp://localhost:4243` specifies an alternate port.

---

### **Session**

A client must establish a session with the Matchmaking Server before any game can begin. The client sends a `HELO` message with the protocol version and a self-chosen client identifier (e.g., a username or UUID). The server responds with a `SESS` message containing the protocol version and a unique session identifier.

---

### **Matchmaking**

Once in a session, a client may either:

* **Create a private room** using `CREA`, receiving a room code to share with another player.  
* **Join a private room** using `JOIN` with a known room code.  
* **Enter the random queue** using `QJOIN`, which pairs the client with the next available player.

When two players are paired, the Matchmaking Server notifies both clients of the Game Server address and match ID, then hands the connection off. Clients connect to the Game Server independently using a `GCON` message.

---

### **Getting into a Game**

1. Client sends `HELO` to Matchmaking Server → Server responds with `SESS`.  
2. Client sends `CREA` or `QJOIN` → Server pairs players.  
3. Server sends `MATCH` (with Game Server address and match ID) to both clients.  
4. Both clients send `GCON` to the Game Server to begin the match.  
5. Game Server sends `STRT` to both clients indicating who moves first.

---

### **Making a Move**

1. The active player's client sends `MOVE` with the column number (1–7) to the Game Server.  
2. The Game Server validates the move.  
3. If valid: the server updates the board and sends a `BORD` message to both clients reflecting the new state, followed by a `YRMV` message indicating the next player's turn.  
4. If invalid: the server sends an `INVL` message to the offending client; the board state is unchanged.

---

### **Winning and Recording Results**

1. After a successful move, the Game Server checks for a winning condition.  
2. If four-in-a-row is detected, the server sends a `TERM` message to both clients declaring the winner.  
3. The Game Server sends a `SAVE` message to the Statistics Server with the match result.  
4. The Statistics Server responds with `ACKD` once the result is recorded.  
5. Both clients are sent a `LBYE` message directing them back to the lobby.

---

### **Turn Timeout**

The Game Server runs a **45-second server-side turn timer** beginning the moment a player's turn starts. If the timer expires before a move is received, the server treats the idle player as having forfeited. The waiting player is awarded the win, a `TERM` message is sent to both clients, and the result is recorded with the Statistics Server.

---

### **Crash and Disconnection Handling**

If a client disconnects unexpectedly mid-game (detected via lost TCP connection or missed heartbeat), the Game Server:

1. Declares the remaining connected player the winner by default.  
2. Sends a `TERM` message to the remaining client noting the opponent's disconnection.  
3. Logs the result (including the disconnect) to the Statistics Server.

---

## **Message Reference**

Messages consist of a 4-letter ASCII command phrase followed by optional parameters, terminated by CRLF (`\r\n`). Fields are delimited by whitespace (space or tab); multiple whitespace characters are treated as a single delimiter. All command headers are case-insensitive; uppercase is recommended for consistency.

---

### **HELO**

*Client → Matchmaking Server*

Initiates a session. Includes the protocol version and the client's chosen identifier.

`HELO <version> <client-id>`

Example: `HELO 1 alice@example.com`

---

### **SESS**

*Matchmaking Server → Client*

Confirms session creation. Includes the agreed protocol version and the server-assigned session identifier.

`SESS <version> <session-id>`

Example: `SESS 1 0cb8d694-3999-4bc6-8351-0e978b62a08d`

---

### **CREA**

*Client → Matchmaking Server*

Creates a new private room. The server responds with a `ROOM` message containing the generated room code.

`CREA <client-id>`

---

### **ROOM**

*Matchmaking Server → Client*

Confirms room creation and provides the room code to share with an opponent.

`ROOM <room-code>`

---

### **JOIN**

*Client → Matchmaking Server*

Joins a private room by room code.

`JOIN <client-id> <room-code>`

---

### **QJOIN**

*Client → Matchmaking Server*

Enters the random matchmaking queue.

`QJOIN <client-id>`

---

### **MATCH**

*Matchmaking Server → Client*

Notifies both matched players of the Game Server address and the match identifier.

`MATCH <match-id> <game-server-ip> <game-server-port>`

---

### **GCON**

*Client → Game Server*

Announces the client's presence on the Game Server to begin a matched game.

`GCON <match-id> <client-id>`

---

### **STRT**

*Game Server → Client*

Signals the start of the match. Identifies which player moves first (Red) and which is second (Yellow).

`STRT <match-id> <red-client-id> <yellow-client-id>`

---

### **MOVE**

*Client → Game Server*

Submits a move. The column parameter is an integer from 1 (leftmost) to 7 (rightmost).

`MOVE <match-id> <client-id> <column>`

---

### **BORD**

*Game Server → Client*

Broadcasts the current board state. The board is represented as a 42-character linear string, read left-to-right, top-to-bottom, where `R` \= Red, `Y` \= Yellow, and `*` \= empty.

`BORD <match-id> <red-client-id> <yellow-client-id> <next-to-move-client-id> |<board-string>|`

Example: `BORD M1 CID1 CID2 CID2 |*|*|*|*|*|*|*|...|R|...|`

---

### **YRMV**

*Game Server → All Clients*

Notifies all clients whose turn it is. The Game Server will not accept `MOVE` commands from any client other than the one named here.

`YRMV <match-id> <client-id>`

---

### **INVL**

*Game Server → Client*

Notifies the active player that their submitted move was illegal. The board state is unchanged.

`INVL <match-id> <reason>`

---

### **TERM**

*Game Server → All Clients*

Signals game over. Includes the match ID and the winning client's ID. For draws, no client ID is sent. For forfeits or disconnects, a reason string follows.

`TERM <match-id> [<winner-client-id>] [<reason>] KTHXBYE`

Examples:

* Win: `TERM M1 CID1 KTHXBYE`  
* Draw: `TERM M1 KTHXBYE`  
* Forfeit: `TERM M1 CID1 DISCONNECT KTHXBYE`

---

### **SAVE**

*Game Server → Statistics Server*

Sends a completed match result for storage.

`SAVE <match-id> <winner-client-id|DRAW> <loser-client-id|DRAW> <duration-seconds> <reason>`

---

### **ACKD**

*Statistics Server → Game Server*

Confirms a result was successfully stored.

`ACKD <match-id>`

---

### **LBYE**

*Game Server → Client*

Directs the client back to the lobby after a game concludes.

`LBYE <match-id>`

---

### **GDBY**

*Client or Server → Counterpart*

Signals the sender is closing the session. If sent by a client currently in a game, it implicitly forfeits that game.

`GDBY`

---

### **STAT**

*Client → Game Server*

Requests the current status of a game.

`STAT <match-id>`

---

### **LIST**

*Client → Statistics Server*

Requests player statistics. With `PLAYER <client-id>`, returns stats for a specific player. With `ALL`, returns all stored records.

`LIST PLAYER <client-id>` or `LIST ALL`

---

### **Client-Sent Messages**

| Message | Destination |
| ----- | ----- |
| `HELO` | Matchmaking Server |
| `CREA` | Matchmaking Server |
| `JOIN` | Matchmaking Server |
| `QJOIN` | Matchmaking Server |
| `GCON` | Game Server |
| `MOVE` | Game Server |
| `STAT` | Game Server |
| `LIST` | Statistics Server |
| `GDBY` | Matchmaking / Game Server |

### **Server-Sent Messages**

| Message | Sender |
| ----- | ----- |
| `SESS` | Matchmaking Server |
| `ROOM` | Matchmaking Server |
| `MATCH` | Matchmaking Server |
| `STRT` | Game Server |
| `BORD` | Game Server |
| `YRMV` | Game Server |
| `INVL` | Game Server |
| `TERM` | Game Server |
| `LBYE` | Game Server |
| `SAVE` | Game Server |
| `ACKD` | Statistics Server |
| `GDBY` | Any |

---

## **Communication Scenarios**

### **Scenario 1: Getting into a Game**

    Client (Lobby)      Matchmaking Server         Game Server
      |                      |                       |
      |-- HELO 1 CID1 ----->|                       |
      |<-- SESS 1 SID1 -----|                       |
      |                      |                       |
      |-- QJOIN CID1 ------>|                       |
      |                      | (waits for opponent) |
      |                      |                       |
      |<-- MATCH M1 IP:P ---|                       |
      |                      |                       |
      |-- GCON M1 CID1 --------------------------->|
      |                      |                       |
      |<-- STRT M1 CID1 CID2 ---------------------|

### **Scenario 2: Making a Move**

    Player 1 (Client)       Game Server       Player 2 (Client)
        |                     |                    |
        |-- MOVE M1 CID1 3 ->|                    |
        |                     | [Server validates] |
        |<-- BORD M1 ... ----|-- BORD M1 ... ---->|
        |<-- YRMV M1 CID2 ---|-- YRMV M1 CID2 -->|

### **Scenario 3: Winning and Saving Results**

    Client              Game Server          Statistics Server
     |                      |                       |
     |<-- TERM M1 CID1 -----|                       |
     |                      |-- SAVE M1 CID1 ----->|
     |                      |<-- ACKD M1 ----------|
     |<-- LBYE M1 ----------|                       |

        

### **Scenario 4: Handling a Disconnect**

    Client (Player A)      Game Server       Statistics Server
        |                     |                    |
        |                     | [P2 connection lost]
        |<-- TERM M1 CID1 DISCONNECT KTHXBYE ----|
        |                     |                    |
        |                     |-- SAVE M1 CID1 DISCONNECT -->|
        |                     |<-- ACKD M1 --------|
        |<-- LBYE M1 --------|                    |

---

## **Error and Failure Handling**

### **Matchmaking Server Crash**

If players are already in a game, they will not notice any disruption. New players will be unable to start new games until the server recovers. A standby backup matchmaker should be maintained for high availability.

### **Game Server Crash**

The active game is lost. Clients receive a `TERM` message indicating server failure and are redirected back to the lobby. The result may not be fully recorded.

### **Statistics Server Crash**

The Game Server queues results locally. Once the Statistics Server comes back online, the Game Server retries delivery of all queued results in order.

### **Slow or Missing Messages**

The Game Server enforces a **45-second turn timer**. If no move is received before the timer expires, the idle player forfeits, the waiting player is awarded the win, and the result is sent to the Statistics Server.

---

## **References**

* Milton Bradley, *Connect Four* (1974). Hasbro.  
* [Wikipedia: Connect Four](https://en.wikipedia.org/wiki/Connect_Four)  
* INFO314 Tic-Tac-Toe RFC Reference Implementation: [https://github.com/info314-26sp/tic-tac-toe](https://github.com/info314-26sp/tic-tac-toe)

