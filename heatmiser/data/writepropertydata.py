
class WritePropertyData():
 
    def __init__(self, name : str, dcb_offset : int, min=None, max=None, options=None, twobyte=False, isTime=False):
        self.name = name
        self.dcb_offset = dcb_offset
        self.min = min
        self.max = max
        self.options = options
        self.twobyte = twobyte
        self.isTime = isTime
    
    def isChoice(self):
        return len(self.options) > 0
