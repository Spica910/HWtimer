import sys
import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QListWidget, QCheckBox, QRubberBand, QListWidgetItem
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal, QRect, QPoint, QSize, QElapsedTimer
from PyQt5.QtGui import QFont, QPainter, QPen, QColor
import ctypes
import pyautogui

# SetThreadExecutionState 함수 정의
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

# SetThreadExecutionState 함수 로드
try:
    SetThreadExecutionState = ctypes.windll.kernel32.SetThreadExecutionState
except AttributeError:
    SetThreadExecutionState = None

class FlipClockLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFont(QFont("Arial", 48))  # 큰 글꼴 설정
        self.setAlignment(Qt.AlignCenter)

    def setTextWithFlip(self, text):
        current_text = self.text()
        if current_text != text:
            self.setText(text)  # 새로운 텍스트로 변경
            print(f"Flipping from {current_text} to {text}")  # 디버깅용 출력

class ScreenMonitor(QThread):
    color_changed = pyqtSignal(tuple)

    def __init__(self, region):
        super().__init__()
        self.region = region
        self.running = False

    def run(self):
        self.running = True
        previous_color = None

        while self.running:
            try:
                screenshot = pyautogui.screenshot(region=self.region)
                frame = np.array(screenshot)
                if frame.size == 0:
                    raise ValueError("Empty frame captured")
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # 특정 영역의 평균 색상 계산
                current_color = cv2.mean(frame)[:3]

                if previous_color is not None:
                    # 색상 변화 감지
                    if np.linalg.norm(np.array(current_color) - np.array(previous_color)) > 50:
                        self.color_changed.emit(current_color)

                previous_color = current_color
            except Exception as e:
                print(f"Error capturing screenshot: {e}")
            self.msleep(100)  # 100ms마다 화면을 모니터링

    def stop(self):
        self.running = False
        self.wait()

class RegionSelector(QWidget):
    region_selected = pyqtSignal(QRect)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Select Region')
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.showFullScreen()
        self.rubber_band = QRubberBand(QRubberBand.Rectangle, self)
        self.origin = QPoint()

    def mousePressEvent(self, event):
        self.origin = event.pos()
        self.rubber_band.setGeometry(QRect(self.origin, QSize()))
        self.rubber_band.show()

    def mouseMoveEvent(self, event):
        self.rubber_band.setGeometry(QRect(self.origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        self.rubber_band.hide()
        selected_region = self.rubber_band.geometry()
        self.region_selected.emit(selected_region)
        self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))  # 반투명 검정색 배경

class Overlay(QWidget):
    def __init__(self, region, parent=None):
        super().__init__(parent)
        self.region = region
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.showFullScreen()

    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(Qt.red, 2, Qt.SolidLine)
        painter.setPen(pen)
        brush = QColor(255, 0, 0, 100)  # 반투명 붉은색
        painter.setBrush(brush)
        painter.drawRect(self.region)

class TimerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.elapsed_timer = QElapsedTimer()
        self.elapsed_time = 0  # 경과 시간 (초)
        self.lap_times = []  # 랩 타임 저장
        self.is_running = False  # 타이머 상태
        self.monitoring = False  # 모니터링 상태
        self.monitor_region = None  # 모니터링할 영역
        self.overlay = None  # 오버레이 창

    def init_ui(self):
        self.setWindowTitle('플립 클락 타이머')
        self.setGeometry(100, 100, 400, 500)

        self.layout = QVBoxLayout()

        self.label = FlipClockLabel("00:00:00.00", self)
        self.layout.addWidget(self.label)

        self.start_stop_button = QPushButton('Start', self)
        self.start_stop_button.clicked.connect(self.toggle_timer)
        self.layout.addWidget(self.start_stop_button)

        self.lap_button = QPushButton('Lap', self)
        self.lap_button.clicked.connect(self.record_lap)
        self.layout.addWidget(self.lap_button)

        self.reset_button = QPushButton('Reset', self)
        self.reset_button.clicked.connect(self.reset_timer)
        self.layout.addWidget(self.reset_button)

        self.monitor_button = QPushButton('Start Monitoring', self)
        self.monitor_button.clicked.connect(self.toggle_monitoring)
        self.layout.addWidget(self.monitor_button)

        self.color_label = QLabel("Current Color: N/A", self)
        self.layout.addWidget(self.color_label)

        self.lap_list = QListWidget(self)
        self.layout.addWidget(self.lap_list)

        self.checkbox = QCheckBox("Disable Screensaver", self)
        self.checkbox.stateChanged.connect(self.toggle_screensaver)
        self.layout.addWidget(self.checkbox)

        self.setLayout(self.layout)

    def toggle_timer(self):
        if self.is_running:
            self.timer.stop()
            self.elapsed_time += self.elapsed_timer.elapsed() / 1000.0  # 밀리초를 초로 변환
            self.start_stop_button.setText('Start')
        else:
            self.elapsed_timer.start()
            self.timer.start(10)  # 10ms마다 timeout 신호 발생 (100분의 1초)
            self.start_stop_button.setText('Stop')
        self.is_running = not self.is_running

    def update_timer(self):
        current_time = self.elapsed_time + self.elapsed_timer.elapsed() / 1000.0  # 밀리초를 초로 변환
        minutes, seconds = divmod(int(current_time), 60)
        milliseconds = int((current_time - int(current_time)) * 100)
        self.label.setTextWithFlip(f"{minutes:02}:{seconds:02}.{milliseconds:02}")

    def record_lap(self, color=None):
        current_time = self.elapsed_time + self.elapsed_timer.elapsed() / 1000.0  # 밀리초를 초로 변환
        minutes, seconds = divmod(int(current_time), 60)
        milliseconds = int((current_time - int(current_time)) * 100)
        lap_time = f"{minutes:02}:{seconds:02}.{milliseconds:02}"
        self.lap_times.append((lap_time, color))
        item_text = lap_time
        if color:
            int_color = tuple(map(int, color))  # float 값을 int로 변환
            item_text += f" - Color: {int_color}"
            item = QListWidgetItem(item_text)
            item.setBackground(QColor(int_color[0], int_color[1], int_color[2]))
        else:
            item = QListWidgetItem(item_text)
        self.lap_list.addItem(item)

    def reset_timer(self):
        self.timer.stop()
        self.elapsed_time = 0
        self.label.setText("00:00:00.00")
        self.lap_times.clear()
        self.lap_list.clear()
        self.start_stop_button.setText('Start')
        self.is_running = False

    def toggle_screensaver(self):
        if SetThreadExecutionState is not None:
            if self.checkbox.isChecked():
                # 화면 보호기 비활성화
                SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
            else:
                # 화면 보호기 활성화
                SetThreadExecutionState(ES_CONTINUOUS)
        else:
            print("SetThreadExecutionState function is not available.")

    def toggle_monitoring(self):
        if self.monitoring:
            self.monitor_button.setText('Start Monitoring')
            self.monitor_thread.stop()
            if self.overlay:
                self.overlay.close()
            self.monitoring = False
        else:
            self.monitor_button.setText('Stop Monitoring')
            self.select_region()

    def select_region(self):
        self.region_selector = RegionSelector()
        self.region_selector.region_selected.connect(self.start_monitoring)
        self.region_selector.show()

    def start_monitoring(self, region):
        self.monitor_region = (region.left(), region.top(), region.width(), region.height())
        self.overlay = Overlay(region)
        self.monitor_thread = ScreenMonitor(self.monitor_region)
        self.monitor_thread.color_changed.connect(self.update_color_label)
        self.monitor_thread.color_changed.connect(lambda color: self.record_lap(color))
        self.monitor_thread.start()
        self.monitoring = True

    def update_color_label(self, color):
        int_color = tuple(map(int, color))  # float 값을 int로 변환
        self.color_label.setText(f"Current Color: {int_color}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    timer_app = TimerApp()
    timer_app.show()
    sys.exit(app.exec_())