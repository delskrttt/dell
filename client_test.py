import asyncio
import grpc
import tic_tac_toe_pb2 as pb
import tic_tac_toe_pb2_grpc as pb_grpc


# -------------------------------------------------
#  Fungsi kirim pesan client -> server (stream)
# -------------------------------------------------
async def send_messages(stream, player_name, match_id_container):
    print(f"\nMengirim JOIN sebagai '{player_name}' ...\n")
    await stream.write(pb.ClientMessage(join=pb.Join(player_name=player_name)))

    while True:
        cmd = input("Masukkan perintah (MOVE x y / EXIT): ").strip().lower()

        if cmd == "exit":
            print("Keluar dari game...")
            await stream.done_writing()
            return

        if cmd.startswith("move"):
            parts = cmd.split()
            if len(parts) != 3:
                print("Format salah! Gunakan: move x y")
                continue

            x = int(parts[1])
            y = int(parts[2])

            if match_id_container["id"] is None:
                print("❌ Belum dapat MATCH ID dari server!")
                continue

            await stream.write(pb.ClientMessage(
                move=pb.Move(
                    match_id=match_id_container["id"],
                    x=x,
                    y=y
                )
            ))
            print(f"Move terkirim: ({x}, {y})")


# -------------------------------------------------
#  Fungsi terima pesan server -> client (stream)
# -------------------------------------------------
async def receive_messages(stream, match_id_container):
    async for msg in stream:
        if msg.HasField("joined"):
            j = msg.joined
            match_id_container["id"] = j.match_id
            print("\n=== MATCH DIMULAI ===")
            print(f"Match ID      : {j.match_id}")
            print(f"Simbol kamu   : {j.your_symbol}")
            print(f"Lawan         : {j.opponent}")
            print(f"Mulai oleh    : {j.start_player}")
            print("======================\n")

        elif msg.HasField("state"):
            s = msg.state
            print("\n=== UPDATE GAME ===")
            print("Board:", s.board)
            print("Next Turn:", s.next_turn)
            print("Status:", s.status)
            print("====================\n")

        elif msg.HasField("err"):
            print("\n❌ ERROR:", msg.err.message, "\n")


# -------------------------------------------------
#  Main: Menjalankan client
# -------------------------------------------------
async def main():
    print("Pilih Mode:")
    print("1. Player A")
    print("2. Player B")
    p = input("Masukkan pilihan: ")

    if p == "1":
        name = "PlayerA"
    elif p == "2":
        name = "PlayerB"
    else:
        print("Pilihan salah.")
        return

    # Konfigurasi alamat server
    server_address = "localhost:50052"

    async with grpc.aio.insecure_channel(server_address) as channel:
        stub = pb_grpc.GameStub(channel)

        match_id_container = {"id": None}

        # Membuat stream dua arah
        stream = stub.Play()

        # Jalankan sender dan receiver bersamaan
        sender = asyncio.create_task(send_messages(stream, name, match_id_container))
        receiver = asyncio.create_task(receive_messages(stream, match_id_container))

        await asyncio.wait([sender, receiver], return_when=asyncio.FIRST_COMPLETED)


if __name__ == "__main__":
    asyncio.run(main())

