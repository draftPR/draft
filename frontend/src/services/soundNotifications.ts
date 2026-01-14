/**
 * Sound notifications service for task completion events.
 * Plays audio feedback when tasks complete, fail, or need attention.
 */

export type SoundType = 
  | "success"      // Task completed successfully
  | "error"        // Task failed
  | "warning"      // Needs attention (e.g., needs_human)
  | "notification" // Generic notification
  | "start";       // Task started

interface SoundConfig {
  frequency: number;
  duration: number;
  type: OscillatorType;
  volume: number;
}

// Sound configurations for each type
const SOUND_CONFIGS: Record<SoundType, SoundConfig[]> = {
  success: [
    { frequency: 523.25, duration: 100, type: "sine", volume: 0.3 }, // C5
    { frequency: 659.25, duration: 100, type: "sine", volume: 0.3 }, // E5
    { frequency: 783.99, duration: 200, type: "sine", volume: 0.3 }, // G5
  ],
  error: [
    { frequency: 220, duration: 150, type: "sawtooth", volume: 0.2 },
    { frequency: 207.65, duration: 300, type: "sawtooth", volume: 0.2 },
  ],
  warning: [
    { frequency: 440, duration: 100, type: "triangle", volume: 0.25 },
    { frequency: 440, duration: 100, type: "triangle", volume: 0.25 },
    { frequency: 440, duration: 100, type: "triangle", volume: 0.25 },
  ],
  notification: [
    { frequency: 880, duration: 100, type: "sine", volume: 0.2 },
    { frequency: 1108.73, duration: 150, type: "sine", volume: 0.2 },
  ],
  start: [
    { frequency: 392, duration: 80, type: "sine", volume: 0.2 },
    { frequency: 523.25, duration: 100, type: "sine", volume: 0.2 },
  ],
};

let audioContext: AudioContext | null = null;
let soundEnabled = true;
let volume = 0.5; // Master volume (0-1)

function getAudioContext(): AudioContext {
  if (!audioContext) {
    audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
  }
  return audioContext;
}

async function playTone(config: SoundConfig, startTime: number): Promise<void> {
  const ctx = getAudioContext();
  
  const oscillator = ctx.createOscillator();
  const gainNode = ctx.createGain();
  
  oscillator.connect(gainNode);
  gainNode.connect(ctx.destination);
  
  oscillator.type = config.type;
  oscillator.frequency.setValueAtTime(config.frequency, startTime);
  
  // Apply volume envelope
  const adjustedVolume = config.volume * volume;
  gainNode.gain.setValueAtTime(0, startTime);
  gainNode.gain.linearRampToValueAtTime(adjustedVolume, startTime + 0.01);
  gainNode.gain.exponentialRampToValueAtTime(0.001, startTime + config.duration / 1000);
  
  oscillator.start(startTime);
  oscillator.stop(startTime + config.duration / 1000);
}

/**
 * Play a sound notification
 */
export async function playSound(type: SoundType): Promise<void> {
  if (!soundEnabled) return;
  
  try {
    const ctx = getAudioContext();
    
    // Resume context if suspended (browser autoplay policy)
    if (ctx.state === "suspended") {
      await ctx.resume();
    }
    
    const configs = SOUND_CONFIGS[type];
    let currentTime = ctx.currentTime;
    
    for (const config of configs) {
      await playTone(config, currentTime);
      currentTime += config.duration / 1000 + 0.05; // Small gap between notes
    }
  } catch (err) {
    console.warn("Failed to play sound:", err);
  }
}

/**
 * Enable or disable sound notifications
 */
export function setSoundEnabled(enabled: boolean): void {
  soundEnabled = enabled;
  if (typeof window !== "undefined") {
    localStorage.setItem("smartkanban_sound_enabled", String(enabled));
  }
}

/**
 * Check if sound is enabled
 */
export function isSoundEnabled(): boolean {
  return soundEnabled;
}

/**
 * Set master volume (0-1)
 */
export function setVolume(v: number): void {
  volume = Math.max(0, Math.min(1, v));
  if (typeof window !== "undefined") {
    localStorage.setItem("smartkanban_volume", String(volume));
  }
}

/**
 * Get current volume (0-1)
 */
export function getVolume(): number {
  return volume;
}

/**
 * Initialize sound settings from localStorage
 */
export function initSoundSettings(): void {
  if (typeof window === "undefined") return;
  
  const storedEnabled = localStorage.getItem("smartkanban_sound_enabled");
  if (storedEnabled !== null) {
    soundEnabled = storedEnabled === "true";
  }
  
  const storedVolume = localStorage.getItem("smartkanban_volume");
  if (storedVolume !== null) {
    volume = parseFloat(storedVolume);
  }
}

/**
 * Play sound based on ticket state transition
 */
export function playSoundForTransition(fromState: string, toState: string): void {
  if (toState === "done") {
    playSound("success");
  } else if (toState === "failed" || toState === "blocked") {
    playSound("error");
  } else if (toState === "needs_human") {
    playSound("warning");
  } else if (toState === "executing" && fromState === "planned") {
    playSound("start");
  }
}

/**
 * Play sound for job status change
 */
export function playSoundForJobStatus(status: string): void {
  switch (status) {
    case "completed":
      playSound("success");
      break;
    case "failed":
      playSound("error");
      break;
    case "cancelled":
      playSound("warning");
      break;
  }
}

// Initialize on module load
if (typeof window !== "undefined") {
  initSoundSettings();
}
