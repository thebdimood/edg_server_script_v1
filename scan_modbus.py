from pymodbus import ModbusException
from pymodbus.client import ModbusSerialClient

# Initialiser le client
client = ModbusSerialClient(
    port='COM5',
    baudrate=9600,
    parity='O',
    stopbits=1,
    bytesize=8,
    timeout=0.5
)

if not client.connect():
    print("Impossible de se connecter au port COM5")
    exit(1)

active_addresses = []

# Scanner les adresses 1 à 10
for unit_id in range(1, 11):
    try:
        # Lire un registre existant (ici le registre du premier flotteur = 4)
        result = client.read_input_registers(address=2 ,count=1, slave=unit_id)
        if result and not result.isError():
            active_addresses.append(unit_id)
            print(f"✅ Appareil détecté à l'adresse {unit_id}")
    except ModbusException as e:
        print(f"⚠️ Erreur à l'adresse {unit_id}: {e}")

client.close()

print("\nAdresses détectées :", active_addresses)