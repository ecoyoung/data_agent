from fastapi import FastAPI

from data_agent.config import get_settings
from data_agent.feishu.webhook import router as feishu_router


settings = get_settings()

app = FastAPI(title="数探 - 亚马逊数据查询机器人", debug=settings.debug)
app.include_router(feishu_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "shu-tan"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "data_agent.main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=settings.debug,
    )
