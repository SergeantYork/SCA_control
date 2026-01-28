import pyvisa
import asyncio
import warnings
import numpy as np
import matplotlib.pyplot as plt

def connect_to_tektronix():
    """
    Connect to Tektronix TBS 1000C oscilloscope via USB
    """
    try:
        # Create a resource manager
        rm = pyvisa.ResourceManager('@py')

        # List all available instruments
        print("Searching for instruments...")
        resources = rm.list_resources()
        print(f"Found instruments: {resources}")

        # Find Tektronix device (0x0699/1689 is Tektronix vendor ID, 0x03c4/964 is TBS1000C model)
        tek_device = None
        for resource in resources:
            # Check for vendor ID 1689 (0x0699) and model 964 (0x03c4)
            if 'USB' in resource and ('1689' in resource or '0699' in resource.lower()):
                tek_device = resource
                break

        if not tek_device:
            print("Tektronix oscilloscope not found. Trying first USB device...")
            for resource in resources:
                if 'USB' in resource:
                    tek_device = resource
                    break

        if not tek_device:
            print("No USB devices found. Make sure the oscilloscope is connected.")
            return None

        # Connect to the device
        print(f"Connecting to: {tek_device}")
        scope = rm.open_resource(tek_device)

        # Set timeout (in milliseconds)
        scope.timeout = 5000

        # Query identification
        idn = scope.query('*IDN?')
        print(f"Connected to: {idn.strip()}")

        return scope

    except Exception as e:
        print(f"Error connecting to oscilloscope: {e}")
        return None


def get_waveform(scope, channel=1):
    """
    Get waveform data from the oscilloscope

    Args:
        scope: PyVISA instrument object
        channel: Channel number (1-4)

    Returns:
        time_data: numpy array of time values
        voltage_data: numpy array of voltage values
    """
    try:
        # Set data source to the specified channel
        scope.write(f'DATa:SOUrce CH{channel}')

        # Set data encoding to binary
        scope.write('DATa:ENCdg RPBinary')

        # Set data width to 2 bytes
        scope.write('DATa:WIDth 2')

        # Get waveform preamble (scaling information)
        preamble = scope.query('WFMOutpre?').split(';')

        # Extract scaling factors
        # Format: BYT_NR;BIT_NR;ENCDG;BN_FMT;BYT_OR;WFID;NR_PT;PT_FMT;XUNIT;XINCR;XZERO;PT_OFF;YUNIT;YMULT;YOFF;YZERO
        points = int(preamble[6])
        xincr = float(preamble[9])   # Time increment per point
        xzero = float(preamble[10])  # Time of first point
        ymult = float(preamble[13])  # Voltage multiplier
        yoff = float(preamble[14])   # Voltage offset
        yzero = float(preamble[15])  # Voltage zero

        # Get the waveform data
        scope.write('CURVe?')
        raw_data = scope.read_raw()

        # Parse binary data (skip header bytes)
        header_len = 2 + int(chr(raw_data[1]))
        wave_data = raw_data[header_len:-1]

        # Convert to numpy array (16-bit signed integers, big-endian)
        adc_wave = np.frombuffer(wave_data, dtype=np.dtype('>i2'))

        # Convert ADC values to voltage
        voltage_data = ((adc_wave - yoff) * ymult) + yzero

        # Generate time array
        time_data = np.arange(0, points) * xincr + xzero

        return time_data, voltage_data

    except Exception as e:
        print(f"Error getting waveform: {e}")
        return None, None


if __name__ == "__main__":
    # Suppress the asyncio cleanup warning
    warnings.filterwarnings('ignore', category=ResourceWarning)

    # Connect to the oscilloscope
    scope = connect_to_tektronix()

    if scope:
        print("\nConnection successful!")

        # Example: Get current settings
        print(f"Vertical scale CH1: {scope.query('CH1:SCAle?').strip()}")
        print(f"Horizontal scale: {scope.query('HORizontal:SCAle?').strip()}")

        # Get waveform from channel 1
        print("\nCapturing waveform from CH1...")
        time_data, voltage_data = get_waveform(scope, channel=1)

        if time_data is not None and voltage_data is not None:
            print(f"Captured {len(voltage_data)} points")

            # Plot the waveform
            plt.figure(figsize=(10, 6))
            plt.plot(time_data * 1e6, voltage_data)  # Convert time to microseconds
            plt.xlabel('Time (µs)')
            plt.ylabel('Voltage (V)')
            plt.title('Oscilloscope Trace - Channel 1')
            plt.grid(True)
            plt.show()

        # Close connection when done
        scope.close()
        print("\nConnection closed.")

    # Properly close any remaining event loops
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.stop()
        loop.close()
    except:
        pass
