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

    def index(self, x, y): 
        return x * 3 + y

    def apply_move(self, symbol, x, y):
        if self.status != "ONGOING":
            return False, "Game sudah selesai"
        if self.next_turn != symbol:
            return False, "Bukan giliran kamu"

        idx = self.index(x, y)
        if not (0 <= x < 3 and 0 <= y < 3):
            return False, "Koordinat di luar batas (0-2)"

        if self.board[idx]:
            return False, "Kotak sudah diisi"

        self.board[idx] = symbol
        self.check_winner()

        if self.status == "ONGOING":
            # Ganti giliran ke simbol lawan
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
                # Status pemenang, misalnya "X_WON" atau "O_WON"
                self.status = f"{self.board[a]}_WON"
                return

        # Cek DRAW jika semua kotak terisi dan belum ada pemenang
        if all(self.board) and self.status == "ONGOING":
            self.status = "DRAW"


# -------------------------------
# Implementasi Servicer gRPC
# -------------------------------
class GameService(pb_grpc.GameServicer):
    def __init__(self):
        self.waiting_player = None
        self.matches = {}

    async def Play(self, request_iterator, context):
        queue = asyncio.Queue()
        # Inisialisasi player, termasuk referensi ke match, agar mudah dibersihkan
        player = {"queue": queue, "symbol": None, "match": None, "name": None}

        # Jalankan task untuk menerima pesan dari client secara asinkron
        recv_task = asyncio.create_task(self.handle_messages(request_iterator, player))

        try:
            while True:
                # Tunggu pesan untuk dikirim kembali ke client
                msg = await queue.get()
                if msg is None:
                    # Sinyal untuk mengakhiri stream ke client
                    break
                yield msg
        finally:
            # Pastikan task penerima di-cancel saat loop pengiriman selesai atau terputus
            recv_task.cancel()
            await self.handle_disconnect(player)

    async def handle_messages(self, requests, player):
        try:
            async for req in requests:
                if req.HasField("join"):
                    player["name"] = req.join.player_name
                    await self.handle_join(player)
                elif req.HasField("move"):
                    await self.handle_move(player, req.move)
        except grpc.aio.AioRpcError:
            # Terjadi error RPC (koneksi terputus)
            print(f"Client {player['name']} disconnected via RPC error.")
        except Exception as e:
            print(f"Error handling client {player['name']}: {e}")
        finally:
            # Posisikan None di queue untuk mengakhiri loop pengiriman di Play()
            await player["queue"].put(None)

    async def handle_disconnect(self, player):
        print(f"Cleaning up resources for {player['name']}...")
        match = player.get("match")
        
        # Hapus pemain dari daftar tunggu jika dia belum menemukan lawan
        if self.waiting_player == player:
            self.waiting_player = None
            print(f"Removed {player['name']} from waiting list.")
            return

        # Jika player berada di match
        if match and match.id in self.matches:
            # Beri tahu lawan bahwa game berakhir (jika belum berakhir)
            if match.status == "ONGOING":
                match.status = "ABORTED"
                opponent_symbol = "O" if player["symbol"] == "X" else "X"
                opponent = match.players[opponent_symbol]
                
                # Kirim pesan error ke lawan
                await opponent["queue"].put(pb.ServerMessage(err=pb.Error(
                    message=f"Lawan ({player['name']}) terputus. Game ABORTED."
                )))
                
                # Sinyal lawan untuk mengakhiri stream-nya juga
                await opponent["queue"].put(None) 
            
            # Hapus match dari daftar match aktif
            del self.matches[match.id]
            print(f"Match {match.id} cleaned up.")
            
    async def handle_join(self, player):
        # ... (Kode handle_join tetap sama)
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

        # Buat pesan State Game
        state_msg = pb.ServerMessage(state=pb.GameState(
            match_id=match.id,
            board=match.board,
            next_turn=match.next_turn,
            status=match.status
        ))

        # Kirim pesan State Game ke kedua pemain
        for p in match.players.values():
            await p["queue"].put(state_msg)


# -------------------------------
# Fungsi utama menjalankan server
# -------------------------------
async def serve():
    server = grpc.aio.server()
    pb_grpc.add_GameServicer_to_server(GameService(), server)

    # Memilih port 50051 (dari 9237179)
    server.add_insecure_port("[::]:50051")
    print("Server gRPC TicTacToe berjalan di 0.0.0.0:50051 (localhost dan LAN)...")

    await server.start()
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())