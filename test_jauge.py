import asyncio
from pymodbus.client import AsyncModbusSerialClient
import logging

# -------------------------------
# CONFIGURATION
# -------------------------------
PORT = 'COM5'
BAUDRATE = 9600
PARITY = 'O'
STOPBITS = 1
BYTESIZE = 8
TIMEOUT = 0.5

UNIT_IDS = [1]  # Adresses connues uniquement
REGISTRE_FLOTTEUR = {  # Mapping des flotteurs à leurs registres
    0: 0x0000,
    1: 0x0002,
    2: 0x0004
}

# Logging minimal pour voir les erreurs
logging.basicConfig(level=logging.INFO)


# -------------------------------
# FONCTIONS ASYNC
# -------------------------------
async def flush_buffer(client):
    """Vider le buffer série pour éviter les vieux octets"""
    try:
        while True:
            r = await client.protocol.transport.read(256)
            if not r:
                break
    except Exception:
        pass  # ignorer les erreurs de flush


async def lire_flotteur(client, unit_id, flott_id, reg_addr):
    """Lire un registre d'un flotteur de manière asynchrone"""
    try:
        result = await client.read_input_registers(
            address=reg_addr,
            count=2,
            slave=unit_id
        )
        if result and not result.isError() and getattr(result, 'unit', unit_id) == unit_id:
            raw = (result.registers[0] << 16) + result.registers[1]
            value_mm = raw / 65536
            print(f"Flotteur {flott_id} (unité {unit_id}): {value_mm:.2f} mm")
        else:
            print(f"⚠ Flotteur {flott_id} (unité {unit_id}): réponse invalide")
    except Exception as e:
        print(f"⚠ Flotteur {flott_id} (unité {unit_id}): erreur {e}")


async def main():
    client = AsyncModbusSerialClient(
        port=PORT,
        baudrate=BAUDRATE,
        parity=PARITY,
        stopbits=STOPBITS,
        bytesize=BYTESIZE,
        timeout=TIMEOUT
    )

    await client.connect()
   

    try:
        while True:
            tasks = []
            for unit_id in UNIT_IDS:
               # await flush_buffer(client)
                for flott_id, reg_addr in REGISTRE_FLOTTEUR.items():
                    tasks.append(lire_flotteur(client, unit_id, flott_id, reg_addr))
            await asyncio.gather(*tasks)
            await asyncio.sleep(30)  # pause entre les lectures
    except KeyboardInterrupt:
        print("\n⏹ Arrêt du script par l'utilisateur")
    finally:
        client.close()
        print("🔌 Connexion série fermée")


# -------------------------------
# EXECUTION
# -------------------------------
if __name__ == '__main__':
    asyncio.run(main())