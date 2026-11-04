import asyncio, asyncpg
from app.config import settings
from app.auth.jwt_handler import JWTHandler


async def main():
    dsn = settings.DATABASE_URL.replace('postgresql+asyncpg', 'postgresql')
    conn = await asyncpg.connect(dsn)
    rows = await conn.fetch('select id, username, email, role from users order by created_at nulls last limit 10')
    for r in rows:
        print(r['id'], r['username'], r['email'], r['role'])
    admin = next((r for r in rows if r['role'] == 'admin'), rows[0])
    token = JWTHandler().create_access_token(
        user_id=str(admin['id']),
        email=admin['email'],
        role=admin['role'],
        username=admin['username'],
    )
    open('/tmp/token_new.txt', 'w').write(token)
    print('TOKEN_WRITTEN', len(token))
    await conn.close()


asyncio.run(main())
