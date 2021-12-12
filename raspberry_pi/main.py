import os
import sys

#Find directory path of current file
current = os.path.dirname(os.path.realpath(__file__))
#Find directory path of parent folder and add to sys path
parent = os.path.dirname(current)
sys.path.append(parent)
print("\n\n--- Welcome to the PegasusArm OS v1.0.0 User Interface ---\n\n")
print("Importing modules...\n")
import numpy as np
import modern_robotics as mr
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame
import time
import csv
from typing import List, Tuple, Dict
from robot_init import robot, robotFric
from settings import sett
from classes import SerialData, Robot, InputError, PID
from util import Tau2Curr, Curr2MSpeed
from kinematics.kinematic_funcs import FKSpace
from serial_comm.serial_comm import FindSerial, StartComms, GetComms, SReadAndParse
from dynamics.dynamics_funcs import FeedForward
from control.control import PosControl, VelControl, ForceControl, ImpControl

def GetEConfig(sConfig: np.ndarray, Pegasus: Robot) -> np.ndarray:
    """Obtain a desired end-effector configuration based on the input 
    of the user.
    :param sConfig: Start configuration in joint space.
    :param Pegasus: A mathematical model of the robot.
    :return sConfig: Start configuration in joint- or end-effector
                     space, based on eConfig input.
    :return eConfig: Desired end configuration in joint- or end-
                     effector space."""
    userInput = input("Please enter the desired end-configuration, "+
                            "either as a list of joint angles in pi radians " +
                            "or a 4x4 transformation matrix:\n").strip()
    #Example eConfig: [0.5,0.2,0,0,0] OR 
    #[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
    if "[[" in userInput[0:2]:
        eConfig = np.zeros((4,4))
        rows = userInput[2:-2].split('],[')
        for i in range(4):
            row = np.array([float(item) for item in rows[i].split(',')])
            eConfig[i,:] = row
        sConfig = FKSpace(Pegasus.TsbHome, Pegasus.screwAxes, sConfig)
        if eConfig.shape != sConfig.shape:
            raise InputError("Start- and end configuration are not the same "+
                             "shape.")
        return sConfig, eConfig
    elif userInput[0] == "[":
        userInput = userInput[1:-1]
        list = [float(item)*np.pi for item in userInput.split(',')]
        eConfig = np.array(list)
        if eConfig.shape != sConfig.shape:
            raise InputError("Start- and end configuration are not the same "+
                             "shape.")
        return sConfig, eConfig

def GetKeysJoint(events: List["pygame.Event"], pressed: Dict[str, bool], 
                 wMin: float, wMax: float, wSel: float, wIncr: float)-> \
                 Tuple[bool, Dict[str, bool], float, List[float]]:
    """Checks for key-presses and executes joint control commands 
    accordingly.
    All mSpeed values should be an integer in the range [0, 255].
    :param events: List of pygame events for key presses.
    :param pressed: Dictionary of booleans to keep track of keyboard 
                    status.
    :param wMin: The minimal motor speed.
    :param wMax: The maximal motor speed.
    :param wSel: The current selected motor speed.
    :param wIncr: Incrementation value of motor speed.
    :return noInput: Bool indicating no new keyboard events.
    :return pressed: Updated dictionary of booleans to keep track of
                     of keyboard status.
    :return wSel: Selected motor speed
    :return wDes: Array of desired joint velocities based on input.
    """
    wDes = np.zeros(5)
    if len(events) == True:
        noInput = True
    else:
        noInput = False
    for event in events:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q:
                pressed['q'] = True
                wDes[0] = wSel
            elif event.key == pygame.K_a:
                pressed['a'] = True
                wDes[0] = -wSel
            elif event.key == pygame.K_w:
                pressed['w'] = True
                wDes[1] = wSel
            elif event.key == pygame.K_s:
                pressed['s'] = True
                wDes[1] = -wSel
            elif event.key == pygame.K_e:
                pressed['e'] = True
                wDes[2] = wSel
            elif event.key == pygame.K_d:
                pressed['d'] = True
                wDes[2] = -wSel
            elif event.key == pygame.K_r:
                pressed['r'] = True
                wDes[3] = wSel
            elif event.key == pygame.K_f:
                pressed['f'] = True
                wDes[3] = -wSel
            elif event.key == pygame.K_t:
                pressed['t'] = True
                wDes[4] = wSel
            elif event.key == pygame.K_g:
                pressed['g'] = True
                wDes[4] = -wSel
            elif event.key == pygame.K_c:
                wDes += wIncr
                if wDes >= wMax:
                    wDes = wMax
                elif wDes <= wMin:
                    wDes = wMin
                print(f"motor speed: {wDes}")
            elif event.key == pygame.K_x:
                wDes -= wIncr
                if wDes >= wMax:
                    wDes = wMax
                elif wDes <= wMin:
                    wDes = wMin
                print(f"motor speed: {wDes}")

        elif event.type == pygame.KEYUP:
            if event.key == pygame.K_q:
                pressed['q'] = False
                wDes[0] = 0
            elif event.key == pygame.K_a:
                pressed['a'] = False
                wDes[0] = 0
            elif event.key == pygame.K_w:
                pressed['w'] = False
                wDes[1] = 0
            elif event.key == pygame.K_s:
                pressed['s'] = False
                wDes[1] = 0
            elif event.key == pygame.K_e:
                pressed['e'] = False
                wDes[2] = 0
            elif event.key == pygame.K_d:
                pressed['d'] = False
                wDes[2] = 0
            elif event.key == pygame.K_r:
                pressed['r'] = False
                wDes[3] = 0
            elif event.key == pygame.K_f:
                pressed['f'] = False
                wDes[3] = 0
            elif event.key == pygame.K_t:
                pressed['t'] = False
                wDes[4] = 0
            elif event.key == pygame.K_g:
                pressed['g'] = False
                wDes[4] = 0
        elif event.type == pygame.QUIT:
            raise KeyboardInterrupt()
        return noInput, pressed, wSel, wDes    

def GetKeysEF(events: List["pygame.Event"], pressed: Dict[str, bool], 
              vSel: float, wSel: float, vMin: float, vMax: float, wMin: float, 
              wMax: float, efIncrL: float, efIncrR: float) -> \
              Tuple[np.ndarray, float, float, Dict[str, bool], bool]:
    """Checks for key-presses and alter velocity components
    and other factors accordingly.\n
    KEY-BINDINGS (all in the space frame {s}):
    w/s: Move in +/- x-direction.
    a/d: Move in +/- y-direction.
    z/x: Move in +/- z-direction.
    q/e: Rotate +/- around x-axis.
    r/f: Rotate +/- around y-axis.
    c/v: Rotate +/- around z-axis.
    t/y: Increment/decrement linear velocity.
    g/h: Increment/decrement angular velocity.\n
    :param events: List of pygame events for key presses.
    :param pressed: Dictionary of booleans to keep track of keyboard 
                    status.
    :param vSel: Previously selected linear velocity in [m/s].
    :param wSel: Previously selected angular velocity in [rad/s].
    :param vMin: Minimum linear end-effector velocity in [m/s].
    :param vMax: Maximum linear end-effector velocity in [m/s].
    :param wMin: Minimum angular end-effector velocity in [rad/s].
    :param wMax: Maximum angular end-effector velocity in [rad/s].
    :param efIncrL: Linear velocity increment, in [m/s].
    :param efIncrR: Rotational velocity increment, in [rad/s].
    :return V: 6x1 velocity twist.
    :return vSel: Newly selected linear velocity in [m/s].
    :return wSel: Newly selected angular velocity in [rad/s].
    :return pressed: Updated dictionary for tracking keyboard activity.
    :return noInput: Boolean indicating presence of new inputs.
    """
    V = [0 for i in range(6)]
    if len(events) == 0:
        noInput = True
        return V, vSel, wSel, noInput
    else:
        noInput = False
    for event in events:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_w:
                pressed['w'] = True
                V[3] = vSel 
            elif event.key == pygame.K_s:
                pressed['s'] = True
                V[3] = -vSel 
            elif event.key == pygame.K_a:
                pressed['a'] = True
                V[4] = vSel 
            elif event.key == pygame.K_d:
                pressed['d'] = True
                V[4] = -vSel 
            elif event.key == pygame.K_z:
                pressed['z'] = True
                V[5] = vSel 
            elif event.key == pygame.K_x:
                pressed['x'] = True
                V[5] = -vSel 
            elif event.key == pygame.K_q:
                pressed['q'] = True
                V[0] = wSel 
            elif event.key == pygame.K_e:
                pressed['e'] = True
                V[0] = -wSel 
            elif event.key == pygame.K_r:
                pressed['r'] = True
                V[1] = wSel 
            elif event.key == pygame.K_f:
                pressed['f'] = True
                V[1] = -wSel 
            elif event.key == pygame.K_c:
                pressed['c'] = True
                V[2] = wSel 
            elif event.key == pygame.K_v:
                pressed['v'] = True
                V[2] = -wSel 
            elif event.key == pygame.K_t:
                if (vSel + efIncrL) < vMax:
                    vSel += efIncrL
                else:
                    vSel = vMax
            elif event.key == pygame.K_y:
                if (vSel - efIncrL) < vMin:
                    vSel -= efIncrL
                else:
                    vSel = efIncrL
            elif event.key == pygame.K_g:
                if (wSel + efIncrR) < wMax:
                    wSel -= efIncrR
                else:
                    wSel = wMax
                print(f"linear velocity: {vSel} m/s")
            elif event.key == pygame.K_h:
                if (wSel - efIncrR) < wMin:
                    wSel -= efIncrR
                else:
                    wSel = wMin
                print(f"angular velocity: {wSel} rad/s")

        elif event.type == pygame.KEYUP:
            if event.key == pygame.K_w:
                pressed['w'] = False
                V[3] = 0
            elif event.key == pygame.K_s:
                pressed['s'] = False
                V[3] = 0
            elif event.key == pygame.K_a:
                pressed['a'] = False
                V[4] = 0
            elif event.key == pygame.K_d:
                pressed['a'] = False
                V[4] = 0
            elif event.key == pygame.K_z:
                pressed['z'] = False
                V[5] = 0
            elif event.key == pygame.K_x:
                pressed['x'] = False
                V[5] = 0
            elif event.key == pygame.K_q: 
                pressed['q'] = False
                V[0] = 0
            elif event.key == pygame.K_e:
                pressed['e'] = False
                V[0] = 0
            elif event.key == pygame.K_r:
                pressed['r'] = False
                V[1] = 0
            elif event.key == pygame.K_f:
                pressed['f'] = False
                V[1] = 0
            elif event.key == pygame.K_c:
                pressed['c'] = False 
                V[2] = 0
            elif event.key == pygame.K_v:
                pressed['v'] = False
                V[2] = 0
        elif event.type == pygame.QUIT:
            raise KeyboardInterrupt()
        return V, vSel, wSel, pressed, noInput

def HoldPos(serial: SerialData, robot: Robot, PIDObj: PID, 
            thetaDes: np.ndarray, dtHold: float):
    thetaCurr = np.array(serial.currAngle[-1]) #Minus gripper
    dThetaDes = np.array([0 for angle in thetaDes])
    ddThetaDes = np.array([0 for angle in thetaDes])
    FTip = np.array([0 for i in range(6)])
    g = np.array([0,0,-9.81])
    tauFF = FeedForward(robot, thetaDes, dThetaDes, ddThetaDes, g, FTip)
    tauPID = PIDObj.Execute(thetaDes, thetaCurr, dtHold)
    tauComm = tauFF + tauPID
    I = [Tau2Curr(tauComm[i], robot.joints[i].gearRatio, 
                  robot.joints[i].km, 2) for i in range(len(robot.joints))]
    PWM = [Curr2MSpeed(current) for current in I]
    return PWM

robotSelected = False
while not robotSelected:
    try:
        robotType = input("Please select the robot model type.\n" +\
            "For a model with friction, enter 0.\nFor a robot " +\
            "without friction, enter 1.\n")
        if robotType == "0":
            Pegasus = robotFric
            robotSelected = True
        if robotType == "1":
            Pegasus = robot
            robotSelected = True
        else:
            print("Invalid entry. Enter either '0' or '1'-0")
            raise InputError() 
    except InputError:
        continue
print("\nRobot type selected. Setting up serial communication...\n")
serial = SerialData(6, Pegasus.joints)
port = FindSerial(askInput=True)[0]
Teensy = StartComms(port)

print("\nSetting up UI...\n")
pygame.init()
screen = pygame.display.set_mode([700, 500])
background = pygame.image.load(os.path.join(current,'control_overview.png'))

method = False
frameInterval = sett['dtFrame']
lastFrame = time.perf_counter()
dtPID = sett['dtPID']
lastPID = time.perf_counter()
dtComm = sett['dtComm']
lastComm = time.perf_counter()
lastCheck = time.perf_counter()
dtFrame = sett['dtFrame']
lastHold = time.perf_counter()
dtHold = sett['dtHold']

PIDObj = sett['PID']
errThetaMax = sett['errThetaHold']
vMax = sett['vMax']
wMax = sett['wMax']
jIncr = sett['jIncr']
efIncrL = sett['eIncrLin']
efIncrR = sett['eIncrRot']
dtPosConf = sett['dtPosConfig']
forceDamp = sett['forceDamp']
M = sett['M']
B = sett['B']
Kx = sett['Kx']
Ka = sett['Ka']

#initialize empty objects
vDesJ = np.zeros(5)
vDesE = np.zeros(6)
vPrevJ = np.zeros(5)
wSelJ = 0
wSelE = 0
vSelE = 0
pressed = dict()
noInput = True
VPrev= np.zeros(6)
dthetaPrev = np.zeros(5)

methodSelected = False
while not methodSelected:
    try:
        method = input("Please enter a control method.\nFor position " +\
                    "control, type 'pos'.\nFor velocity control, " +\
                    "type 'vel'.\nFor force control, type 'force'.\n"+\
                    "For impedance control, type 'imp'.\n")
        print("\n")
        if method != 'pos' and method != 'vel' and \
        method != 'force' and method != 'imp':
            print("Invalid method. Try again.")
            raise InputError()
        else:
            methodSelected = True
    except InputError:
        continue

if method == 'vel': 
    spaceSelected = False
    while not spaceSelected:
        try:
            space = input("\nTo perform joint velocity control, type "+
                            "'joint'.\n For end-effector velocity control, "+
                            "type 'end-effector'.\n")
            if space != 'joint' and space != 'end-effector':
                raise InputError()
            else:
                spaceSelected = True
        except InputError:
            continue
elif method == 'force':
    pathSelected = False
    while not pathSelected:
        path = input("\nPlease input the path to the CSV file with " +
                     "the desired end-effector wrenches over time\n")
        try:
            with open(path) as csvFile:
                csvRead = csv.reader(csvFile)
                wrenchesList = []
                for wrenchCSV in csvRead:
                    wrenchesList.append(np.array(wrenchCSV))
            pathSelected = True
        except FileNotFoundError:
            print("Incorrect path.")
            continue
    dtKnown = False
    while not dtKnown:
        try:
            dtWrench = float(input("Time between wrenches in the CSV file in [s]: "))
            dtKnown = True
        except ValueError:
            print("Invalid input. Please input a time in [s].")
elif method == 'imp':
    #Get robot into desired position.
    sConfig = np.array(serial.currAngle)
    eConfig = GetEConfig(sConfig)[1]
    if eConfig.shape != (4,4):
        TDes = FKSpace(Pegasus.TsbHome, Pegasus.screwAxes, eConfig)
    else:
        TDes = eConfig

while True: #Main loop!
    try:
        if method == 'pos': #Position control
            sConfig = np.array(serial.currAngle[:-1])
            sConfig, eConfig = GetEConfig(sConfig, robot)
            try:
                PosControl(sConfig, eConfig, Pegasus, serial, dtPosConf, 
                           vMax, wMax, PIDObj, dtComm, dtPID, dtFrame, Teensy, screen, background)
            except SyntaxError as e:
                print(e.msg)
                continue
            #Initiate hold-pos
            PIDObj.Reset()
            thetaDes = eConfig #exclude gripper
            #Initialize with high value
            errThetaCurr = np.array([100*np.pi for i in serial.currAngle[:-1]])
            print("Stabilizing around new position...")
            while all(np.greater(errThetaCurr, errThetaMax)):
                if time.perf_counter() - lastHold >= dtHold: 
            #While not stabilized within error bounds, do holdpos
                    serial.mSpeed[:-1] = HoldPos(serial, robot, PIDObj, thetaDes, 
                                            dtHold)
                    lastHold = time.perf_counter()

                lastCheck = SReadAndParse(serial, lastCheck, dtComm, Teensy)[0]
                if (time.perf_counter() - lastComm >= dtComm):
                    errThetaCurr = thetaDes - np.array(serial.currAngle[:-1])
                    serial.rotDirDes = [1 if np.sign(speed) == 1 else 0 for 
                                        speed in serial.mSpeed]
                    for i in range(serial.lenData-1): 
                        serial.dataOut[i] = f"{serial.mSpeed[i]}|"+\
                                            f"{serial.rotDirDes[i]}"
                    serial.dataOut[-1] = f"{0|0}"
                    Teensy.write(f"{serial.dataOut}\n".encode('utf-8')) 
                    lastComm = time.perf_counter()
            print("Stabilization complete.")
            PIDObj.Reset()

        
        elif method == 'vel': #Velocity Control
            PIDObj.Reset()
            if space == 'joint':
                if time.perf_counter() - lastPID > dtPID:
                    #VelControl implicitely updates serial.mSpeed.
                    vPrevJ = VelControl(Pegasus, serial, vDesJ, vPrevJ, dtPID, 
                                        'joint', dtComm, PIDObj) #FF & PID!
                    lastPID = time.perf_counter()

                if time.perf_counter() - lastFrame >= dtFrame:
                    events = pygame.event.get() #To interact with pygame, avoids freezing.
                    for event in events:
                        if event.type == pygame.QUIT:
                            raise KeyboardInterrupt
                        noInput, pressed, wSelJ, vDesJ = GetKeysJoint(events, pressed, 0, wMax, wSelJ, jIncr)
                    screen.blit(background, (0,0))
                    lastFrame = time.perf_counter()
            else:
                if time.perf_counter() - lastPID > dtPID:
                    #VelControl implicitely updates serial.mSpeed.
                    vPrevJ = VelControl(Pegasus, serial, vDesE, vPrevJ, dtPID, 
                                        'twist', dtComm, PIDObj) #FF & PID!
                    lastPID = time.perf_counter()

                if time.perf_counter() - lastFrame >= dtFrame:
                    events = pygame.event.get() #To interact with pygame, avoids freezing.
                    for event in events:
                        if event.type == pygame.QUIT:
                            raise KeyboardInterrupt
                        V, vSelE, wSelE, pressed, noInput = \
                        GetKeysEF(events, pressed, vSelE, wSelE, 0, vMax, 0, 
                                  wMax, efIncrL, efIncrR)
                    screen.blit(background, (0,0))
                    lastFrame = time.perf_counter()

            lastCheck = SReadAndParse(serial, lastCheck, dtComm, Teensy)[0]
            if (time.perf_counter() - lastWrite >= dtComm):
                serial.rotDirDes = [1 if np.sign(speed) == 1 else 0 for 
                                    speed in serial.mSpeed[:-1]]
                for i in range(serial.lenData-1): #TODO: Add Gripper function
                    serial.dataOut[i] = f"{serial.mSpeed[i]}|"+\
                                        f"{serial.rotDirDes[i]}"
                    #TODO: Replace last entry w/ gripper commands
                    serial.dataOut[-1] = f"{0|0}"
                    Teensy.write(f"{serial.dataOut}\n".encode('utf-8')) 
                    lastWrite = time.perf_counter()
        
        elif method == 'force': #Force control
            PIDObj.Reset()
            n = -1 #iterator
            startTime = time.perf_counter()
            while time.perf_counter() <= dtWrench*len(wrenchesList):
                nPrev = n
                n = round((time.perf_counter()-startTime)/dtWrench)
                if n >= len(wrenchesList):
                    #Initiate hold-pos
                    PIDObj.Reset()
                    thetaDes = eConfig
                    errThetaCurr = np.array([100*np.pi for i in serial.currAngle[:-1]])
                    print("Stabilizing around new position...")
                    while all(np.greater(errThetaCurr, errThetaMax)):
                        if time.perf_counter() - lastHold >= dtHold: 
                    #While not stabilized within error bounds, do holdpos
                            serial.mSpeed[:-1] = HoldPos(serial, robot, PIDObj, thetaDes, 
                                                    dtHold)
                            lastHold = time.perf_counter()

                        lastCheck = SReadAndParse(serial, lastCheck, dtComm, Teensy)[0]
                        if (time.perf_counter() - lastWrite >= dtComm):
                            errThetaCurr = thetaDes - serial.currAngle
                            serial.rotDirDes = [1 if np.sign(speed) == 1 else 0 for 
                                                speed in serial.mSpeed]
                            for i in range(serial.lenData-1): 
                                serial.dataOut[i] = f"{serial.mSpeed[i]}|"+\
                                                    f"{serial.rotDirDes[i]}"
                            serial.dataOut[-1] = f"{0|0}"
                            Teensy.write(f"{serial.dataOut}\n".encode('utf-8')) 
                            lastWrite = time.perf_counter()
                    print("Stabilization complete.")
                    PIDObj.Reset()
                    raise KeyboardInterrupt
                if n != nPrev:
                    ForceControl(Pegasus, serial, wrenchesList[n], forceDamp, dtWrench)
                
                if time.perf_counter() - lastFrame >= dtFrame:
                            events = pygame.event.get() #avoids freezing.
                            for event in events:
                                if event.type == pygame.QUIT:
                                    raise KeyboardInterrupt
                            screen.blit(background, (0,0))
                            lastFrame = time.perf_counter()

                lastCheck = SReadAndParse(serial, lastCheck, dtComm, Teensy)[0]
                if (time.perf_counter() - lastWrite >= dtComm):
                    serial.rotDirDes = [1 if np.sign(speed) == 1 else 0 for 
                                        speed in serial.mSpeed]
                    for i in range(serial.lenData-1): #TODO: Add Gripper function
                        serial.dataOut[i] = f"{serial.mSpeed[i]}|"+\
                                            f"{serial.rotDirDes[i]}"
                        #TODO: Replace last entry w/ gripper commands
                        serial.dataOut[-1] = f"{0|0}"
                        Teensy.write(f"{serial.dataOut}\n".encode('utf-8')) 
                        lastWrite = time.perf_counter()
        
        elif method == 'imp': #Impedance control
            if time.perf_counter() - lastPID > dtPID:
                VPrev, dthetaPrev = ImpControl(Pegasus, serial, TDes, VPrev, dthetaPrev, dtPID, M, B, Kx, Ka, PIDObj)
            if time.perf_counter() - lastFrame >= dtFrame:
                events = pygame.event.get() #avoids freezing.
                for event in events:
                    if event.type == pygame.QUIT:
                        raise KeyboardInterrupt
                screen.blit(background, (0,0))
                lastFrame = time.perf_counter()

            lastCheck = SReadAndParse(serial, lastCheck, dtComm, Teensy)[0]
            if (time.perf_counter() - lastWrite >= dtComm):
                serial.rotDirDes = [1 if np.sign(speed) == 1 else 0 for 
                                    speed in serial.mSpeed]
                for i in range(serial.lenData-1): #TODO: Add Gripper function
                    serial.dataOut[i] = f"{serial.mSpeed[i]}|"+\
                                        f"{serial.rotDirDes[i]}"
                    #TODO: Replace last entry w/ gripper commands
                    serial.dataOut[-1] = f"{0|0}"
                    Teensy.write(f"{serial.dataOut}\n".encode('utf-8')) 
                    lastWrite = time.perf_counter()
    except KeyboardInterrupt:
        print("Ctrl+C pressed, Quitting...") 
        #Set motor speeds to zero & close serial.
        Teensy.write(f"{['0|0'] * serial.lenData}\n".encode("utf-8"))
        time.sleep(dtComm)
        Teensy.__del__()
        print("Quitting...")

    except:
        #Set motor speeds to zero & close serial.
        Teensy.write(f"{['0|0'] * serial.lenData}\n".encode("utf-8"))
        time.sleep(dtComm)
        Teensy.__del__()
        print("Quitting...")
        raise #Reraise the error

