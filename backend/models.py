from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class District(Base):
    """School district model"""
    __tablename__ = "districts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False, index=True)
    main_address = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationship to towns
    towns = relationship("DistrictTown", back_populates="district", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<District(id={self.id}, name='{self.name}')>"


class DistrictTown(Base):
    """District towns - allows many-to-many relationship between districts and towns"""
    __tablename__ = "district_towns"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    district_id = Column(Integer, ForeignKey("districts.id", ondelete="CASCADE"), nullable=False)
    town_name = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship to district
    district = relationship("District", back_populates="towns")

    # Create composite index for efficient queries
    __table_args__ = (
        Index('ix_district_towns_town_district', 'town_name', 'district_id'),
    )

    def __repr__(self):
        return f"<DistrictTown(id={self.id}, district_id={self.district_id}, town='{self.town_name}')>"
