import paho.mqtt.client as mqtt


class MqttInterface:
    """Handles all MQTT-related oeprations. Connects to a broker, extracts the topics received and 
    forwards the data received in the topics selected by the user to the plot interface"""
    def __init__(self,  parent):
        self.mqttc = None
        self.host = None
        self.port = None
        self.currentTopic = None
        self.topics = []
        self.subscribedTopics = []
        self.data = {}
        self.parent = parent
        pass

    def alert(self, msg):
        """Calls the parents alert method, if any"""
        if self.parent:
            self.parent.alert(msg)

    def createClient(self):
        """Creates a mqtt client and connects to the provided host and port"""
        success = False
        if self.port and self.host:
            try:
                # if there is already a client, disconnecting
                if self.mqttc:
                    self.mqttc.disconnect()
                self.mqttc = mqtt.Client()
                self.mqttc.connect(self.host, self.port, 60)
                self.mqttc.loop_start()
                self.mqttc.on_message = self.onMessage
                success = True
            except:
                self.alert("Could not connect to the MQTT broker. Check that the broker is running")
        return(success)

    def subscribe(self, topic):   
        """Adds the selected topic to the list of subscribed topics. Payloads for that topic will be collcted from now on."""
        if not(self.parent._isScanOn):
            self.mqttc.subscribe(topic)
        self.subscribedTopics.append(topic)
        self.data[topic] = []

    def startScan(self):
        """Start scanning for topics by suscribing to all topics. The payloads will not be ignored"""
        self.mqttc.subscribe('#')

    def get_topic_values(self, topic, numeral = True):
        """Wrapper function to return the values accumulated for a given topic"""
        values = []
        for val in self.data[topic]:
            if isinstance(val, bytes):
                val = val.decode('utf-8')
            if isinstance(val, str) and numeral:
                try:
                    val = float(val)
                    values.append(val)
                except ValueError:
                    pass

        return(values)
        

    def stopScan(self):
        """Stops the scanning process. Unsuscribe from all topics"""
        self.mqttc.unsubscribe('#')

    def onMessage(self, mqttc, obj, msg):
        """handles data storing upon MQTT """
        # tracking MQTT topics
        # scanning 
        if not msg.topic in self.topics:
            self.topics.append(msg.topic)

        if msg.topic in self.subscribedTopics:
            if not(msg.topic in self.data):
                # initalizing an empty list to store the topic's data
                self.data[msg.topic] = []
            self.data[msg.topic].append(msg.payload)

    def onScan(self, mqttc, obj, msg):
        """handles message reception in scanning mode. Adds the detected topics to the internal list of topics"""
        if not msg.topic in self.topics:
            self.topics.append(msg.topic)

