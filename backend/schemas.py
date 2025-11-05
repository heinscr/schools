from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, ValidationError
import re

# Validation constants
# Allow alphanumeric, spaces, hyphens (including em dash), apostrophes, periods, ampersands, commas, parentheses, colons, and hash
SAFE_TEXT_PATTERN = re.compile(r'^[a-zA-Z0-9\s\-\'.&,():#—/]+$')
DISTRICT_TYPE_PATTERN = re.compile(r'^[a-z_]+$')
VALID_DISTRICT_TYPES = {
    'municipal',
    'regional_academic',
    'regional_vocational',
    'county_agricultural',
    'charter',
    'other'
}
MAX_TOWNS_PER_DISTRICT = 50


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
    district_url: Optional[str] = Field(None, max_length=500)
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate district name contains only safe characters"""
        if not v or not v.strip():
            raise ValueError('District name cannot be empty')

        v = v.strip()

        if not SAFE_TEXT_PATTERN.match(v):
            raise ValueError(
                'District name contains invalid characters. '
                'Only alphanumeric, spaces, hyphens, apostrophes, periods, colons, '
                'ampersands, commas, parentheses, forward slashes, and hash symbols are allowed.'
            )

        return v

    @field_validator('main_address')
    @classmethod
    def validate_main_address(cls, v: Optional[str]) -> Optional[str]:
        """Validate main address contains only safe characters"""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        if not SAFE_TEXT_PATTERN.match(v):
            raise ValueError(
                'Main address contains invalid characters. '
                'Only alphanumeric, spaces, hyphens, apostrophes, periods, colons, '
                'ampersands, commas, parentheses, forward slashes, and hash symbols are allowed.'
            )

        return v

    @field_validator('district_url')
    @classmethod
    def validate_district_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate district URL is a valid URL format"""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        # Basic URL validation - must start with http:// or https://
        if not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError('District URL must start with http:// or https://')

        return v

class DistrictCreate(DistrictBase):
    """Schema for creating a district"""
    towns: List[str] = Field(default_factory=list, description="List of town names")
    district_type: str = Field(..., description="Type of district (e.g. municipal, regional_academic, etc.)")

    @field_validator('towns')
    @classmethod
    def validate_towns(cls, v: List[str]) -> List[str]:
        """Validate towns list"""
        if not v:
            return []

        if len(v) > MAX_TOWNS_PER_DISTRICT:
            raise ValueError(f'Too many towns (max {MAX_TOWNS_PER_DISTRICT})')

        validated_towns = []
        for town in v:
            if not town or not town.strip():
                continue  # Skip empty entries

            town = town.strip()

            if len(town) > 100:
                raise ValueError(f'Town name too long (max 100 characters): {town[:50]}...')

            if not SAFE_TEXT_PATTERN.match(town):
                raise ValueError(
                    f'Town name contains invalid characters: {town[:50]}... '
                    'Only alphanumeric, spaces, hyphens, apostrophes, periods, colons, '
                    'ampersands, commas, parentheses, and hash symbols are allowed.'
                )

            validated_towns.append(town)

        return validated_towns

    @field_validator('district_type')
    @classmethod
    def validate_district_type(cls, v: str) -> str:
        """Validate district type is from allowed list"""
        if not v or not v.strip():
            raise ValueError('District type cannot be empty')

        v = v.strip().lower()

        if v not in VALID_DISTRICT_TYPES:
            raise ValueError(
                f'Invalid district type: {v}. '
                f'Allowed types: {", ".join(sorted(VALID_DISTRICT_TYPES))}'
            )

        return v


class DistrictUpdate(BaseModel):
    """Schema for updating a district"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    main_address: Optional[str] = Field(None, max_length=500)
    district_url: Optional[str] = Field(None, max_length=500)
    towns: Optional[List[str]] = Field(None, description="List of town names")
    district_type: Optional[str] = Field(None, description="Type of district (e.g. municipal, regional_academic, etc.)")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate district name contains only safe characters"""
        if v is None:
            return v

        if not v.strip():
            raise ValueError('District name cannot be empty')

        v = v.strip()

        if not SAFE_TEXT_PATTERN.match(v):
            raise ValueError(
                'District name contains invalid characters. '
                'Only alphanumeric, spaces, hyphens, apostrophes, periods, colons, '
                'ampersands, commas, parentheses, forward slashes, and hash symbols are allowed.'
            )

        return v

    @field_validator('main_address')
    @classmethod
    def validate_main_address(cls, v: Optional[str]) -> Optional[str]:
        """Validate main address contains only safe characters"""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        if not SAFE_TEXT_PATTERN.match(v):
            raise ValueError(
                'Main address contains invalid characters. '
                'Only alphanumeric, spaces, hyphens, apostrophes, periods, colons, '
                'ampersands, commas, parentheses, forward slashes, and hash symbols are allowed.'
            )

        return v

    @field_validator('district_url')
    @classmethod
    def validate_district_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate district URL is a valid URL format"""
        if v is None:
            return v

        v = v.strip()
        if not v:
            return None

        # Basic URL validation - must start with http:// or https://
        if not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError('District URL must start with http:// or https://')

        return v

    @field_validator('towns')
    @classmethod
    def validate_towns(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate towns list"""
        if v is None:
            return v

        if len(v) > MAX_TOWNS_PER_DISTRICT:
            raise ValueError(f'Too many towns (max {MAX_TOWNS_PER_DISTRICT})')

        validated_towns = []
        for town in v:
            if not town or not town.strip():
                continue  # Skip empty entries

            town = town.strip()

            if len(town) > 100:
                raise ValueError(f'Town name too long (max 100 characters): {town[:50]}...')

            if not SAFE_TEXT_PATTERN.match(town):
                raise ValueError(
                    f'Town name contains invalid characters: {town[:50]}... '
                    'Only alphanumeric, spaces, hyphens, apostrophes, periods, colons, '
                    'ampersands, commas, parentheses, and hash symbols are allowed.'
                )

            validated_towns.append(town)

        return validated_towns

    @field_validator('district_type')
    @classmethod
    def validate_district_type(cls, v: Optional[str]) -> Optional[str]:
        """Validate district type is from allowed list"""
        if v is None:
            return v

        if not v.strip():
            raise ValueError('District type cannot be empty')

        v = v.strip().lower()

        if v not in VALID_DISTRICT_TYPES:
            raise ValueError(
                f'Invalid district type: {v}. '
                f'Allowed types: {", ".join(sorted(VALID_DISTRICT_TYPES))}'
            )

        return v


class DistrictResponse(DistrictBase):
    """Schema for district response"""
    id: str  # Changed from int to str for DynamoDB UUIDs
    towns: List[str] = Field(default_factory=list, description="List of town names")
    district_type: str = Field(..., description="Type of district (e.g. municipal, regional_academic, etc.)")
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
