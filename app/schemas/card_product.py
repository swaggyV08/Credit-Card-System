from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from app.models.enums import CardNetwork, CardVariant, ProductStatus
from app.schemas.base import PaginationSchema

class CardProductSummaryResponse(BaseModel):
    card_product_id: UUID = Field(alias="id")
    credit_product_id: UUID
    card_network: CardNetwork
    card_variant: CardVariant
    status: ProductStatus

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class CardProductPaginationResponse(BaseModel):
    items: List[CardProductSummaryResponse]
    pagination: PaginationSchema
