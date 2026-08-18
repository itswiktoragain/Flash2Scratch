from __future__ import annotations

import sys
import traceback
from pathlib import Path


def main() -> int:
    try:
        from PySide6.QtCore import QObject, QThread, Signal, Slot
        from PySide6.QtWidgets import (
            QApplication,
            QFileDialog,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPlainTextEdit,
            QProgressBar,
            QPushButton,
            QVBoxLayout,
            QWidget,
        )
    except ImportError:
        print("PySide6 is required for the desktop UI.", file=sys.stderr)
        print("Install it with: python -m pip install -e '.[gui]'", file=sys.stderr)
        return 2

    from .converter import convert

    class ConversionWorker(QObject):
        finished = Signal(object)
        failed = Signal(str)

        def __init__(self, swf: str, output: str, ffdec: str | None):
            super().__init__()
            self.swf = swf
            self.output = output
            self.ffdec = ffdec

        @Slot()
        def run(self) -> None:
            try:
                report = convert(self.swf, self.output, ffdec=self.ffdec or None)
            except Exception:
                self.failed.emit(traceback.format_exc())
                return
            self.finished.emit(report)

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self._thread: QThread | None = None
            self._worker: ConversionWorker | None = None

            self.setWindowTitle("Flash2Scratch — AS3 SWF to Scratch 3")
            self.resize(820, 590)
            self.setMinimumSize(680, 500)
            self.setAcceptDrops(True)

            root = QWidget(self)
            self.setCentralWidget(root)
            layout = QVBoxLayout(root)
            layout.setContentsMargins(24, 22, 24, 22)
            layout.setSpacing(14)

            title = QLabel("Flash2Scratch")
            title.setObjectName("title")
            subtitle = QLabel("Convert ActionScript 3 / AVM2 SWF games into Scratch 3 projects")
            subtitle.setObjectName("subtitle")
            layout.addWidget(title)
            layout.addWidget(subtitle)

            self.swf_input = QLineEdit()
            self.swf_input.setPlaceholderText("Choose an ActionScript 3 .swf file")
            layout.addWidget(QLabel("Input SWF"))
            layout.addLayout(self._path_row(self.swf_input, "Browse…", self.pick_swf))

            self.output_input = QLineEdit()
            self.output_input.setPlaceholderText("Output Scratch 3 .sb3 file")
            layout.addWidget(QLabel("Output SB3"))
            layout.addLayout(self._path_row(self.output_input, "Browse…", self.pick_output))

            self.ffdec_input = QLineEdit()
            self.ffdec_input.setPlaceholderText("Optional — leave blank to auto-detect FFDec")
            layout.addWidget(QLabel("FFDec executable"))
            layout.addLayout(self._path_row(self.ffdec_input, "Browse…", self.pick_ffdec))

            self.convert_button = QPushButton("Convert to Scratch 3")
            self.convert_button.setObjectName("convertButton")
            self.convert_button.setMinimumHeight(44)
            self.convert_button.clicked.connect(self.start_conversion)
            layout.addWidget(self.convert_button)

            self.progress = QProgressBar()
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
            self.progress.setTextVisible(False)
            layout.addWidget(self.progress)

            self.status = QLabel("Ready")
            self.status.setObjectName("status")
            layout.addWidget(self.status)

            layout.addWidget(QLabel("Conversion log"))
            self.log = QPlainTextEdit()
            self.log.setReadOnly(True)
            self.log.setPlaceholderText("Conversion details will appear here.")
            layout.addWidget(self.log, 1)

            self.setStyleSheet(
                """
                QMainWindow, QWidget {
                    background: #f4f7fb;
                    color: #182230;
                    font-size: 13px;
                }
                QLabel#title {
                    font-size: 28px;
                    font-weight: 700;
                    color: #0c1d36;
                }
                QLabel#subtitle {
                    color: #64748b;
                    font-size: 14px;
                    margin-bottom: 8px;
                }
                QLabel#status {
                    color: #526175;
                }
                QLineEdit, QPlainTextEdit {
                    background: white;
                    border: 1px solid #cbd5e1;
                    border-radius: 8px;
                    padding: 9px;
                    selection-background-color: #1677ff;
                }
                QLineEdit:focus, QPlainTextEdit:focus {
                    border: 1px solid #1677ff;
                }
                QPushButton {
                    background: #e8eef7;
                    border: 1px solid #c8d4e3;
                    border-radius: 8px;
                    padding: 9px 14px;
                }
                QPushButton:hover {
                    background: #dce7f5;
                }
                QPushButton#convertButton {
                    background: #1677ff;
                    color: white;
                    border: none;
                    font-weight: 700;
                    font-size: 14px;
                }
                QPushButton#convertButton:hover {
                    background: #0f68e6;
                }
                QPushButton:disabled {
                    color: #94a3b8;
                    background: #e2e8f0;
                }
                QProgressBar {
                    background: #e2e8f0;
                    border: none;
                    border-radius: 4px;
                    min-height: 8px;
                    max-height: 8px;
                }
                QProgressBar::chunk {
                    background: #1677ff;
                    border-radius: 4px;
                }
                """
            )

        def _path_row(self, edit: QLineEdit, button_text: str, callback):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(edit, 1)
            button = QPushButton(button_text)
            button.clicked.connect(callback)
            row.addWidget(button)
            return row

        def pick_swf(self) -> None:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Choose ActionScript 3 SWF",
                self.swf_input.text(),
                "Flash files (*.swf);;All files (*)",
            )
            if path:
                self._set_swf(path)

        def pick_output(self) -> None:
            suggested = self.output_input.text() or self._suggest_output()
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Scratch project",
                suggested,
                "Scratch 3 projects (*.sb3);;All files (*)",
            )
            if path:
                if not path.lower().endswith(".sb3"):
                    path += ".sb3"
                self.output_input.setText(path)

        def pick_ffdec(self) -> None:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Choose FFDec executable",
                self.ffdec_input.text(),
                "All files (*)",
            )
            if path:
                self.ffdec_input.setText(path)

        def _set_swf(self, path: str) -> None:
            self.swf_input.setText(path)
            self.output_input.setText(str(Path(path).with_suffix(".sb3")))

        def _suggest_output(self) -> str:
            text = self.swf_input.text().strip()
            return str(Path(text).with_suffix(".sb3")) if text else "output.sb3"

        def start_conversion(self) -> None:
            swf = self.swf_input.text().strip()
            output = self.output_input.text().strip() or self._suggest_output()
            ffdec = self.ffdec_input.text().strip() or None

            if not swf:
                QMessageBox.warning(self, "Missing SWF", "Choose a SWF file first.")
                return
            if not Path(swf).is_file():
                QMessageBox.warning(self, "SWF not found", f"This file does not exist:\n{swf}")
                return
            if Path(swf).suffix.lower() != ".swf":
                QMessageBox.warning(self, "Wrong file type", "The input file must be a .swf file.")
                return
            if not output.lower().endswith(".sb3"):
                output += ".sb3"
                self.output_input.setText(output)
            if ffdec and not Path(ffdec).is_file():
                QMessageBox.warning(self, "FFDec not found", f"This FFDec path does not exist:\n{ffdec}")
                return

            self.log.setPlainText(
                "Starting conversion…\n"
                f"SWF: {swf}\n"
                f"SB3: {output}\n"
                + (f"FFDec: {ffdec}\n" if ffdec else "FFDec: auto-detect\n")
            )
            self.status.setText("Converting…")
            self.convert_button.setEnabled(False)
            self.progress.setRange(0, 0)

            thread = QThread(self)
            worker = ConversionWorker(swf, output, ffdec)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.finished.connect(self._conversion_finished)
            worker.failed.connect(self._conversion_failed)
            worker.finished.connect(thread.quit)
            worker.failed.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            worker.failed.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(self._thread_finished)

            self._thread = thread
            self._worker = worker
            thread.start()

        @Slot(object)
        def _conversion_finished(self, report) -> None:
            self.progress.setRange(0, 1)
            self.progress.setValue(1)
            self.convert_button.setEnabled(True)
            self.status.setText(f"Done — {report.output}")
            self.log.setPlainText(report.text())
            QMessageBox.information(
                self,
                "Conversion finished",
                f"Scratch project created successfully:\n{report.output}",
            )

        @Slot(str)
        def _conversion_failed(self, details: str) -> None:
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
            self.convert_button.setEnabled(True)
            self.status.setText("Conversion failed")
            self.log.setPlainText(details)
            last_line = next((line for line in reversed(details.splitlines()) if line.strip()), "Unknown error")
            QMessageBox.critical(self, "Conversion failed", last_line)

        def _thread_finished(self) -> None:
            self._thread = None
            self._worker = None

        def dragEnterEvent(self, event) -> None:
            urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
            if any(Path(url.toLocalFile()).suffix.lower() == ".swf" for url in urls):
                event.acceptProposedAction()

        def dropEvent(self, event) -> None:
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if Path(path).suffix.lower() == ".swf":
                    self._set_swf(path)
                    event.acceptProposedAction()
                    break

        def closeEvent(self, event) -> None:
            if self._thread is not None and self._thread.isRunning():
                QMessageBox.information(
                    self,
                    "Conversion still running",
                    "The current conversion is still running. Let it finish before closing the app.",
                )
                event.ignore()
                return
            event.accept()

    app = QApplication(sys.argv)
    app.setApplicationName("Flash2Scratch")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
