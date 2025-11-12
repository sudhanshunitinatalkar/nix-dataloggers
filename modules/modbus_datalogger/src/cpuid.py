def get_cpuid():
    """
    Gets the Raspberry Pi's CPU serial number as a string.
    
    Reads from /proc/cpuinfo to find the 'Serial' line.
    """
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('Serial'):
                    # The line looks like 'Serial\t\t: 00000000xxxxxxxx'
                    # Split on ':' and take the second part, then strip whitespace
                    cpuid = line.split(':')[1].strip()
                    return cpuid
    except FileNotFoundError:
        # This will happen if not run on a Linux system (like a Pi)
        print("Error: /proc/cpuinfo not found. Are you on a Raspberry Pi?")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    
    # If we get through the file without finding a 'Serial' line
    print("Error: Could not find 'Serial' in /proc/cpuinfo.")
    return None


if __name__ == "__main__":
    print(get_cpuid())