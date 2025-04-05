import uvicorn


def server():
    uvicorn.run("apps.server:app", port=8084, reload=True)
