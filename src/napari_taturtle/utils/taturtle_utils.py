from enum import Enum

class State(Enum):
    IDLE = 0
    RUNNING = 1

class UpdateType(Enum):
    BATCH = 'batch'
    N_IMAGES = 'number of images'
    IMAGE = 'image'
    AUTOCROP = 'autocrop'
    THICKNESS = 'thickness'
    DONE = 'done'
    CRASHED = 'crashed'
    FAILED = 'failed'