"""
Módulo de integración con el ESP32 (Puente LIN para HVAC General/Fujitsu).
Permite la comunicación bidireccional con el firmware C++ que controla
la máquina de conductos a través del transceptor LIN.
"""

class HVACBridge:
    def __init__(self, port='/dev/ttyUSB0', baudrate=19200):
        self.port = port
        self.baudrate = baudrate

    def connect(self):
        pass

    def set_temperature(self, temp: float):
        pass

    def get_status(self) -> dict:
        return {"status": "mock_status"}
