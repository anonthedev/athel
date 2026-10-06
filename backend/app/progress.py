from langgraph.config import get_stream_writer


def announce(message: str) -> None:
    try:
        get_stream_writer()({"type": "activity", "message": message})
    except RuntimeError:
        return
