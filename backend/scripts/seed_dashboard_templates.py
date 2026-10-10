"""Seed 3 system dashboard templates."""

import asyncio
import uuid
from sqlalchemy import select
from app.core.db import session_factory
from app.models.dashboard_template import DashboardTemplate

TEMPLATES = [
    {
        "name": "iPad Landscape",
        "description": "Landscape tablet dashboard for family overview",
        "layout_type": "ipad_landscape",
        "is_system": True,
        "created_by": "r2-d2",
        "widgets": [
            {
                "type": "calendar",
                "position": {"x": 0, "y": 0, "w": 40, "h": 100},
                "config": {"view": "agenda", "days": 7}
            },
            {
                "type": "note",
                "position": {"x": 40, "y": 0, "w": 60, "h": 70},
                "config": {"title": "Today's Summary", "note_id": None}
            },
            {
                "type": "weather",
                "position": {"x": 40, "y": 70, "w": 60, "h": 30},
                "config": {"location": "Hong Kong"}
            }
        ]
    },
    {
        "name": "Mobile",
        "description": "Compact mobile dashboard for on-the-go",
        "layout_type": "mobile",
        "is_system": True,
        "created_by": "r2-d2",
        "widgets": [
            {
                "type": "calendar",
                "position": {"x": 0, "y": 0, "w": 100, "h": 40},
                "config": {"view": "agenda", "days": 3}
            },
            {
                "type": "note",
                "position": {"x": 0, "y": 40, "w": 100, "h": 40},
                "config": {"title": "Today's Summary", "note_id": None}
            },
            {
                "type": "weather",
                "position": {"x": 0, "y": 80, "w": 100, "h": 20},
                "config": {"location": "Hong Kong"}
            }
        ]
    },
    {
        "name": "E-Ink Display",
        "description": "Low-power e-ink display dashboard",
        "layout_type": "e_ink",
        "is_system": True,
        "created_by": "r2-d2",
        "widgets": [
            {
                "type": "calendar",
                "position": {"x": 0, "y": 0, "w": 100, "h": 50},
                "config": {"view": "agenda", "days": 1}
            },
            {
                "type": "weather",
                "position": {"x": 0, "y": 50, "w": 100, "h": 50},
                "config": {"location": "Hong Kong"}
            }
        ]
    }
]

async def main():
    async with session_factory() as s:
        # Check if templates already exist
        existing = (await s.execute(select(DashboardTemplate))).scalars().all()
        if existing:
            print(f"Skipping: {len(existing)} templates already exist")
            return
        
        for template in TEMPLATES:
            s.add(DashboardTemplate(
                name=template["name"],
                description=template["description"],
                layout_type=template["layout_type"],
                widgets=template["widgets"],
                is_system=template["is_system"],
                created_by=template["created_by"]
            ))
        
        await s.commit()
        print(f"Seeded {len(TEMPLATES)} system templates")

if __name__ == "__main__":
    asyncio.run(main())

