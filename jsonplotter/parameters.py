
## Plot parameters
DEFAULT_PLOT_COLOR = '#56dbd8'
DEFAULT_CMAP = 'Blues'
# DEFAULT_MPL_TEMPLATE = "dark_background"
DEFAULT_MPL_TEMPLATE = "seaborn-white"

PLOT_REFRESH_TIME = 1000 # ms
MINIMUM_REFRESH_TIME = 100 # ms
MAXIMUM_REFRESH_TIME = 2000 # ms
SPEED_DIAL_STEP_SIZE = 100 # ms
DEFAULT_TICK_TIME = 1
PLOT_DATA_MAX_DIGITS = 6
LOG_DIR = "SerialLogs"
DEFAULT_LABEL_FONT_SIZE = 18


## Serial parameters
DEFAULT_BAUDRATE = 115200

## MQTT parameters
AUTHORIZED_MQTT_PORTS = [
    1883, # standard
    8883, # secure MQTT
    9001 # web sockets
    ]
DEFAULT_PORT = 1883
DEFAULT_HOST = '127.0.0.1'

TOPIC_REFRESH_TIME = 500 # ms

## UI paraemeters

## icons
PARAM_DEFAULT_ICON = 'piano.svg'