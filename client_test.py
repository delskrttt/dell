import asyncio
import grpc
import tic_tac_toe_pb2 as pb
import tic_tac_toe_pb2_grpc as pb_grpc

# Container untuk menyimpan Match ID yang diterima dari server
match_id_container = {"id": None}

async def request_messages(player_name):
    # Kirim pesan join pertama ke server
    yield pb.ClientMessage(join=pb.Join(player_name=player_name))
    
    # Tunggu input user untuk gerakan berikutnya
    while True:
        # Mengambil input dari user. Menggunakan asyncio.to_thread untuk non-blocking input
        # agar tidak memblokir loop asinkron (fungsi ini meniru behavior input() non-asinkron)
        user_input = await asyncio.to_thread(input, f"[{player_name}] Masukkan perintah (MOVE x y / EXIT): ")
        user_input = user_input.strip().lower()

        if user_input == "exit":
            print("Keluar dari game...")
            break

        if user_input.startswith("move"):
            parts = user_input.split()
            if len(parts) != 3:
                print("Format salah! Gunakan: move x y")
                continue
            
            try:
                x = int(parts[1])
                y = int(parts[2])
            except ValueError:
                print("Koordinat harus berupa angka.")
                continue

            if match_id_container["id"] is None:
                print("❌ Belum dapat MATCH ID dari server! Tunggu konfirmasi JOIN.")
                continue
            
            # Menggunakan match_id yang sudah disimpan di container
            yield pb.ClientMessage(
                move=pb.Move(
                    match_id=match_id_container["id"],
                    x=x,
                    y=y
                )
            )
            print(f"Move terkirim: ({x}, {y})")
        else:
             print("Perintah tidak dikenal. Gunakan MOVE x y atau EXIT.")
    
    # Setelah loop berakhir (karena 'exit'), fungsi generator selesai, 
    # yang akan menutup stream penulisan ke server.

async def play_game():
    # --- Pilihan Player ---
    print("Pilih Mode:")
    print("1. Player A")
    print("2. Player B")
    p = input("Masukkan pilihan: ")

    if p == "1":
        name = "PlayerA"
        server_address = "localhost:50052" # Mengambil dari HEAD
    elif p == "2":
        name = "PlayerB"
        server_address = "localhost:50051" # Menggunakan port default atau yang lain
    else:
        print("Pilihan salah.")
        return

    print(f"\nMenghubungkan ke server {server_address} sebagai '{name}'...\n")

    async with grpc.aio.insecure_channel(server_address) as channel:
        stub = pb_grpc.GameStub(channel)

        # Menerima respon dari server
        async for response in stub.Play(request_messages(name)):
            if response.HasField("joined"):
                j = response.joined
                match_id_container["id"] = j.match_id # Menyimpan Match ID
                print("\n=== MATCH DIMULAI ===")
                print(f"Match ID      : {j.match_id}")
                print(f"Simbol kamu   : {j.your_symbol}")
                print(f"Lawan         : {j.opponent}")
                print(f"Mulai oleh    : {j.start_player}")
                print("======================\n")

            elif response.HasField("state"):
                s = response.state
                print("\n=== UPDATE GAME ===")
                # Mencoba menampilkan board 3x3 (mengambil dari 9237179)
                board = s.board
                if len(board) == 9:
                    print(f"| {board[0]} | {board[1]} | {board[2]} |")
                    print(f"| {board[3]} | {board[4]} | {board[5]} |")
                    print(f"| {board[6]} | {board[7]} | {board[8]} |")
                else:
                    print("Board:", s.board)
                    
                print("Next Turn:", s.next_turn)
                print("Status:", s.status)
                print("====================\n")

            elif response.HasField("err"):
                print("\n❌ ERROR:", response.err.message, "\n")
            
            # Jika game berakhir, kita bisa keluar dari loop asinkron
            if response.HasField("state") and (response.state.status == "WIN" or response.state.status == "DRAW"):
                print("Game berakhir. Keluar.")
                break

async def main():
    try:
        await play_game()
    except grpc.aio.AioRpcError as e:
         print(f"Koneksi gRPC gagal: {e.code().name}. Pastikan server berjalan di alamat yang benar.")
    except Exception as e:
         print(f"Terjadi kesalahan tak terduga: {e}")

if __name__ == "__main__":
    # Karena input() dipanggil di fungsi generator (request_messages), 
    # kita perlu menggunakan mode asinkron yang mendukung I/O blocking.
    # Namun, karena kita menggunakan asyncio.to_thread, kita bisa menjalankan 
    # main() secara normal.
    asyncio.run(main())