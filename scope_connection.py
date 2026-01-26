import pyvisa

scope = pyvisa.ResourceManager()

available_resources = scope.list_resources()

print("Available instruments:", available_resources)
