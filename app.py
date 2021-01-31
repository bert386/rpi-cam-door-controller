
### Logging function package in order to display AWS Connection and callback messages
import sys, traceback
import logging
import os

### JSON Processing Python package
import json
from json import load

### PIR Modtion sensor package
from gpiozero import MotionSensor

### PUBNUB Package
# sudo pip install pubnub
from pubnub.callbacks import SubscribeCallback
from pubnub.enums import PNStatusCategory, PNOperationType
from pubnub.exceptions import PubNubException
from pubnub.pnconfiguration import PNConfiguration
from pubnub.pubnub import PubNub, SubscribeListener

### Time package, used to implement thread and timing in RPI
import time
import threading

import datetime as dt

### RPI CSI Camera Package
import picamera
'''
    sudo apt-get update
    sudo apt-get install python-picamera python3-picamera
'''

# External module imports
import RPi.GPIO as GPIO

### FLASK Web server package
from flask import Flask, render_template, request, jsonify

from multiprocessing import Process, Manager, Value, Lock

import urllib2

Detected = 0
NonDetecetd = 0

DeviceStatus = {
    'PIR' : 0,
    'Relay' : 0,
    'FreeSpace' : 100,
    'videoCount' : 10
    }

### Web server instance
app = Flask(__name__)

###
cur_time = dt.datetime.now()
starttime = cur_time.strftime("%Y/%m/%d %H:%M:%S")
print(starttime)

### PIR Sensor instance
pir = MotionSensor(4) # BCM 4-Physical 7
RelayStatus = False
RelayPin = 18 # Physical 12, BCM18

# Pin Setup:
GPIO.setmode(GPIO.BCM) # Broadcom pin-numbering scheme
GPIO.setup(RelayPin, GPIO.OUT) # Relay pin set as output
GPIO.output(RelayPin, GPIO.LOW)

def GetVideoCount():
    Directory = 'static/videos/'
    Filelist = os.listdir(Directory) # returns list
    return len(Filelist)

def DeleteFile():
    Directory = 'static/videos/'
    VideoCount = GetVideoCount()
    p = os.popen('ls ' + Directory + ' -l')
    i = 0
    while VideoCount > 0:
        i = i + 1
        line = p.readline()
        if i==2:
            FileName = line.split()[8]
            Command = 'sudo rm static/videos/'
            os.system(Command + FileName)
            print FileName + ' deleted.'
            break

def getDiskSpacePerc():
    p = os.popen("df -h /")
    i = 0
    while 1:
        i = i+1
        line = p.readline()
        if i==2:
            return(int(line.split()[1:5][3].rstrip('%')))

def VideoCaptureProc(e):
    ### Checking FreeSpace
    print('Disk Free Space ' + str(100 - getDiskSpacePerc()) + '%')
    if(getDiskSpacePerc() > 90): ## if it is used over 90% 
        DeleteFile()
    print('Video Capture is staretd!')

    with picamera.PiCamera(resolution='640x480', framerate=24) as camera:    
        camera.start_preview()
        camera.annotate_background = picamera.Color('black')
        camera.annotate_text = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        TimeStamp = dt.datetime.now().strftime('%Y%m%d%H%M%S')
        
        # camera.capture(('static/videos/' + TimeStamp) + '.jpg')

        camera.start_recording('temp.h264')
        start = dt.datetime.now()
        while (dt.datetime.now() - start).seconds < 10 and not e.isSet():
            camera.annotate_text = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            camera.wait_recording(0.2)
        print('Video Capture is finished!')
        camera.stop_preview()
        camera.stop_recording()

    ### Codec converting
    Command = 'MP4Box -fps 24 -add '
    Command += 'temp.h264 '
    Command += ('static/videos/' + TimeStamp)
    Command += '.mp4'
    print(Command)
    os.system(Command)

    ### Sync method Publish
    pnconfig = PNConfiguration()

    ### This is for Pubkey and subkey , Channel name

    pnconfig.publish_key = 'pub-****************************************'
    pnconfig.subscribe_key = 'sub-c-************************************'

    Channel = 'TestChannel'
    pubnub = PubNub(pnconfig)
    Happentime = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    pubnub.publish()\
        .channel(Channel)\
        .message(['Message', 'Motion is Detected!!!, ' + Happentime])\
        .should_store(True)\
        .use_post(True)\
        .sync()
    DeviceStatus['videoCount'] = GetVideoCount()    
    DeviceStatus['FreeSpace'] = 100 - getDiskSpacePerc()

def MotionDetectProc(e):
    HoldingInterval = 30
    LastCapture = dt.datetime.now()
    motionDetected = False
    
    while not e.isSet():
        if((dt.datetime.now() - LastCapture).seconds > HoldingInterval):
        pir.wait_for_motion(1)
        if(pir.motion_detected and (dt.datetime.now() - LastCapture).seconds > HoldingInterval):
            motionDetected = True
            LastCapture = dt.datetime.now()
            DeviceStatus['PIR'] = 1
            GPIO.output(RelayPin, GPIO.HIGH)
            DeviceStatus['Relay'] = 1
            print 'Motion Detected, Relay Opened!'

            global CapEvent
            CapEvent = threading.Event()
            CaptureThread = threading.Thread(target=VideoCaptureProc, args=(CapEvent,))
            CaptureThread.start()

            ### Sync method Publish
            pnconfig = PNConfiguration()

            ### This is for Pubkey and subkey , Channel name
            pnconfig.publish_key = 'pub-c-****'
            pnconfig.subscribe_key = 'sub-c-***'
            Channel = 'TestChannel'
            pubnub = PubNub(pnconfig)
            Happentime = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            pubnub.publish()\
                .channel(Channel)\
                .message(['Message', 'Motion is Detected!!!, ' + Happentime])\
                .should_store(True)\
                .use_post(True)\
                .sync()
        pir.wait_for_no_motion(1)
        if(pir.motion_detected == False):
            DeviceStatus['PIR'] = 0

        if(pir.motion_detected == False and (dt.datetime.now() - LastCapture).seconds > HoldingInterval)):
            GPIO.output(RelayPin, GPIO.LOW)
            DeviceStatus['Relay'] = 0


########
DetectEvent = threading.Event()
DetectThread = threading.Thread(target=MotionDetectProc, args=(DetectEvent,))
DetectThread.start()

CapEvent = threading.Event()


# Web serveice proces routines
@app.route("/")
def Index():
    templateData = {
            'title' : starttime,
            'DeviceStatus' : DeviceStatus
            }
    return render_template("index.html", **templateData)

@app.route("/index/Getstatus")
def GetStatus():
    return jsonify(DeviceStatus=DeviceStatus)

@app.route("/video")
def Video():
    VideoList = []
    VideoCount = GetVideoCount()

    Directory = 'static/videos/'
    VideoCount = GetVideoCount()

    if(VideoCount > 0):
        p = os.popen('ls ' + Directory + ' -l')
        line = p.readline()
        i = 0
        while True:
            i = i + 1
            line = p.readline()
            if(len(line) == 0):
                break

            FileName = line.split()[8]
            VideoItem = {
                'id':'1', 'FileName':'20170428061254.mp4', 'Duration':'00:00:10', 'Thumb':'', 'Notes':''
            }

            VideoItem['id'] = str(i)
            VideoItem['FileName'] = FileName
            VideoItem['Duration'] = '00:00:10'
            VideoList.append(VideoItem)

    json_data = json.dumps(VideoList)
    print json_data
    
    templateData = {
            'title' : starttime,
            'VideoList' : json_data
            }
    return render_template("Video.html", **templateData)

def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()

@app.route('/shutdown')
def shutdown():
    shutdown_server()
    return 'Server shutting down...'

def FlaskProc():
    app.run(host='0.0.0.0', debug=True, threaded=True, use_reloader=False)
    print "Program Stopped!"

if __name__ == '__main__':
    # Init Status variables
    DeviceStatus['FreeSpace'] = 100 - getDiskSpacePerc()
    DeviceStatus['videoCount'] = GetVideoCount()

    FlaskEvent = threading.Event()
    Flaskthread = threading.Thread(target=FlaskProc, args=())
    Flaskthread.start()
    try:
        '''
        CapEvent = threading.Event()
        LastCapture = dt.datetime.now()
        CaptureInterval = 30
        '''
        while True:
            '''
            if((dt.datetime.now() - LastCapture).seconds > CaptureInterval):
                CapEvent = threading.Event()
                CaptureThread = threading.Thread(target=VideoCaptureProc, args=(CapEvent,))
                CaptureThread.start()
                LastCapture = dt.datetime.now()
            '''
            time.sleep(2)
    except KeyboardInterrupt: # If CTRL+C is pressed, exit cleanly:
        CapEvent.set()
        DetectEvent.set()
        urllib2.urlopen("http://0.0.0.0:5000/shutdown").read()        
        #server.terminate()
        #server.join()
    finally:
        time.sleep(2) 
