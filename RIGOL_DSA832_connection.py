import pyvisa
import numpy as np
import time
import matplotlib
# Set backend - try interactive first, fallback to Agg (file-based)
try:
    import tkinter
    matplotlib.use('TkAgg')
    print("Using TkAgg backend for interactive display")
except ImportError:
    try:
        matplotlib.use('Qt5Agg')
        print("Using Qt5Agg backend for interactive display")
    except:
        # Use Agg backend which works without GUI (saves to file)
        matplotlib.use('Agg')
        print("Using Agg backend (non-interactive - plot will be saved to file)")
        print("To enable interactive plots, install tkinter: sudo apt-get install python3-tk")
import matplotlib.pyplot as plt

# ============================================================================
# CONFIGURATION VARIABLES - Modify these to configure the spectrum analyzer
# ============================================================================

# TCP/IP VISA address of the spectrum analyzer
SCOPE_ADDRESS = "TCPIP::192.168.10.2::INSTR"

# Frequency Configuration (in Hz)
# Option 1: Set start and stop frequencies directly
START_FREQ = 2e9  # Set to None to use current instrument setting, or specify in Hz (e.g., 1e6 for 1 MHz)
STOP_FREQ = 3e9   # Set to None to use current instrument setting, or specify in Hz (e.g., 1e9 for 1 GHz)

# Option 2: Set center frequency and span (used if START_FREQ and STOP_FREQ are None)
CENTER_FREQ = None  # Set to None to use current instrument setting, or specify in Hz (e.g., 500e6 for 500 MHz)
SPAN = None         # Set to None to use current instrument setting, or specify in Hz (e.g., 10e6 for 10 MHz)

# Reference Level (in dBm)
REFERENCE_LEVEL = 0  # Set to None to use current instrument setting, or specify in dBm (e.g., -20.0)

# Number of Points
NUM_POINTS = 3001 # Set to None to use current instrument setting, or specify number (101 to 3001, default: 601)

# Trace Mode Configuration
# Set the type/mode of the trace. Options:
#   'WRITe'     - Clear Write: Real-time display, clears and updates with each sweep (default)
#   'MAXHold'   - Max Hold: Displays maximum value from multiple sweeps, updates if new maximum found
#   'MINHold'   - Min Hold: Displays minimum value from multiple sweeps, updates if new minimum found
#   'VIEW'      - View: Freezes current trace data for observation (stops updating)
#   'BLANk'     - Blank: Disables trace display and all measurements for this trace
#   'VIDeoavg'  - Video Average: Logarithmic average of data from multiple sweeps (smoother trace)
#   'POWeravg'  - Power Average: Linear average of data from multiple sweeps (smoother trace)
# Set to None to use current instrument setting
TRACE_MODE = 'MAXHold'  # Example: 'MAXHold' for max hold, 'WRITe' for clear write

# Trace Number (which trace to configure and acquire)
TRACE_NUMBER = 1  # 1, 2, or 3 (Trace 4 is math trace, cannot be set directly)

# Max Hold Wait Time (in seconds)
# When TRACE_MODE is set to 'MAXHold', this specifies how long to wait after setting max hold
# before acquiring the trace. This allows multiple sweeps to accumulate maximum values.
MAX_HOLD_WAIT_TIME = 10  # Wait time in seconds (default: 10 seconds)

# ============================================================================

# Use pyvisa-py backend
rm = pyvisa.ResourceManager('@py')

scope = None
try:
    # Open the instrument at the given IP address
    scope = rm.open_resource(SCOPE_ADDRESS)
    scope.timeout = 30000  # 30 s timeout for trace data transfer
    
    # Simple identification query to verify the connection
    print("Connected to:", scope.query('*IDN?').strip())
    
    # Configure frequency settings if specified
    if START_FREQ is not None and STOP_FREQ is not None:
        print(f"Setting frequency range: {START_FREQ/1e6:.3f} MHz to {STOP_FREQ/1e6:.3f} MHz")
        scope.write(f':FREQuency:STARt {START_FREQ}')
        scope.write(f':FREQuency:STOP {STOP_FREQ}')
    elif CENTER_FREQ is not None and SPAN is not None:
        print(f"Setting center frequency: {CENTER_FREQ/1e6:.3f} MHz, span: {SPAN/1e6:.3f} MHz")
        scope.write(f':FREQuency:CENTer {CENTER_FREQ}')
        scope.write(f':FREQuency:SPAN {SPAN}')
    
    # Configure reference level if specified
    if REFERENCE_LEVEL is not None:
        print(f"Setting reference level: {REFERENCE_LEVEL} dBm")
        scope.write(f':DISPlay:WINdow:TRACe:Y:SCALe:RLEVel {REFERENCE_LEVEL}')
    
    # Configure number of points if specified
    if NUM_POINTS is not None:
        if 101 <= NUM_POINTS <= 3001:
            print(f"Setting number of points: {NUM_POINTS}")
            scope.write(f':SWEep:POINts {NUM_POINTS}')
        else:
            print(f"Warning: NUM_POINTS ({NUM_POINTS}) is out of range (101-3001). Using current instrument setting.")
    
    # Configure trace mode if specified
    if TRACE_MODE is not None:
        valid_modes = ['WRITe', 'MAXHold', 'MINHold', 'VIEW', 'BLANk', 'VIDeoavg', 'POWeravg']
        if TRACE_MODE in valid_modes:
            print(f"Setting trace {TRACE_NUMBER} mode: {TRACE_MODE}")
            scope.write(f':TRACe{TRACE_NUMBER}:MODE {TRACE_MODE}')
            
            # If max hold or min hold is selected, wait for accumulation
            if TRACE_MODE in ['MAXHold', 'MINHold']:
                print(f"Enabling continuous sweep for {MAX_HOLD_WAIT_TIME} seconds to accumulate {TRACE_MODE} data...")
                scope.write(':INIT:CONT ON')  # Enable continuous sweep for accumulation
                time.sleep(MAX_HOLD_WAIT_TIME)  # Wait for sweeps to accumulate
                print(f"Wait complete. Stopping continuous sweep...")
                scope.write(':INIT:CONT OFF')  # Stop continuous sweep
        else:
            print(f"Warning: TRACE_MODE '{TRACE_MODE}' is invalid. Valid options: {valid_modes}")
            print("Using current instrument setting.")
    
    # Set trace data format to ASCII for easier parsing
    scope.write(':FORMat:TRACe:DATA ASCii')
    
    # Start sweep (only if not already handled by max/min hold logic above)
    if TRACE_MODE not in ['MAXHold', 'MINHold']:
        print("Starting single sweep...")
        scope.write(':INIT:CONT OFF')  # Stop continuous sweep
        scope.write(':INIT')  # Start a single sweep
        scope.write('*WAI')  # Wait for operation to complete
    
    # Get frequency parameters for X-axis
    try:
        start_freq = float(scope.query(':FREQuency:STARt?'))
        stop_freq = float(scope.query(':FREQuency:STOP?'))
    except Exception as e:
        print(f"Warning: Could not get start/stop frequency: {e}")
        print("Trying center/span format...")
        try:
            center_freq = float(scope.query(':FREQuency:CENTer?'))
            span = float(scope.query(':FREQuency:SPAN?'))
            start_freq = center_freq - span/2
            stop_freq = center_freq + span/2
        except Exception as e2:
            print(f"Error getting frequency parameters: {e2}")
            raise
    
    # Get number of points
    try:
        num_points = int(scope.query(':SWEep:POINts?'))
    except Exception as e:
        print(f"Warning: Could not get number of points: {e}")
        num_points = 601  # Default for DSA832E
    
    print(f"Frequency range: {start_freq/1e6:.3f} MHz to {stop_freq/1e6:.3f} MHz")
    print(f"Number of points: {num_points}")
    
    # Acquire trace data from specified trace
    trace_label = f'TRACE{TRACE_NUMBER}'
    print(f"Acquiring trace data from {trace_label}...")
    trace_data = scope.query(f':TRACe:DATA? {trace_label}')
    
    # Parse trace data
    # Format: #<n><length><data> or comma-separated ASCII
    trace_str = trace_data.strip()
    
    # Handle binary format header if present
    if trace_str.startswith('#'):
        # Binary format header - skip it
        # Format: #<n><length><data>
        # The first digit after # is the number of digits in the length field
        header_digits = int(trace_str[1])
        # Extract the length value
        length_str = trace_str[2:2+header_digits]
        data_length = int(length_str)
        # Skip header: # + 1 digit + length digits
        data_start = 2 + header_digits
        trace_str = trace_str[data_start:].strip()
    
    # Convert to numpy array
    trace_str = trace_str.strip()
    if not trace_str:
        raise ValueError("No trace data received")
    
    # Parse comma-separated values (may have spaces after commas)
    amplitude_values = np.array([float(x.strip()) for x in trace_str.split(',') if x.strip()])
    
    print(f"Parsed {len(amplitude_values)} data points")
    print(f"First few values: {amplitude_values[:5]}")
    print(f"Last few values: {amplitude_values[-5:]}")
    
    # Create frequency array
    frequency_values = np.linspace(start_freq, stop_freq, len(amplitude_values))
    
    # Plot the spectrum
    print("Creating plot...")
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(frequency_values/1e6, amplitude_values, linewidth=1.5)  # Convert Hz to MHz
    ax.set_xlabel('Frequency (MHz)', fontsize=12)
    ax.set_ylabel('Amplitude (dBm)', fontsize=12)
    ax.set_title(f'Spectrum Analyzer Trace - {trace_label}', fontsize=14)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    
    # Save plot to file
    plt.savefig('spectrum_trace.png', dpi=150, bbox_inches='tight')
    print("Plot saved to spectrum_trace.png")
    
    # Try to show plot interactively (only works if GUI backend is available)
    try:
        print("Displaying plot window...")
        plt.show(block=True)
    except Exception as e:
        print(f"Could not display interactive plot: {e}")
        print("Plot has been saved to spectrum_trace.png - please open it to view")
    
    print(f"\nTrace acquired: {len(amplitude_values)} points")
    print(f"Frequency range: {frequency_values[0]/1e6:.6f} to {frequency_values[-1]/1e6:.6f} MHz")
    print(f"Amplitude range: {amplitude_values.min():.3f} to {amplitude_values.max():.3f} dBm")
    
    # Restore continuous sweep mode
    scope.write(':INIT:CONT ON')

except Exception as e:
    print(f"\nError occurred: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
finally:
    if scope is not None:
        scope.close()
        print("Connection closed.")
