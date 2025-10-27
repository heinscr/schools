from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from models import District, DistrictTown
from schemas import DistrictCreate, DistrictUpdate


class DistrictService:
    """Service layer for district operations"""

    @staticmethod
    def create_district(db: Session, district_data: DistrictCreate) -> District:
        """Create a new district with associated towns"""
        # Create district
        db_district = District(
            name=district_data.name,
            main_address=district_data.main_address
        )
        db.add(db_district)
        db.flush()  # Flush to get the district ID

        # Add towns
        for town_name in district_data.towns:
            db_town = DistrictTown(
                district_id=db_district.id,
                town_name=town_name.strip()
            )
            db.add(db_town)

        db.commit()
        db.refresh(db_district)
        return db_district

    @staticmethod
    def get_district(db: Session, district_id: int) -> Optional[District]:
        """Get a district by ID"""
        return db.query(District).filter(District.id == district_id).first()

    @staticmethod
    def get_districts(
        db: Session,
        name: Optional[str] = None,
        town: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[District], int]:
        """
        Get districts with optional filtering
        Returns tuple of (districts, total_count)
        """
        query = db.query(District)

        # Apply filters
        if name:
            query = query.filter(District.name.ilike(f"%{name}%"))

        if town:
            # Join with district_towns to filter by town
            query = query.join(DistrictTown).filter(
                DistrictTown.town_name.ilike(f"%{town}%")
            ).distinct()

        # Get total count before pagination
        total = query.count()

        # Apply pagination
        districts = query.offset(offset).limit(limit).all()

        return districts, total

    @staticmethod
    def update_district(
        db: Session,
        district_id: int,
        district_data: DistrictUpdate
    ) -> Optional[District]:
        """Update a district"""
        db_district = db.query(District).filter(District.id == district_id).first()
        if not db_district:
            return None

        # Update district fields
        if district_data.name is not None:
            db_district.name = district_data.name
        if district_data.main_address is not None:
            db_district.main_address = district_data.main_address

        # Update towns if provided
        if district_data.towns is not None:
            # Delete existing towns
            db.query(DistrictTown).filter(DistrictTown.district_id == district_id).delete()

            # Add new towns
            for town_name in district_data.towns:
                db_town = DistrictTown(
                    district_id=district_id,
                    town_name=town_name.strip()
                )
                db.add(db_town)

        db.commit()
        db.refresh(db_district)
        return db_district

    @staticmethod
    def delete_district(db: Session, district_id: int) -> bool:
        """Delete a district (cascade deletes towns)"""
        db_district = db.query(District).filter(District.id == district_id).first()
        if not db_district:
            return False

        db.delete(db_district)
        db.commit()
        return True

    @staticmethod
    def search_districts(
        db: Session,
        query_text: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[District], int]:
        """
        Search districts by name or town
        Returns tuple of (districts, total_count)
        """
        query = db.query(District)

        if query_text:
            # Search in both district name and town names
            query = query.outerjoin(DistrictTown).filter(
                or_(
                    District.name.ilike(f"%{query_text}%"),
                    DistrictTown.town_name.ilike(f"%{query_text}%")
                )
            ).distinct()

        # Get total count
        total = query.count()

        # Apply pagination
        districts = query.offset(offset).limit(limit).all()

        return districts, total
