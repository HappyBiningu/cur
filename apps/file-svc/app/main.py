from fastapi import FastAPI

app = FastAPI(title="file-svc")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/readyz")
def readyz():
    return {"status": "ready"}

@app.get("/")
def root():
    return {"service": "file-svc"}