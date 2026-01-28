import pyvisa
import asyncio
import warnings
import numpy as np
import matplotlib.pyplot as plt

# Configuration
NUM_POINTS = 601  # Number of points to capture per trace (max 10000 for TBS1000C)
NUM_TRACES = 20  # Number of traces to capture
TRIGGER_CHANNEL = 2  # Trigger on channel 2
TRIGGER_LEVEL = 1.5  # Trigger level in volts
TRIGGER_SLOPE = 'RISE'  # Trigger on rising edge ('RISE' or 'FALL')

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

        # Set timeout (in milliseconds) - reduce for faster operations
        scope.timeout = 2000

        # Disable headers in responses for faster parsing
        scope.write('HEADer OFF')

        # Query identification
        idn = scope.query('*IDN?')
        print(f"Connected to: {idn.strip()}")

        return scope

    except Exception as e:
        print(f"Error connecting to oscilloscope: {e}")
        return None


def wait_for_trigger(scope, timeout=10):
    """
    Wait for the oscilloscope to trigger and acquire data

    Args:
        scope: PyVISA instrument object
        timeout: Maximum time to wait in seconds

    Returns:
        True if triggered, False if timeout
    """
    import time

    # Start acquisition (single sequence)
    scope.write('ACQuire:STATE RUN')
    scope.write('ACQuire:STOPAfter SEQUENCE')

    # Wait for trigger and acquisition to complete
    start_time = time.time()
    while time.time() - start_time < timeout:
        # Check if acquisition is complete
        state = scope.query('ACQuire:STATE?').strip()
        if state == '0':  # Acquisition stopped (triggered and captured)
            return True
        time.sleep(0.01)  # Small delay to avoid hammering the scope

    return False


def get_waveform(scope, channel=1, num_points=None, preamble_cache=None):
    """
    Get waveform data from the oscilloscope

    Args:
        scope: PyVISA instrument object
        channel: Channel number (1-4)
        num_points: Number of points to capture (None=all available, or specify value like 1000, 2500, 10000)
        preamble_cache: Cached preamble data to skip re-querying (for speed)

    Returns:
        time_data: numpy array of time values
        voltage_data: numpy array of voltage values
        preamble_data: dict with preamble info (for caching)
    """
    try:
        # Only set data parameters if not already set (first call)
        if preamble_cache is None:
            # Set data source to the specified channel
            scope.write(f'DATa:SOUrce CH{channel}')

            # Set record length if specified
            if num_points is not None:
                scope.write(f'DATa:STARt 1')
                scope.write(f'DATa:STOP {num_points}')
            else:
                # Get all available points
                scope.write('DATa:STARt 1')
                scope.write('DATa:STOP 10000')  # Max available on TBS1000C

            # Set data encoding to binary
            scope.write('DATa:ENCdg RPBinary')

            # Set data width to 2 bytes
            scope.write('DATa:WIDth 2')

            # Get waveform preamble (scaling information)
            preamble = scope.query('WFMOutpre?').split(';')
        else:
            preamble = preamble_cache

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

        return time_data, voltage_data, preamble

    except Exception as e:
        print(f"Error getting waveform: {e}")
        return None, None, None


def setup_trigger(scope, channel, level, slope='RISE'):
    """
    Setup edge trigger on specified channel

    Args:
        scope: PyVISA instrument object
        channel: Channel number to trigger on (1-4)
        level: Trigger level in volts
        slope: Trigger slope ('RISE' or 'FALL')
    """
    try:
        # Set trigger type to edge
        scope.write('TRIGger:A:TYPE EDGE')

        # Set trigger source
        scope.write(f'TRIGger:A:EDGE:SOUrce CH{channel}')

        # Set trigger level
        scope.write(f'TRIGger:A:LEVel:CH{channel} {level}')

        # Set trigger slope
        scope.write(f'TRIGger:A:EDGE:SLOpe {slope}')

        # Set trigger mode to normal (wait for trigger)
        scope.write('TRIGger:A:MODe NORMAL')

        print(f"Trigger set: CH{channel}, {level}V, {slope} edge")

    except Exception as e:
        print(f"Error setting up trigger: {e}")


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

        # Setup trigger
        setup_trigger(scope, TRIGGER_CHANNEL, TRIGGER_LEVEL, TRIGGER_SLOPE)

        # Step 1: Capture all traces (each trace waits for a trigger)
        print(f"\nCapturing {NUM_TRACES} traces from CH1 ({NUM_POINTS} points each)...")
        print(f"Waiting for trigger on CH{TRIGGER_CHANNEL} at {TRIGGER_LEVEL}V {TRIGGER_SLOPE}...")

        all_traces = []
        time_data = None
        preamble_cache = None  # Cache preamble to avoid re-querying

        import time
        start_time = time.time()

        for i in range(NUM_TRACES):
            # Wait for trigger event
            if wait_for_trigger(scope, timeout=30):
                # Get waveform from channel 1 (use cached preamble after first capture)
                t_data, v_data, preamble = get_waveform(scope, channel=1, num_points=NUM_POINTS, preamble_cache=preamble_cache)

                if t_data is not None and v_data is not None:
                    if time_data is None:
                        time_data = t_data  # Store time data once (same for all traces)
                        preamble_cache = preamble  # Cache preamble for subsequent captures
                    all_traces.append(v_data)

                    # Print progress every 10 traces
                    if (i + 1) % 10 == 0:
                        elapsed = time.time() - start_time
                        rate = (i + 1) / elapsed
                        print(f"Progress: {i + 1}/{NUM_TRACES} traces ({rate:.1f} traces/sec)")
                else:
                    print(f"Error capturing trace {i + 1}")
                    break
            else:
                print(f"Timeout! No trigger received for trace {i + 1}")
                break

        elapsed = time.time() - start_time
        print(f"\nCapture took {elapsed:.2f} seconds ({len(all_traces)/elapsed:.1f} traces/sec)")

        print(f"\nCapture complete! Successfully captured {len(all_traces)} traces")

        # Step 2: Save the data
        if len(all_traces) > 0 and time_data is not None:
            # Convert to numpy array for easier handling
            traces_array = np.array(all_traces)
            print(f"Data shape: {traces_array.shape} (traces x points)")

            # Save to file
            np.savez('oscilloscope_traces.npz', time=time_data, traces=traces_array)
            print("Data saved to 'oscilloscope_traces.npz'")

            # Step 3: Plot all traces overlaid
            print("\nPlotting all traces...")
            plt.figure(figsize=(12, 8))
            for i, voltage_data in enumerate(all_traces):
                plt.plot(time_data * 1e6, voltage_data, alpha=0.3, linewidth=0.5)

            plt.xlabel('Time (µs)')
            plt.ylabel('Voltage (V)')
            plt.title(f'{len(all_traces)} Overlaid Oscilloscope Traces - Channel 1')
            plt.grid(True)
            plt.show()
        else:
            print("No traces captured successfully")

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
