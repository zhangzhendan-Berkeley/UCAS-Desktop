"""Local IPC: launching the shortcut again restores the existing window."""
import hashlib
from PySide6.QtCore import QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def server_name(data_path):
    digest = hashlib.sha256(str(data_path.resolve()).casefold().encode()).hexdigest()[:24]
    return 'UCASDesktop-' + digest


def activate_existing(name):
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(800):
        return False
    socket.write(b'show\n')
    socket.waitForBytesWritten(800)
    socket.disconnectFromServer()
    return True


class InstanceServer(QObject):
    def __init__(self, name, show_window, parent=None):
        super().__init__(parent)
        self.show_window = show_window
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.server.newConnection.connect(self.receive)
        # Only the process holding app.lock may create/remove this endpoint.
        QLocalServer.removeServer(name)
        if not self.server.listen(name):
            raise RuntimeError('无法创建本地窗口唤醒接口：' + self.server.errorString())

    def receive(self):
        while self.server.hasPendingConnections():
            connection = self.server.nextPendingConnection()
            connection.disconnected.connect(connection.deleteLater)
            connection.disconnectFromServer()
            QTimer.singleShot(0, self.show_window)

    def close(self):
        self.server.close()
