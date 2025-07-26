import pygame
import threading
import os
from typing import Optional

class AlarmManager:
    def __init__(self):
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        self.volume = 0.7
        self.alarm_thread = None
        
        # Create simple alarm sounds programmatically
        self.create_alarm_sounds()
    
    def create_alarm_sounds(self):
        """Create alarm sounds programmatically"""
        try:
            # Create a simple beep sound for sprint complete (softer)
            self.create_beep_sound("sprint_complete.wav", frequency=800, duration=0.3, volume=0.5)
            
            # Create a more noticeable alarm for break complete (louder, longer)
            self.create_beep_sound("break_complete.wav", frequency=1000, duration=0.8, volume=0.8)
            
        except Exception as e:
            print(f"Warning: Could not create alarm sounds: {e}")
    
    def create_beep_sound(self, filename: str, frequency: int, duration: float, volume: float):
        """Create a simple beep sound"""
        import numpy as np
        
        sample_rate = 22050
        frames = int(duration * sample_rate)
        
        # Generate sine wave
        arr = np.zeros((frames, 2))
        for i in range(frames):
            time = float(i) / sample_rate
            wave = np.sin(2 * np.pi * frequency * time) * volume
            arr[i][0] = wave  # Left channel
            arr[i][1] = wave  # Right channel
        
        # Convert to pygame sound
        sound_array = (arr * 32767).astype(np.int16)
        sound = pygame.sndarray.make_sound(sound_array)
        
        # Store in memory
        if not hasattr(self, 'sounds'):
            self.sounds = {}
        self.sounds[filename] = sound
    
    def set_volume(self, volume: float):
        """Set alarm volume (0.0 to 1.0)"""
        self.volume = max(0.0, min(1.0, volume))
    
    def play_sprint_complete_alarm(self):
        """Play sprint complete alarm (softer)"""
        self._play_alarm("sprint_complete.wav", repeat=1)
    
    def play_break_complete_alarm(self):
        """Play break complete alarm (more noticeable)"""
        self._play_alarm("break_complete.wav", repeat=3)
    
    def _play_alarm(self, sound_name: str, repeat: int = 1):
        """Play alarm sound in separate thread"""
        if self.alarm_thread and self.alarm_thread.is_alive():
            return  # Don't play multiple alarms simultaneously
        
        self.alarm_thread = threading.Thread(
            target=self._alarm_worker, 
            args=(sound_name, repeat),
            daemon=True
        )
        self.alarm_thread.start()
    
    def _alarm_worker(self, sound_name: str, repeat: int):
        """Worker function to play alarm sound"""
        try:
            if hasattr(self, 'sounds') and sound_name in self.sounds:
                sound = self.sounds[sound_name]
                sound.set_volume(self.volume)
                
                for _ in range(repeat):
                    sound.play()
                    pygame.time.wait(int(sound.get_length() * 1000))  # Wait for sound to finish
                    if repeat > 1:
                        pygame.time.wait(200)  # Brief pause between repeats
            else:
                # Fallback: system beep
                print("\a" * repeat)  # System bell
                
        except Exception as e:
            print(f"Error playing alarm: {e}")
            # Fallback: system beep
            print("\a" * repeat)
    
    def stop_alarm(self):
        """Stop currently playing alarm"""
        try:
            pygame.mixer.stop()
        except:
            pass
    
    def cleanup(self):
        """Cleanup pygame mixer"""
        try:
            pygame.mixer.quit()
        except:
            pass