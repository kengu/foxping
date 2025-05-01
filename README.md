# FoxPing 🦊

FoxPing is a robust and flexible bait alert system designed to listen for 433 MHz transmitters — 
especially compatible with the driveway alarm from Biltema:

🔗 [https://www.biltema.no/hjem/sikkerhet-i-hjemmet/alarm/alarm-til-innkjorselen-2000033277](https://www.biltema.no/hjem/sikkerhet-i-hjemmet/alarm/alarm-til-innkjorselen-2000033277)

## 🚀 Features

- Automatic learning of new codes and channel assignments
- Per-channel sound alerts (CH01–CH16)
- Timeout notification if no input is received for 10 seconds
- Logging of unknown and suspicious signals
- JSON-based persistence for manual editing and inspection
- Works on Raspberry Pi, Linux, macOS, and Windows

## Supported detectors
I have only tested this with Biltema driveway alarm detectors labeled with `CH13`, `CH14` and `CH15`. 
You can find the actual codes decoded using `433_rtl` in the [test](test/) folder. 

## Usage
```bash
python3 foxping.py -h
usage: foxping.py [-h] [-F {log,json,csv}] [-s] [files ...]

FoxPing - 433 MHz Bait Alert System

positional arguments:
  files                 Optional input file(s). If omitted, reads from stdin.

options:
  -h, --help            show this help message and exit
  -F, --format {log,json,csv}
                        Input format to parse (default: log)
  -s, --sound           Enable sound playback (off by default)

Use -F log for console output or -F json for structured logging.
```

This will run FoxPing with known channels 13, 14 and 15 with format `JSON`
```bash
python3 foxping.py -F json test/ch13.json test/ch14.json test/ch15.json
```
The output is
```json
{"msg_time": "2025-05-01 22:15:00", "channel": "CH13", "code": "bfafaa8", "count": 0}
{"msg_time": "2025-05-01 22:15:00", "channel": "CH14", "code": "efafaa8", "count": 0}
{"msg_time": "2025-05-01 22:15:00", "channel": "CH15", "code": "fbafaa8", "count": 0}
```

## ⚙️ Setup

Install `rtl_433` and connect a compatible RTL-SDR USB receiver.

Start FoxPing with:

```bash
rtl_433 -f 433920000 -R 0 -X 'n=biltema,m=OOK_PWM,s=480,l=1500,r=1450,t=450,g=0,y=0' -F json | python3 foxping.py
```

## 📁 Storage Files

| File                    | Description                              |
| ----------------------- | ---------------------------------------- |
| `known_ids.json`        | Manually assigned codes to channel names |
| `learned_codes.json`    | Codes automatically learned by FoxPing   |
| `unknown_codes.json`    | Codes that could not be classified       |
| `suspicious_codes.json` | Codes suspiciously close to known codes  |

## 🔊 Sound Support

- **macOS**: Uses `afplay` to play system sounds
- **Linux**: Uses `canberra-gtk-play`
- **Windows**: Uses `winsound.Beep` with tone per channel

## 📡 Range Improvement

For better performance and range, it is recommended to slightly modify the antenna on the Biltema unit, as described in this Norwegian guide:

🔧 [https://viltfall.wordpress.com/2020/04/15/biltema-aatevarsler/](https://viltfall.wordpress.com/2020/04/15/biltema-aatevarsler/)

## 🔧 Planned Improvements

- MQTT integration for remote alerting
- Auto-pruning of inactive or noisy codes
- Web dashboard for live monitoring and log inspection

