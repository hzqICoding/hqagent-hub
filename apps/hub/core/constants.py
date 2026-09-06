# 协议版本只有一个事实源：packages/protocol/VERSION，由生成器写进生成物（裁决 D24）。
# 不要在这里硬编码——协议升版时会静默失配，而两边都自认为是对的。
from protocol.generated.python import PROTOCOL_VERSION as PROTOCOL_VERSION

APP_VERSION = "0.1.0"
DEFAULT_EVENT_PAGE_SIZE = 200
MAX_EVENT_PAGE_SIZE = 1000
WS_TICKET_TTL_SECONDS = 30

