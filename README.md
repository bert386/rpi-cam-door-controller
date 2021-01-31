# rpi-cam-door-controller
Motion based door controller system using Raspberry Pi

# Components
- RPI zero W
- RPI CSI compatible Camera
- 2 Relay modules
- PIR motion sensor

# Functionalities
- monitoring status of PIR and relay status via Flask web service
- management and palyback of recorded video file list on flask backend
- video capturing when motion detected for specified time
- publish mqtt message to pbunub service
- automatic launch monitor script when RPI boots

# Packages requirements
    sudo apt-get install python-picamera python3-picamera
    sudo apt install python-gpiozero
