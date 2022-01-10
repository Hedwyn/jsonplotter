import json
from typing import cast

class JsonParser:
    def __init__(self, filename = None):
        self.logs = []
        self.filename = filename
        if self.filename:
            if not(self.filename.endswith('.json')):
                raise IOError("File extension is not valid. Please provide a json file")
            self.parse_file()


    def parse_file(self):
        """Parses the json file and stores the json logs in the class instance"""
        try:
            f = open(self.filename)
        except:
            raise FileNotFoundError("Please provide a valid file path")
        
        for idx, line in enumerate(f):
            try:
                self.logs.append(json.loads(line))
            except:
                print("Line " + str(idx) + " is not properly formatted and will be ignored")

    def parse_line(self, line):
        """Parses a given line and stores it as a dictionary in the class instance logs. If the line is not valid json it will be ignored"""
        if line.startswith("{"):
            try:
                self.logs.append(json.loads(line))
            except:
                pass
        
    def extract_topics(self):
        """Extracts all keys that have at least a single instance in the json logs extracted
        Returns-------------
        topics: list[str]
            List of the topics found in the json logs."""
        topics = []
        for log in self.logs:
            for topic in log:
                if not(topic in topics):
                    topics.append(topic)
        return(topics)
    
    def get_topic_values(self, topic, numeral = True):
        """Returns all the values collected for a given key (= topic)
        Parameters----------
        topic: str
            key to look for in the json logs
        numeral: type
            Whether the values shoud be casted to floats. If False, the original type is kept. 
        Returns-------------
        values: list[]
            List of values associated to the given topic."""
        values = []
        for log in self.logs:
            if topic in log:
                value = log[topic]
                if numeral:
                    try:
                        value = float(value)
                        values.append(value)
                    except:
                        print(str(value) + "cannot be safely casted to a float")
        return(values)

    def clear_all(self):
        """Erases all the data gathered"""
        self.logs.clear()
        

      

if __name__ == "__main__":
    # p = JsonParser("jj")
    # p = JsonParser("jj.json")
    F = "COM3_COM4_SF9_BW400_79.json"
    G = "test.json"
    p = JsonParser(F)
    print(p.extract_topics())
    values = p.get_topic_values("distance", float)
    print(values)
    print(type(values[0]))
    
