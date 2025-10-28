from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class DistrictTownBase(BaseModel):
    """Base schema for district town"""
    town_name: str = Field(..., min_length=1, max_length=100)


class DistrictTownCreate(DistrictTownBase):
    """Schema for creating a district town"""
    pass


class DistrictTownResponse(DistrictTownBase):
    """Schema for district town response"""
    id: int
    district_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class DistrictBase(BaseModel):
    """Base schema for district"""
    name: str = Field(..., min_length=1, max_length=255)
    main_address: Optional[str] = Field(None, max_length=500)


class DistrictCreate(DistrictBase):
    """Schema for creating a district"""
    towns: List[str] = Field(default_factory=list, description="List of town names")


class DistrictUpdate(BaseModel):
    """Schema for updating a district"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    main_address: Optional[str] = Field(None, max_length=500)
    towns: Optional[List[str]] = Field(None, description="List of town names")


class DistrictResponse(DistrictBase):
    """Schema for district response"""
    id: str  # Changed from int to str for DynamoDB UUIDs
    towns: List[str] = Field(default_factory=list, description="List of town names")
    created_at: str  # Changed from datetime to str for ISO format strings
    updated_at: str  # Changed from datetime to str for ISO format strings

    class Config:
        from_attributes = True


class DistrictListResponse(BaseModel):
    """Schema for paginated district list response"""
    data: List[DistrictResponse]
    total: int
    limit: int
    offset: int
