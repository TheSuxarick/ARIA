"""
ARIA Sound Effects
Pleasant sounds for listening start/stop like Siri/Google Assistant
"""
import numpy as np
import os
from config import SOUNDS_DIR, SAMPLE_RATE


def generate_sine_wave(frequency, duration, sample_rate=SAMPLE_RATE, amplitude=0.3):
    """Generate a sine wave"""
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    wave = amplitude * np.sin(2 * np.pi * frequency * t)
    return wave.astype(np.float32)


def apply_envelope(audio, attack=0.05, decay=0.1, sustain=0.7, release=0.15):
    """Apply ADSR envelope to audio"""
    length = len(audio)
    attack_samples = int(length * attack)
    decay_samples = int(length * decay)
    release_samples = int(length * release)
    sustain_samples = length - attack_samples - decay_samples - release_samples
    
    envelope = np.concatenate([
        np.linspace(0, 1, attack_samples),  # Attack
        np.linspace(1, sustain, decay_samples),  # Decay
        np.full(sustain_samples, sustain),  # Sustain
        np.linspace(sustain, 0, release_samples)  # Release
    ])
    
    # Ensure same length
    if len(envelope) > length:
        envelope = envelope[:length]
    elif len(envelope) < length:
        envelope = np.pad(envelope, (0, length - len(envelope)))
    
    return audio * envelope


def generate_listen_start_sound():
    """
    Generate a pleasant "listening started" sound
    Two ascending tones like Siri/Google
    """
    # Two quick ascending notes
    note1 = generate_sine_wave(880, 0.12)   # A5
    note2 = generate_sine_wave(1318, 0.15)  # E6
    
    # Add harmonics for richness
    note1 += generate_sine_wave(1760, 0.12, amplitude=0.15)  # Octave harmonic
    note2 += generate_sine_wave(2636, 0.15, amplitude=0.15)
    
    # Apply envelopes
    note1 = apply_envelope(note1, attack=0.05, release=0.2)
    note2 = apply_envelope(note2, attack=0.05, release=0.25)
    
    # Small gap between notes
    gap = np.zeros(int(SAMPLE_RATE * 0.03), dtype=np.float32)
    
    # Combine
    sound = np.concatenate([note1, gap, note2])
    
    # Normalize
    sound = sound / np.max(np.abs(sound)) * 0.5
    
    return sound


def generate_listen_stop_sound():
    """
    Generate a pleasant "listening stopped" sound
    Two descending tones
    """
    # Two quick descending notes
    note1 = generate_sine_wave(1318, 0.1)   # E6
    note2 = generate_sine_wave(880, 0.18)   # A5
    
    # Add harmonics
    note1 += generate_sine_wave(2636, 0.1, amplitude=0.12)
    note2 += generate_sine_wave(1760, 0.18, amplitude=0.12)
    
    # Apply envelopes
    note1 = apply_envelope(note1, attack=0.03, release=0.15)
    note2 = apply_envelope(note2, attack=0.03, release=0.3)
    
    # Small gap
    gap = np.zeros(int(SAMPLE_RATE * 0.02), dtype=np.float32)
    
    # Combine
    sound = np.concatenate([note1, gap, note2])
    
    # Normalize
    sound = sound / np.max(np.abs(sound)) * 0.4
    
    return sound


def generate_error_sound():
    """Generate a gentle error sound"""
    # Low tone
    sound = generate_sine_wave(330, 0.3)  # E4
    sound += generate_sine_wave(277, 0.3, amplitude=0.2)  # C#4 - minor second for tension
    
    sound = apply_envelope(sound, attack=0.05, release=0.4)
    sound = sound / np.max(np.abs(sound)) * 0.35
    
    return sound


def generate_success_sound():
    """Generate a pleasant success sound"""
    # Major chord arpeggio (C-E-G)
    note1 = generate_sine_wave(523, 0.1)   # C5
    note2 = generate_sine_wave(659, 0.1)   # E5
    note3 = generate_sine_wave(784, 0.15)  # G5
    
    note1 = apply_envelope(note1, attack=0.02, release=0.2)
    note2 = apply_envelope(note2, attack=0.02, release=0.2)
    note3 = apply_envelope(note3, attack=0.02, release=0.3)
    
    gap = np.zeros(int(SAMPLE_RATE * 0.02), dtype=np.float32)
    
    sound = np.concatenate([note1, gap, note2, gap, note3])
    sound = sound / np.max(np.abs(sound)) * 0.4
    
    return sound


class SoundPlayer:
    """Play ARIA sound effects"""
    
    def __init__(self):
        # Pre-generate sounds
        self.sounds = {
            'listen_start': generate_listen_start_sound(),
            'listen_stop': generate_listen_stop_sound(),
            'error': generate_error_sound(),
            'success': generate_success_sound()
        }
    
    def play(self, sound_name):
        """Play a sound by name"""
        import sounddevice as sd
        
        if sound_name in self.sounds:
            sd.play(self.sounds[sound_name], SAMPLE_RATE)
            sd.wait()
    
    def play_listen_start(self):
        """Play listening started sound"""
        self.play('listen_start')
    
    def play_listen_stop(self):
        """Play listening stopped sound"""
        self.play('listen_stop')
    
    def play_error(self):
        """Play error sound"""
        self.play('error')
    
    def play_success(self):
        """Play success sound"""
        self.play('success')


# Singleton
_player = None

def get_sound_player():
    global _player
    if _player is None:
        _player = SoundPlayer()
    return _player


if __name__ == "__main__":
    import time
    
    player = SoundPlayer()
    
    print("Playing listen start sound...")
    player.play_listen_start()
    time.sleep(0.5)
    
    print("Playing listen stop sound...")
    player.play_listen_stop()
    time.sleep(0.5)
    
    print("Playing success sound...")
    player.play_success()
    time.sleep(0.5)
    
    print("Playing error sound...")
    player.play_error()
