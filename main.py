import os

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="PhishGuard API")


class PredictRequest(BaseModel):
    url: str = Field(..., min_length=1)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "PhishGuard API is running"}


@app.post("/predict")
def predict(payload: PredictRequest) -> dict[str, str]:
    _ = payload.url
    return {"prediction": "safe"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
