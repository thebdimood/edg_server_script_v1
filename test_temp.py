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

UNIT_IDS = [1]  # Adresse(s) du capteur

# Registres des températures (0-4 points)
REGISTRES_TEMP = {
    0: 0x0006,
    1: 0x0007,
    2: 0x0008,
    3: 0x0009,
    4: 0x000A
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


async def lire_temperature(client, unit_id, temp_id, reg_addr):
    """Lire un registre de température"""
    try:
        result = await client.read_input_registers(
            address=reg_addr,
            count=1,
            slave=unit_id
        )
        if result and not result.isError() and getattr(result, 'unit', unit_id) == unit_id:
            raw = result.registers[0]
            # Parsing signé, entier:8 bits, décimal:8 bits
            if raw >= 0x8000:
                raw -= 0x10000  # conversion en signé
            value_c = raw / 256
            print(f"Température {temp_id} (unité {unit_id}): {value_c:.2f} °C")
        else:
            print(f"⚠ Température {temp_id} (unité {unit_id}): réponse invalide")
    except Exception as e:
        print(f"⚠ Température {temp_id} (unité {unit_id}): erreur {e}")


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
                await flush_buffer(client)
                for temp_id, reg_addr in REGISTRES_TEMP.items():
                    tasks.append(lire_temperature(client, unit_id, temp_id, reg_addr))
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