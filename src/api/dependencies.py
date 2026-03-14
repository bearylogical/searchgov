from fastapi import HTTPException, Request


def get_facade(request: Request):
    """Return the TemporalGraph facade stored on app.state.

    Raises HTTP 503 if the facade has not been initialised yet.
    """
    facade = getattr(request.app.state, "facade", None)
    if facade is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    return facade
