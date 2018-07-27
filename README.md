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
  
## Library Design

pymetasys consists of several logical components.
  1. The serial interface ([pyserial](https://github.com/pyserial)) reads and writes bytes from the RS-232 serial connection to Metasys.
  2. The terminal emulator ([pyte](https://github.com/pyte)) emulates the VT100 terminal and converts the data to a string buffer for screen scraping.
  3. The Metasys controller exposes the API, translates these functions to keystrokes for Metasys and scrapes the VT100 "screen" to read the output.
  
I can think of a few design challenges:
  1. The serial interface can be a bit laggy, and some of the Metasys control screens refresh every few seconds. How do I make sure the screen scraping buffer is accurate?
  2. The Metasys UI signs the operator out after a period of inactivity. How can I avoid "signing in" to the Metasys for every command? This will dramatically slow down the API performance.
  3. Since the serial interface supports only one operator at a time, how do I gracefully ensure only one connection at a time?
  
  More to come as I make progress on this project!
