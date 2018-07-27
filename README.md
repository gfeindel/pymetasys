# pymetasys
Metasys Companion is a legacy building control system from Johnson Controls. My church's building is about 30 years old, and they use this system to manage the HVAC and electrical systems. The only interface to Metasys is a VT100 terminal via an RS-232 serial connection. Obviously, this is not conducive to mobile management.

## Why write a Python library for Metasys?
I began this project to learn Python, version control, TDD, and web dev. I also want to help the facilities team at my church. I don't expect such an esoteric library to be of much use to anyone else, but maybe I'll be surprised! 

## Project Goals

pymetasis should be able to:
  1. Create, modify or delete points and groups, and
  2. Provide basic reporting of system status,
  3. Through a simple, mobile-friendly web interface and RESTful API.
  

