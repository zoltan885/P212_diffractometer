#!/home/hegedues/miniforge3/envs/pyfai/bin/python
# -*- coding: utf-8 -*-
"""
Created on Tue Oct 24 09:45:55 2023

@author: hegedues
"""

import sys
import os
import psutil
import time
import datetime
import logging
logFormatter = logging.Formatter("%(asctime)-25.25s %(threadName)-12.12s %(name)-25.24s %(levelname)-10.10s %(message)s")
rootLogger = logging.getLogger()
rootLogger.setLevel(logging.INFO)
#logging.getLogger().setLevel(logging.DEBUG)
fileHandler = logging.FileHandler(os.path.join(os.getcwd(), 'log.log'))
fileHandler.setFormatter(logFormatter)
rootLogger.addHandler(fileHandler)

consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
rootLogger.addHandler(consoleHandler)


import glob

import multiprocessing
from multiprocessing import Event, Process, Queue, Pool
from threading import Thread
import queue
from pathlib import Path



from PyQt5 import QtWidgets, uic, QtGui
from PyQt5.QtCore import QRunnable, Qt, QThreadPool, pyqtSignal, QThread, QObject, pyqtSlot, QTimer

from PyQt5.QtGui import QPixmap

from PyQt5.QtWidgets import (
    QMainWindow,
    QLabel,
    QGridLayout,
    QWidget,
    QPushButton,
    QProgressBar,
    QFileDialog,
    QSizePolicy,
    )

try:
    import PyTango as PT
    TANGO = True
except ImportError as e:
    logging.warning(f"{e}")



# resource:
# https://doc.qt.io/qt-5/stylesheet-examples.html


_coolBlue = '#0d6efd'

_TangoStateColors = {'ON': '#42f545',
                     'OFF': '#f4f7f2',
                     'MOVING': '#427ef5',
                     'STANDBY': '#f5f253',
                     'FAULT': '#cc2b2b',
                     'INIT': '#daa06d',
                     'ALARM': '#eb962f',
                     'DISABLE': '#f037fa',
                     'UNKNOWN': '#808080'}

mots = {'idtz2': 'p21/motor/eh3_u1.06',
        'idty2': 'p21/motor/eh3_u1.05',
        'idtx2': 'p21/motor/eh3_u1.10',
        'idry2': 'p21/motor/eh3_u1.04',
        'idrx2': 'p21/motor/eh3_u1.09',
        'idrz1': 'p21/motor/eh3_u2.05',
        'idty1': 'p21/motor/eh3_u1.14',
        'idry1': 'p21/motor/eh3_u1.13'}


FASTTIMER = 0.1
SLOWTIMER = 1

PROGRESS = '|-'

class myQLabel(QLabel):
    '''
    This class is supposed to resize the label on size change, but does not yet work properly
    https://stackoverflow.com/questions/29852498/syncing-label-fontsize-with-layout-in-pyqt
    '''
    def __init__(self, *args, **kargs):
        super(myQLabel, self).__init__(*args, **kargs)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored))
        self.setMinSize(14)

    def setMinSize(self, minfs):
        f = self.font()
        f.setPixelSize(minfs)
        br = QtGui.QFontMetrics(f).boundingRect(self.text())
        self.setMinimumSize(br.width(), br.height())

    def resizeEvent(self, event):
        super(myQLabel, self).resizeEvent(event)
        if not self.text():
            return
        # --- fetch current parameters ----
        f = self.font()
        cr = self.contentsRect()
        # --- iterate to find the font size that fits the contentsRect ---
        dw = event.size().width() - event.oldSize().width()   # width change
        dh = event.size().height() - event.oldSize().height()  # height change
        print(f'resize: {dw} {dh}')
        fs = max(f.pixelSize(), 1)
        while True:
            f.setPixelSize(fs)
            br = QtGui.QFontMetrics(f).boundingRect(self.text())
            if dw >= 0 and dh >= 0:  # label is expanding
                if br.height() <= cr.height() and br.width() <= cr.width():
                    fs += 1
                else:
                    f.setPixelSize(max(fs - 1, 1))  # backtrack
                    break
            else:  # label is shrinking
                if br.height() > cr.height() or br.width() > cr.width():
                    fs -= 1
                else:
                    break
            if fs < 1:
                break
        # --- update font size ---
        self.setFont(f)






class MainWidget(QtWidgets.QWidget):
    def __init__(self, *args, **kwargs):
        super(MainWidget, self).__init__(*args, **kwargs)
        uic.loadUi('diffractometerGUI.ui', self)
        t0 = time.time()

        self.mot = {}
        font = self.frame.font()
        font.setPointSize(50)
        grid = QGridLayout()
        for i,(k,v) in enumerate(mots.items()):
            self.mot[k] = {}

            # name labels
            self.mot[k]['label'] = QLabel(k)
            self.mot[k]['label'].setStyleSheet('''QLabel {
                                                        font-size: 30px;
                                                        font-weight: 600;
                                                        }''')

            # position labels
            self.mot[k]['value'] = QLabel('position')
            self.mot[k]['value'].setStyleSheet('''QLabel {
                                                        color: #0d6efd;
                                                        font-size: 30px;
                                                        font=weight: 600;
                                                        border-radius: 5px;
                                                        border: 2px solid #0d6efd;
                                                        }''')

            self.mot[k]['state'] = QPushButton('state')
            self.mot[k]['state'].setStyleSheet('''QPushButton {
                                                            color: #fff;
                                                            font-weight: 600;
                                                            border-radius: 5px;
                                                            border: 1px solid #0d6efd;
                                                            padding: 5px 15px;
                                                            outline: 0px;
                                                            font-size: 30px;
                                                            }''')
            self.mot[k]['state'].setStyleSheet("QPushButton {background-color: %s}" % _TangoStateColors['UNKNOWN'])

            grid.addWidget(self.mot[k]['label'], i, 0)
            grid.addWidget(self.mot[k]['value'], i, 1)
            grid.addWidget(self.mot[k]['state'], i, 2)
            try:
                self.mot[k]['DeviceProxy'] = PT.DeviceProxy('tango://hasep21eh3:10000/%s' % v)
                logging.info(f"{k} connected")
            except:
                self.mot[k]['DeviceProxy'] = None
                logging.error(f"Failed to connect to {k}")


        self.frame_2.setLayout(grid)

        self.label_pixmap.setPixmap(QPixmap('./drawing.png'))
        self.label_pixmap.setScaledContents(True)


        self.timerSlow = QTimer()
        self.timerSlow.start(int(1000*SLOWTIMER))
        self.timerFast = QTimer()
        self.timerFast.start(int(1000*FASTTIMER))

        self.timerFast.timeout.connect(self.update_states_pos)


    def _upd(self, *args):
        key = args[0]
        position = self.mot[key]['DeviceProxy'].position
        self.mot[key]['value'].setText(f"{position:.4f}")
        state = str(self.mot[key]['DeviceProxy'].state())
        self.mot[key]['state'].setStyleSheet('QPushButton {background-color: %s}' % _TangoStateColors[state])
        self.mot[key]['state'].setText(state)


    def update_states_pos(self):
        threads = []
        for i, k in enumerate(self.mot.keys()):
            thread = Thread(target=self._upd, args=(k,))
            threads.append(thread)
        for t in threads:
            t.start()
        time.sleep(FASTTIMER)
        self.label.setText(PROGRESS[(time.time()-self.t0) % len(PROGRESS)])
        for t in threads:
            t.join()

        #with Pool(len(self.mot.keys())) as p:
            #DPs = [self.mot[k]['DeviceProxy'] for k in self.mot.keys()]  # this is not picklable
            #labels = [self.mot[k]['value'] for k in self.mot.keys()]
            #btns = [self.mot[k]['state'] for k in self.mot.keys()]
            #p.map(self._upd, [(self, k) for k in self.mot.keys()])




def exitHandler():
    print('BYE')


def mainGUI():
    app = QtWidgets.QApplication(sys.argv)
    app.aboutToQuit.connect(exitHandler)
    #app.setStyleSheet(Path('style.qss').read_text())
    main = MainWidget()
    main.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    mainGUI()
















