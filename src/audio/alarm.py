"""
Audio alarm functionality for Pomodoro timer
"""
import threading
import time
import math
from pathlib import Path
from utils.logging import verbose_print, error_print, info_print, debug_print

try:
    # Try to use pygame for better audio support
    # Suppress pygame's startup messages
    import os
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

def generate_beep_tone(frequency=800, duration=0.5, volume=0.7):
    """Generate a simple beep tone using pygame or fallback"""
    if not PYGAME_AVAILABLE:
        # Fallback to system bell
        debug_print("Using system bell fallback")
        print("\a")  # System bell
        return
    
    try:
        # Initialize pygame mixer
        pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=512)
        pygame.mixer.init()
        
        # Generate tone using numpy arrays if available
        try:
            import numpy as np
            sample_rate = 22050
            frames = int(duration * sample_rate)
            
            # Generate sine wave
            arr = np.sin(2 * np.pi * frequency * np.linspace(0, duration, frames))
            # Apply volume and convert to 16-bit stereo
            arr = (arr * volume * 32767).astype(np.int16)
            arr = np.repeat(arr.reshape(frames, 1), 2, axis=1)  # Make stereo
            
            # Create and play sound
            sound = pygame.sndarray.make_sound(arr)
            sound.play()
            time.sleep(duration)
            
        except ImportError:
            # Fallback without numpy - use simple sine wave generation
            import array
            sample_rate = 22050
            frames = int(duration * sample_rate)
            arr = array.array('h')
            
            for i in range(frames):
                time_point = float(i) / sample_rate
                wave = math.sin(2 * math.pi * frequency * time_point)
                sample = int(wave * volume * 32767)
                arr.append(sample)  # Left channel
                arr.append(sample)  # Right channel
            
            # Create and play sound
            sound = pygame.sndarray.make_sound(arr)
            sound.play()
            time.sleep(duration)
        
        pygame.mixer.quit()
        
    except Exception as e:
        error_print(f"Audio error: {e}")
        # Fallback to system bell
        debug_print("Using system bell fallback")
        print("\a")

# Available alarm sounds
ALARM_SOUNDS = {
    "gentle_chime": {
        "name": "Gentle Chime",
        "description": "Soft two-tone chime",
        "type": "generated"
    },
    "classic_beep": {
        "name": "Classic Beep", 
        "description": "Simple single beep",
        "type": "generated"
    },
    "triple_bell": {
        "name": "Triple Bell",
        "description": "Three ascending tones",
        "type": "generated"
    },
    "urgent_alert": {
        "name": "Urgent Alert",
        "description": "Sharp attention-getting sound",
        "type": "generated"
    },
    "meditation_bowl": {
        "name": "Meditation Bowl",
        "description": "Calming resonant tone",
        "type": "generated"
    },
    "none": {
        "name": "No Sound",
        "description": "Silent (no alarm)",
        "type": "generated"
    }
}

# System sound directories to search (platform-specific)
def get_system_sound_dirs():
    """Get platform-specific system sound directories"""
    import platform
    system = platform.system()
    
    if system == 'Darwin':  # macOS
        return [
            "/System/Library/Sounds",
            "/Library/Sounds",
            str(Path.home() / "Library" / "Sounds"),
            "/System/Library/Components/CoreAudio.component/Contents/SharedSupport/SystemSounds"
        ]
    elif system == 'Linux':  # Linux
        return [
            "/usr/share/sounds/gnome/default/alerts",
            "/usr/share/sounds/freedesktop/stereo", 
            "/usr/share/sounds/sound-icons",
            "/usr/share/sounds"
        ]
    else:  # Windows and others
        return [
            "C:/Windows/Media"
        ]

def get_system_sounds():
    """Get list of system sound files"""
    import os
    import glob
    
    system_sounds = {}
    # Include more audio formats for cross-platform compatibility
    sound_extensions = ['*.wav', '*.ogg', '*.oga', '*.mp3', '*.aiff', '*.aif', '*.caf', '*.m4a']
    
    for sound_dir in get_system_sound_dirs():
        if os.path.exists(sound_dir):
            for ext in sound_extensions:
                pattern = os.path.join(sound_dir, '**', ext)
                for filepath in glob.glob(pattern, recursive=True):
                    # Skip test files and very large files
                    if os.path.getsize(filepath) > 1024 * 1024:  # Skip files > 1MB
                        continue
                    if 'test' in os.path.basename(filepath).lower():
                        continue
                        
                    filename = os.path.basename(filepath)
                    name_without_ext = os.path.splitext(filename)[0]
                    
                    # Create display name from filename
                    display_name = name_without_ext.replace('-', ' ').replace('_', ' ').title()
                    
                    key = f"file:{filepath}"
                    system_sounds[key] = {
                        "name": display_name,
                        "description": f"System sound: {filename}",
                        "type": "file",
                        "path": filepath
                    }
    
    return system_sounds

def get_available_alarms():
    """Get list of all available alarm sounds (generated + system)"""
    alarms = ALARM_SOUNDS.copy()
    alarms.update(get_system_sounds())
    return alarms

def play_sound_file(filepath, volume=0.7):
    """Play a sound file using pygame"""
    if not PYGAME_AVAILABLE:
        error_print(f"Cannot play sound file: {filepath} (pygame not available)")
        return
    
    try:
        pygame.mixer.init()
        sound = pygame.mixer.Sound(filepath)
        sound.set_volume(volume)
        sound.play()
        
        # Wait for sound to finish
        while pygame.mixer.get_busy():
            import time
            time.sleep(0.1)
            
        pygame.mixer.quit()
        
    except Exception as e:
        error_print(f"Error playing sound file {filepath}: {e}")
        # Fallback to system bell
        debug_print("Using system bell fallback")
        print("\a")

def play_alarm_sound(sound_name="gentle_chime", volume=0.7):
    """Play a specific alarm sound by name"""
    
    # Check for global audio disable flag
    import os
    if os.environ.get('POMODORA_NO_AUDIO') == '1':
        debug_print(f"Audio disabled - skipping alarm: {sound_name}")
        return
    
    if sound_name == "none":
        return  # No sound
    
    # Check if it's a file-based sound
    if sound_name.startswith("file:"):
        filepath = sound_name[5:]  # Remove "file:" prefix
        play_sound_file(filepath, volume)
        return
    
    # Handle generated sounds
    if sound_name == "gentle_chime":
        # Soft two-tone chime
        generate_beep_tone(frequency=600, duration=0.3, volume=volume)
        time.sleep(0.1)
        generate_beep_tone(frequency=800, duration=0.3, volume=volume)
        
    elif sound_name == "classic_beep":
        # Simple single beep
        generate_beep_tone(frequency=800, duration=0.5, volume=volume)
        
    elif sound_name == "triple_bell":
        # Three ascending tones
        generate_beep_tone(frequency=600, duration=0.2, volume=volume)
        time.sleep(0.1)
        generate_beep_tone(frequency=800, duration=0.2, volume=volume)
        time.sleep(0.1)
        generate_beep_tone(frequency=1000, duration=0.3, volume=volume)
        
    elif sound_name == "urgent_alert":
        # Sharp attention-getting sound
        generate_beep_tone(frequency=1000, duration=0.2, volume=volume)
        time.sleep(0.1)
        generate_beep_tone(frequency=1000, duration=0.2, volume=volume)
        time.sleep(0.1)
        generate_beep_tone(frequency=1200, duration=0.4, volume=volume)
        
    elif sound_name == "meditation_bowl":
        # Calming resonant tone
        generate_beep_tone(frequency=432, duration=1.0, volume=volume * 0.8)
        
    else:
        # Fallback to gentle chime
        play_alarm_sound("gentle_chime", volume)

def play_alarm(alarm_type="sprint_complete", volume=0.7):
    """Play appropriate alarm for the given event (legacy function)"""
    
    if alarm_type == "sprint_complete":
        play_alarm_sound("gentle_chime", volume)
        
    elif alarm_type == "break_complete":
        play_alarm_sound("urgent_alert", volume)
    
    else:
        play_alarm_sound("classic_beep", volume)

def play_alarm_async(alarm_type="sprint_complete", volume=0.7):
    """Play alarm in a separate thread to avoid blocking"""
    def _play():
        try:
            play_alarm(alarm_type, volume)
        except Exception as e:
            error_print(f"Audio error: {e}")
    
    thread = threading.Thread(target=_play, daemon=True)
    thread.start()