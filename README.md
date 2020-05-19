# pymetasys
Pymetasys is a Python library that exposes basic functionality of the Metasys Companion building control system.

Metasys Companion is a legacy building control system from Johnson Controls. My church's building is about 30 years old, and they use this system to manage the HVAC and electrical systems. The only interface to Metasys is a VT100 terminal via an RS-232 serial connection. Obviously, this is not conducive to mobile management.

## Why write a Python library for Metasys?
I began this project to learn Python, version control, TDD, and web dev. I also want to help the facilities team at my church. I don't expect such an esoteric library to be of much use to anyone else, but maybe I'll be surprised! 

## Project Goals

pymetasis should be able to:
  1. Create, modify or delete points and groups, and
  2. Provide basic reporting of system status,
  3. Through a simple, mobile-friendly web interface and RESTful API.
  
## Design

Each action can be represented as:
  1. The sequence of characters used to reach that screen.
  2. The pattern that matches the desired field.
  3. The value for the field.

  Rather than trying to maintain the state of the serial console, pymetasys begins each operation from the main screen. This slows the process down, but it simplifies the logic dramatically.

pymetasys consists of several logical components.
  1. The serial interface ([pyserial](https://github.com/pyserial)) reads and writes bytes from the RS-232 serial connection to Metasys.
  2. The terminal emulator ([pyte](https://github.com/pyte)) emulates the VT100 terminal and converts the data to a string buffer for screen scraping.
  3. The Metasys controller exposes the API, translates these functions to keystrokes for Metasys and scrapes the VT100 "screen" to read the output.
  
I can think of a few design challenges:
  1. The serial interface can be a bit laggy, and some of the Metasys control screens refresh every few seconds. How do I make sure the screen scraping buffer is accurate?
  2. The Metasys UI signs the operator out after a period of inactivity. How can I avoid "signing in" to the Metasys for every command? This will dramatically slow down the API performance.
  3. Since the serial interface supports only one operator at a time, how do I gracefully ensure only one connection at a time? Use some kind of interprocess communication (IPC), so that web processes communicate with a singleton control process that accesses the serial port.
  4. How do I authenticate and authorize users to protect against malicious actions?
  
  More to come as I make progress on this project!
