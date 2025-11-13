import asyncio
import uuid
import grpc
import tic_tac_toe_pb2 as pb
import tic_tac_toe_pb2_grpc as pb_grpc


# -------------------------------
# Struktur data untuk 1 pertandingan
# -------------------------------
class Match:
    def __init__(self, p1, p2):
        self.id = str(uuid.uuid4())
        self.players = {"X": p1, "O": p2}
        self.board = [""] * 9
        self.next_turn = "X"
        self.status = "ONGOING"

    def index(self, x, y): return x * 3 + y

    def apply_move(self, symbol, x, y):
        if self.status != "ONGOING":
            return False, "Game sudah selesai"
        if self.next_turn != symbol:
            return False, "Bukan giliran kamu"
        idx = self.index(x, y)
        if self.board[idx]:
            return False, "Kotak sudah diisi"
        self.board[idx] = symbol
        self.check_winner()
        if self.status == "ONGOING":
            self.next_turn = "O" if symbol == "X" else "X"
        return True, "OK"

    def check_winner(self):
        lines = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8),
            (0, 3, 6), (1, 4, 7), (2, 5, 8),
            (0, 4, 8), (2, 4, 6)
        ]
        for a, b, c in lines:
            if self.board[a] and self.board[a] == self.board[b] == self.board[c]:
                self.status = f"{self.board[a]}_WON"
                return
        if all(self.board):
            self.status = "DRAW"


# -------------------------------
# Implementasi Servicer gRPC
# -------------------------------
class GameService(pb_grpc.GameServicer):
    def __init__(self):
        self.waiting_player = None  # pemain tunggu
        self.matches = {}

    async def Play(self, request_iterator, context):
        queue = asyncio.Queue()
        player = {"queue": queue, "symbol": None, "match": None, "name": None}
        asyncio.create_task(self.handle_messages(request_iterator, player))

        while True:
            msg = await queue.get()
            if msg is None:
                break
            yield msg

    async def handle_messages(self, requests, player):
        try:
            async for req in requests:
                if req.HasField("join"):
                    player["name"] = req.join.player_name
                    await self.handle_join(player)
                elif req.HasField("move"):
                    await self.handle_move(player, req.move)
        except Exception as e:
            print("Client disconnected:", e)

    async def handle_join(self, player):
        if not self.waiting_player:
            print(f"{player['name']} menunggu lawan...")
            self.waiting_player = player
        else:
            p1 = self.waiting_player
            p2 = player
            self.waiting_player = None
            match = Match(p1, p2)
            self.matches[match.id] = match
            p1["symbol"], p2["symbol"] = "X", "O"
            p1["match"] = p2["match"] = match

            # Kirim info joined ke kedua pemain
            await p1["queue"].put(pb.ServerMessage(joined=pb.Joined(
                match_id=match.id,
                your_symbol="X",
                opponent=p2["name"],
                start_player="X"
            )))
            await p2["queue"].put(pb.ServerMessage(joined=pb.Joined(
                match_id=match.id,
                your_symbol="O",
                opponent=p1["name"],
                start_player="X"
            )))
            print(f"Match {match.id} dimulai: {p1['name']} (X) vs {p2['name']} (O)")

    async def handle_move(self, player, move):
        match = player.get("match")
        if not match:
            await player["queue"].put(pb.ServerMessage(err=pb.Error(message="Belum masuk match")))
            return

        ok, msg = match.apply_move(player["symbol"], move.x, move.y)
        if not ok:
            await player["queue"].put(pb.ServerMessage(err=pb.Error(message=msg)))
            return

        # kirim status ke kedua pemain
        state = pb.ServerMessage(state=pb.GameState(
            match_id=match.id,
            board=match.board,
            next_turn=match.next_turn,
            status=match.status
        ))
        for p in match.players.values():
            await p["queue"].put(state)


# -------------------------------
# Fungsi utama menjalankan server
# -------------------------------
async def serve():
    server = grpc.aio.server()
    pb_grpc.add_GameServicer_to_server(GameService(), server)
    server.add_insecure_port("[::]:50052")  # bisa diakses lewat localhost atau IP LAN
    print("Server gRPC TicTacToe berjalan di 0.0.0.0:50051 (localhost dan LAN)...")
    await server.start()
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
