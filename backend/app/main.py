
from fastapi import FastAPI

# Initialize FastAPI application
app = FastAPI(
    title="C3 ZKP Supply Chain Verification System",
    description="Zero-Knowledge Proof Based Supply Chain Verification",
    version="1.0.0"
)

# Root endpoint
@app.get("/")
def root():
    return {
        "message": "C3 ZKP Backend is running successfully",
        "system": "System 1 - ZKP",
        "status": "Active"
    }

# Health check endpoint
@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }
