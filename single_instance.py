"""Mutex e sinalização de ativação para impedir cópias duplicadas no Windows."""

import ctypes
import os
import threading

_MUTEX_NAME = r"Local\AutoCommitter-Desktop-Instance"
_EVENT_NAME = r"Local\AutoCommitter-Desktop-Activate"
_ERROR_ALREADY_EXISTS = 183
_EVENT_MODIFY_STATE = 0x0002
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 0x102


class InstanciaUnica:
    def __init__(self, mutex, evento):
        self._mutex = mutex
        self._evento = evento
        self._encerrar = threading.Event()
        self._thread = None

    def observar_ativacao(self, callback):
        if not self._evento:
            return

        def aguardar():
            kernel32 = ctypes.windll.kernel32
            while not self._encerrar.is_set():
                resultado = kernel32.WaitForSingleObject(self._evento, 500)
                if resultado == _WAIT_OBJECT_0:
                    callback()
                elif resultado != _WAIT_TIMEOUT:
                    return

        self._thread = threading.Thread(
            target=aguardar, name="auto-committer-ativacao", daemon=True
        )
        self._thread.start()

    def fechar(self):
        self._encerrar.set()
        kernel32 = ctypes.windll.kernel32
        if self._mutex:
            kernel32.ReleaseMutex(self._mutex)
        for handle in (self._evento, self._mutex):
            if handle:
                kernel32.CloseHandle(handle)


def adquirir_instancia():
    if os.name != "nt":
        return InstanciaUnica(None, None)

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.OpenEventW.restype = ctypes.c_void_p
    mutex = kernel32.CreateMutexW(None, True, _MUTEX_NAME)
    if not mutex:
        raise OSError("Não foi possível criar o bloqueio de instância única.")
    if kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
        evento = kernel32.CreateEventW(None, False, False, _EVENT_NAME)
        if evento:
            kernel32.SetEvent(evento)
            kernel32.CloseHandle(evento)
        kernel32.CloseHandle(mutex)
        return None

    evento = kernel32.CreateEventW(None, False, False, _EVENT_NAME)
    if not evento:
        kernel32.ReleaseMutex(mutex)
        kernel32.CloseHandle(mutex)
        raise OSError("Não foi possível iniciar a comunicação entre janelas.")
    return InstanciaUnica(mutex, evento)
