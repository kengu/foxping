import argparse
import os
import sys
import logging
import json
import time
import shutil
import platform
import subprocess
import traceback
from io import StringIO
from collections import defaultdict
from datetime import datetime, timedelta, date

EXPECTED_BIT_LENGTH = 25
EXPECTED_HEX_LENGTH = (EXPECTED_BIT_LENGTH + 3) // 4  # 7 hex characters
KNOWN_MASK          = 0x1FFFFF
KNOWN_ID            = 0x7AFAA8
IDLE_TIMEOUT        = 5
IDLE_TIMEOUT_MAX    = 10*60

# Known channel ids
KNOWN_IDS_FILE = "known_ids.json"

def load_known_ids():
  if os.path.exists(KNOWN_IDS_FILE):
      try:
          with open(KNOWN_IDS_FILE) as f:
              return json.load(f)
      except BrokenPipeError as e:
          tb = StringIO()
          traceback.print_exc(file=tb)
          panic(f"Failed to load {KNOWN_IDS_FILE}", error=str(e), trace=tb.getvalue())
      except Exception as e:
          warn(f"Failed to load {KNOWN_IDS_FILE}", error=str(e))
  return {}

known_ids = {}

# Suspicious codes
SUSPICIOUS_CODES_FILE = "suspicious_codes.json"

def load_suspicious():

  if os.path.exists(SUSPICIOUS_CODES_FILE):
      try:
          with open(SUSPICIOUS_CODES_FILE) as f:
              return json.load(f)
      except BrokenPipeError as e:
          tb = StringIO()
          traceback.print_exc(file=tb)
          panic(f"Failed to load {SUSPICIOUS_CODES_FILE}", error=str(e), trace=tb.getvalue())
      except Exception as e:
          warn(f"Failed to load {SUSPICIOUS_CODES_FILE}", error=str(e))
  return {}

def save_suspicious():
    try:
        with open(SUSPICIOUS_CODES_FILE, "w") as f:
            json.dump(suspicious_codes, f, indent=2)
    except BrokenPipeError as e:
        tb = StringIO()
        traceback.print_exc(file=tb)
        panic("Failed to save {SUSPICIOUS_CODES_FILE}", error=str(e), trace=tb.getvalue())
    except Exception:
        warn(f"Failed to save {SUSPICIOUS_CODES_FILE}")
        pass

suspicious_codes = {}

# Learned codes
LEARNED_CODES_FILE = "learned_codes.json"
LEARN_THRESHOLD = 3

def load_learned():
  if os.path.exists(LEARNED_CODES_FILE):
      try:
          with open(LEARNED_CODES_FILE) as f:
              return json.load(f)
      except BrokenPipeError as e:
          tb = StringIO()
          traceback.print_exc(file=tb)
          panic(f"Failed to load {LEARNED_CODES_FILE}", error=str(e), trace=tb.getvalue())
      except Exception as e:
          warn(f"Failed to load {LEARNED_CODES_FILE}", error=str(e))
  return {}

def save_learned():
    try:
        with open(LEARNED_CODES_FILE, "w") as f:
            json.dump(learned_codes, f, indent=2)
    except Exception:
        pass

learned_codes = {}

# Unknown codes
UNKNOWN_CODES_FILE = "unknown_codes.json"

def load_unknown():
    if os.path.exists(UNKNOWN_CODES_FILE):
        try:
            with open(UNKNOWN_CODES_FILE) as f:
                return json.load(f)
        except BrokenPipeError as e:
            tb = StringIO()
            traceback.print_exc(file=tb)
            panic(f"Failed to load {UNKNOWN_CODES_FILE}", error=str(e), trace=tb.getvalue())
        except Exception as e:
            warn(f"Failed to load {UNKNOWN_CODES_FILE}", error=str(e))
    return {}

def save_unknown():
    try:
        with open(UNKNOWN_CODES_FILE, "w") as f:
            json.dump(unknown_codes, f, indent=2)
    except Exception:
        pass

unknown_codes = {}

# Sound mapping for CH01 to CH16 using known macOS, Linux, and Windows defaults
MACOS_SOUND_MAP = [
    "Basso", "Blow", "Tink", "Frog", "Funk", "Glass", "Hero",
    "Morse", "Purr", "Pop", "Bottle", "Sosumi", "Submarine", "Ping"
]
LINUX_SOUND_MAP = [
    "bell", "complete", "message-new-instant", "dialog-information",
    "dialog-warning", "dialog-error", "service-logout", "service-login",
    "battery-low", "camera-shutter", "phone-incoming-call", "alarm-clock-elapsed",
    "bell-terminal", "dialog-question", "dialog-password", "audio-volume-change"
]
WINDOWS_FREQS = [
    440, 494, 523, 587, 659, 698, 784, 880,
    988, 1047, 1175, 1319, 1397, 1568, 1760, 1976
]

if platform.system() == "Darwin":
    SOUND_FILES = {f"CH{i+1:02d}": f"/System/Library/Sounds/{name}.aiff" for i, name in enumerate(MACOS_SOUND_MAP)}
elif platform.system() == "Linux":
    SOUND_FILES = {f"CH{i+1:02d}": name for i, name in enumerate(LINUX_SOUND_MAP)}
elif platform.system() == "Windows":
    SOUND_FILES = {f"CH{i+1:02d}": freq for i, freq in enumerate(WINDOWS_FREQS)}
else:
    SOUND_FILES = {}

def play_sound_if_enabled(channel):
    if not play_sound_enabled:
        return
    base_channel = channel.rstrip("?")
    sound = SOUND_FILES.get(base_channel)
    try:
        if platform.system() == "Darwin" and isinstance(sound, str):
            if os.path.exists(sound):
                subprocess.Popen(["afplay", sound])
            else:
                warn(f"Sound missing: {sound}")
        elif platform.system() == "Linux" and isinstance(sound, str):
            subprocess.Popen(["canberra-gtk-play", "-i", sound])
        elif platform.system() == "Windows" and isinstance(sound, int):
            try:
                import winsound
                winsound.Beep(sound, 200)
            except ImportError:
                pass
    except Exception as e:
        warn(f"Sound playback failed for {channel}: {e}")

# Check if code is too close to any known ID
def is_too_close_to_known_id(code_int, clean_code, msg_time):
    diff = code_int ^ KNOWN_ID
    for known_code in known_ids.keys():
        if known_code == clean_code:
            continue

        d = bin((int(known_code, 16) ^ KNOWN_ID) ^ diff).count("1")
        if d < 2:
            entry = suspicious_codes.get(known_code, {
                "known_code": known_code,
                "suspicious": {}
            })

            sub = entry["suspicious"].get(clean_code, {
                "count": 0,
                "first_seen": msg_time,
                "hamming_distance": d
            })

            sub["count"] += 1
            try:
                ts = datetime.strptime(msg_time, "%Y-%m-%d %H:%M:%S")
                delta = abs(ts - last_output_time.get(known_code, datetime.min))
                if delta <= timedelta(seconds=3):
                    sub["correlated_time"] = {
                        "delta_seconds": round(delta.total_seconds(), 2),
                        "timestamp": ts.isoformat()
                    }
            except Exception:
                pass

            entry["suspicious"][clean_code] = sub
            suspicious_codes[known_code] = entry
            save_suspicious()
            info(f"Suspicious code [{clean_code}] logged for known code [{known_code}] with hamming distance [{d}]")
            return True
    return False

def estimate_channel_id(diff, learned):
    """
    Estimate the channel ID based on the XOR difference (`diff`) from KNOWN_ID.

    This uses fixed offsets corresponding to CH01–CH16:
    CH01 → diff = (0 << 20), CH02 → (1 << 20), ..., CH16 → (15 << 20)

    The function finds the closest matching offset and returns an estimated channel like "CH13?".
    """
    channel_diffs = [(i, (i - 1) << 20) for i in range(1, 17)]
    closest = min(channel_diffs, key=lambda x: abs(x[1] - diff))
    return f"CH{closest[0]:02d}?"


# Message count and output throttling
message_count = defaultdict(lambda: -1)
last_output_time = defaultdict(lambda: datetime.min)
last_known_ids_mtime = os.path.getmtime(KNOWN_IDS_FILE) if os.path.exists(KNOWN_IDS_FILE) else 0

# Process one line at the time from stdio
def process_input_line(line, last_input_time):
    try:
        data = json.loads(line)
        last_input_time = time.time()
        if data.get("model") != "biltema":
            return last_input_time

        codes = data.get("codes", [])
        for code in codes:
            clean_code = code.split("}")[-1] if "}" in code else code

            if len(clean_code) != EXPECTED_HEX_LENGTH:
                return last_input_time

            try:
                code_int = int(clean_code, 16)
            except ValueError:
                return last_input_time

            msg_time = data.get("time", "unknown")

            if is_too_close_to_known_id(code_int, clean_code, msg_time):
                return last_input_time

            channel = None
            if clean_code in known_ids:
                channel = known_ids[clean_code]
            elif clean_code in learned_codes:
                channel = learned_codes[clean_code].get("code")
            elif (code_int & KNOWN_MASK) != (KNOWN_ID & KNOWN_MASK):
                diff = code_int ^ KNOWN_ID
                estimated_channel = estimate_channel_id(diff, learned_codes)

                unknown_entry = unknown_codes.get(clean_code, {
                    "code": clean_code,
                    "count": 0,
                    "first_seen": msg_time
                })

                unknown_entry["count"] += 1
                if estimated_channel:
                    unknown_entry["estimated_channel"] = estimated_channel

                # Check if this code came close to a known code in time
                try:
                    closest_known = None
                    closest_delta = None
                    threshold = timedelta(seconds=1)

                    ts = datetime.strptime(msg_time,"%Y-%m-%d %H:%M:%S")
                    for known_code, last_seen in last_output_time.items():
                        if known_code in known_ids:
                            delta = abs(ts - last_seen)
                            if delta <= threshold:
                                if closest_delta is None or delta < closest_delta:
                                    closest_known = known_code
                                    closest_delta = delta

                    if closest_known:
                        unknown_entry["correlated_with"] = {
                            "code": closest_known,
                            "channel": known_ids[closest_known],
                            "delta_seconds": round(closest_delta.total_seconds(), 2),
                            "timestamp": ts.isoformat()
                        }
                except Exception:
                    pass

                unknown_codes[clean_code] = unknown_entry
                save_unknown()
                info(f"Unknown code [{clean_code}] counted [{unknown_entry['count']}] times")
                return last_input_time

            else:
                diff = code_int ^ KNOWN_ID
                channel = estimate_channel_id(diff, learned_codes)

            message_count[clean_code] = message_count.get(clean_code, 0) + 1
            count = message_count[clean_code]

            if channel.endswith("?") and count >= LEARN_THRESHOLD:
                learned_channel = channel.rstrip("?")
                learned_codes[clean_code] = {
                    "code": clean_code,
                    "count": count,
                    "first_seen": msg_time,
                    "estimated_channel": channel,
                    "channel": learned_channel
                }
                save_learned()
                info(f"Learned code [{clean_code}] as {learned_channel} (count={count})")
                channel = learned_channel

            ts = datetime.strptime(msg_time, "%Y-%m-%d %H:%M:%S")
            if count <=1 or (ts - last_output_time[clean_code] >= timedelta(seconds=3)):
                line = f"[{msg_time}]  Channel: {channel}  Code: {clean_code}  Count: {count}"
                log(line, msg_time=msg_time, channel=channel, code=clean_code, count=count)
                last_output_time[clean_code] = ts

            play_sound_if_enabled(channel)

    except Exception as e:
        tb = StringIO()
        traceback.print_exc(file=tb)
        panic(f"Failed to decode JSON", error=str(e), trace=tb.getvalue(), raw=line.strip())

    return last_input_time

# Logging functions
LOG_FILE = "log.txt"
LOG_LEVELS = ["FINE", "INFO", "LOG" ,"ERROR"]
log_file = None
log_level = "INFO"
log_format = "log"
log_formats=["log", "json", "csv"]

def open_log():
    global log_file
    os.makedirs("logs", exist_ok=True)

    log_path = os.path.join("logs", LOG_FILE)
    if os.path.exists(log_path):
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        rotated = os.path.join("logs", f"log_{timestamp}.txt")
        shutil.move(log_path, rotated)

    log_file = open(log_path, "a", encoding="utf-8")

def fine(message, **kwargs):
    log(message, level="FINE", **kwargs)

def info(message, **kwargs):
    log(message, level="INFO", **kwargs)

def warn(message, **kwargs):
    log(message, level="WARN", **kwargs)

def panic(message, **kwargs):
    log(message, level="ERROR", **kwargs)
    close_log()
    sys.exit(-1)

def log(message, level="LOG", **kwargs):
    global log_file, log_level

    if LOG_LEVELS.index(level) < LOG_LEVELS.index(log_level):
        return

    raw = kwargs.get("raw","")
    error = kwargs.get("error","")
    trace = kwargs.get("trace", "")
    timestamp = datetime.now().isoformat()
    line = f"{timestamp}: {level}: {message}"
    if len(raw) > 0:
        line = f"{line}: {raw}"
    if len(error) > 0:
        line = f"{line}: {error}"
        if len(trace) > 0:
            line = f"{line}: {trace}"

    if log_format == "log":
        if level in ["LOG","INFO","FINE"]:
            print(line, flush=True)
        else:
            print(line, file=sys.stderr, flush=True)
    elif level == "LOG":
        if log_format == "json":
            print(json.dumps(kwargs), flush=True)
        elif log_format == "csv":
            # Expected keys: msg_time, channel, code, count
            csv_line = ",".join([
                kwargs.get("msg_time", timestamp),
                kwargs.get("channel", ""),
                kwargs.get("code", ""),
                str(kwargs.get("count", "")),
            ])
            print(csv_line, flush=True)

    # Always write to log file
    log_file.write(f"{line}\n")
    log_file.flush()

    rotate_log_if_needed()
    remove_old_log_files()

def rotate_log_if_needed():
    # Rotate if log file is too large (>1 MB)
    try:
        log_path = os.path.join("logs", LOG_FILE)
        if os.path.getsize(log_path) > 1_000_000:
            log_file.close()
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            rotated_path = os.path.join("logs", f"log_{timestamp}.txt")
            shutil.move(log_path, rotated_path)
            log_file = open(log_path, "a", encoding="utf-8")
    except Exception as e:
        tb = StringIO()
        traceback.print_exc(file=tb)
        trace = tb.getvalue()
        print(f"[WARN] Failed to rotate log: {e}\n {trace}", file=sys.stderr, flush=True)

def remove_old_log_files():
    try:
        log_dir = "logs"
        rotated_logs = sorted(
            [f for f in os.listdir(log_dir) if f.startswith("log_") and f.endswith(".txt")],
            key=lambda f: os.path.getmtime(os.path.join(log_dir, f)),
            reverse=True
        )
        max_logs = 5
        for old_log in rotated_logs[max_logs:]:
            os.remove(os.path.join(log_dir, old_log))
    except Exception as e:
        tb = StringIO()
        traceback.print_exc(file=tb)
        trace = tb.getvalue()
        print(f"[WARN] Failed to clean up old logs: {e}\n {trace}", file=sys.stderr, flush=True)

def close_log():
    try:
        log_file.close()
    except Exception:
        pass

def human_time_since(seconds):
    seconds = int(seconds)
    if seconds < 1:
        return "now"
    elif seconds == 1:
        return "1 second"
    elif seconds < 60:
        return f"{seconds} seconds"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if minutes == 0:
            return f"{hours} hour{'s' if hours != 1 else ''}"
        else:
            return f"{hours} hour{'s' if hours != 1 else ''} and {minutes} minute{'s' if minutes != 1 else ''}"


def show_estimated_ids():
    print("=== Estimated IDs (based on fixed offsets) ===")
    for i in range(1, 17):
        diff = (i - 8) << 20
        code = KNOWN_ID ^ diff
        print(f"{code:07x} → CH{i:02d}?")
    print()

def show_analysis():
    print("=== Known IDs ===")
    for code, channel in known_ids.items():
        print(f"{code} → {channel}")
    print()

    print("=== Learned Codes ===")
    for code, entry in learned_codes.items():
        count = entry.get("count", "?")
        first_seen = entry.get("first_seen", "?")
        estimated = entry.get("estimated_channel", "?")
        channel = entry.get("channel", "?")
        print(f"{code} (estimated={estimated}, count={count}, first_seen={first_seen})")
    print()

    print("=== Suspicious Codes Grouped by Known Code ===")
    for known_code, entry in suspicious_codes.items():
        channel = known_ids.get(known_code, "?")
        print(f"{known_code} ({channel}):")

        for suspect_code, info in entry.get("suspicious", {}).items():
            count = info.get("count", 0)
            distance = info.get("hamming_distance", "?")
            first_seen = info.get("first_seen", "?")

            print(f"  ↳ {suspect_code} (count={count}, distance={distance}, first_seen={first_seen})")

            corr = info.get("correlated_time")
            if corr:
                print(f"     ↳ correlated at Δ={corr.get('delta_seconds', '?')}s (t={corr.get('timestamp', '?')})")
    print()

    print("=== Unknown Codes ===")
    for code, entry in unknown_codes.items():
        count = entry.get("count", "?")
        first_seen = entry.get("first_seen", "?")
        estimated = entry.get("estimated_channel", "?")

        print(f"{code} (count={count}, first_seen={first_seen}, estimated={estimated})")

        corr = entry.get("correlated_with")
        if corr:
            print(f"  ↳ correlated with {corr.get('code', '?')} ({corr.get('channel', '?')}, Δ={corr.get('delta_seconds', '?')}s) (t={corr.get('timestamp', '?')})")
    print()

    print("=== Estimated IDs (based on fixed offsets) ===")
    print()
    print(f"{'Channel':<10}\t{'Estimate':<7}\t{'Known':<6}  \t{'Hamming':<10}")
    print("-" * 55)
    for i in range(1, 17):
        diff = (i - 1) << 20
        code_int = KNOWN_ID ^ diff
        code_hex = f"{code_int:07x}"
        expected_channel = f"CH{i:02d}"
        known_code = next((k for k, v in known_ids.items() if v == expected_channel), "-")

        # Calculate Hamming distance between estimated code and KNOWN_ID
        if known_code != "-":
            hamming = bin(KNOWN_ID ^ code_int).count("1")
        else:
            hamming = "-"

        print(f"{expected_channel:<8}\t{code_hex:<10}\t{known_code:<10}\t{hamming:<4}")
    print()

def parse_args():
    parser = argparse.ArgumentParser(
        description="FoxPing - 433_rtl based Bait Alert Tracking Service",
        epilog="Use -F log for console output or -F json for structured logging."
    )
    parser.add_argument("-F", "--format", choices=log_formats, default="log", help="Input format to parse (default: log)")
    parser.add_argument("-s", "--sound", action="store_true", help="Enable sound playback (off by default)")
    parser.add_argument("-A", "--analyze", action="store_true", help="Print full code analysis and exit")
    parser.add_argument("-L", "--log-level", choices=LOG_LEVELS, default="INFO", help="Set minimum log level (default: INFO)")
    parser.add_argument("files", nargs="*", help="Optional input file(s). If omitted, reads from stdin.")

    return parser.parse_args()

def main():
    global log_format, log_level, log_file, known_ids, learned_codes, suspicious_codes, unknown_codes, last_known_ids_mtime, play_sound_enabled

    open_log()

    args = parse_args()
    log_level = args.log_level
    known_ids = load_known_ids()
    learned_codes = load_learned()
    suspicious_codes = load_suspicious()
    unknown_codes = load_unknown()
    last_input_time = time.time()

    if args.analyze:
        show_analysis()
        return

    play_sound_enabled = args.sound
    if args.format not in log_formats:
        warn(f"Unsupported format: {args.format}, defaulting to 'log'")
        log_format = "log"
    else:
        log_format = args.format

    if args.files:
        for filename in args.files:
            try:
                with open(filename) as f:
                    for line in f:
                        last_input_time = process_input_line(line, last_input_time)
            except Exception as e:
                warn(f"Failed to read {filename}", error=str(e))
    else:
        info("====================================================")
        info("[INFO] Foxping started. Press Ctrl+C to exit.")
        info("====================================================")

        if os.name != "nt":
            import select
            timeout = IDLE_TIMEOUT
            in_timeout = True
            stdin_fd = sys.stdin.fileno()
            last_line_time = datetime.now()
            while True:
                rlist, _, _ = select.select([stdin_fd], [], [], timeout)
                if rlist:
                    now = datetime.now()
                    line = sys.stdin.readline()
                    if not line:
                        break
                    if(in_timeout):
                        in_timeout = False
                        elapsed = (now - last_line_time).total_seconds()
                        fine(f"[STDIN] Received {len(line)} characters ({human_time_since(elapsed)})")

                    last_line_time = now
                    last_input_time = process_input_line(line, last_input_time)
                    timeout = IDLE_TIMEOUT
                else:
                    in_timeout = True
                    now = datetime.now()
                    elapsed = (now - last_line_time).total_seconds()
                    fine(f"[STDIN] Waiting for input... ({human_time_since(elapsed)})")
                    timeout = min(timeout + IDLE_TIMEOUT, IDLE_TIMEOUT_MAX)
        else:
            for line in sys.stdin:
                last_input_time = process_input_line(line, last_input_time)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        info("Stopped by user (Ctrl+C). Exiting cleanly.")
        save_learned()
        save_unknown()
        save_suspicious()
        close_log()
    except BrokenPipeError as e:
        tb = StringIO()
        traceback.print_exc(file=tb)
        panic(f"Broken pipe", error=str(e), trace=tb.getvalue())
    except Exception as e:
        tb = StringIO()
        traceback.print_exc(file=tb)
        panic(f"Unexpected error", error=str(e), trace=tb.getvalue())