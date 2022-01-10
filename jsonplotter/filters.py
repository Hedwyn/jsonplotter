import numpy as np
from abc import ABC, abstractmethod, abstractproperty

DEFAULT_WIDTH = 21
DEFAULT_ELIMINATION_RATIO = 1


class Filter(ABC):
    """Abstract class for filters, contains all the methods common to all filters"""    
    def __init__(self):
        self._userParams = {}

    @classmethod
    def name(cls):
        return(cls.__name__) 

    @classmethod
    def getAvailableFilters(cls):
        """Returns the names of all available filters"""
        for subclass in cls.__subclasses__():
            yield from subclass.getAvailableFilters()
            yield subclass

    @property
    def userParams(self):
        return(self._userParams)
    
    @userParams.setter
    def userParams(self, params):
        """Sets the parameters accesible to the user.
        Params:
        params: list - List of references to the parameters settable by the user"""
        for param in params:
            if hasattr(self, param):
                ## Checking that the attribute exists
                self._userParams[param] = params[param]

    @abstractmethod
    def apply(self):
        pass

class MovingMedian(Filter):
    """Moving median implementation"""
    def __init__(self, inputData =  None, width = DEFAULT_WIDTH, ratio = DEFAULT_ELIMINATION_RATIO):
        super().__init__()
        self.input = inputData # reference to thet data to filter
        self.width = width
        self.ratio = ratio
        self.cutExtrema = int(self.width * self.ratio / 2)
        self.userParams = {'width': int, 'ratio':float}
   
    def apply(self):
        if len(self.input) < self.width:
            return(self.input)
        elif self.ratio == 1:
            return([np.median(self.input[i:i+self.width]) for i in range(len(self.input) - self.width)])
        output = []
        for i in range(len(self.input) - self.width):
            currentBlock = self.input[i:i + self.width]
            currentBlock = np.sort(currentBlock)
            if self.cutExtrema > 0:
                filteredVal = np.mean(currentBlock[self.cutExtrema : -self.cutExtrema])
            else:
                filteredVal = np.mean(currentBlock)
            output.append(filteredVal)
        return(output)

    # def applyx(self):
    #     if len(self.input) < self.width:
    #         return(self.input)
    #     output = []
    #     currentBlock = np.sort(self.input[:self.width])

    #     for i, val in enumerate(self.input[self.width:]):
    #         currentBlock = np.delete(currentBlock, np.searchsorted(currentBlock, self.input[i - self.width]) - 1)
    #         valIdx = np.searchsorted(currentBlock, val)
    #         currentBlock = np.insert(currentBlock, valIdx, val)
    #         if self.cutExtrema > 0:
    #             filteredVal = np.mean(currentBlock[self.cutExtrema : -self.cutExtrema])
    #         else:
    #             filteredVal = np.mean(currentBlock)
    #         output.append(filteredVal)
    #     return(output)

class MovingAverage(MovingMedian):
    """A regular moving average filter. Defined as a subcase of moving median"""
    def __init__(self, inputData = None, width = DEFAULT_WIDTH):
        super().__init__(inputData, width, ratio = 0)


class MedianCentering(Filter):
    """Centers the data on their median"""
    def __init__(self, inputData = None):
        super().__init__()
        self.input = inputData
    
    def apply(self):
        if self.input:
            median = np.median(self.input)
            output = [x - median for x in self.input]
            return(output)

class MeanCentering(Filter):
    """Centers the data on their mean"""
    def __init__(self, inputData = None):
        super().__init__()
        self.input = inputData
    
    def apply(self):
        if self.input:
            mean = np.mean(self.input)
            output = [x - mean for x in self.input]
            return(output)

class MinCentering(Filter):
    """Centers the data on their minimum value"""
    def __init__(self, inputData = None):
        super().__init__()
        self.input = inputData
    
    def apply(self):
        if self.input:
            mean = min(self.input)
            output = [x - mean for x in self.input]
            return(output)



if __name__ == "__main__":
    import random
    input = []
    random.seed(10)
    for i in range(40):
        input.append(random.randint(0, 10))
    f = MovingMedian(input, 10, 0)
    print(input)
    print(f.apply())    
    print([cls.name() for cls in Filter.getAvailableFilters()])
    
