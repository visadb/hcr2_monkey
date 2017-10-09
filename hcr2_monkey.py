# -*- coding: utf-8 -*-
from time import sleep, strftime, time
from com.android.monkeyrunner import MonkeyRunner, MonkeyDevice
from java.awt import Color
from javax.swing import AbstractAction, BoxLayout, JComponent, JFrame, JLabel, KeyStroke
from threading import Thread
from datetime import datetime, timedelta
import socket
import os
import signal
import sys
import tempfile

def total_seconds(td):
    return td.seconds + td.microseconds/1e6

class MenuAction(AbstractAction):
    def __init__(self, cb, key, desc, parentMenu):
        AbstractAction.__init__(self)
        self.cb = cb
        self.key = key
        self.desc = desc
        self.parentMenu = parentMenu
    def actionPerformed(self, actionEvent):
        from java.lang import Thread, ThreadDeath
        def resetParentMenu():
            label = self.parentMenu.actionLabels[self.key]
            label.setBackground(self.parentMenu.defaultBackground)
            label.setForeground(Color.black)
            self.parentMenu.frame.title = self.parentMenu.titleBase
            self.parentMenu.actionThread = None

        if self.parentMenu.actionThread != None and self.key == "ESCAPE":
            self.parentMenu.actionThread.stop()
            resetParentMenu()
            return
        if self.parentMenu.actionThread != None and self.key == "R":
            self.cb()
            return
        elif self.parentMenu.actionThread != None:
            return
        print "Running action:", self.desc
        self.parentMenu.frame.title = self.parentMenu.titleBase+", "+self.desc+"..."
        label = self.parentMenu.actionLabels[self.key]
        label.setBackground(Color.red)
        label.setForeground(Color.yellow)
        def runCbAndResetMenu():
            try:
                self.cb()
            except ThreadDeath:
                print "Action aborted:", self.desc
            finally:
                resetParentMenu()
        self.parentMenu.actionThread = Thread(runCbAndResetMenu)
        self.parentMenu.actionThread.start()

class ActionMenu:
    def __init__(self):
        self.titleBase = 'HCR2 Monkey'
        self.frame = JFrame(self.titleBase, defaultCloseOperation = JFrame.EXIT_ON_CLOSE, size=(300,250))
        self.inputMap = self.frame.getRootPane().getInputMap(JComponent.WHEN_IN_FOCUSED_WINDOW)
        self.actionMap = self.frame.getRootPane().getActionMap()
        self.actionLabels = {}
        self.actionThread = None

        self.defaultBackground = self.frame.getBackground()
        self.frame.getContentPane().setLayout(BoxLayout(self.frame.getContentPane(), BoxLayout.Y_AXIS))

        self.addAction("ESCAPE", "Abort current action", lambda: None)
    def addAction(self, key, desc, cb):
        if " " in key:
            strokeString = key
        else:
            strokeString = "pressed "+key

        stroke = KeyStroke.getKeyStroke(strokeString)
        if stroke == None:
            raise ValueError("Invalid key: "+str(key))
        self.inputMap.put(stroke, key)
        self.actionMap.put(key, MenuAction(cb, key, desc, self))
        self.actionLabels[key] = JLabel(key+": "+desc)
        self.actionLabels[key].setOpaque(True)
        self.frame.getContentPane().add(self.actionLabels[key])
    def run(self):
        print "Starting menu"
        self.frame.visible = True
        while True:
            sleep(300)

class GameState(object):
    MAINSTATE_INGAME   = "main_ingame"
    MAINSTATE_UNKNOWN  = "main_unknown"
    MAINSTATES = [MAINSTATE_INGAME, MAINSTATE_UNKNOWN]

    def __init__(self, mainState, subState, timestamp):
        self.mainState = mainState
        self.subState = subState
        self.timestamp = timestamp

    def getMainState(self):
        return self._mainState
    def setMainState(self, val):
        if val not in self.MAINSTATES:
            raise ValueError("invalid mainState: "+str(val))
        self._mainState = val
    mainState = property(getMainState, setMainState)

    def __str__(self):
        return "GameState(%s, %s, %s)" % (self.mainState, self.subState, self.timestamp)

class GameStateDetector:
    def __init__(self, monkeydevice):
        self.device = monkeydevice

        # subImageDetectionSpecs: (BufferedImage, (x,y,w,h), requiredSimilarityPercent)
        self.inGameDetection = (self.readImg("in_game_rpm_edge.png"), (484,647,19,4), 99.3)
        self.distanceNumberRects = [
                (577, 641, 16, 20),
                (561, 641, 16, 20),
                (544, 641, 16, 20),
                (527, 641, 16, 20),
                ]
        self.modelNumbers = [self.readImg(str(i)+".png") for i in range(0,10)]
        self.modelBlankNumber = self.readImg("blank_num.png")

    @staticmethod
    def readImg(filename):
        from java.io import File
        from javax.imageio import ImageIO
        import sys, os
        scriptDir = os.path.dirname(sys.argv[0])
        return ImageIO.read(File(os.path.join(scriptDir, "stateDetectionImages", filename)))

    def readDistance(self, shot):
        return sum([self.readDistanceNumber(slot, shot)*10**slot for slot in range(4)])

    def readDistanceNumber(self, slot, shot):
        rect = self.distanceNumberRects[slot]
        if self.checkSubImage((self.modelBlankNumber, rect, 97.0), shot):
            #print("Slot %d is blank" % slot)
            return 0

        minDissimilarity, minCand = 1e300, 0
        for cand in range(0, 10):
            subImageDetectionSpec = (self.modelNumbers[cand], rect, 95.0)
            dissimilarity, maxDissimilarity, _ = self.imageDissimilarity(subImageDetectionSpec, shot)
            if float(dissimilarity)/maxDissimilarity < 0.005:
                #print("Obvious cand %d for slot %d, %f/%f - %f" % (cand, slot, dissimilarity, maxDissimilarity, float(dissimilarity)/maxDissimilarity))
                return cand
            if dissimilarity < minDissimilarity:
                minDissimilarity = dissimilarity
                minCand = cand
        return minCand


    def imageDissimilarity(self, subImageDetectionSpec, shot=None):
        shot = shot or self.device.takeSnapshot()
        imagedata, rect, requiredSimilarityPercent = subImageDetectionSpec
        subImageOnScreen = shot.getSubImage(rect)

        maxDissimilarity = rect[2]*rect[3]*0xff*3
        maxAllowedDissimilarity = max(0, maxDissimilarity * (100.0-requiredSimilarityPercent)/100.0)
        dissimilarity = 0
        for y in range(rect[3]):
            for x in range(rect[2]):
                #screenshotCoords = self.horizontalCoordsToScreenshotCoords((x,y), rect[3])
                screenPixel = subImageOnScreen.getRawPixelInt(x,y) & 0xffffff
                subImagePixel = imagedata.getRGB(x,y) & 0xffffff
                #print "comparing image %s 0x%x with screen %s 0x%x" % ((x,y), subImagePixel, screenshotCoords, screenPixel)
                dissimilarity += self.getPixelDissimilarity(screenPixel, subImagePixel)
                if dissimilarity > maxAllowedDissimilarity:
                    break
        #print "Dissimilarity %.1f/%.1f" % (dissimilarity, maxAllowedDissimilarity)
        return dissimilarity, maxDissimilarity, maxAllowedDissimilarity


    def checkSubImage(self, subImageDetectionSpec, shot=None):
        dissimilarity, _, maxAllowedDissimilarity = self.imageDissimilarity(subImageDetectionSpec, shot)
        return dissimilarity <= maxAllowedDissimilarity

    @staticmethod
    def getPixelDissimilarity(color1, color2):
        dissimilarity = 0
        for component in range(3):
            componentVal1 = GameStateDetector.getColorComponent(color1, component)
            componentVal2 = GameStateDetector.getColorComponent(color2, component)
            dissimilarity += abs(componentVal1 - componentVal2)
        return dissimilarity
    @staticmethod
    def getColorComponent(color, componentNumber):
            return (color & (0xff << (componentNumber*8))) >> (componentNumber*8)

    def getMainState(self, shot):
        if self.checkSubImage(self.inGameDetection, shot): return GameState.MAINSTATE_INGAME
        else: return GameState.MAINSTATE_UNKNOWN

    def getSubState(self, mainState, shot):
        if mainState == GameState.MAINSTATE_INGAME:
            distance = self.readDistance(shot)
            return distance
        else:
            return None

    def getGameState(self):
        timestamp = datetime.now()
        shot = self.device.takeSnapshot()
        mainState = self.getMainState(shot)

        return GameState(mainState, self.getSubState(mainState, shot), timestamp)


class MonkeyActions:
    printed = False

    leftPedal = (250, 232)
    rightPedal = (250, 2304)

    breakPedal = (330,470)
    throttlePedal = (1120,719)
    startAndNext = (1170,636)

    countrysideLevel = (990,360)
    forestLevel = (945,575)
    cityLevel = (720,719)

    def __init__(self):
        signal.signal(signal.SIGINT, self.exitGracefully)
        self.readParams()
        #self.startMinitouch()
        self.device = MonkeyRunner.waitForConnection(1, "ce061716ad19601e0d7e")
        self.gameStateDetector = GameStateDetector(self.device)
        self.gameStateHistory = []
        self.lastParams = ()
        self.lastBoost = datetime.now()
        #self.connectToMinitouch()
        #self.lastMainState = None

    def readParams(self):
        params_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'params')
        f = open(params_file, 'r')
        self.stuckCutoffTime, self.stuckBoostTime, self.boostMinInterval = stuckParams = eval(f.readline())
        self.params = []
        while True:
            line = f.readline()
            if len(line.strip()) == 0:
                break
            paramtuple = eval(line)
            if len(paramtuple) != 5:
                raise SyntaxError()
            self.params.append(paramtuple)
        f.close()
        print "Read params: %s, %s" % (stuckParams, self.params)

    def getParams(self, distance):
        for i in range(len(self.params) - 1, -1, -1):
            if distance >= self.params[i][0]:
                return self.params[i][1:]

    def exitGracefully(self, signum, frame):
        signal.signal(signal.SIGINT, signal.getsignal(signal.SIGINT))
        self.killAllMonkeys()
        sys.exit(1)

    def killAllMonkeys(self):
        try:
            self.device.shell('killall com.android.commands.monkey')
        except:
            print "Error killing monkeys"

    def startMinitouch(self):
      def threadCode():
        os.system("adb shell /data/local/tmp/minitouch")
      Thread(target=threadCode).start()
      os.system("adb forward tcp:1111 localabstract:minitouch")

    def connectToMinitouch(self):
        self.socket = None
        for res in socket.getaddrinfo("localhost", 1111, socket.AF_UNSPEC, socket.SOCK_STREAM):
            af, socktype, proto, canonname, sa = res
            try:
                self.socket = socket.socket(af, socktype, proto)
            except socket.error:
                self.socket = None
                continue
            try:
                self.socket.connect(sa)
            except socket.error:
                self.socket.close()
                self.socket = None
                continue
            break
            if self.socket is None:
              raise RuntimeError("socket probulemu")


    def screenshot(self):
        shot = self.device.takeSnapshot()
        filename = strftime("%Y-%m-%d_%H%M%S.png")
        dirPath = os.path.join(tempfile.gettempdir(), "ff3_monkey")
        pathToFile = os.path.join(dirPath, filename)
        if not os.path.exists(dirPath):
            os.mkdir(dirPath)

        print "Writing screenshot to", pathToFile
        shot.writeToFile(pathToFile)

    def touch_down(self, contact, coords):
        self.socket.sendall("d %d %d %d 50\n" % (contact, coords[0], coords[1]))

    def touch_up(self, contact):
        self.socket.sendall("u %d\n" % (contact,))

    def touch_commit(self):
        self.socket.sendall("c\n")

    def tap(self, coords, timePressed=0.01, delayAfter=0.010):
        self.touch_down(0, coords)
        self.touch_commit()
        sleep(timePressed)
        self.touch_up(0)
        self.touch_commit()
        sleep(delayAfter)

    def tapStart(self):
        self.tap((433, 2047))

    def pressBack(self, delayAfter=0.150):
        self.device.press("KEYCODE_BACK", MonkeyDevice.DOWN_AND_UP)
        sleep(delayAfter)

    def pressCountryside(self):
        self.device.touch(self.countrysideLevel[0], self.countrysideLevel[1], MonkeyDevice.DOWN_AND_UP)

    def pressForest(self):
        self.device.touch(self.forestLevel[0], self.forestLevel[1], MonkeyDevice.DOWN_AND_UP)

    def pressCity(self):
        self.device.touch(self.cityLevel[0], self.cityLevel[1], MonkeyDevice.DOWN_AND_UP)

    def pressNextOrStart(self):
        self.device.touch(self.startAndNext[0], self.startAndNext[1], MonkeyDevice.DOWN_AND_UP)

    def pressBreak(self, time=0.02):
        self.device.drag(self.breakPedal, self.breakPedal, time)

    def pressThrottle(self, time=1.1):
        self.device.drag(self.throttlePedal, self.throttlePedal, time, 1)

    def hiirThrottle(self, time, maxTDur, breakT, sleepT):
        for i in range(0, int(time/maxTDur)):
            self.pressThrottle(maxTDur)
            if breakT > 0:
                self.pressBreak(breakT)
            if sleepT > 0:
                sleep(sleepT)
        if time%maxTDur > 0.03:
            self.pressThrottle(time%maxTDur)

    def testHiirThrottle(self):
        self.hiirThrottle(0.54, 0.25, 0.0, 0.08)


    def getMainState(self):
        self.lastMainState = self.gameStateDetector.getGameState().getMainState()
        return self.lastMainState


    def grindOnce(self):
        self.pressCountryside()
        self.pressNextOrStart()

        latestGameStates = self.gameStateHistory[-20:]
        if len(latestGameStates) == 0:
            self.pressCountryside()
            self.pressNextOrStart()
            self.pressThrottle(1.0)
            return
        elif latestGameStates[-1].mainState == GameState.MAINSTATE_UNKNOWN:
            print("Unknown state...")
            self.pressCountryside()
            self.pressNextOrStart()
            sleep(0.1)
        elif latestGameStates[-1].mainState == GameState.MAINSTATE_INGAME:
            latestGameState = latestGameStates[-1]
            print("%s: %s" % (latestGameState.timestamp, latestGameState.subState))

            self.boostIfStuckAssumingInGame(latestGameStates)

            t, s1, b, s2 = params = self.getParams(latestGameState.subState)
            if params != self.lastParams:
                print "Params changed: %s" % (params,)
                self.lastParams = params
            #print("Using params %s" % (params,))
            self.pressThrottle(t)
            if s1 > 0:
                sleep(s1)
            if b > 0:
                self.pressBreak(b)
            if s2 > 0:
                sleep(s2)

    def boostIfStuckAssumingInGame(self, latestGameStates):
        latestGameState = latestGameStates[-1]
        if latestGameState.subState == 0:
            return
        cutoffTime = datetime.now() - timedelta(seconds=self.stuckCutoffTime)
        sameDistanceSinceCutoffTime = [state.mainState == GameState.MAINSTATE_INGAME and state.subState == latestGameState.subState
            for state in latestGameStates
            if state.timestamp > cutoffTime]
        stuck = len(sameDistanceSinceCutoffTime) > 1 and all(sameDistanceSinceCutoffTime)
        if stuck:
            seconds_since_last_boost = total_seconds(datetime.now() - self.lastBoost)
            if seconds_since_last_boost > self.boostMinInterval:
                print "Stuck, BOOST!"
                self.lastBoost = datetime.now()
                self.pressThrottle(self.stuckBoostTime)
            else:
                print "Skipping boost as only %0.2fs / %0.2fs since last boost" % (seconds_since_last_boost, self.boostMinInterval)

    def grindForever(self):
        self.readParams()
        while True:
            self.grindOnce()

    def printCurrentState(self):
        print self.gameStateDetector.getGameState()

    def quit(self):
        from java.lang import System
        print "Quitting..."
        self.killAllMonkeys()
        System.exit(0)

    def readGameStateForever(self):
        while True:
            self.gameStateHistory.append(self.gameStateDetector.getGameState())
            size = len(self.gameStateHistory)
            if size >= 2 and self.gameStateHistory[-2].mainState == GameState.MAINSTATE_INGAME and self.gameStateHistory[-1].mainState == GameState.MAINSTATE_UNKNOWN:
                print "Died at %d" % self.gameStateHistory[-2].subState

            if size > 100:
                self.gameStateHistory = self.gameStateHistory[(size-50):]
            #print(self.gameStateHistory)

    def startReadingGameState(self):
        Thread(target=self.readGameStateForever).start()

    def addMenuActions(self, menu):
        menu.addAction("S", "Take screenshot", self.screenshot)
        menu.addAction("MINUS", "Print game state to stdout", self.printCurrentState)
        menu.addAction("P", "Press break", self.pressBreak)
        menu.addAction("L", "Select level", self.pressCity)
        menu.addAction("N", "Press next or start", self.pressNextOrStart)
        menu.addAction("T", "Throttle", self.pressThrottle)
        menu.addAction("H", "Hiir-throttle", self.testHiirThrottle)
        menu.addAction("B", "Back", self.pressBack)
        menu.addAction("G", "Grind once", self.grindOnce)
        menu.addAction("F", "grind Forever", self.grindForever)
        menu.addAction("R", "Reload params", self.readParams)
        menu.addAction("Q", "Quit", self.quit)

def main():
    menu = ActionMenu()
    ma = MonkeyActions()
    ma.addMenuActions(menu)
    ma.startReadingGameState()
    menu.run()

main()
