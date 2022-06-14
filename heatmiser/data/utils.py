import signal
import inspect
import os

def check_param(param_name : str, param_type : type, param):
    """
    Checks if param is or type param_type and raises a ValueError if it is not
    function can be obtained from 
    """
    if type(param) != param_type:
      f_info = inspect.stack()[1]
      filename = os.path.basename(f_info.filename)
      lineno = f_info.lineno
      function = f_info.function
      raise ValueError(f"{filename} {function} line {lineno} parameter error: {param_name} must be a {param_type}, {type(param)} supplied")

class GracefulKiller:
    """
    Class to handle SIGINT and SIGTERM
    When either is received self.kill_now is set True for detection by a calling procedure or loop
    """
    _kill_now = False
    def __init__(self, sigint : bool = True, sigterm : bool = True):
        if sigint:
            signal.signal(signal.SIGINT, self.exit_gracefully)
        if sigterm:
            signal.signal(signal.SIGTERM, self.exit_gracefully)
        if not (sigterm or sigint):
            raise ValueError("Unable to capture SIGINT or SIGTERM")
    
    @property
    def kill_now(self):
        return self._kill_now

    def exit_gracefully(self, *kwargs):
        self._kill_now = True
