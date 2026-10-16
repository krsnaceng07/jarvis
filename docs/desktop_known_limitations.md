# Desktop Automation Known Limitations

1. **UAC / Elevated Windows**: Windows Security prevents non-elevated processes from sending inputs to elevated Administrator windows (UIPI - User Interface Privilege Isolation). JARVIS must run with appropriate privileges to control elevated admin consoles.
2. **Direct3D / Exclusive Fullscreen Games**: Exclusive fullscreen applications bypass the Windows Desktop Window Manager (`DWM`). Windowed or borderless modes are required for automation.
3. **Lock Screen**: When Windows is locked (`Win+L`), the desktop station switches away from `WinSta0\Default`. JARVIS pauses interactive GUI input until the session is unlocked.
