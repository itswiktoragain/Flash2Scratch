from __future__ import annotations
import sys
from pathlib import Path

def main():
    try:
        from PySide6.QtWidgets import QApplication,QFileDialog,QMainWindow,QPushButton,QLineEdit,QPlainTextEdit,QVBoxLayout,QWidget,QLabel
    except ImportError:
        print("Install GUI support with: pip install -e '.[gui]'",file=sys.stderr); return 2
    from .converter import convert
    class W(QMainWindow):
        def __init__(self):
            super().__init__(); self.setWindowTitle('Flash2Scratch — AS3 SWF → Scratch 3'); self.resize(720,460); root=QWidget(); self.setCentralWidget(root); l=QVBoxLayout(root); self.swf=QLineEdit(); self.out=QLineEdit(); self.log=QPlainTextEdit(); self.log.setReadOnly(True)
            for text,edit,cb in [('SWF',self.swf,self.pick),('SB3 output',self.out,self.save)]: l.addWidget(QLabel(text)); l.addWidget(edit); b=QPushButton('Browse…'); b.clicked.connect(cb); l.addWidget(b)
            go=QPushButton('Convert to Scratch 3'); go.clicked.connect(self.run); l.addWidget(go); l.addWidget(self.log)
        def pick(self):
            p,_=QFileDialog.getOpenFileName(self,'Open SWF','','Flash (*.swf)');
            if p:self.swf.setText(p);self.out.setText(str(Path(p).with_suffix('.sb3')))
        def save(self):
            p,_=QFileDialog.getSaveFileName(self,'Save SB3',self.out.text(),'Scratch 3 (*.sb3)');
            if p:self.out.setText(p if p.endswith('.sb3') else p+'.sb3')
        def run(self):
            try:self.log.setPlainText(convert(self.swf.text(),self.out.text() or str(Path(self.swf.text()).with_suffix('.sb3'))).text())
            except Exception as e:self.log.setPlainText(str(e))
    app=QApplication(sys.argv); w=W(); w.show(); return app.exec()

if __name__=='__main__':raise SystemExit(main())
