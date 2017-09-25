The purpose of this project is to automate repetitive tasks in the Android
version of Final Fantasy III. ff3\_monkey is based on monkeyrunner from Android
Development Tools. It has a simple GUI that acts as a menu to launch various
monkeyrunner macros.

![Screenshot of ff3\_monkey GUI](https://raw.github.com/yarogami/ff3_monkey/master/gui_screenshot.png)

Currently ff3\_monkey is capable of fully autonomous exp training in Bahamut's
lair. See [a demo in YouTube](http://youtu.be/mRf27ptouD4).

ff3\_monkey has been tested on Linux (Debian testing), OS X 10.8 and Windows 7.
It requires the [Android Development
Tools](http://developer.android.com/tools/help/adt.html) and [Jython
2.5.x](http://www.jython.org/downloads.html). To run it, simply run
`monkeyrunner ff3_monkey.py`.

Note: The game needs to be set up in a specific way for this to work: default
names for characters, items and spells in specific places etc... Furthermore,
ff3\_monkey will only work on devices with a 720x1280 screen.

