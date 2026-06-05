from fastapi import APIRouter


router = APIRouter(tags=["agents"])


@router.get("/agents")
def list_agents() -> dict[str, list[dict[str, str]]]:
    return {
        "agents": [
            {
                "id": "orchestrator",
                "name": "Orchestrator",
                "description": "Coordinates the multi-agent workflow.",
            },
            {
                "id": "ui_builder",
                "name": "UI Builder",
                "description": "Drafts React UI artifacts.",
            },
            {
                "id": "code_reviewer",
                "name": "Code Reviewer",
                "description": "Reviews generated code and suggests improvements.",
            },
        ]
    }

