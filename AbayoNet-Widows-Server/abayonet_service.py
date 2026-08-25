"""
AbayoNet Windows Service
Place this file in the SAME folder as abayonet.py

Install:  python abayonet_service.py install
Start:    python abayonet_service.py start
Stop:     python abayonet_service.py stop
Remove:   python abayonet_service.py remove
"""
import sys, os, time, subprocess, logging

# Everything lives in the same folder as this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)

logging.basicConfig(
    filename=os.path.join(BASE_DIR, 'data', 'service.log'),
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger('AbayoNetSvc')

try:
    import win32serviceutil, win32service, win32event, servicemanager
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

if HAS_WIN32:
    class AbayoNetService(win32serviceutil.ServiceFramework):
        _svc_name_         = 'AbayoNet'
        _svc_display_name_ = 'AbayoNet Enterprise Monitor'
        _svc_description_  = 'AbayoNet NOC monitoring. Dashboard: http://localhost:8780'

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self._stop_evt = win32event.CreateEvent(None, 0, 0, None)
            self._proc     = None

        def SvcStop(self):
            log.info('Stop requested')
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self._stop_evt)
            if self._proc:
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=8)
                except Exception as e:
                    log.warning(f'Terminate: {e}')

        def SvcDoRun(self):
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, ''))
            log.info('Service started')
            self._run()

        def _find_python(self):
            # sys.executable is unreliable here: when this code is actually
            # running AS a Windows service (not invoked manually), pywin32
            # hosts it inside pythonservice.exe, so sys.executable points at
            # pythonservice.exe — a service host that can't run arbitrary
            # scripts, not a general-purpose interpreter. The real python.exe
            # lives in the same installation directory regardless of which
            # exe loaded the interpreter, so derive it from sys.exec_prefix.
            for base in (sys.exec_prefix, sys.base_exec_prefix):
                for name in ('python.exe', 'python3.exe'):
                    candidate = os.path.join(base, name)
                    if os.path.isfile(candidate):
                        return candidate
            log.warning('Could not locate python.exe under sys.exec_prefix; '
                         f'falling back to sys.executable ({sys.executable}), '
                         'which will fail if this is pythonservice.exe')
            return sys.executable

        def _run(self):
            script = os.path.join(BASE_DIR, 'abayonet.py')
            py     = self._find_python()
            log.info(f'Resolved python interpreter: {py}')
            while True:
                if win32event.WaitForSingleObject(
                        self._stop_evt, 0) == win32event.WAIT_OBJECT_0:
                    break
                log.info(f'Starting: {py} {script}')
                try:
                    self._proc = subprocess.Popen(
                        [py, script, '--no-browser', '--service'],
                        cwd=BASE_DIR,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW)
                    while True:
                        rc = win32event.WaitForSingleObject(self._stop_evt, 1000)
                        if rc == win32event.WAIT_OBJECT_0:
                            self._proc.terminate()
                            self._proc.wait(timeout=8)
                            log.info('Stopped by SCM')
                            return
                        if self._proc.poll() is not None:
                            log.warning(f'Process exited ({self._proc.returncode})')
                            break
                    # wait 5s then restart
                    if win32event.WaitForSingleObject(
                            self._stop_evt, 5000) == win32event.WAIT_OBJECT_0:
                        return
                except Exception as e:
                    log.error(f'Run error: {e}')
                    time.sleep(5)

if __name__ == '__main__':
    if not HAS_WIN32:
        print('pywin32 not found. Install it: pip install pywin32')
        print('Then run:  python abayonet_service.py install')
        sys.exit(1)
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(AbayoNetService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(AbayoNetService)
