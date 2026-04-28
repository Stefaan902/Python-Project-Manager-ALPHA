import sys
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QComboBox,
    QRadioButton,
    QSpinBox,
    QPushButton,
    QGraphicsScene,
    QGraphicsView
)
from PyQt5.QtGui import QBrush, QPen
from PyQt5.QtWidgets import QGraphicsTextItem
from PyQt5.QtCore import Qt

TIME_SCALE = 40   # pixels per time unit
ROW_HEIGHT = 40
LEFT_MARGIN = 120
TOP_MARGIN = 40


def draw_gantt(scene, tasks):
    scene.clear()  
    draw_timeline(scene, max_time=15)

    for row, task in enumerate(tasks):
        x = LEFT_MARGIN + task["start"] * TIME_SCALE
        y = TOP_MARGIN + row * ROW_HEIGHT
        width = task["duration"] * TIME_SCALE
        height = ROW_HEIGHT - 10

        # Draw task bar
        rect = scene.addRect(
            x, y, width, height,
            pen=QPen(Qt.black),
            brush=QBrush(Qt.blue)
        )

        # Task label (left side)
        label = QGraphicsTextItem(task["name"])
        label.setPos(10, y)
        scene.addItem(label)

        # Start time label
        start_label = QGraphicsTextItem(str(task["start"]))
        start_label.setPos(x, y + height)
        scene.addItem(start_label)

        # End time label
        end_time = task["start"] + task["duration"]
        end_label = QGraphicsTextItem(str(end_time))
        end_label.setPos(x + width - 10, y + height)
        scene.addItem(end_label)



def drawGanttChart():
    
    tasks = [
        {"name": "P1", "start": 0, "duration": 4},
        {"name": "P2", "start": 4, "duration": 3},
        {"name": "P3", "start": 7, "duration": 5},
    ]

    app = QApplication(sys.argv)

    # Create the scene
    scene = QGraphicsScene()

    # Dialog dimensions
    DIALOG_WIDTH = 800
    DIALOG_HEIGHT = 600

    # Create dialog
    dialog = QDialog()
    dialog.setFixedSize(DIALOG_WIDTH, DIALOG_HEIGHT)

    # Algorithm selection
    algorithmComboBox = QComboBox()
    algorithmComboBox.addItems(["FCFS", "SJF", "RR", "Prioritet"])

    # Number of processes selection
    numProcessesComboBox = QComboBox()
    for i in range(4, 10):
        numProcessesComboBox.addItem(str(i))

    # Preemptive radio button
    preemptiveRadioButton = QRadioButton("Sa pretpraznjenjem")

    # Spin box limits
    MAX_ARRIVAL_TIME = 20
    MAX_PROCESS_TIME = 30
    MAX_PRIORITY = 9

    arrivalTimeSpinBoxes = []
    processTimeSpinBoxes = []
    prioritySpinBoxes = []

    num_processes = int(numProcessesComboBox.currentText())

    for _ in range(num_processes):
        arrival = QSpinBox()
        arrival.setRange(0, MAX_ARRIVAL_TIME)

        process = QSpinBox()
        process.setRange(1, MAX_PROCESS_TIME)

        priority = QSpinBox()
        priority.setRange(0, MAX_PRIORITY)

        arrivalTimeSpinBoxes.append(arrival)
        processTimeSpinBoxes.append(process)
        prioritySpinBoxes.append(priority)

    # Button
    drawButton = QPushButton("Gantt chart")
    drawButton.clicked.connect(lambda: draw_gantt(scene, tasks))

    # Graphics view
    view = QGraphicsView(scene)
    view.setFixedSize(DIALOG_WIDTH, DIALOG_HEIGHT)

    # Add widgets to scene
    scene.addWidget(algorithmComboBox)
    scene.addWidget(numProcessesComboBox)
    scene.addWidget(preemptiveRadioButton)

    for i in range(len(arrivalTimeSpinBoxes)):
        scene.addWidget(arrivalTimeSpinBoxes[i])
        scene.addWidget(processTimeSpinBoxes[i])
        scene.addWidget(prioritySpinBoxes[i])

    scene.addWidget(drawButton)

    # Set the view as the dialog's main content
    view.setParent(dialog)

    # Show dialog
    dialog.show()
    sys.exit(app.exec_())


def draw_timeline(scene, max_time=15):
    for t in range(max_time + 1):
        x = LEFT_MARGIN + t * TIME_SCALE

        # Vertical grid line
        scene.addLine(
            x, TOP_MARGIN - 10,
            x, TOP_MARGIN + 300,
            QPen(Qt.lightGray)
        )

        # Time label
        label = QGraphicsTextItem(str(t))
        label.setPos(x - 5, 5)
        scene.addItem(label)


if __name__ == "__main__":
    drawGanttChart()
