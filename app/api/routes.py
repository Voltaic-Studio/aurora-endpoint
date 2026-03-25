from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.schemas import AskRequest, AskResponse

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    cache_service = request.app.state.cache_service
    return {
        "status": "ok",
        "cache": cache_service.get_status(),
    }


@router.post("/ask", response_model=AskResponse)
async def ask(request: Request, payload: AskRequest) -> AskResponse:
    qa_service = request.app.state.qa_service
    try:
        return await qa_service.answer_question(payload.question)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Service is temporarily unavailable") from exc
