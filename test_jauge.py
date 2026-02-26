import time
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

# =========================
# Configuration Modbus
# =========================
PORT = '/dev/ttyUSB0'  # Adapté selon ton adaptateur RS485
BAUDRATE = 9600
UNIT_ID = 1            # Adresse de la jauge

client = ModbusSerialClient(
    port=PORT,
    baudrate=BAUDRATE,
    parity='O',        # parité impaire
    stopbits=1,
    bytesize=8,
    timeout=1
)

if not client.connect():
    print("Impossible de se connecter au Modbus")
    exit(1)


def lire_niveau(flott_id):
    registre = {0: 4, 1: 2}  # Flotteur 0 -> registre 4, Flotteur 1 -> registre 2
    try:
        resp = client.read_input_registers(address=registre[flott_id], count=2, slave=UNIT_ID)
        if resp.isError():
            raise ModbusException(resp)
        # Combine 2 registres 16 bits en 32 bits
        raw = (resp.registers[0] << 16) + resp.registers[1]
        niveau_mm = raw / 65536
        return niveau_mm
    except Exception as e:
        print(f"Erreur lecture flotteur {flott_id} :", e)
        return None

try:
    while True:
        niveau0 = lire_niveau(0)
        niveau1 = lire_niveau(1)

        print(f"Niveau Flotteur 0 : {niveau0:.2f} mm" if niveau0 is not None else "Erreur Flotteur 0")
        print(f"Niveau Flotteur 1 : {niveau1:.2f} mm" if niveau1 is not None else "Erreur Flotteur 1")
        print("-" * 40)

        # Attendre 2 minutes
        time.sleep(120)

except KeyboardInterrupt:
    print("Arrêt du script par l'utilisateur")

finally:
    client.close()
    print("Client Modbus fermé")