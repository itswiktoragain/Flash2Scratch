from __future__ import annotations

import sys
import traceback
from pathlib import Path


def main() -> int:
    try:
        from PySide6.QtCore import Qt, QThread, Signal, Slot
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
    from .ffdec import detect_runtime, ensure_ffdec

    class ConversionThread(QThread):
        status_message = Signal(str)
        succeeded = Signal(str, str)
        failed = Signal(str)

        def __init__(self, swf: str, output: str, ffdec: str | None, parent=None):
            super().__init__(parent)
            self.swf = swf
            self.output = output
            self.ffdec = ffdec

        def _status(self, message: str) -> None:
            self.status_message.emit(message)

        def run(self) -> None:
            try:
                self._status("Checking FFDec…")
                ffdec_path = ensure_ffdec(self.ffdec or None, status=self._status)
                self._status("Detecting Flash runtime…")
                runtime = detect_runtime(ffdec_path, Path(self.swf))
                self._status(
                    f"Detected SWF v{runtime.swf_version} — {runtime.actionscript}"
                )
                self._status("Decompiling and translating the SWF…")
                report = convert(self.swf, self.output, ffdec=ffdec_path)
                # Only plain Python strings cross the worker/UI thread boundary.
                self.succeeded.emit(report.text(), str(report.output))
            except Exception:
                self.failed.emit(traceback.format_exc())

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self._thread: ConversionThread | None = None
            self.setWindowTitle("Flash2Scratch — SWF to Scratch 3")
            self.resize(840, 630)
            self.setMinimumSize(690, 520)
            self.setAcceptDrops(True)

            root = QWidget(self)
            self.setCentralWidget(root)
            layout = QVBoxLayout(root)
            layout.setContentsMargins(24, 22, 24, 22)
            layout.setSpacing(14)

            title = QLabel("Flash2Scratch")
            title.setObjectName("title")
            subtitle = QLabel(
                "Convert ActionScript 1, 2, and 3 SWF games into Scratch 3 projects"
            )
            subtitle.setObjectName("subtitle")
            layout.addWidget(title)
            layout.addWidget(subtitle)

            self.swf_input = QLineEdit()
            self.swf_input.setPlaceholderText(
                "Choose a Flash .swf file (AVM1/AS1-2 or AVM2/AS3)"
            )
            layout.addWidget(QLabel("Input SWF"))
            layout.addLayout(self._path_row(self.swf_input, "Browse…", self.pick_swf))

            self.output_input = QLineEdit()
            self.output_input.setPlaceholderText("Output Scratch 3 .sb3 file")
            layout.addWidget(QLabel("Output SB3"))
            layout.addLayout(
                self._path_row(self.output_input, "Browse…", self.pick_output)
            )

            self.ffdec_input = QLineEdit()
            self.ffdec_input.setPlaceholderText(
                "Optional override — leave blank for automatic FFDec"
            )
            layout.addWidget(QLabel("FFDec executable (optional)"))
            layout.addLayout(
                self._path_row(self.ffdec_input, "Browse…", self.pick_ffdec)
            )

            note = QLabel(
                "FFDec is installed automatically from the official JPEXS GitHub "
                "release when it is missing."
            )
            note.setObjectName("note")
            note.setWordWrap(True)
            layout.addWidget(note)

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

            self.status = QLabel("Ready — Flash 8 / ActionScript 2 is supported")
            self.status.setObjectName("status")
            self.status.setWordWrap(True)
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
                QLabel#subtitle, QLabel#note, QLabel#status { color: #64748b; }
                QLabel#subtitle { font-size: 14px; margin-bottom: 8px; }
                QLabel#note { font-size: 12px; }
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
                QPushButton:hover { background: #dce7f5; }
                QPushButton#convertButton {
                    background: #1677ff;
                    color: white;
                    border: none;
                    font-weight: 700;
                    font-size: 14px;
                }
                QPushButton#convertButton:hover { background: #0f68e6; }
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

        def _path_row(self, edit, text, callback):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(edit, 1)
            button = QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
            return row

        def pick_swf(self) -> None:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Choose Flash SWF",
                self.swf_input.text(),
                "Flash files (*.swf);;All files (*)",
            )
            if path:
                self._set_swf(path)

        def pick_output(self) -> None:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Scratch project",
                self.output_input.text() or self._suggest_output(),
                "Scratch 3 projects (*.sb3);;All files (*)",
            )
            if path:
                self.output_input.setText(
                    path if path.lower().endswith(".sb3") else path + ".sb3"
                )

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
            swf = self.swf_input.text().strip()
            return str(Path(swf).with_suffix(".sb3")) if swf else "output.sb3"

        def start_conversion(self) -> None:
            swf = self.swf_input.text().strip()
            output = self.output_input.text().strip() or self._suggest_output()
            ffdec = self.ffdec_input.text().strip() or None

            if not swf:
                QMessageBox.warning(self, "Missing SWF", "Choose a SWF file first.")
                return
            if not Path(swf).is_file():
                QMessageBox.warning(
                    self, "SWF not found", f"This file does not exist:\n{swf}"
                )
                return
            if Path(swf).suffix.lower() != ".swf":
                QMessageBox.warning(
                    self, "Wrong file type", "The input file must be a .swf file."
                )
                return
            if ffdec and not Path(ffdec).is_file():
                QMessageBox.warning(
                    self, "FFDec not found", f"This FFDec path does not exist:\n{ffdec}"
                )
                return
            if self._thread is not None and self._thread.isRunning():
                return

            if not output.lower().endswith(".sb3"):
                output += ".sb3"
                self.output_input.setText(output)

            self.log.setPlainText(
                "Starting conversion…\n"
                f"SWF: {swf}\n"
                f"SB3: {output}\n"
                + (
                    f"FFDec override: {ffdec}\n"
                    if ffdec
                    else "FFDec: automatic detection / installation\n"
                )
            )
            self.status.setText("Starting…")
            self.convert_button.setEnabled(False)
            self.progress.setRange(0, 0)

            thread = ConversionThread(swf, output, ffdec, self)
            queued = Qt.ConnectionType.QueuedConnection
            thread.status_message.connect(self._thread_status, queued)
            thread.succeeded.connect(self._conversion_finished, queued)
            thread.failed.connect(self._conversion_failed, queued)
            thread.finished.connect(self._thread_finished, queued)
            self._thread = thread
            thread.start()

        @Slot(str)
        def _thread_status(self, message: str) -> None:
            self.status.setText(message)
            self.log.appendPlainText(message)

        @Slot(str, str)
        def _conversion_finished(self, report_text: str, output: str) -> None:
            self.progress.setRange(0, 1)
            self.progress.setValue(1)
            self.convert_button.setEnabled(True)
            self.status.setText(f"Done — {output}")
            self.log.setPlainText(report_text)
            QMessageBox.information(
                self,
                "Conversion finished",
                f"Scratch project created successfully:\n{output}",
            )

        @Slot(str)
        def _conversion_failed(self, details: str) -> None:
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
            self.convert_button.setEnabled(True)
            self.status.setText("Conversion failed")
            self.log.setPlainText(details)
            last_line = next(
                (line for line in reversed(details.splitlines()) if line.strip()),
                "Unknown error",
            )
            QMessageBox.critical(self, "Conversion failed", last_line)

        @Slot()
        def _thread_finished(self) -> None:
            thread = self._thread
            self._thread = None
            if thread is not None:
                thread.deleteLater()

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
