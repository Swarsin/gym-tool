import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import BiomechanicsLog

async def main():
    db = AsyncSessionLocal()
    res = await db.execute(select(BiomechanicsLog).order_by(BiomechanicsLog.id.desc()).limit(5))
    logs = res.scalars().all()
    for l in logs:
        print(f"Log ID: {l.id} | Status: {l.status} | Reps: {l.total_reps} | Overlay: {l.overlay_video_url}")
    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
