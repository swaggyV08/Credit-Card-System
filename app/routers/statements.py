import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.rbac import require, AuthenticatedPrincipal
from app.schemas.base import envelope_success

from app.schemas.transactions.operations import StatementSummarySchema, CreateExportRequest
from app.services.transactions.operations_service import StatementService

router = APIRouter(tags=["Statements"])

@router.get("/cards/{card_id}/statements")
def list_statements(
    card_id: uuid.UUID,
    year: int | None = None,
    month: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    detail: bool = Query(False, description="Include full line-item details"),
    db: Session = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require("statement:read"))
):
    """Lists billing cycle statements. Use ?detail=true to get full details instead of using a separate endpoint."""
    if month is not None and (month < 1 or month > 12):
        from app.core.exceptions import AppError
        raise AppError(code="INVALID_MONTH", message="Month must be between 1 and 12", http_status=422)
    stmts = StatementService.list_statements(db, card_id, year, month)
    total = len(stmts)
    paginated = stmts[(page - 1) * page_size : page * page_size]
    
    if detail:
        # Get full details for the paginated slice
        from app.schemas.transactions.operations import StatementDetailSchema
        data = []
        for s in paginated:
            full_stmt = StatementService.get_statement_detail(db, s.id)
            data.append(StatementDetailSchema.model_validate(full_stmt).model_dump(mode='json'))
    else:
        # Just summaries
        data = [StatementSummarySchema.model_validate(s).model_dump(mode='json') for s in paginated]
        
    return envelope_success({
        "data": data,
        "meta": {"total": total, "page": page, "page_size": page_size}
    })

# DELETE: POST /cards/{card_id}/statements/{statement_id}/exports removed as per directive.
